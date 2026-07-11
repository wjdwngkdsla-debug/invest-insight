from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import requests

from scripts.config import DART_API_KEY, ROOT_DIR
from scripts.sources.dart_api import download_document_text, _clean_text, get_corp_code, get_reports

DART_BASE = "https://opendart.fss.or.kr/api"
SCHEDULE_PATH = ROOT_DIR / "data" / "ipo_schedule.json"
TARGETS_PATH = ROOT_DIR / "data" / "ipo_targets.json"
# 시트에 이름만 적어 넣은 "아직 DART가 못 찾은 회사" 요청 목록 (sheets_sync.py가 씀 → 다음 배치가 읽음)
SEED_PATH = ROOT_DIR / "data" / "ipo_seed_names.json"

# 발굴 창 — 수요예측→청약→상장까지 수개월 걸릴 수 있어 넉넉히 둔다.
LOOKBACK_DAYS = 210
# 종목당 신고서 다운로드 상한 — 정정이 많아도 최신 몇 건이면 전 필드가 채워진다.
MAX_DOCS_PER_CORP = 4

TIER_LABELS = ["6개월", "3개월", "1개월", "15일"]

# 정정이력 추적 대상 필드 (시트 정정이력 탭에 적재)
TRACKED_FIELDS = {
    "band_low": "희망가액(하단)",
    "band_high": "희망가액(상단)",
    "final_price": "확정공모가",
    "forecast_start": "수요예측 시작",
    "forecast_end": "수요예측 종료",
    "sub_start": "청약 시작",
    "sub_end": "청약 종료",
    "listing_date": "상장일",
}


# ── 공용 헬퍼 ──────────────────────────────────────────────


def _fmt_date(y: str, m: str, d: str) -> str:
    return f"{int(y):04d}-{int(m):02d}-{int(d):02d}"


def _to_int(s: str) -> int:
    return int(s.replace(",", ""))


def _rows(table_xml: str) -> list[list[str]]:
    """DART XML 표 파싱 — 실적보고서 일부 표는 TD 대신 TE 태그를 써서 dart_api의 파서가 놓친다."""
    out: list[list[str]] = []
    for tr in re.findall(r"<TR[\s\S]*?</TR>", table_xml, flags=re.I):
        cells = [_clean_text(c) for c in re.findall(r"<T[DHE][^>]*>([\s\S]*?)</T[DHE]>", tr, flags=re.I)]
        cells = [c for c in cells if c]
        if cells:
            out.append(cells)
    return out


def _tables(doc: str) -> list[str]:
    return re.findall(r"<TABLE[\s\S]*?</TABLE>", doc, flags=re.I)


# ── 1) 시장 전체 지분증권 신고서 스트림 (예정 IPO 자동 발굴) ──


def fetch_equity_filings(days_back: int = LOOKBACK_DAYS) -> list[dict[str, Any]]:
    """list.json C001(지분증권 증권신고서) 시장 전체 조회.

    corp_code 없는 조회는 DART가 검색기간을 3개월로 제한하므로 90일 조각으로 나눠 훑는다.
    """
    if not DART_API_KEY:
        return []
    filings: list[dict[str, Any]] = []
    seen: set[str] = set()
    chunk_end = datetime.today()
    remaining = days_back
    while remaining > 0:
        span = min(remaining, 90)
        chunk_begin = chunk_end - timedelta(days=span)
        page = 1
        while True:
            res = requests.get(
                f"{DART_BASE}/list.json",
                params={
                    "crtfc_key": DART_API_KEY,
                    "bgn_de": chunk_begin.strftime("%Y%m%d"),
                    "end_de": chunk_end.strftime("%Y%m%d"),
                    "pblntf_detail_ty": "C001",
                    "page_no": page,
                    "page_count": 100,
                },
                timeout=30,
            )
            res.raise_for_status()
            data = res.json()
            if data.get("status") != "000":
                break
            for f in data.get("list", []) or []:
                rcp = f.get("rcept_no") or ""
                if rcp and rcp not in seen:
                    seen.add(rcp)
                    filings.append(f)
            if page >= int(data.get("total_page") or 1):
                break
            page += 1
        chunk_end = chunk_begin - timedelta(days=1)
        remaining -= span + 1
    return filings


def group_upcoming_ipos(filings: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """미상장 법인(corp_cls=E)만 남긴다 — 상장사의 유상증자 신고서(Y/K)를 걸러내면 곧 예정 IPO 목록."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for f in filings:
        if (f.get("corp_cls") or "") != "E":
            continue
        grouped.setdefault(f["corp_code"], []).append(f)
    for corp_filings in grouped.values():
        corp_filings.sort(key=lambda f: (f.get("rcept_dt") or "", f.get("rcept_no") or ""), reverse=True)
    return grouped


# ── 2) 신고서 본문 파싱 ──────────────────────────────────


def _parse_band(plain: str) -> tuple[int, int] | None:
    """희망밴드 — 기재정정 문서는 '정정 전' 본문이 앞, '정정 후' 본문이 뒤에 오므로 마지막 매치가 최신값."""
    patterns = [
        r"희망공모가액(?:인|은|을)?[^\d]{0,20}([\d,]{4,12})\s*원\s*~\s*([\d,]{4,12})\s*원",
        r"공모희망가(?:액)?(?:을|은|는)?[^\d]{0,20}([\d,]{4,12})\s*원\s*~\s*([\d,]{4,12})\s*원",
        r"모집\(매출\)가액\(예정\)\s*[:：]\s*([\d,]{4,12})\s*원\s*~\s*([\d,]{4,12})\s*원",
    ]
    best: tuple[int, int, int] | None = None  # (pos, low, high)
    for pat in patterns:
        for m in re.finditer(pat, plain):
            low, high = _to_int(m.group(1)), _to_int(m.group(2))
            if 100 <= low <= high <= 10_000_000 and (best is None or m.start() > best[0]):
                best = (m.start(), low, high)
    return (best[1], best[2]) if best else None


def _parse_final_price(plain: str) -> int:
    prices: Counter[int] = Counter()
    for m in re.finditer(r"확정공모가액(?:은|을|인)?\s*[^\d]{0,10}([\d,]{4,12})\s*원", plain):
        p = _to_int(m.group(1))
        if 100 <= p <= 10_000_000:
            prices[p] += 1
    return prices.most_common(1)[0][0] if prices else 0


_KDATE = r"(20\d{2})\s*년\s*(\d{1,2})\s*월\s*(\d{1,2})\s*일"


def _parse_range(plain: str, lead_patterns: list[str]) -> tuple[str, str] | None:
    """'{선행패턴} 2026년 06월 17일(수) ~ 2026년 06월 23일(화)' 형태의 날짜 구간.

    기재정정 문서는 '정정 전' 본문이 앞, '정정 후' 본문이 뒤에 반복되므로
    문서에서 가장 뒤에 나오는 매치를 최신 일정으로 본다. (빅웨이브로보틱스 연기 케이스)
    """
    best_range: tuple[int, str, str] | None = None
    best_single: tuple[int, str, str] | None = None
    for lead in lead_patterns:
        for m in re.finditer(lead + r"[^\d]{0,15}" + _KDATE + r"[^\d~]{0,8}~[^\d]{0,8}(?:(20\d{2})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일", plain):
            start = _fmt_date(m.group(1), m.group(2), m.group(3))
            end = _fmt_date(m.group(4) or m.group(1), m.group(5), m.group(6))
            if best_range is None or m.start() > best_range[0]:
                best_range = (m.start(), start, end)
        for m in re.finditer(lead + r"[^\d]{0,15}" + _KDATE, plain):
            d = _fmt_date(m.group(1), m.group(2), m.group(3))
            if best_single is None or m.start() > best_single[0]:
                best_single = (m.start(), d, d)
    chosen = best_range or best_single
    return (chosen[1], chosen[2]) if chosen else None


def _parse_forecast(plain: str) -> tuple[str, str] | None:
    return _parse_range(plain, [r"수요예측\s*일시", r"수요예측\s*(?:예정일|기간)(?:은|는)?", r"수요예측[^\n]{0,10}접수기간"])


def _parse_subscription(plain: str) -> tuple[str, str] | None:
    """청약일 — 세 가지 표기 전부에서 매치를 모아 문서상 가장 뒤의 것(정정 후)을 쓴다."""
    best: tuple[int, str, str] | None = None

    def consider(pos: int, start: str, end: str) -> None:
        nonlocal best
        if best is None or pos > best[0]:
            best = (pos, start, end)

    for lead in [r"※\s*청약일\s*[:：]", r"청약일\s*[:：]"]:
        for m in re.finditer(lead + r"[^\d]{0,15}" + _KDATE + r"[^\d~]{0,8}~[^\d]{0,8}(?:(20\d{2})\s*년\s*)?(\d{1,2})\s*월\s*(\d{1,2})\s*일", plain):
            consider(m.start(), _fmt_date(m.group(1), m.group(2), m.group(3)), _fmt_date(m.group(4) or m.group(1), m.group(5), m.group(6)))
    # 표 형태: 청약기일 ... (우리사주조합 제외) 기관/일반 개시일 ~ 종료일
    for m in re.finditer(r"청약기일[\s\S]{0,200}?기관투자자[\s\S]{0,80}?개시일\s*" + _KDATE + r"[\s\S]{0,40}?종료일\s*" + _KDATE, plain):
        consider(m.start(), _fmt_date(m.group(1), m.group(2), m.group(3)), _fmt_date(m.group(4), m.group(5), m.group(6)))
    for m in re.finditer(r"청약기일[\s\S]{0,120}?개시일\s*" + _KDATE + r"[\s\S]{0,40}?종료일\s*" + _KDATE, plain):
        consider(m.start(), _fmt_date(m.group(1), m.group(2), m.group(3)), _fmt_date(m.group(4), m.group(5), m.group(6)))
    # 공모개요 표: 청약기일 납입기일 ... 2026.07.01 ~ 2026.07.02
    for m in re.finditer(r"청약기일[\s\S]{0,80}?(20\d{2})\.(\d{1,2})\.(\d{1,2})\s*~\s*(20\d{2})\.(\d{1,2})\.(\d{1,2})", plain):
        consider(m.start(), _fmt_date(m.group(1), m.group(2), m.group(3)), _fmt_date(m.group(4), m.group(5), m.group(6)))
    return (best[1], best[2]) if best else None


def _parse_payment(plain: str) -> str:
    """납입기일 — 정정 문서에서 옛 값이 곳곳에 남으므로 청약기일 표에 붙은 납입기일의 마지막 매치를 우선한다."""
    paired = list(re.finditer(r"청약기일[\s\S]{0,400}?납입기일\s*" + _KDATE, plain))
    if paired:
        m = paired[-1]
        return _fmt_date(m.group(1), m.group(2), m.group(3))
    loose = list(re.finditer(r"납입기일\s*" + _KDATE, plain))
    if loose:
        m = loose[-1]
        return _fmt_date(m.group(1), m.group(2), m.group(3))
    m = re.search(r"납입기일[\s\S]{0,60}?(20\d{2})\.(\d{1,2})\.(\d{1,2})", plain)
    if m:
        return _fmt_date(m.group(1), m.group(2), m.group(3))
    return ""


def _parse_underwriter(plain: str) -> str:
    names: Counter[str] = Counter()
    for m in re.finditer(r"(?:대표주관회사|공동주관회사)(?:인|는|은)?\s*[:：]?\s*([가-힣A-Za-z0-9&]{2,12}증권)", plain):
        names[m.group(1)] += 1
    if not names:
        return ""
    top = [name for name, _ in names.most_common(2)]
    return top[0] if len(top) == 1 or names[top[0]] >= names[top[1]] * 3 else "·".join(top)


def _parse_market(plain: str) -> str:
    kosdaq = len(re.findall(r"코스닥\s*시장\s*상장", plain))
    kospi = len(re.findall(r"유가증권\s*시장\s*상장", plain))
    if kosdaq or kospi:
        return "코스닥" if kosdaq >= kospi else "코스피"
    return ""


def _parse_offer_shares(plain: str) -> int:
    m = re.search(r"(?:모집\s*또는\s*매출|모집\(매출\))\s*주식의?\s*수\s*(?:기명식)?\s*보통주\s*([\d,]{4,15})\s*주", plain)
    return _to_int(m.group(1)) if m else 0


def _parse_demand_tables(doc: str) -> tuple[float, list[dict[str, Any]]]:
    """수요예측 경쟁률 + 기간별 확약 '신청' 내역 — [발행조건확정] 신고서의 결과 표."""
    demand_ratio = 0.0
    commit_apply: list[dict[str, Any]] = []
    for table in _tables(doc):
        txt = _clean_text(table)
        rows = _rows(table)
        if not rows:
            continue
        header = " ".join(rows[0])
        # 단순경쟁률 표: '경쟁률' 행의 마지막(합계) 값
        if "기관투자자" in txt and "경쟁률" in txt:
            for r in rows:
                if r and r[0].replace(" ", "").startswith("경쟁률") and len(r) > 2:
                    try:
                        val = float(r[-1].replace(",", ""))
                        if val > 0:
                            demand_ratio = val
                    except ValueError:
                        pass
        # 확약 신청 표: 행 라벨 'N개월/15일 확약'+'미확약', 헤더에 합계 열이 있는 표만 (마지막 3열 = 합계 건수/수량/신청가격)
        if "미확약" in txt and "신청가격" in txt and "합계" in header:
            tiers: dict[str, int] = {}
            total = 0
            for r in rows:
                label = (r[0] if r else "").replace(" ", "")
                nums = [c for c in r if re.fullmatch(r"[\d,]{2,}", c)]
                if len(nums) < 2:
                    continue
                if label in {f"{t}확약" for t in TIER_LABELS}:
                    tiers[label.replace("확약", "")] = _to_int(nums[-2])
                elif label == "미확약":
                    tiers["미확약"] = _to_int(nums[-2])
                elif label.startswith("합계"):
                    total = _to_int(nums[-2])
            if total and len(tiers) >= 3:
                commit_apply = [
                    {"period": t, "qty": tiers[t], "pct": round(tiers[t] / total * 100, 2)}
                    for t in TIER_LABELS + ["미확약"]
                    if t in tiers
                ]
    return demand_ratio, commit_apply


def parse_offering_doc(doc: str) -> dict[str, Any]:
    plain = _clean_text(doc)
    band = _parse_band(plain)
    forecast = _parse_forecast(plain)
    sub = _parse_subscription(plain)
    demand_ratio, commit_apply = _parse_demand_tables(doc)
    return {
        "band_low": band[0] if band else 0,
        "band_high": band[1] if band else 0,
        "final_price": _parse_final_price(plain),
        "forecast_start": forecast[0] if forecast else "",
        "forecast_end": forecast[1] if forecast else "",
        "sub_start": sub[0] if sub else "",
        "sub_end": sub[1] if sub else "",
        "payment_date": _parse_payment(plain),
        "underwriter": _parse_underwriter(plain),
        "market": _parse_market(plain),
        "offer_shares": _parse_offer_shares(plain),
        "demand_ratio": demand_ratio,
        "commit_apply": commit_apply,
    }


# ── 3) 실적보고서 파싱 (청약 후: 개인청약경쟁률 + 확약 '배정') ──


def find_result_report(corp_code: str) -> dict[str, Any] | None:
    if not DART_API_KEY:
        return None
    res = requests.get(
        f"{DART_BASE}/list.json",
        params={
            "crtfc_key": DART_API_KEY,
            "corp_code": corp_code,
            "bgn_de": (datetime.today() - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d"),
            "end_de": datetime.today().strftime("%Y%m%d"),
            "page_no": 1,
            "page_count": 100,
            "pblntf_ty": "C",
        },
        timeout=30,
    )
    res.raise_for_status()
    data = res.json()
    if data.get("status") != "000":
        return None
    reports = [r for r in (data.get("list") or []) if "증권발행실적보고서" in (r.get("report_nm") or "")]
    reports.sort(key=lambda r: (r.get("rcept_dt") or "", r.get("rcept_no") or ""), reverse=True)
    return reports[0] if reports else None


_NUM_TOKEN = r"(?:\s+(?:[\d,]+(?:\.\d+)?|-)(?=\s|$))"


def parse_result_report(doc: str) -> dict[str, Any]:
    plain = _clean_text(doc)
    out: dict[str, Any] = {"sub_ratio": 0.0, "commit_alloc": []}

    # 개인청약경쟁률 = 일반투자자 청약수량 ÷ 최초 배정수량 (청약 및 배정현황 표)
    seg_at = plain.find("청약 및 배정현황")
    if seg_at >= 0:
        seg = plain[seg_at : seg_at + 800]
        m = re.search(r"일반투자자\s+([\d,]+)\s+[\d.]+\s+([\d,]+)\s+([\d,]+)", seg)
        if m:
            alloc, qty = _to_int(m.group(1)), _to_int(m.group(3))
            if alloc > 0 and qty > alloc:
                out["sub_ratio"] = round(qty / alloc, 2)

    # 기간별 확약 배정현황 — 각 행의 마지막 (수량, 비중) 쌍이 합계 열
    seg_at = plain.find("의무보유확약기간별 배정현황")
    if seg_at >= 0:
        seg = plain[seg_at : seg_at + 1600]
        alloc_rows: list[dict[str, Any]] = []
        for tier in TIER_LABELS + ["미확약"]:
            label = tier if tier == "미확약" else rf"{tier}\s*확약"
            m = re.search(label + rf"({_NUM_TOKEN}{{2,30}})", seg)
            if not m:
                continue
            nums = [t for t in m.group(1).split() if t != "-"]
            if len(nums) < 2:
                continue
            try:
                qty = _to_int(nums[-2])
                pct = float(nums[-1].replace(",", ""))
            except ValueError:
                continue
            alloc_rows.append({"period": tier, "qty": qty, "pct": pct})
        if len(alloc_rows) >= 3:
            out["commit_alloc"] = alloc_rows
    return out


# ── 4) 상장일 연결 (IPO종목 탭 → ipo_targets.json) ─────────


def _norm_name(name: str) -> str:
    return re.sub(r"[\s㈜()\[\]]|주식회사", "", name or "")


def load_listing_map() -> dict[str, dict[str, str]]:
    if not TARGETS_PATH.exists():
        return {}
    try:
        targets = json.loads(TARGETS_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, dict[str, str]] = {}
    for t in targets:
        key = _norm_name(t.get("name") or "")
        if key:
            out[key] = {"listing_date": t.get("listing_date") or "", "code": str(t.get("code") or "")}
    return out


# ── 5) 메인 갱신 루프 ─────────────────────────────────────


def load_state() -> dict[str, Any]:
    if SCHEDULE_PATH.exists():
        try:
            return json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"updated": "", "items": []}


def _core_fields_filled(item: dict[str, Any]) -> bool:
    return bool(item.get("band_low") and item.get("forecast_start") and item.get("sub_start") and item.get("underwriter"))


def _fetch_corp_filings(corp_code: str, days_back: int) -> list[dict[str, Any]]:
    """특정 회사 하나의 발행공시만 직접 조회 — 시장 전체 C001 스트림에 안 걸린 회사를 위한 개별 검색."""
    end = datetime.today()
    begin = end - timedelta(days=days_back)
    reports = get_reports(corp_code, start_date=begin.strftime("%Y%m%d"), end_date=end.strftime("%Y%m%d"))
    relevant = [r for r in reports if any(k in (r.get("report_nm") or "") for k in ("지분증권", "투자설명서", "철회신고서"))]
    relevant.sort(key=lambda r: (r.get("rcept_dt") or "", r.get("rcept_no") or ""), reverse=True)
    return relevant


def seed_new_items(
    items_by_corp: dict[str, dict[str, Any]],
    process_corp,
    history: list[dict[str, Any]],
    today: str,
    log,
    prev_pending_names: set[str],
    deleted_corps: dict[str, dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """시트에 이름만 적어 넣은 회사를 DART corpCode로 찾아 편입한다 (자동발굴이 놓친 회사용).

    아직 공시가 없거나 DART에서 이름을 못 찾으면 "확인 필요" 목록(작업목록[4]용)으로 반환하고
    매 배치 재시도한다. 해결되면(직전 배치까지 확인 필요였던 이름이 이번에 데이터를 확보하면)
    정정이력에 편입 완료로 기록한다.
    """
    if not SEED_PATH.exists():
        return []
    try:
        names = json.loads(SEED_PATH.read_text(encoding="utf-8"))
    except Exception:
        return []
    if not isinstance(names, list):
        return []

    from urllib.parse import quote

    def find_by_name(norm: str) -> dict[str, Any] | None:
        return next((i for i in items_by_corp.values() if _norm_name(i.get("name") or "") == norm), None)

    def mark_resolved(name: str) -> None:
        if name in prev_pending_names:
            history.append({
                "date": today, "name": name, "type": "수동추가", "field": "상태",
                "old": "확인 필요", "new": "편입 완료",
            })

    def dart_search_link(query: str) -> str:
        return f"https://dart.fss.or.kr/dsab002/main.do?textCrpNm={quote(query)}"

    unresolved: list[dict[str, Any]] = []
    for raw in names:
        name = str(raw or "").strip()
        if not name:
            continue
        existing = find_by_name(_norm_name(name))
        if existing and (existing.get("band_low") or existing.get("forecast_start")):
            mark_resolved(name)
            continue  # 이미 실제 데이터 확보됨 (시장 전체 자동발굴로 해결됐을 수도 있음)

        corp = get_corp_code(name)
        if not corp or not corp.get("corp_code"):
            log(f"수동추가 실패(DART 미등록 회사명): {name}")
            unresolved.append({"name": name, "status": "not_found", "link": dart_search_link(name)})
            continue
        corp_code = corp["corp_code"]
        if deleted_corps and corp_code in deleted_corps:
            log(f"수동추가 무시(삭제된 종목): {name}")
            continue  # 톰스톤: 사용자가 명시적으로 삭제한 종목은 seed로도 재편입하지 않음
        if corp_code in items_by_corp and not existing:
            mark_resolved(name)
            continue  # 자동발굴이 이미 다른 표기로 잡아둔 동일 회사

        link = dart_search_link(corp.get("corp_name") or name)
        try:
            filings = _fetch_corp_filings(corp_code, LOOKBACK_DAYS * 2)
        except Exception as exc:
            log(f"수동추가 조회 실패: {name} ({exc})")
            unresolved.append({"name": name, "status": "pending", "link": link})
            continue

        if filings:
            item = process_corp(corp_code, corp.get("corp_name") or name, filings, existing)
            items_by_corp[corp_code] = item
            if item.get("band_low") or item.get("forecast_start"):
                mark_resolved(name)
            else:
                unresolved.append({"name": name, "status": "pending", "link": link})
        else:
            if not existing:
                log(f"수동추가: {name} — 아직 DART 공시 없음, 대기 등록(매 배치 재조회)")
                items_by_corp[corp_code] = {
                    "corp_code": corp_code,
                    "name": corp.get("corp_name") or name,
                    "first_filing_date": datetime.today().strftime("%Y%m%d"),
                    "last_rcept_no": "",
                    "withdrawn": False,
                    "seeded": True,
                }
            unresolved.append({"name": name, "status": "pending", "link": link})

    return unresolved


def detect_listings_from_krx(
    items_by_corp: dict[str, dict[str, Any]],
    snapshot: dict[str, dict[str, Any]],
    trading_date: str,
    history: list[dict[str, Any]],
    log,
) -> int:
    """상장일 자동 감지 — IPO일정에 있는 회사가 KRX 스냅샷에 처음 나타난 날 = 상장일.

    운영자가 IPO일정 탭에 상장일을 안 채워도 자동 백업으로 채워진다. 배치가 매일 도니
    상장 다음날엔 확실히 잡힌다. 사용자가 이미 시트에서 상장일을 수정한 종목(manual_fields에
    listing_date 포함)은 건드리지 않는다.
    """
    if not snapshot:
        return 0
    name_to_meta: dict[str, tuple[str, dict[str, Any]]] = {}
    for code, meta in snapshot.items():
        key = _norm_name(meta.get("name") or "")
        if key and key not in name_to_meta:
            name_to_meta[key] = (code, meta)

    detected = 0
    for item in items_by_corp.values():
        if item.get("listing_date"):
            continue
        if "listing_date" in (item.get("manual_fields") or []):
            continue
        match = name_to_meta.get(_norm_name(item.get("name") or ""))
        if not match:
            continue
        code, meta = match
        item["listing_date"] = trading_date
        if not item.get("stock_code"):
            item["stock_code"] = code
        if not item.get("market"):
            item["market"] = meta.get("market") or ""
        history.append({
            "date": trading_date, "name": item.get("name", ""), "type": "상장확인(KRX)",
            "field": "상장일", "old": "미정", "new": trading_date,
        })
        log(f"KRX 상장 감지: {item.get('name')} → {trading_date} (코드 {code})")
        detected += 1
    return detected


def refresh_ipo_schedule(
    days_back: int = LOOKBACK_DAYS,
    verbose: bool = True,
    krx_snapshot: dict[str, dict[str, Any]] | None = None,
    krx_trading_date: str | None = None,
) -> dict[str, Any]:
    def log(msg: str) -> None:
        if verbose:
            print(f"[IPO일정] {msg}", file=sys.stderr)

    state = load_state()
    items_by_corp: dict[str, dict[str, Any]] = {i["corp_code"]: i for i in state.get("items", [])}
    history: list[dict[str, Any]] = list(state.get("history") or [])
    prev_pending_names = {p.get("name") for p in state.get("seed_pending", []) if isinstance(p, dict)}
    # 톰스톤: 사용자가 IPO취소 컬럼에서 "삭제"한 종목. 저장된 rcept_no보다 새 신고서가
    # 나오면 자동 부활, 그 이하면 계속 무시. IPO종목·락업 캘린더는 독립이라 여기서 안 건드림.
    deleted_corps: dict[str, dict[str, Any]] = dict(state.get("deleted_corps") or {})

    filings = fetch_equity_filings(days_back)
    grouped = group_upcoming_ipos(filings)
    log(f"C001 신고서 {len(filings)}건 → 미상장 법인 {len(grouped)}곳")

    today = datetime.today().strftime("%Y-%m-%d")
    listing_map = load_listing_map()

    def process_corp(corp_code: str, name: str, corp_filings: list[dict[str, Any]], old: dict[str, Any] | None) -> dict[str, Any]:
        """신고서 목록(최신순) → 병합 파싱된 IPO일정 항목. 자동발굴·수동추가(seed) 양쪽에서 공용으로 쓴다."""
        newest = corp_filings[0]
        withdrawn = any("철회신고서" in (f.get("report_nm") or "") for f in corp_filings)

        if old and old.get("last_rcept_no") == newest.get("rcept_no"):
            return old  # 새 공시 없음 → 문서 재다운로드 생략

        log(f"파싱: {name} ({len(corp_filings)}건, 최신 {newest.get('report_nm')})")
        item = dict(old or {})
        item.update({
            "corp_code": corp_code,
            "name": name,
            "first_filing_date": corp_filings[-1].get("rcept_dt") or "",
            "last_rcept_no": newest.get("rcept_no") or "",
        })
        if not withdrawn:
            merged: dict[str, Any] = {}
            for f in corp_filings[:MAX_DOCS_PER_CORP]:
                rname = f.get("report_nm") or ""
                if "철회" in rname:
                    continue
                try:
                    doc = download_document_text(f["rcept_no"])
                except Exception as exc:
                    log(f"  문서 실패 {f['rcept_no']}: {exc}")
                    continue
                parsed = parse_offering_doc(doc)
                for key, val in parsed.items():
                    # 최신 문서 우선 — 이미 값이 있으면 옛 문서 값으로 덮지 않는다
                    if key not in merged or not merged[key]:
                        if val:
                            merged[key] = val
                if _core_fields_filled(merged) and merged.get("final_price"):
                    break
                if _core_fields_filled(merged) and not any("발행조건확정" in (g.get("report_nm") or "") for g in corp_filings):
                    break
            locked = set(item.get("manual_fields") or [])  # 시트에서 운영자가 고친 필드는 파싱이 덮지 않는다
            for key, val in merged.items():
                if key in locked:
                    continue
                if val or key not in item:
                    old_val = item.get(key)
                    # 기존 편입 종목의 값이 정정공시로 바뀌면 이력에 남긴다 (최초 편입은 제외)
                    if old and key in TRACKED_FIELDS and old_val not in (None, "", 0) and val and val != old_val:
                        history.append({
                            "date": today,
                            "name": name,
                            "type": "정정공시",
                            "field": TRACKED_FIELDS[key],
                            "old": str(old_val),
                            "new": str(val),
                        })
                    item[key] = val
        item["withdrawn"] = withdrawn
        return item

    for corp_code, corp_filings in grouped.items():
        name = corp_filings[0].get("corp_name") or ""
        newest_rcp = corp_filings[0].get("rcept_no") or ""
        tomb = deleted_corps.get(corp_code)
        if tomb and newest_rcp <= (tomb.get("last_rcept_no") or ""):
            continue  # 삭제된 종목 — 톰스톤보다 새 신고서 나올 때만 부활
        if tomb:
            log(f"부활: {name} (톰스톤 {tomb.get('last_rcept_no')} → 새 신고서 {newest_rcp})")
            history.append({
                "date": today, "name": name, "type": "부활",
                "field": "신규 신고서", "old": "삭제됨", "new": newest_rcp,
            })
            deleted_corps.pop(corp_code, None)
        items_by_corp[corp_code] = process_corp(corp_code, name, corp_filings, items_by_corp.get(corp_code))

    seed_pending = seed_new_items(items_by_corp, process_corp, history, today, log, prev_pending_names, deleted_corps)

    # KRX 스냅샷으로 상장일 자동 감지(운영자 미입력 대비 백업)
    if krx_snapshot and krx_trading_date:
        detect_listings_from_krx(items_by_corp, krx_snapshot, krx_trading_date, history, log)

    # 상장일 연결 + 실적보고서 보강 + 정리
    kept: list[dict[str, Any]] = []
    for item in items_by_corp.values():
        linked = listing_map.get(_norm_name(item.get("name") or ""))
        if linked:
            if "listing_date" not in (item.get("manual_fields") or []):
                item["listing_date"] = linked["listing_date"]
            item["stock_code"] = linked["code"]
        item.setdefault("listing_date", "")
        item.setdefault("stock_code", "")

        sub_end = item.get("sub_end") or ""
        if not item.get("withdrawn") and sub_end and sub_end < today and not item.get("report_rcp"):
            try:
                report = find_result_report(item["corp_code"])
                if report:
                    parsed = parse_result_report(download_document_text(report["rcept_no"]))
                    if parsed.get("sub_ratio") or parsed.get("commit_alloc"):
                        item.update(parsed)
                        item["report_rcp"] = report["rcept_no"]
                        log(f"실적보고서 반영: {item.get('name')} (개인청약 {parsed.get('sub_ratio')}:1)")
            except Exception as exc:
                log(f"실적보고서 실패 {item.get('name')}: {exc}")

        # 정리 규칙: 상장 다음날부터 제외 / 철회 후 30일 지남 / 무소식 210일
        # 상장 후는 락업 캘린더가 이어받으므로 IPO일정에는 남길 필요가 없다.
        listing = item.get("listing_date") or ""
        first = item.get("first_filing_date") or ""
        drop = False
        if listing and listing < today:
            drop = True
        if item.get("withdrawn") and first and first < (datetime.today() - timedelta(days=30)).strftime("%Y%m%d"):
            drop = True
        if not listing and first and first < (datetime.today() - timedelta(days=days_back)).strftime("%Y%m%d"):
            drop = True
        if not drop:
            kept.append(item)

    kept.sort(key=lambda i: (i.get("sub_start") or "9999", i.get("name") or ""))
    result = {
        "updated": datetime.today().strftime("%Y-%m-%d %H:%M"),
        "items": kept,
        "history": history[-500:],
        "seed_pending": seed_pending,
        "deleted_corps": deleted_corps,
    }
    SCHEDULE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULE_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"저장: {len(kept)}종목 → {SCHEDULE_PATH.name}")
    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="IPO 일정 데이터 갱신 (DART C001 스트림)")
    parser.add_argument("--days", type=int, default=LOOKBACK_DAYS, help="발굴 창(일)")
    args = parser.parse_args()
    result = refresh_ipo_schedule(days_back=args.days)
    for item in result["items"]:
        print(
            f"{item.get('name','?'):<12} {item.get('market','?'):<4} "
            f"밴드 {item.get('band_low',0):,}~{item.get('band_high',0):,} 확정 {item.get('final_price',0):,} "
            f"수요예측 {item.get('forecast_start','미정')} 청약 {item.get('sub_start','미정')} "
            f"상장 {item.get('listing_date') or '미정'} 주관 {item.get('underwriter') or '미정'}"
        )


if __name__ == "__main__":
    main()
