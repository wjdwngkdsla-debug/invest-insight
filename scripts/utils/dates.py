from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

from dateutil.relativedelta import relativedelta

ROOT_DIR = Path(__file__).resolve().parents[2]
HOLIDAYS_PATH = ROOT_DIR / "data" / "holidays.json"

_HOLIDAYS_CACHE: set[str] | None = None


def market_holidays() -> set[str]:
    """거래소 휴장일(YYYY-MM-DD) 집합.

    출처는 Google Sheet의 '휴장일' 탭 — 배치 시작 시 sheets_sync가
    data/holidays.json으로 내려받는다. 운영자가 탭에 추가하면 다음
    배치부터 자동 반영. 파일이 없으면 주말만 보정한다.
    """
    global _HOLIDAYS_CACHE
    if _HOLIDAYS_CACHE is None:
        try:
            _HOLIDAYS_CACHE = set(json.loads(HOLIDAYS_PATH.read_text(encoding="utf-8")))
        except Exception:
            _HOLIDAYS_CACHE = set()
    return _HOLIDAYS_CACHE


CALC = {
    "15일": lambda d: d + timedelta(days=15),
    "1개월": lambda d: d + relativedelta(months=1),
    "2개월": lambda d: d + relativedelta(months=2),
    "3개월": lambda d: d + relativedelta(months=3),
    "6개월": lambda d: d + relativedelta(months=6),
    "12개월": lambda d: d + relativedelta(months=12),
    "1년": lambda d: d + relativedelta(years=1),
    "24개월": lambda d: d + relativedelta(months=24),
    "2년": lambda d: d + relativedelta(years=2),
    "30개월": lambda d: d + relativedelta(months=30),
    "36개월": lambda d: d + relativedelta(months=36),
    "3년": lambda d: d + relativedelta(years=3),
}


def parse_date(date_str: str) -> datetime:
    return datetime.strptime(date_str, "%Y-%m-%d")


def next_trading_day(d: datetime) -> datetime:
    holidays = market_holidays()
    t = d
    while t.weekday() >= 5 or t.strftime("%Y-%m-%d") in holidays:
        t += timedelta(days=1)
    return t


def release_display(d: datetime) -> tuple[str, datetime]:
    """해제일을 주말·휴장일을 반영한 실제 거래 가능일로 표시한다.

    휴장일은 시트 '휴장일' 탭 기준(연 단위 수동 관리), 주말은 자동.
    API 실제 반환일이 확인되면 그 값이 최우선으로 덮는다(build 참고).
    """
    t = next_trading_day(d)
    return t.strftime("%Y-%m-%d"), t


def calc_release_date(listing_date: str, period: str) -> tuple[str, str, str]:
    """반환: date(원본), date_display(거래가능일), tradable_date(거래가능일).

    투자설명서의 유통가능 요약표에는 5년 등 예상하지 못한 기간이 나올 수 있어
    CALC에 없는 "N개월"/"N년"도 일반식으로 처리한다.
    """
    base = parse_date(listing_date)
    if period in CALC:
        raw_date = CALC[period](base)
    else:
        m_month = re.fullmatch(r"(\d+)개월", str(period).strip())
        m_year = re.fullmatch(r"(\d+)년", str(period).strip())
        if m_month:
            raw_date = base + relativedelta(months=int(m_month.group(1)))
        elif m_year:
            raw_date = base + relativedelta(years=int(m_year.group(1)))
        else:
            raise ValueError(f"지원하지 않는 기간입니다: {period}")
    display, tradable = release_display(raw_date)
    return raw_date.strftime("%Y-%m-%d"), display, tradable.strftime("%Y-%m-%d")
