from __future__ import annotations

from datetime import datetime, timedelta
from dateutil.relativedelta import relativedelta

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


def release_display(d: datetime) -> tuple[str, datetime]:
    """해제일을 보정 없이 원본 그대로 표시한다.

    주말/휴장일 → 다음 거래일 보정은 하지 않기로 결정(2026-07-09).
    임시공휴일 등 변수가 많아 수동 휴장일 목록은 유지보수 부담만 크고,
    해제일이 곧 매도일도 아니기 때문. 휴장일 안내는 사이트 푸터 문구로 대체.
    """
    base = d.strftime("%Y-%m-%d")
    return base, d


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
