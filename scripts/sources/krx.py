from __future__ import annotations

from datetime import datetime, timedelta
import re
import time
from zoneinfo import ZoneInfo
import requests

from scripts.config import KRX_HEADERS, KRX_URLS

KRX_BASE_INFO_URLS = [
    ("https://data-dbg.krx.co.kr/svc/apis/sto/stk_isu_base_info", "코스피"),
    ("https://data-dbg.krx.co.kr/svc/apis/sto/ksq_isu_base_info", "코스닥"),
]


def _to_int(value: object) -> int:
    return int(re.sub(r"[^\d]", "", str(value or "0")) or 0)


def krx_base_info(bas_dd: str) -> dict[str, dict] | None:
    """종목기본정보 {code: {name, market, list_dd(YYYY-MM-DD), shrs, secugrp}}. 휴장일이면 None.

    시세 스냅샷과 달리 상장일(LIST_DD)을 직접 준다 — first-appearance 추정 대신 실제 상장일 기록.
    단 이것도 T-1이라 당일 아침엔 당일 상장 종목이 없다(저녁 배치가 필요한 이유).
    """
    out: dict[str, dict] = {}
    empty = True
    for url, market in KRX_BASE_INFO_URLS:
        try:
            res = requests.post(url, headers=KRX_HEADERS, json={"basDd": bas_dd}, timeout=30)
            items = res.json().get("OutBlock_1", [])
        except Exception:
            items = []
        if items:
            empty = False
        for it in items:
            code = str(it.get("ISU_SRT_CD", "")).strip()  # 단축코드 6자리
            name = (it.get("ISU_NM") or "").strip()
            if not code or not name:
                continue
            raw_dd = re.sub(r"[^\d]", "", str(it.get("LIST_DD") or ""))
            list_dd = f"{raw_dd[:4]}-{raw_dd[4:6]}-{raw_dd[6:8]}" if len(raw_dd) == 8 else ""
            out[code] = {
                "name": name,
                "market": (it.get("MKT_TP_NM") or market).strip(),
                "list_dd": list_dd,
                "shrs": _to_int(it.get("LIST_SHRS")),
                "secugrp": (it.get("SECUGRP_NM") or "").strip(),
            }
        time.sleep(0.15)
    return None if empty else out


def latest_base_info(lookback_days: int = 10) -> tuple[str | None, dict[str, dict]]:
    """최근 거래일의 종목기본정보 마스터. (기준일, {code: info}). 없으면 (None, {})."""
    today = datetime.now(ZoneInfo("Asia/Seoul"))
    for back in range(lookback_days + 1):
        bas_dd = (today - timedelta(days=back)).strftime("%Y%m%d")
        info = krx_base_info(bas_dd)
        if info:
            return f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:8]}", info
    return None, {}


def krx_snapshot(bas_dd: str) -> dict[str, dict] | None:
    """{code: {name, market, shrs, close_price, market_cap}}. 휴장일이면 None."""
    out: dict[str, dict] = {}
    empty = True
    for url, market in KRX_URLS:
        try:
            res = requests.post(url, headers=KRX_HEADERS, json={"basDd": bas_dd}, timeout=30)
            res.raise_for_status()
            payload = res.json()
            items = payload.get("OutBlock_1", []) if isinstance(payload, dict) else []
        except (requests.RequestException, ValueError):
            # KRX occasionally returns an empty or non-JSON response. Treat that
            # market as unavailable so a transient response does not abort the
            # entire scheduled build; the lookback caller can try another date.
            items = []
        if items:
            empty = False
        for it in items:
            code = str(it.get("ISU_CD", "")).strip()
            name = (it.get("ISU_NM") or "").strip()
            if not code or not name:
                continue
            out[code] = {
                "name": name,
                "market": market,
                "shrs": _to_int(it.get("LIST_SHRS")),
                "close_price": _to_int(it.get("TDD_CLSPRC")),
                "market_cap": _to_int(it.get("MKTCAP")),
            }
        time.sleep(0.15)
    return None if empty else out


def find_stock_by_name(name: str, lookback_days: int = 10) -> tuple[str | None, dict | None, str | None]:
    today = datetime.now(ZoneInfo("Asia/Seoul"))
    for back in range(lookback_days + 1):
        bas_dd = (today - timedelta(days=back)).strftime("%Y%m%d")
        snap = krx_snapshot(bas_dd)
        if not snap:
            continue
        for code, meta in snap.items():
            if meta.get("name") == name:
                return code, meta, bas_dd
    return None, None, None


def is_common_ipo_candidate(code: str, name: str) -> bool:
    """보통주 + 스팩·리츠 제외. 주의: isdigit() 금지. 영문 혼용 코드 존재."""
    return len(code) == 6 and code[-1] == "0" and not any(k in name for k in ("스팩", "리츠"))
