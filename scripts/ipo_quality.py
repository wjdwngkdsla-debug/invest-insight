"""Shared, stage-aware IPO quality checks. Missing is never a confirmed zero."""
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo
from scripts.ipo_evidence import demand_waiting

PERIODS = ("미확약", "15일", "1개월", "3개월", "6개월")


def quantity(value):
    if isinstance(value, bool) or value is None:
        return None
    text = str(value).replace(",", "").strip()
    return int(text) if re.fullmatch(r"\d+", text) else None


def tier_quantity(tier):
    if not isinstance(tier, dict) or tier.get("source") == "zero_missing":
        return None
    return quantity(tier.get("qty"))


def holder_review_note(item):
    snapshot = item.get("holder_lockup") or {}
    if snapshot.get("status") not in {"review", "error"}:
        return ""
    parts = [f"DART {snapshot.get('rcept_no', '')}"]
    if snapshot.get("basis") == "float_summary":
        cumulative = snapshot.get("cumulative_rows") or []
        if cumulative:
            last = cumulative[-1]
            parts.append(f"요약표 마지막 {last['period']}: {last['cumulative_float']:,}주 / {last.get('float_pct')}%")
    if snapshot.get("referenced_filing_date"):
        parts.append(f"참조 본문 {snapshot['referenced_filing_date']}")
    unresolved = snapshot.get("unresolved") or []
    unit = snapshot.get("quantity_unit", "주")
    if unresolved:
        parts.extend(f"{r['qty']:,}{unit}: {r.get('period_text') or '기간 미기재'}" for r in unresolved)
    elif snapshot.get("reported_totals") and quantity(snapshot.get("parsed_total")) is not None:
        expected = snapshot["reported_totals"][-1]
        actual = snapshot["parsed_total"]
        parts.append(f"원문 합계 {expected:,}{unit} / 행 합계 {actual:,}{unit} / 차이 {expected - actual:+,}{unit}")
    if snapshot.get("last_verified"):
        parts.append(f"이전 검산값 보존: {snapshot['last_verified'].get('rcept_no', '')}")
    for row in snapshot.get('ratio_mismatches') or []:
        parts.append(f"{row['period']} {row['qty']:,}주: 원문 {row['reported_pct']}% / 계산 {row['calculated_pct']}%")
    return "; ".join(parts)


def security_type(title="", text=""):
    # Issuance title/identity only: risk-factor references are not classification evidence.
    compact = re.sub(r"\s+", "", title)
    kind = re.search(r"(?:증권신고서|투자설명서)\(([^)]+)\)", compact)
    identity = kind.group(1) if kind else ""
    if not identity:
        body = re.sub(r"\s+", "", text)
        cover = body.split("증권신고의효력발생일", 1)[0][:700]
        if re.search(r"투자계약증권(?:제\d+호|[:：][\d,]+)", cover):
            return "non_equity"
        match = re.search(r"(?:증권의종류|모집\(매출\)하는증권의종류)[:：]?(.{0,70})", body)
        identity = match.group(1) if match else ""
    if any(k in identity for k in ("투자계약증권", "채무증권", "수익증권", "파생결합증권")):
        return "non_equity"
    if "증권예탁증권" in identity:
        return "depositary_receipt"
    if any(k in identity for k in ("지분증권", "보통주", "기명식보통")):
        return "equity"
    return ""


def result_waiting(item, today=None):
    today = today or datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    check = item.get("result_source_check") or {}
    try:
        age = (date.fromisoformat(today) - date.fromisoformat(check.get("checked_at", ""))).days
    except ValueError:
        return False
    return check.get("status") == "waiting" and not item.get("report_rcp") and 0 <= age <= 1


def quality_gaps(item, has_holders=False, float_pct_known=None, today=None):
    today = today or datetime.now(ZoneInfo("Asia/Seoul")).date().isoformat()
    gaps = []
    if item.get("quality_refresh_error"):
        gaps.append("원천 재수집 실패(기존 값 유지)")
    if (item.get("result_source_check") or {}).get("status") == "parse_incomplete" and not allocation_resolved(item):
        gaps.append("실적보고서 파싱 확인")
    def ended(field):
        value = str(item.get(field) or "")
        try:
            return date.fromisoformat(value).isoformat() < today
        except ValueError:
            return False
    forecast_done = (ended("forecast_end") or bool(item.get("demand_ratio") or item.get("report_rcp"))) and not demand_waiting(item, today)
    subscription_done = ended("sub_end") or bool(item.get("report_rcp"))
    for field, label in (("market", "시장"), ("band_low", "희망가하단"), ("band_high", "희망가상단"), ("offer_shares", "공모주식수"), ("underwriter", "주관사")):
        if not item.get(field):
            gaps.append(label)
    if forecast_done:
        if not quantity(item.get("final_price")):
            gaps.append("확정공모가")
        if not item.get("demand_ratio"):
            gaps.append("수요예측경쟁률")
    for field, label, due in (("commit_apply", "확약신청", forecast_done), ("commit_alloc", "확약배정", subscription_done)):
        if not due:
            continue
        tiers = {r.get("period"): r for r in item.get(field) or [] if isinstance(r, dict)}
        missing = [p for p in PERIODS if tier_quantity(tiers.get(p)) is None]
        if missing:
            state = "공시 대기: " if field == "commit_alloc" and result_waiting(item, today) else ""
            gaps.append(f"{state}{label}({', '.join(missing)})")
    if subscription_done and not item.get("listing_date"):
        gaps.append("상장일 미정")
    if subscription_done and not item.get("sub_ratio"):
        gaps.append(("공시 대기: " if result_waiting(item, today) else "") + "개인청약경쟁률")
    snapshot = item.get("holder_lockup") or {}
    if item.get("holder_source_error"):
        gaps.append("구주물량 원문 조회 실패")
    holder_rows = snapshot.get("rows") or []
    empty_summary = snapshot.get("basis") == "float_summary" and snapshot.get("total") == 0
    if snapshot.get("status") == "verified" and ((not holder_rows and not empty_summary) or any(tier_quantity(r) is None for r in holder_rows)
            or sum(tier_quantity(r) or 0 for r in holder_rows) != quantity(snapshot.get("total"))):
        gaps.append("구주물량 저장값 검산 실패")
    initial = quantity(item.get("initial_shares"))
    if initial and (quantity(snapshot.get("total")) or 0) > initial:
        gaps.append("구주물량이 최초상장주식수 초과")
    if not has_holders and snapshot.get("status") != "verified":
        gaps.append("구주물량" + (f"({snapshot['reason']})" if snapshot.get("reason") else ""))
    elif snapshot.get("status") in {"review", "error"}:
        gaps.append("구주물량 최신 공시 확인" + (f"({snapshot['reason']})" if snapshot.get("reason") else ""))
    if float_pct_known is False:
        gaps.append("상장일유통가능")
    gaps.extend(capital_gaps(item))
    return gaps


def capital_gaps(item):
    gaps = []
    snapshot = item.get('holder_lockup') or {}
    adjustment = snapshot.get('capital_adjustment') or {}
    if adjustment and (adjustment.get('result_receipt') != item.get('report_rcp')
                       or adjustment.get('summary_receipt') != snapshot.get('rcept_no')):
        gaps.append('공시 변경: 의무인수 조정 재검증 필요')
    initial = quantity(item.get('initial_shares'))
    cumulative = snapshot.get('cumulative_rows') or []
    if initial and snapshot.get('status') == 'verified' and cumulative:
        last = cumulative[-1]['cumulative_float']
        if last > initial or (snapshot.get('coverage') == 'full' and last != initial):
            gaps.append(f'요약표·최초상장주식수 불일치({last:,}/{initial:,})')
    tiers = {r.get('period'): r for r in item.get('commit_alloc') or []}
    if all(tier_quantity(tiers.get(p)) is not None for p in PERIODS):
        allocated = sum(tier_quantity(tiers[p]) for p in PERIODS)
        locked = allocated - tier_quantity(tiers['미확약'])
        offer = quantity(item.get('offer_shares'))
        if offer and allocated > offer:
            gaps.append('기관 총배정이 공모주식수 초과')
        # The summary baseline already includes offered shares: subtract institution
        # locks from baseline, never add total allocation to total listed shares.
        if cumulative and locked > cumulative[0]['cumulative_float']:
            gaps.append('기관 확약배정이 상장일 유통가능물량 초과')
        if initial and snapshot.get('status') == 'verified' and (quantity(snapshot.get('total')) or 0) + locked > initial:
            gaps.append('기존주주·기관 확약물량이 최초상장주식수 초과')
    return gaps


def allocation_resolved(item):
    tiers = {r.get("period"): r for r in item.get("commit_alloc") or []}
    return bool(item.get("sub_ratio")) and all(tier_quantity(tiers.get(p)) is not None for p in PERIODS)


def quality_advisories(item):
    notes = []
    if demand_waiting(item, datetime.now(ZoneInfo('Asia/Seoul')).date().isoformat()):
        notes.append('수요예측 결과 공시 대기: 운영자 확인, 다음 공시 또는 청약 시작일에 재검증')
    snapshot = item.get("holder_lockup") or {}
    if snapshot.get("status") == "verified" and snapshot.get("detail_advisory"):
        notes.append("요약표 예정 일정 정상; 상세표 참고: " + snapshot["detail_advisory"].get("reason", ""))
    if snapshot.get('coverage') == 'disclosed_periods_only':
        notes.append('공시된 기간까지 집계: 잔여 물량·해제일은 미추정')
    if snapshot.get('capital_adjustment'):
        notes.append(snapshot['capital_adjustment']['reason'])
    if snapshot.get('summary_reconciliation'):
        notes.append(snapshot['summary_reconciliation']['reason'])
    if (item.get("result_source_check") or {}).get("status") == "parse_incomplete" and allocation_resolved(item):
        notes.append("배정 저장값 보완 완료; 자동 파서 재검증 미완료")
    return notes
