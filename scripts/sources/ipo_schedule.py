from __future__ import annotations

import json
import re
import sys
from collections import Counter
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from typing import Any

import requests

from scripts.config import DART_API_KEY, ROOT_DIR
from scripts.sources.dart_api import download_document_text, _clean_text, get_corp_code, get_reports
from scripts.management import apply_stock_management, is_fixed_excluded, merge_stock_management

DART_BASE = "https://opendart.fss.or.kr/api"
SCHEDULE_PATH = ROOT_DIR / "data" / "ipo_schedule.json"
TARGETS_PATH = ROOT_DIR / "data" / "ipo_targets.json"
# 시트에 이름만 적어 넣은 "아직 DART가 못 찾은 회사" 요청 목록 (sheets_sync.py가 씀 → 다음 배치가 읽음)
SEED_PATH = ROOT_DIR / "data" / "ipo_seed_names.json"
MANAGEMENT_PATH = ROOT_DIR / "data" / "stock_management.json"

# 발굴 창 — 수요예측→청약→상장까지 수개월 걸릴 수 있어 넉넉히 둔다.
LOOKBACK_DAYS = 210
# 백필 창 — 이미 상장한 과거 종목의 신고서·실적보고서 조회용. corp_code 지정 조회는
# DART가 기간 제한을 두지 않으므로 넓게 잡아도 호출 1번이다. (420일 창으로는
# 2024~2025 상반기 상장 종목의 공시를 영영 못 찾아 85건이 빈 껍데기로 남았던 원인)
BACKFILL_LOOKBACK_DAYS = 1825
# 백필은 종목당 문서 3~5건을 내려받는 무거운 작업이라 배치당 처리 수를 제한한다.
# 완료된 종목은 ipo_parse_version/report_rcp로 스킵되므로 며칠에 걸쳐 자연 소화된다.
MAX_BACKFILL_PER_RUN = 10**9
# 종목당 신고서 다운로드 상한 — 정정이 많아도 최신 몇 건이면 전 필드가 채워진다.
MAX_DOCS_PER_CORP = 4

# 파서가 개선되면 기존 공시번호가 같아도 한 번만 다시 읽어 누락 필드를 보강한다.
# 완료 후 item에 버전을 저장하므로 일일 배치마다 같은 문서를 반복 다운로드하지 않는다.
IPO_PARSE_VERSION = 3

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
    chunk_end = datetime.now(ZoneInfo("Asia/Seoul"))
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
    patterns = [
        r"(?:모집\s*또는\s*매출|모집\(매출\))\s*주식의?\s*수\s*(?:기명식)?\s*보통주\s*([\d,]{4,15})\s*주",
        r"(?:총\s*)?공모\s*주식\s*수[^\d]{0,40}([\d,]{4,15})\s*주",
        r"공모주식수[^\d]{0,40}([\d,]{4,15})\s*주",
        r"모집\s*주식\s*수[^\d]{0,40}([\d,]{4,15})\s*주",
    ]
    for pattern in patterns:
        m = re.search(pattern, plain)
        if m:
            return _to_int(m.group(1))
    return 0


def _parse_demand_tables(doc: str) -> tuple[float, list[dict[str, Any]]]:
    """수요예측 경쟁률 + 기간별 확약 '신청' 내역 — [발행조건확정] 신고서의 결과 표."""
    demand_ratio = 0.0
    commit_apply: list[dict[str, Any]] = []
    for table in _tables(doc):
        txt = _clean_text(table)
        rows = _rows(table)
        if not rows:
            continue
        # DART 문서마다 합계가 첫 행 또는 2~3번째 다중 헤더에 놓인다. 표 전체에
        # 필요한 표식이 있는지 확인하고, 행 라벨은 앞쪽 셀들을 합쳐 판정한다.
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
        if "미확약" in txt and "신청가격" in txt and "합계" in txt:
            tiers: dict[str, int] = {}
            total = 0
            for r in rows:
                label = "".join(r[:3]).replace(" ", "") if r else ""
                nums = [c for c in r if re.fullmatch(r"[\d,]{2,}", c)]
                tier = next((t for t in TIER_LABELS if f"{t}확약" in label), "")
                if not tier and "미확약" in label:
                    tier = "미확약"
                if tier:
                    # 구간 행이 표에 있는데 값이 전부 "-" = 확정된 0. 기록해서
                    # 사이트의 '미정'(미수집)과 구분한다 (토모큐브 1개월·15일 케이스)
                    tiers[tier] = _to_int(nums[-2]) if len(nums) >= 2 else 0
                elif "합계" in label and len(nums) >= 2:
                    total = _to_int(nums[-2])
            if total and len(tiers) >= 3:
                # 모든 종목은 5구간(미확약·15일·1개월·3개월·6개월)을 갖는다.
                # 표에 행 자체가 없는 구간은 0으로 간주하되 zero_missing 표식을 남겨
                # 검토필요에서 확인을 요청한다 (기입 생략 관행 대응).
                commit_apply = []
                for t in TIER_LABELS + ["미확약"]:
                    if t in tiers:
                        commit_apply.append({"period": t, "qty": tiers[t], "pct": round(tiers[t] / total * 100, 2)})
                    else:
                        commit_apply.append({"period": t, "qty": 0, "pct": 0.0, "source": "zero_missing"})
    return demand_ratio, commit_apply


def _parse_ipo_intent(plain: str) -> bool:
    """진짜 신규상장(IPO)인지 판별 — 미상장사의 유상증자(케이디비생명보험 등)를 걸러낸다.

    IPO 증권신고서는 반드시 '신규상장/코스닥·유가증권시장 상장/상장예비심사/상장을 목적' 문구를
    담는다. 미상장사가 자금조달용 유상증자를 하면 이런 상장 의도 문구가 없다.
    """
    return bool(re.search(
        r"신규\s*상장|코스닥\s*시장\s*상장|유가증권\s*시장\s*상장|상장\s*예비\s*심사|상장을\s*목적|코스닥시장\s*상장|공모를\s*통한\s*(?:신규\s*)?상장",
        plain,
    ))


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
        "is_listing_ipo": _parse_ipo_intent(plain),
    }


def _is_confirmed_ipo(item: dict[str, Any]) -> bool:
    """사이트 노출 여부 판정. 신호 부족하면 검토대기(비공개)로 돌린다.

    강한 IPO 신호: 상장 의도 문구 / 상장 시장 확정 / 수요예측 실시(증자는 수요예측 안 함).
    """
    if item.get("is_listing_ipo"):
        return True
    if item.get("market"):
        return True
    if item.get("forecast_start"):
        return True
    return False


# ── 3) 실적보고서 파싱 (청약 후: 개인청약경쟁률 + 확약 '배정') ──


def find_result_report(corp_code: str, listing_date: str = "", sub_end: str = "") -> dict[str, Any] | None:
    """증권발행실적보고서 조회.

    과거 종목은 상장일 주변 창(신고~상장+40일)으로 좁혀 찾는다 — 최근 N일 창으로는
    옛 실적보고서를 못 찾고, 무제한 최신순으로 잡으면 상장 이후 유상증자 실적보고서를
    IPO 실적으로 오인할 수 있어서다.
    """
    if not DART_API_KEY:
        return None
    now = datetime.now(ZoneInfo("Asia/Seoul"))
    if listing_date and re.fullmatch(r"\d{4}-\d{2}-\d{2}", listing_date):
        base = datetime.strptime(listing_date, "%Y-%m-%d")
        bgn_de = (base - timedelta(days=180)).strftime("%Y%m%d")
        end_de = min(base + timedelta(days=40), now.replace(tzinfo=None)).strftime("%Y%m%d")
    elif sub_end and re.fullmatch(r"\d{4}-\d{2}-\d{2}", sub_end):
        base = datetime.strptime(sub_end, "%Y-%m-%d")
        bgn_de = (base - timedelta(days=30)).strftime("%Y%m%d")
        end_de = min(base + timedelta(days=60), now.replace(tzinfo=None)).strftime("%Y%m%d")
    else:
        bgn_de = (now - timedelta(days=LOOKBACK_DAYS)).strftime("%Y%m%d")
        end_de = now.strftime("%Y%m%d")
    res = requests.get(
        f"{DART_BASE}/list.json",
        params={
            "crtfc_key": DART_API_KEY,
            "corp_code": corp_code,
            "bgn_de": bgn_de,
            "end_de": end_de,
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

    # 일부 실적보고서는 표 구조가 흔들려도 본문에 개인/일반 청약 경쟁률을 직접 적는다.
    for m in re.finditer(r"(?:개인|일반)\s*청약\s*경쟁률[^\d]{0,30}([\d,]+(?:\.\d+)?)\s*(?::|대)?\s*1", plain):
        try:
            value = float(m.group(1).replace(",", ""))
        except ValueError:
            continue
        if value > 0:
            out["sub_ratio"] = value

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
            tokens = m.group(1).split()
            nums = [t for t in tokens if t != "-"]
            if len(nums) < 2:
                # 구간이 표에 있는데 값이 전부 "-" = 확정된 0으로 기록 ('미정'과 구분)
                if tokens and all(t == "-" for t in tokens):
                    alloc_rows.append({"period": tier, "qty": 0, "pct": 0.0})
                continue
            try:
                qty = _to_int(nums[-2])
                pct = float(nums[-1].replace(",", ""))
            except ValueError:
                continue
            alloc_rows.append({"period": tier, "qty": qty, "pct": pct})
        if len(alloc_rows) >= 3:
            # 5구간 강제 — 표에 없는 구간은 0 + zero_missing 표식 (검토필요 확인 요청)
            present = {str(row.get("period")) for row in alloc_rows}
            for tier in TIER_LABELS + ["미확약"]:
                if tier not in present:
                    alloc_rows.append({"period": tier, "qty": 0, "pct": 0.0, "source": "zero_missing"})
            out["commit_alloc"] = alloc_rows
    return out


def _should_fetch_result_report(item: dict[str, Any], today: str) -> bool:
    """청약 종료 당일부터 DART 실적보고서를 조회할 수 있는지 판정한다."""
    sub_end = item.get("sub_end") or ""
    return bool(
        not item.get("withdrawn")
        and sub_end
        and sub_end <= today
        and not item.get("report_rcp")
    )


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


def _ipo_era_filings(filings: list[dict[str, Any]], listing_date: str) -> list[dict[str, Any]]:
    """상장일 기준 IPO 시점 공시만 남긴다 (상장일+15일 이내 접수분).

    상장 후 유상증자(주주배정) 투자설명서가 5년 창의 최신 공시로 잡히면 희망밴드가
    없어 파싱이 빈다 (이뮨온시아·클로봇·엑셀세라퓨틱스). 상장일을 알면 그 이전
    IPO 문서만 골라 원래 공모 정보를 파싱한다. 상장일 미상이면 원본을 그대로 둔다.
    """
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", listing_date or ""):
        return filings
    cutoff = (datetime.strptime(listing_date, "%Y-%m-%d") + timedelta(days=15)).strftime("%Y%m%d")
    era = [f for f in filings if (f.get("rcept_dt") or "") <= cutoff]
    return era or filings  # 창에 아무것도 없으면(데이터 이상) 원본 유지


# ── 5) 메인 갱신 루프 ─────────────────────────────────────


def load_state() -> dict[str, Any]:
    if SCHEDULE_PATH.exists():
        try:
            return json.loads(SCHEDULE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"updated": "", "items": [], "past_items": []}


def _core_fields_filled(item: dict[str, Any]) -> bool:
    return bool(item.get("band_low") and item.get("forecast_start") and item.get("sub_start") and item.get("underwriter"))


def _fetch_corp_filings(corp_code: str, days_back: int) -> list[dict[str, Any]]:
    """특정 회사 하나의 발행공시만 직접 조회 — 시장 전체 C001 스트림에 안 걸린 회사를 위한 개별 검색."""
    end = datetime.now(ZoneInfo("Asia/Seoul"))
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
    fixed_exclusions: dict[str, dict[str, Any]] | None = None,
    heavy_budget: dict[str, int] | None = None,
    stock_hints: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    """시트에 이름만 적어 넣은 회사를 DART corpCode로 찾아 편입한다 (자동발굴이 놓친 회사용).

    아직 공시가 없거나 DART에서 이름을 못 찾으면 "확인 필요" 목록(작업목록[4]용)으로 반환하고
    매 배치 재시도한다. 해결되면(직전 배치까지 확인 필요였던 이름이 이번에 데이터를 확보하면)
    정정이력에 편입 완료로 기록한다.

    heavy_budget: 문서 다운로드가 필요한 종목의 배치당 처리 상한(과거 종목 백필과 공유).
    상한 초과분은 pending으로 남겨 다음 배치가 이어서 처리한다.
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

        # 종목코드 힌트가 있으면 코드 우선 매칭 — DART에 동명 비상장사가 있으면
        # 이름 매칭이 엉뚱한(공시 0건) 회사를 잡는다 (티엠씨·인벤테라·키스트론·한텍 케이스)
        stock_hint = (stock_hints or {}).get(_norm_name(name), "")
        corp = get_corp_code(name, stock_code=stock_hint) if stock_hint else get_corp_code(name)
        if not corp or not corp.get("corp_code"):
            log(f"수동추가 실패(DART 미등록 회사명): {name}")
            unresolved.append({"name": name, "status": "not_found", "link": dart_search_link(name)})
            continue
        corp_code = corp["corp_code"]
        if fixed_exclusions and is_fixed_excluded(corp_code, corp.get("corp_name") or name, fixed_exclusions):
            log(f"수동추가 무시(고정 제외): {name}")
            continue
        if deleted_corps and corp_code in deleted_corps:
            log(f"수동추가 무시(삭제된 종목): {name}")
            continue  # 톰스톤: 사용자가 명시적으로 삭제한 종목은 seed로도 재편입하지 않음
        if corp_code in items_by_corp and not existing:
            mark_resolved(name)
            continue  # 자동발굴이 이미 다른 표기로 잡아둔 동일 회사

        link = dart_search_link(corp.get("corp_name") or name)
        # 문서 파싱은 무거우니 배치당 상한을 넘으면 이번엔 건너뛰고 pending 유지
        if heavy_budget is not None and heavy_budget.get("left", 0) <= 0:
            unresolved.append({"name": name, "status": "pending", "link": link})
            continue
        try:
            # 과거 상장 종목 백필까지 커버하도록 넓은 창 사용 (corp 지정 조회라 호출 1번)
            filings = _fetch_corp_filings(corp_code, BACKFILL_LOOKBACK_DAYS)
        except Exception as exc:
            log(f"수동추가 조회 실패: {name} ({exc})")
            unresolved.append({"name": name, "status": "pending", "link": link})
            continue

        if filings:
            if heavy_budget is not None:
                heavy_budget["left"] = heavy_budget.get("left", 0) - 1
            item = process_corp(corp_code, corp.get("corp_name") or name, filings, existing)
            if existing and existing.get("corp_code") != corp_code:
                items_by_corp.pop(str(existing.get("corp_code") or ""), None)
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
                    "first_filing_date": datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d"),
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
    base_info: dict[str, dict[str, Any]] | None = None,
) -> int:
    """KRX 진실 소스 원칙: 상장일·종목코드·시장을 KRX 기준으로 반영한다.

    상장일은 종목기본정보의 LIST_DD(실제 상장일)만 사용한다. 시세 스냅샷은 이미 상장된
    모든 종목을 포함하므로, 스냅샷 기준일을 상장일로 쓰면 과거 종목이 오늘 상장한 것처럼
    오염된다. 스냅샷은 종목코드·시장 보조값으로만 사용한다.
    """
    if not snapshot and not base_info:
        return 0

    # 종목코드/이름 → (코드, 상장일, 시장) 통합 조회표. 기본정보(정확한 LIST_DD)가 우선.
    name_to_meta: dict[str, dict[str, Any]] = {}
    code_to_meta: dict[str, dict[str, Any]] = {}
    for code, meta in (snapshot or {}).items():
        key = _norm_name(meta.get("name") or "")
        entry = {"code": code, "market": meta.get("market") or ""}
        if key and key not in name_to_meta:
            name_to_meta[key] = entry
        if code:
            code_to_meta[code] = entry
    for code, info in (base_info or {}).items():
        key = _norm_name(info.get("name") or "")
        if not key and not code:
            continue
        # 기본정보는 정확한 상장일을 주므로 스냅샷 값을 덮어쓴다
        entry = name_to_meta.setdefault(key, {}) if key else {}
        entry["code"] = code
        entry["market"] = info.get("market") or entry.get("market") or ""
        if info.get("list_dd"):
            entry["list_dd"] = info["list_dd"]
        if code:
            code_to_meta[code] = entry

    detected = 0
    for item in items_by_corp.values():
        item_code = (item.get("stock_code") or "").strip()
        match = code_to_meta.get(item_code) if item_code else None
        if not match:
            match = name_to_meta.get(_norm_name(item.get("name") or ""))
        if not match:
            continue
        code = match.get("code") or ""
        list_dd = match.get("list_dd") or ""

        # 상장일: KRX가 진실. 다르면 자동수정 + 이력 기록.
        current_listing = item.get("listing_date") or ""
        if list_dd and current_listing != list_dd:
            history.append({
                "date": trading_date, "name": item.get("name", ""),
                "type": "KRX 자동수정" if current_listing else "상장확인(KRX)",
                "field": "상장일",
                "old": current_listing or "미정",
                "new": list_dd,
            })
            item["listing_date"] = list_dd
            manual_fields = [f for f in (item.get("manual_fields") or []) if f != "listing_date"]
            if manual_fields:
                item["manual_fields"] = manual_fields
            elif "manual_fields" in item:
                del item["manual_fields"]
            detected += 1
            log(f"KRX 상장 반영: {item.get('name')} {current_listing or '미정'} → {list_dd} (코드 {code})")

        # 종목코드: 사용자가 잘못 넣었으면 KRX 값으로 자동수정
        current_code = (item.get("stock_code") or "").strip()
        if code and current_code != code:
            if current_code:
                history.append({
                    "date": trading_date, "name": item.get("name", ""),
                    "type": "KRX 자동수정", "field": "종목코드",
                    "old": current_code, "new": code,
                })
            item["stock_code"] = code

        if not item.get("market") and match.get("market"):
            item["market"] = match["market"]
    return detected


def _date_or_none(value: str) -> datetime | None:
    try:
        return datetime.strptime(str(value or ""), "%Y-%m-%d")
    except ValueError:
        return None


def _filing_date_or_none(value: str) -> datetime | None:
    text = re.sub(r"[^\d]", "", str(value or ""))
    if len(text) != 8:
        return None
    try:
        return datetime.strptime(text, "%Y%m%d")
    except ValueError:
        return None


def _listing_date_is_plausible(item: dict[str, Any], listing_date: str) -> bool:
    listing = _date_or_none(listing_date)
    if not listing:
        return False
    sub_end = _date_or_none(item.get("sub_end") or "")
    if sub_end:
        # IPO 상장일은 보통 청약 종료 뒤 며칠~수주 안에 온다. 몇 달 이상 벌어지면
        # KRX 시세 기준일이나 잘못된 수기값이 순환 저장된 것으로 본다.
        # 반대로 상장일이 청약일보다 앞서는 경우는 기존 실제 상장일에 나중 공시 일정이
        # 섞인 케이스일 수 있으므로 여기서 상장일을 지우지 않는다.
        return listing <= sub_end + timedelta(days=120)
    forecast_start = _date_or_none(item.get("forecast_start") or "")
    if forecast_start and listing > forecast_start + timedelta(days=180):
        return False
    first_filing = _filing_date_or_none(item.get("first_filing_date") or "")
    if (
        first_filing
        and not item.get("report_rcp")
        and not item.get("final_price")
        and listing > first_filing + timedelta(days=420)
    ):
        return False
    return True


def _trusted_listing_date(item: dict[str, Any]) -> str:
    listing = item.get("listing_date") or ""
    return listing if _listing_date_is_plausible(item, listing) else ""


def _needs_offering_backfill(item: dict[str, Any]) -> bool:
    """DART 증권신고서/발행조건확정 문서 재파싱이 필요한 IPO일정 빈칸."""
    if item.get("withdrawn") or item.get("fixed_excluded"):
        return False
    if item.get("management_hidden") or item.get("review_pending"):
        return False
    required_any = (
        "band_low", "band_high", "final_price",
        "forecast_start", "forecast_end", "sub_start", "sub_end",
        "underwriter", "market", "offer_shares", "demand_ratio",
    )
    if any(not item.get(field) for field in required_any):
        return True
    if not any((row or {}).get("qty") for row in (item.get("commit_apply") or [])):
        # 전체 문서를 훑고도 확약신청이 없던 종목(DART에 데이터 자체가 없음)은
        # 파서 버전이 오르기 전까지 재시도하지 않는다. 이 마커가 없으면 신청 없는
        # 과거 종목 80여 개가 매 백필마다 문서 5~14건씩 재다운로드하며 시간을 태운다.
        if int(item.get("commit_apply_missing") or 0) >= IPO_PARSE_VERSION:
            return False
        return True
    return False


def _clear_suspicious_listing_date(
    item: dict[str, Any],
    history: list[dict[str, Any]],
    today: str,
    log,
) -> bool:
    listing = item.get("listing_date") or ""
    if not listing or _listing_date_is_plausible(item, listing):
        return False
    if "listing_date" in set(item.get("manual_fields") or []):
        return False
    history.append({
        "date": today,
        "name": item.get("name", ""),
        "type": "자동정리",
        "field": "상장일",
        "old": listing,
        "new": "미정",
    })
    item["listing_date"] = ""
    item.pop("result_report_missing", None)
    log(f"상장일 오염값 제거: {item.get('name')} {listing} → 미정")
    return True


def refresh_ipo_schedule(
    days_back: int = LOOKBACK_DAYS,
    verbose: bool = True,
    krx_snapshot: dict[str, dict[str, Any]] | None = None,
    krx_trading_date: str | None = None,
    krx_base_info: dict[str, dict[str, Any]] | None = None,
    backfill_all: bool = False,
) -> dict[str, Any]:
    def log(msg: str) -> None:
        if verbose:
            print(f"[IPO일정] {msg}", file=sys.stderr)

    state = load_state()
    # reset_sheet 실행은 시트 pull을 건너뛴다. 그래도 커밋된 관리 명령(특히 제외고정과
    # 이름만 수동편입)은 빌드 전에 적용해 불필요한 재파싱/자동부활을 막는다.
    if MANAGEMENT_PATH.exists():
        try:
            saved_management = json.loads(MANAGEMENT_PATH.read_text(encoding="utf-8"))
            targets = json.loads(TARGETS_PATH.read_text(encoding="utf-8")) if TARGETS_PATH.exists() else []
            management_rows = merge_stock_management(saved_management, targets, state)
            _, state, _ = apply_stock_management(management_rows, targets, state)
        except Exception as exc:
            log(f"종목관리 사전 적용 실패(기존 상태로 계속): {exc}")
    items_by_corp: dict[str, dict[str, Any]] = {i["corp_code"]: i for i in state.get("items", [])}
    archived_by_corp: dict[str, dict[str, Any]] = {
        i["corp_code"]: i for i in state.get("past_items", []) if i.get("corp_code")
    }
    history: list[dict[str, Any]] = list(state.get("history") or [])
    prev_pending_names = {p.get("name") for p in state.get("seed_pending", []) if isinstance(p, dict)}
    # 톰스톤: 사용자가 IPO취소 컬럼에서 "삭제"한 종목. 저장된 rcept_no보다 새 신고서가
    # 나오면 자동 부활, 그 이하면 계속 무시. IPO종목·락업 캘린더는 독립이라 여기서 안 건드림.
    deleted_corps: dict[str, dict[str, Any]] = dict(state.get("deleted_corps") or {})
    # 종목관리의 제외고정은 새 공시가 나와도 자동 부활하지 않는다. 기존 파싱값은
    # state에 보존해 재승인 시 전체 문서를 다시 받지 않고 즉시 복구한다.
    fixed_exclusions: dict[str, dict[str, Any]] = dict(state.get("fixed_exclusions") or {})

    filings = fetch_equity_filings(days_back)
    grouped = group_upcoming_ipos(filings)
    log(f"C001 신고서 {len(filings)}건 → 미상장 법인 {len(grouped)}곳")

    now_kst = datetime.now(ZoneInfo("Asia/Seoul"))
    today = now_kst.strftime("%Y-%m-%d")
    listing_map = load_listing_map()

    def apply_manual_commit_values(item: dict[str, Any]) -> dict[str, Any]:
        """수기 확약값(신청·배정)은 공식 파싱 실패 시만 쓰고, 고정한 기간만 계속 유지한다."""
        for field, manual_field in (("commit_apply", "manual_commit_apply"), ("commit_alloc", "manual_commit_alloc")):
            manual = dict(item.get(manual_field) or {})
            if not manual:
                continue
            official = {
                str(value.get("period") or ""): dict(value)
                for value in (item.get(field) or [])
                if isinstance(value, dict) and value.get("period")
            }
            for period, raw in manual.items():
                value = dict(raw or {})
                if value.get("locked") or period not in official:
                    official[period] = {
                        "period": period, "qty": int(value.get("qty") or 0), "pct": 0,
                        "source": "manual_fixed" if value.get("locked") else "manual_temporary",
                        "visible": value.get("visible", True),
                    }
                elif period in official:
                    official[period]["visible"] = value.get("visible", True)
            total = sum(int(value.get("qty") or 0) for value in official.values())
            if total:
                for value in official.values():
                    value["pct"] = round(int(value.get("qty") or 0) / total * 100, 2)
            order = {period: index for index, period in enumerate(["미확약", "15일", "1개월", "3개월", "6개월"])}
            item[field] = sorted(official.values(), key=lambda value: order.get(str(value.get("period") or ""), 99))
        return item

    def process_corp(corp_code: str, name: str, corp_filings: list[dict[str, Any]], old: dict[str, Any] | None) -> dict[str, Any]:
        """신고서 목록(최신순) → 병합 파싱된 IPO일정 항목. 자동발굴·수동추가(seed) 양쪽에서 공용으로 쓴다."""
        newest = corp_filings[0]
        # 철회는 "최신 공시가 철회신고서"일 때만. 과거 철회 후 재도전해 상장한 종목
        # (미트박스·서울보증보험·온코크로스 등)은 5년 창에 옛 철회가 걸려도 철회가 아니다.
        # (any() 판정은 백필 창 확대 후 이들 파싱을 통째로 스킵시키던 버그였음)
        withdrawn = "철회신고서" in (newest.get("report_nm") or "")
        official_periods = {
            str(value.get("period") or "")
            for value in ((old or {}).get("commit_apply") or [])
            if isinstance(value, dict)
            and value.get("qty")
            and str(value.get("source") or "") not in {"manual_fixed", "manual_temporary"}
        }
        needs_temporary_commit_check = any(
            not bool((value or {}).get("locked")) and str(period) not in official_periods
            for period, value in dict((old or {}).get("manual_commit_apply") or {}).items()
        )

        if (
            old
            and old.get("last_rcept_no") == newest.get("rcept_no")
            and int(old.get("ipo_parse_version") or 0) >= IPO_PARSE_VERSION
            and not needs_temporary_commit_check
            and not _needs_offering_backfill(old)
        ):
            return apply_manual_commit_values(old)  # 새 공시 없음 → 문서 재다운로드 생략

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
            selected_filings = list(corp_filings[:MAX_DOCS_PER_CORP])
            # 최신 정정/투자설명서 몇 건 뒤로 밀린 [발행조건확정] 신고서에도
            # 기관 신청표가 있으므로 최소 한 건은 반드시 파싱 후보에 포함한다.
            condition_filing = next(
                (f for f in corp_filings if "발행조건확정" in (f.get("report_nm") or "")),
                None,
            )
            if condition_filing and all(
                f.get("rcept_no") != condition_filing.get("rcept_no") for f in selected_filings
            ):
                selected_filings.append(condition_filing)

            has_condition_filing = condition_filing is not None
            for f in selected_filings:
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
                if (
                    _core_fields_filled(merged)
                    and merged.get("final_price")
                    and (merged.get("commit_apply") or not has_condition_filing)
                ):
                    break
                if _core_fields_filled(merged) and not has_condition_filing:
                    break
            locked = set(item.get("manual_fields") or [])  # 고정 보정은 공시가 덮지 않는다
            provisional = set(item.get("provisional_fields") or [])
            for key, val in merged.items():
                if key in locked:
                    continue
                if val or key not in item:
                    old_val = item.get(key)
                    was_provisional = key in provisional
                    if was_provisional and val:
                        if old_val not in (None, "", 0) and val != old_val:
                            history.append({
                                "date": today, "name": name, "type": "자동확정",
                                "field": TRACKED_FIELDS.get(key, key), "old": str(old_val), "new": str(val),
                            })
                        provisional.discard(key)
                    # 기존 편입 종목의 값이 정정공시로 바뀌면 이력에 남긴다 (최초 편입은 제외)
                    if old and not was_provisional and key in TRACKED_FIELDS and old_val not in (None, "", 0) and val and val != old_val:
                        history.append({
                            "date": today,
                            "name": name,
                            "type": "정정공시",
                            "field": TRACKED_FIELDS[key],
                            "old": str(old_val),
                            "new": str(val),
                        })
                    item[key] = val
            item["ipo_parse_version"] = IPO_PARSE_VERSION
            if provisional:
                item["provisional_fields"] = sorted(provisional)
            else:
                item.pop("provisional_fields", None)
        item["withdrawn"] = withdrawn
        # 파싱을 끝냈는데도 확약신청이 없으면 마커를 남겨 다음 배치가 재시도하지 않게 한다.
        # 새 공시(rcept_no 변경)가 나오면 마커와 무관하게 다시 파싱된다.
        has_official_apply = any(
            (row or {}).get("qty")
            and str((row or {}).get("source") or "") not in {"manual_fixed", "manual_temporary"}
            for row in (item.get("commit_apply") or [])
        )
        if has_official_apply:
            item.pop("commit_apply_missing", None)
        else:
            item["commit_apply_missing"] = IPO_PARSE_VERSION
        return apply_manual_commit_values(item)

    for corp_code, corp_filings in grouped.items():
        name = corp_filings[0].get("corp_name") or ""
        newest_rcp = corp_filings[0].get("rcept_no") or ""
        if is_fixed_excluded(corp_code, name, fixed_exclusions):
            continue
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
        old = items_by_corp.get(corp_code) or archived_by_corp.get(corp_code)
        if not old:
            # 이름만 수동편입한 synthetic 항목을 실제 DART 기업코드로 승격한다.
            old_key, old = next(
                ((key, item) for key, item in items_by_corp.items() if item.get("manual_entry") and _norm_name(item.get("name") or "") == _norm_name(name)),
                ("", None),
            )
            if old and old_key:
                items_by_corp.pop(old_key, None)
        items_by_corp[corp_code] = process_corp(corp_code, name, corp_filings, old)

    # backfill_all=True면 배치당 상한 없이 남은 백필(신고서·실적보고서)을 한 번에 전부 처리한다.
    # Run workflow의 backfill_all 체크 또는 --backfill-all 인자로 켠다.
    heavy_budget = {"left": 10**9 if backfill_all else MAX_BACKFILL_PER_RUN}
    if backfill_all:
        log("backfill_all — 배치당 상한 해제, 미채움 종목 전량 처리")

    # 이름 → 종목코드 힌트 (동명 비상장사 오매칭 방지용). 과거 종목은 이미 상장돼 코드를 안다.
    stock_hints: dict[str, str] = {}
    for source in (archived_by_corp.values(), items_by_corp.values()):
        for entry in source:
            code = str(entry.get("stock_code") or "").strip()
            key = _norm_name(entry.get("name") or "")
            if key and code:
                stock_hints.setdefault(key, code)
    for key, linked in listing_map.items():
        if linked.get("code"):
            stock_hints.setdefault(key, str(linked["code"]))

    seed_pending = seed_new_items(
        items_by_corp, process_corp, history, today, log, prev_pending_names,
        deleted_corps, fixed_exclusions, heavy_budget, stock_hints,
    )

    # 이미 상장된 과거 종목은 시장 전체 C001 조회에서 corp_cls=E(미상장)가 아니어서
    # grouped에 들어오지 않는다. 기관 신청물량이 없는 과거 이력은 기업코드로 직접
    # 공시를 찾아 한 번 보강하고, 파서 버전을 저장해 매일 반복 조회하지 않는다.
    for corp_code, archived in list(archived_by_corp.items()):
        if archived.get("fixed_excluded"):
            archived["ipo_parse_version"] = IPO_PARSE_VERSION
            continue
        _clear_suspicious_listing_date(archived, history, today, log)
        has_official_commit_apply = any(
            isinstance(value, dict)
            and value.get("qty")
            and str(value.get("source") or "") not in {"manual_fixed", "manual_temporary"}
            for value in (archived.get("commit_apply") or [])
        )
        has_temporary_commit_apply = any(
            not bool((value or {}).get("locked"))
            for value in dict(archived.get("manual_commit_apply") or {}).values()
        )

        # corp_code 검증·교정 — 백필 초기에 이름 매칭으로 등록된 항목은 DART 동명
        # 비상장사(공시 0건)를 잡았을 수 있고, manual-* 스텁은 DART 등록명이 달라
        # 이름으로는 영영 못 찾는다. 종목코드(상장 후 확보됨)로 재확인해 다르면 교정하고
        # 파서 상태를 리셋해 아래 보강이 새 corp 기준으로 다시 돌게 한다.
        # (티엠씨·인벤테라·키스트론·한텍·에이치이엠파마·피앤에스미캐닉스가 영영 미채움이던 원인)
        core_missing = not (archived.get("band_low") or archived.get("forecast_start"))
        # 코어(밴드·일정)가 비어 있으면 이전 실행이 남긴 실패 플래그(result_report_missing 등)와
        # 파서 버전을 리셋해 이번 배치가 신고서·실적보고서를 처음부터 다시 채우게 한다.
        # (과거 철회 재도전 종목이 withdrawn 오탐으로 스킵돼 깨진 상태로 굳었던 것 복구)
        if core_missing:
            archived["ipo_parse_version"] = 0
            archived.pop("result_report_missing", None)
            archived.pop("commit_apply_missing", None)
        if core_missing and not archived.get("corp_verified"):
            hint = str(archived.get("stock_code") or "").strip()
            if hint:
                verified = get_corp_code(archived.get("name") or "", stock_code=hint)
                archived["corp_verified"] = True  # 배치마다 재조회하지 않게 1회만
                if verified and verified.get("corp_code") and verified["corp_code"] != corp_code:
                    history.append({
                        "date": today, "name": archived.get("name") or "", "type": "KRX 자동수정",
                        "field": "DART기업코드", "old": str(corp_code), "new": verified["corp_code"],
                    })
                    archived_by_corp.pop(corp_code, None)
                    corp_code = verified["corp_code"]
                    archived["corp_code"] = corp_code
                    # 엉뚱한 corp로 저장된 실패 흔적 리셋 — 새 corp 기준으로 재파싱·재조회
                    archived["ipo_parse_version"] = 0
                    archived.pop("result_report_missing", None)
                    archived.pop("last_rcept_no", None)
                    archived_by_corp[corp_code] = archived
                    log(f"과거 이력 corp 교정: {archived.get('name')} → {corp_code}")

        # ① 신고서 보강 (희망밴드·일정·확약 신청) — 완료 후 버전 저장으로 반복 방지
        needs_filing = (
            _needs_offering_backfill(archived)
            or has_temporary_commit_apply
            or (
                not has_official_commit_apply
                and int(archived.get("ipo_parse_version") or 0) < IPO_PARSE_VERSION
            )
        )
        if has_official_commit_apply:
            archived["ipo_parse_version"] = IPO_PARSE_VERSION

        if needs_filing and heavy_budget["left"] > 0:
            try:
                corp_filings = _fetch_corp_filings(corp_code, BACKFILL_LOOKBACK_DAYS)
                # 상장 후 유상증자 문서가 최신으로 잡히지 않게 IPO 시점 공시만 사용
                corp_filings = _ipo_era_filings(corp_filings, archived.get("listing_date") or "")
                if corp_filings:
                    heavy_budget["left"] -= 1
                    source_item = dict(archived)
                    if has_temporary_commit_apply:
                        source_item["ipo_parse_version"] = 0
                    refreshed = process_corp(
                        corp_code,
                        archived.get("name") or corp_filings[0].get("corp_name") or "",
                        corp_filings,
                        source_item,
                    )
                    archived_by_corp[corp_code] = refreshed
                    archived = refreshed
                    log(
                        f"과거 이력 기관신청 보강: {refreshed.get('name')} "
                        f"({len(refreshed.get('commit_apply') or [])}개 구간)"
                    )
                else:
                    archived["ipo_parse_version"] = IPO_PARSE_VERSION
                    archived["commit_apply_missing"] = IPO_PARSE_VERSION
                    log(f"과거 이력 기관신청 공시 없음: {archived.get('name')}")
            except Exception as exc:
                # 다음 배치에서 재시도할 수 있게 버전은 올리지 않는다.
                log(f"과거 이력 기관신청 보강 실패 {archived.get('name')}: {exc}")

        # ② 실적보고서 보강 (확약 배정·개인청약경쟁률) — 상장일 주변 창으로 조회.
        #    이전엔 이 단계가 없어서 과거 종목의 배정 데이터가 영영 비어 있었다.
        has_report = bool(archived.get("report_rcp"))
        needs_result = (
            not has_report
            and (not archived.get("commit_alloc") or not archived.get("sub_ratio"))
            and (
                # "실적보고서 없음" 판정을 받았으면 파서 버전이 오르기 전까지 재조회하지 않는다.
                # (예전의 `or not sub_ratio` 예외는 보고서가 원래 없는 종목을 매 배치
                #  재조회하게 만들어 배치당 상한 25건을 허탕으로 소진시키던 원인)
                not archived.get("result_report_missing")
                or int(archived.get("ipo_parse_version") or 0) < IPO_PARSE_VERSION
            )
        )
        # 정정 실적보고서 탐지 — 이미 반영한 보고서보다 새 접수번호가 있으면 다시 읽는다.
        # 상장 90일 이내 종목만 재확인(목록 조회는 싸고, 정정은 대부분 이 창 안에 나온다).
        # 전 종목 상시 재확인은 배치당 상한을 다시 허탕으로 소진시키므로 하지 않는다.
        recheck_listing = _trusted_listing_date(archived)
        recheck_correction = (
            has_report
            and bool(recheck_listing)
            and recheck_listing >= (now_kst - timedelta(days=90)).strftime("%Y-%m-%d")
        )
        if (needs_result or recheck_correction) and heavy_budget["left"] > 0:
            try:
                report = find_result_report(
                    corp_code,
                    listing_date=_trusted_listing_date(archived),
                    sub_end=archived.get("sub_end") or "",
                )
                if recheck_correction:
                    # 접수번호가 저장값보다 새것일 때만 문서를 내려받는다(상한 차감도 그때만)
                    if report and str(report["rcept_no"]) > str(archived.get("report_rcp") or ""):
                        heavy_budget["left"] -= 1
                        parsed = parse_result_report(download_document_text(report["rcept_no"]))
                        if parsed.get("sub_ratio") or parsed.get("commit_alloc"):
                            archived.update(parsed)
                            archived["report_rcp"] = report["rcept_no"]
                            log(f"정정 실적보고서 반영: {archived.get('name')} ({report['rcept_no']})")
                elif report:
                    heavy_budget["left"] -= 1
                    parsed = parse_result_report(download_document_text(report["rcept_no"]))
                    if parsed.get("sub_ratio") or parsed.get("commit_alloc"):
                        archived.update(parsed)
                        archived["report_rcp"] = report["rcept_no"]
                        log(f"과거 이력 실적보강: {archived.get('name')} (개인청약 {parsed.get('sub_ratio')}:1)")
                    else:
                        archived["result_report_missing"] = True
                else:
                    # 실적보고서가 없는 상장(스팩합병·이전상장 등) — 재조회 반복 방지 플래그
                    heavy_budget["left"] -= 1
                    archived["result_report_missing"] = True
                    log(f"과거 이력 실적보고서 없음: {archived.get('name')}")
            except Exception as exc:
                log(f"과거 이력 실적보강 실패 {archived.get('name')}: {exc}")

    # KRX로 상장일 자동 감지·확정 (상장일은 종목기본정보 LIST_DD만 사용)
    if (krx_snapshot or krx_base_info) and krx_trading_date:
        detect_listings_from_krx(items_by_corp, krx_snapshot or {}, krx_trading_date, history, log, base_info=krx_base_info)
        detect_listings_from_krx(archived_by_corp, krx_snapshot or {}, krx_trading_date, history, log, base_info=krx_base_info)

    # 상장일 연결 + 실적보고서 보강 + 정리
    kept: list[dict[str, Any]] = []
    for item in items_by_corp.values():
        if item.get("fixed_excluded") or is_fixed_excluded(
            str(item.get("corp_code") or ""), str(item.get("name") or ""), fixed_exclusions
        ):
            item["fixed_excluded"] = True
            item["management_status"] = "제외고정"
            item["review_pending"] = True
            kept.append(item)
            continue
        _clear_suspicious_listing_date(item, history, today, log)
        # IPO종목 탭에서 채운 값은 KRX 감지가 이미 우선 반영했으니 비어있을 때만 보조로 사용.
        linked = listing_map.get(_norm_name(item.get("name") or ""))
        if linked:
            if (
                not item.get("listing_date")
                and linked["listing_date"]
                and _listing_date_is_plausible(item, linked["listing_date"])
            ):
                item["listing_date"] = linked["listing_date"]
            if not item.get("stock_code") and linked["code"]:
                item["stock_code"] = linked["code"]
        item.setdefault("listing_date", "")
        item.setdefault("stock_code", "")

        # 청약 종료 당일 장 마감 후 실적보고서가 공시될 수 있으므로, 그날
        # 저녁 배치부터 바로 조회한다. KRX 시세/종목 존재 여부와는 무관하다.
        if _should_fetch_result_report(item, today):
            try:
                report = find_result_report(
                    item["corp_code"],
                    listing_date=_trusted_listing_date(item),
                    sub_end=item.get("sub_end") or "",
                )
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
        past_listing = bool(listing and listing < today)
        if past_listing:
            drop = True
        if item.get("withdrawn") and first and first < (now_kst - timedelta(days=30)).strftime("%Y%m%d"):
            drop = True
        if not listing and first and first < (now_kst - timedelta(days=days_back)).strftime("%Y%m%d"):
            drop = True
        # 검토대기 판정: 사용자가 승인한 종목은 항상 노출, 아니면 IPO 신호 부족 시 비공개 대기
        if item.get("management_hidden"):
            item["review_pending"] = True
        elif item.get("manual_entry") or item.get("review_approved"):
            item["review_pending"] = False
        else:
            weak = not _is_confirmed_ipo(item)
            if weak and not item.get("review_pending"):
                # 새로 검토대기로 넘어가는 순간만 이력에 남긴다
                history.append({
                    "date": today, "name": item.get("name", ""), "type": "검토대기",
                    "field": "노출", "old": "-", "new": "IPO 신호 부족(비공개)",
                })
            item["review_pending"] = weak

        if past_listing:
            item["archived_at"] = item.get("archived_at") or today
            # 백필 루프가 이미 채워둔 과거 항목을 비어 있는 복사본으로 덮지 않는다.
            # 기존 archived(백필로 밴드·일정·확약이 채워짐)를 베이스로 두고, item의
            # 값이 있는 필드만 덮어쓴다 (미트박스·온코크로스 값이 유실되던 버그 수정).
            prior = archived_by_corp.get(item["corp_code"]) or {}
            merged_archive = dict(prior)
            for key, value in item.items():
                if value not in (None, "", [], {}) or key not in merged_archive:
                    merged_archive[key] = value
            archived_by_corp[item["corp_code"]] = merged_archive
        elif not drop:
            # 상장일 정정으로 미래 일정이 되면 이전 이력에서 다시 진행 일정으로 복귀한다.
            archived_by_corp.pop(item["corp_code"], None)
            kept.append(item)

    # manual-* 스텁 정리 — 시드/시트에서 임시 생성된 항목이 진짜 DART corp_code로 파싱되면
    # 같은 이름의 스텁은 중복이므로 제거한다(스텁의 listing_date는 백필 실행일로 오염돼 있어
    # 남기면 잘못된 상장일이 노출됨). 이름이 빈 스텁도 정리한다.
    real_names = {
        _norm_name(i.get("name") or "")
        for i in list(kept) + list(archived_by_corp.values())
        if not str(i.get("corp_code") or "").startswith("manual-")
    }

    def _is_stale_stub(entry: dict[str, Any]) -> bool:
        if not str(entry.get("corp_code") or "").startswith("manual-"):
            return False
        nm = _norm_name(entry.get("name") or "")
        return not nm or nm in real_names

    stub_removed = 0
    for code, entry in list(archived_by_corp.items()):
        if _is_stale_stub(entry):
            archived_by_corp.pop(code, None)
            stub_removed += 1
    before_kept = len(kept)
    kept = [i for i in kept if not _is_stale_stub(i)]
    stub_removed += before_kept - len(kept)
    if stub_removed:
        log(f"manual 스텁 정리: {stub_removed}건 (진짜 corp_code 항목과 중복/빈 이름)")

    kept.sort(key=lambda i: (i.get("sub_start") or "9999", i.get("name") or ""))
    past_items = sorted(
        archived_by_corp.values(),
        key=lambda i: (i.get("listing_date") or "", i.get("name") or ""),
        reverse=True,
    )
    result = {
        "updated": now_kst.strftime("%Y-%m-%d %H:%M"),
        "items": kept,
        "past_items": past_items,
        "history": history[-500:],
        "seed_pending": seed_pending,
        "deleted_corps": deleted_corps,
        "fixed_exclusions": fixed_exclusions,
    }
    SCHEDULE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCHEDULE_PATH.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    log(f"저장: 진행 {len(kept)}종목 / 이전 이력 {len(past_items)}종목 → {SCHEDULE_PATH.name}")
    return result


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="IPO 일정 데이터 갱신 (DART C001 스트림)")
    parser.add_argument("--days", type=int, default=LOOKBACK_DAYS, help="발굴 창(일)")
    parser.add_argument("--backfill-all", action="store_true", help="배치당 상한 없이 미채움 백필 전량 처리")
    args = parser.parse_args()
    result = refresh_ipo_schedule(days_back=args.days, backfill_all=args.backfill_all)
    for item in result["items"]:
        print(
            f"{item.get('name','?'):<12} {item.get('market','?'):<4} "
            f"밴드 {item.get('band_low',0):,}~{item.get('band_high',0):,} 확정 {item.get('final_price',0):,} "
            f"수요예측 {item.get('forecast_start','미정')} 청약 {item.get('sub_start','미정')} "
            f"상장 {item.get('listing_date') or '미정'} 주관 {item.get('underwriter') or '미정'}"
        )


if __name__ == "__main__":
    main()
