"""Shared, stage-aware IPO quality checks. Missing is never a confirmed zero."""
import re
from datetime import date, datetime
from zoneinfo import ZoneInfo

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
    if (item.get("result_source_check") or {}).get("status") == "parse_incomplete":
        gaps.append("실적보고서 파싱 확인")
    def ended(field):
        value = str(item.get(field) or "")
        try:
            return date.fromisoformat(value).isoformat() < today
        except ValueError:
            return False
    forecast_done = ended("forecast_end") or bool(item.get("demand_ratio") or item.get("report_rcp"))
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
    holder_rows = snapshot.get("rows") or []
    if snapshot.get("status") == "verified" and (not holder_rows or any(tier_quantity(r) is None for r in holder_rows)
            or sum(tier_quantity(r) or 0 for r in holder_rows) != quantity(snapshot.get("total"))):
        gaps.append("구주물량 저장값 검산 실패")
    initial = quantity(item.get("initial_shares"))
    if initial and (quantity(snapshot.get("total")) or 0) > initial:
        gaps.append("구주물량이 최초상장주식수 초과")
    if not has_holders and snapshot.get("status") != "verified":
        gaps.append("구주물량" + (f"({snapshot['reason']})" if snapshot.get("reason") else ""))
    elif snapshot.get("status") in {"review", "error"}:
        gaps.append("구주물량 최신 공시 확인")
    if float_pct_known is False:
        gaps.append("상장일유통가능")
    return gaps
