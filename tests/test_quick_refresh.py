from datetime import datetime
from zoneinfo import ZoneInfo

from scripts.quick_refresh import expected_latest_close_date


KST = ZoneInfo("Asia/Seoul")


def test_expected_close_is_previous_trading_day_before_evening() -> None:
    now = datetime(2026, 9, 8, 10, 30, tzinfo=KST)

    assert expected_latest_close_date(now, holidays=set()) == "2026-09-07"


def test_expected_close_skips_weekend() -> None:
    now = datetime(2026, 9, 7, 10, 30, tzinfo=KST)

    assert expected_latest_close_date(now, holidays=set()) == "2026-09-04"


def test_expected_close_skips_sheet_holiday() -> None:
    now = datetime(2026, 9, 8, 10, 30, tzinfo=KST)

    assert expected_latest_close_date(now, holidays={"2026-09-07"}) == "2026-09-04"
