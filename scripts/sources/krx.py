from __future__ import annotations

from datetime import datetime, timedelta
import re
import time
import requests

from scripts.config import KRX_HEADERS, KRX_URLS


def _to_int(value: object) -> int:
    return int(re.sub(r"[^\d]", "", str(value or "0")) or 0)


def krx_snapshot(bas_dd: str) -> dict[str, dict] | None:
    """{code: {name, market, shrs, close_price}}. 휴장일이면 None."""
    out: dict[str, dict] = {}
    empty = True
    for url, market in KRX_URLS:
        res = requests.post(url, headers=KRX_HEADERS, json={"basDd": bas_dd}, timeout=30)
        items = res.json().get("OutBlock_1", [])
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
            }
        time.sleep(0.15)
    return None if empty else out


def find_stock_by_name(name: str, lookback_days: int = 10) -> tuple[str | None, dict | None, str | None]:
    today = datetime.today()
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
