from __future__ import annotations

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

# 임시 휴장일 세트. 한국천문연구원 특일정보 API/거래소 휴장일 연동 전까지 매년 갱신 필요.
# 법정공휴일 외에 근로자의날, 연말 폐장일 등 KRX 휴장일을 별도 추가해야 함.
HOLIDAYS = {
    # 2026 주요 휴장일 예시
    "20260101", "20260216", "20260217", "20260218", "20260302", "20260505",
    "20260525", "20260817", "20260924", "20260925", "20260928", "20261005",
    "20261009", "20261225", "20261231",
    # 2027 예시
    "20270101",
}

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
    t = d
    while t.weekday() >= 5 or t.strftime("%Y%m%d") in HOLIDAYS:
        t += timedelta(days=1)
    return t


def release_display(d: datetime) -> tuple[str, datetime]:
    base = d.strftime("%Y-%m-%d")
    tradable = next_trading_day(d)
    if tradable != d:
        return f"{base} (거래가능 {tradable.strftime('%m-%d')})", tradable
    return base, tradable


def calc_release_date(listing_date: str, period: str) -> tuple[str, str, str]:
    """반환: date, date_display, tradable_date.

    투자설명서의 유통가능 요약표에는 5년 등 예상하지 못한 기간이 나올 수 있어
    CALC에 없는 "N개월"/"N년"도 일반식으로 처리한다.
    """
    base = parse_date(listing_date)
    if period in CALC:
        raw_date = CALC[period](base)
    else:
        import re
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
