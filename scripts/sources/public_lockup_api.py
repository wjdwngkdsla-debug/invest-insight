from __future__ import annotations

from datetime import datetime
import re
import requests

from scripts.config import DATA_GO_KR_API_KEY, PUBLIC_LOCKUP_API_URL
from scripts.utils.dates import calc_release_date, parse_date, release_display


def _to_int(value: object) -> int | None:
    if value is None:
        return None
    digits = re.sub(r"[^0-9]", "", str(value))
    return int(digits) if digits else None


def _normalize_date(value: object) -> str | None:
    if not value:
        return None
    digits = re.sub(r"[^0-9]", "", str(value))
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}"
    text = str(value).strip()
    if re.fullmatch(r"20\d{2}-\d{2}-\d{2}", text):
        return text
    return None


def _first_existing(item: dict, keys: list[str]) -> object | None:
    for k in keys:
        if k in item and item.get(k) not in (None, ""):
            return item.get(k)
    return None


def fetch_public_lockup_returns(corp_name: str) -> list[dict]:
    """
    공공데이터포털 의무보호예수반환정보조회 API 호출.
    - DART 계산 이벤트 검증용
    - DART에 잡히지 않은 기존주주/보호예수 반환실적 보완용

    주의: 이 API는 기본적으로 '반환실적' 성격이 강하므로, 신규상장 예정 종목의 미래 기존주주 락업이
    항상 미리 내려온다고 가정하면 안 된다.
    """
    params = {
        "serviceKey": DATA_GO_KR_API_KEY,
        "pageNo": 1,
        "numOfRows": 100,
        "resultType": "json",
        "stckIssuCmpyNm": corp_name,
    }
    res = requests.get(PUBLIC_LOCKUP_API_URL, params=params, timeout=30)

    try:
        data = res.json()
    except Exception:
        return [{
            "corp_name": corp_name,
            "api_status": "error",
            "error": "JSON 응답 아님",
            "raw": res.text[:500],
        }]

    body = data.get("response", {}).get("body", {})
    items = body.get("items") or {}
    if not items:
        return []

    item = items.get("item", [])
    if isinstance(item, dict):
        return [item]
    if isinstance(item, list):
        return item
    return []


def normalize_public_return_item(item: dict) -> dict:
    """공공데이터 API 원자료를 서비스 내부 공통 형태로 정규화한다.

    중요:
    - 반환일자는 rsrnDt가 원천 컬럼이다.
    - 반환주식수는 rsrnStckCnt가 원천 컬럼이다.
    - crno는 법인등록번호 성격의 값이므로 절대 수량으로 쓰면 안 된다.
    """
    date_keys = [
        "rsrnDt",  # 반환일자
        "rtnDt", "retuDt", "rtrnDt", "lockUpRetuDt", "isuRtnDt",
        "lockUpRlsDt", "rlsDt", "returnDt", "returnDate", "basDt",
        "반환일자", "반환일", "반환예정일", "해제일자", "해제일",
    ]
    qty_keys = [
        "rsrnStckCnt",  # 반환주식수
        "rtnStkCnt", "retuStkCnt", "rtrnStkCnt", "lockUpRetuStkCnt", "rtnQty", "isuRtnStkCnt",
        "returnQty", "returnStkCnt", "rlsStkCnt", "rlsQty",
        "반환주식수", "반환수량", "해제주식수", "해제수량",
    ]
    reason_keys = [
        "stckLblHoldRcdNm",  # 보호예수/의무보유 사유 구분
        "rsn", "retuRsn", "lockUpRsn", "lockUpRlsRsn", "rlsRsn", "returnRsn",
        "보호예수사유", "보호예수 사유", "반환사유", "해제사유", "사유",
    ]
    holder_keys = [
        "holderNm", "stkOwnrNm", "ownrNm", "shrholdrNm", "shrhldrNm", "nm", "ownerNm",
        "주주명", "소유자명", "예탁자명", "보유자명", "성명",
    ]
    reg_date_keys = [
        "lkupRegDt",  # 보호예수 등록일
        "lockUpRegDt", "regDt", "depoDt", "deprDt", "entrDt",
        "보호예수등록일", "등록일", "예탁일", "보호예수일",
    ]
    security_keys = ["isinCd", "itmsShrtnCd", "isinCdNm", "isuCd", "scrsItmsNm", "itmsNm", "종목명", "주식명", "증권명"]

    date = _normalize_date(_first_existing(item, date_keys))
    qty = _to_int(_first_existing(item, qty_keys))
    reason_raw = _first_existing(item, reason_keys)
    holder_raw = _first_existing(item, holder_keys)
    reg_date = _normalize_date(_first_existing(item, reg_date_keys))
    security_raw = _first_existing(item, security_keys)

    reason = str(reason_raw).strip() if reason_raw else None
    holder_name = str(holder_raw).strip() if holder_raw else None
    security_name = str(security_raw).strip() if security_raw else None

    # 날짜 key가 예외적으로 없을 때만 값 패턴으로 보완한다.
    if date is None:
        for value in item.values():
            maybe = _normalize_date(value)
            if maybe and re.fullmatch(r"20\d{2}-\d{2}-\d{2}", maybe):
                date = maybe
                break

    # 수량은 반드시 반환주식수 계열 컬럼에서만 가져온다.
    # crno, isinCd 등 코드성 숫자가 섞이면 잘못된 물량이 되므로 fallback max 탐색은 하지 않는다.
    return {
        "company_name": item.get("stckIssuCmpyNm"),
        "stock_code": item.get("itmsShrtnCd"),
        "return_date": date,
        "return_qty": qty,
        "reason": reason,
        "holder_name": holder_name,
        "lockup_reg_date": reg_date,
        "security_name": security_name,
        "listed_shares": _to_int(item.get("lblProtTsumIssuStckCnt")),
        "raw": item,
    }

def _date_close(d1: str | None, d2: str | None, days: int = 1) -> bool:
    if not d1 or not d2:
        return False
    try:
        a = datetime.strptime(d1, "%Y-%m-%d")
        b = datetime.strptime(d2, "%Y-%m-%d")
        return abs((a - b).days) <= days
    except Exception:
        return False


def _is_same_event(event: dict, item: dict) -> bool:
    target_dates = {event.get("tradable_date"), event.get("date")}
    target_qty = int(event.get("qty") or 0)
    rd = item.get("return_date")
    rq = item.get("return_qty")
    if not rd or not rq or not target_qty:
        return False
    if rd in target_dates and rq == target_qty:
        return True
    if any(_date_close(rd, td) for td in target_dates if td):
        return abs(rq - target_qty) / target_qty <= 0.01
    return False


def match_event_with_public_api(event: dict, public_items: list[dict]) -> dict:
    """
    DART 계산 이벤트와 공공데이터 반환실적 비교.
    반환일자 ±1일, 수량 1% 이내를 후보로 본다.
    """
    if not public_items:
        event["api_checked"] = True
        return event

    normalized = [normalize_public_return_item(x) for x in public_items]
    target_dates = {event.get("tradable_date"), event.get("date")}
    target_qty = int(event.get("qty") or 0)

    exact = None
    near = None
    for item in normalized:
        rd = item.get("return_date")
        rq = item.get("return_qty")
        if rd in target_dates and rq == target_qty:
            exact = item
            break
        if any(_date_close(rd, td) for td in target_dates if td) and rq and target_qty:
            diff = abs(rq - target_qty) / target_qty
            if diff <= 0.01:
                near = item

    event["api_checked"] = True
    event["api_source"] = "공공데이터포털 getLockUpRetuInfo_V3"

    if exact:
        event["status"] = "반환확인"
        event["source_label"] = "공공데이터 확인"
        event["api_return_date"] = exact.get("return_date")
        event["api_return_qty"] = exact.get("return_qty")
    elif near:
        event["status"] = "수동확인"
        event["source_label"] = "수동확인 필요"
        event["api_return_date"] = near.get("return_date")
        event["api_return_qty"] = near.get("return_qty")

    return event




def infer_period_from_listing_date(listing_date: str | None, return_date: str | None) -> str:
    """상장일과 API 반환일을 비교해 1개월/3개월 등 기간 라벨을 추정한다.

    API 반환일은 실제 거래가능일 기준으로 들어오는 경우가 있어 calc_release_date의
    계산상 해제일(date)과 실제 거래가능일(tradable_date)을 모두 비교한다.
    """
    if not listing_date or not return_date:
        return "보호예수"
    for period in ["15일", "1개월", "2개월", "3개월", "6개월", "12개월", "1년", "24개월", "2년", "30개월", "36개월", "3년"]:
        try:
            date, _date_display, tradable_date = calc_release_date(listing_date, period)
        except Exception:
            continue
        if return_date in {date, tradable_date}:
            return period
    return "보호예수"

def build_events_from_public_api(public_items: list[dict], shares: int, listing_date: str | None = None) -> list[dict]:
    """공공데이터 API 결과를 독립 보호예수 이벤트로 변환한다."""
    today = datetime.today().strftime("%Y-%m-%d")
    events: list[dict] = []
    for item in [normalize_public_return_item(x) for x in public_items]:
        rd = item.get("return_date")
        qty = item.get("return_qty")
        if not rd or not qty:
            continue
        try:
            display, tradable = release_display(parse_date(rd))
        except Exception:
            display, tradable = rd, parse_date(rd)

        reason = item.get("reason")
        holder_name = item.get("holder_name")
        period = infer_period_from_listing_date(listing_date, rd)

        events.append({
            "period": period,
            "date": rd,
            "date_display": display,
            "tradable_date": tradable.strftime("%Y-%m-%d"),
            "qty": int(qty),
            "pct": round(int(qty) / shares * 100, 2) if shares else 0,
            "type": "보호예수",
            "status": "반환확인" if tradable.strftime("%Y-%m-%d") <= today else "예정",
            "source": "공공데이터포털",
            "source_label": "공공데이터 API",
            "rcp": None,
            "api_checked": True,
            "api_return_date": rd,
            "api_return_qty": int(qty),
            "api_source": "공공데이터포털 getLockUpRetuInfo_V3",
            "holder_name": holder_name,
            "reason": reason,
            "lockup_reg_date": item.get("lockup_reg_date"),
        })
    return events


def merge_public_api_events(events: list[dict], public_items: list[dict], shares: int, listing_date: str | None = None) -> list[dict]:
    """
    1) 기존 DART 이벤트는 API로 검증
    2) DART 이벤트와 매칭되지 않은 API 반환실적은 '보호예수' 이벤트로 추가
    """
    verified = [match_event_with_public_api(ev, public_items) for ev in events]
    normalized = [normalize_public_return_item(x) for x in public_items]

    unmatched_raw: list[dict] = []
    for raw, norm in zip(public_items, normalized):
        if not norm.get("return_date") or not norm.get("return_qty"):
            continue
        if any(_is_same_event(ev, norm) for ev in verified):
            continue
        unmatched_raw.append(raw)

    extra = build_events_from_public_api(unmatched_raw, shares, listing_date)
    return sorted(verified + extra, key=lambda e: e.get("tradable_date", "9999-99-99"))
