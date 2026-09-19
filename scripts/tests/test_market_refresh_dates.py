import unittest
from datetime import date
from unittest.mock import Mock

from scripts.update_value_chain_market_cache import find_anchor_date, latest_cached_date, period_start, build_company_market_series
from scripts.update_trade_dram import default_end_month


def cache(*dates):
    return {"issues": [{"companies": [{"week": {
        "tradingValueIndex": [{"date": value} for value in dates]
    }}]}]}


class RefreshDateTests(unittest.TestCase):
    def test_labels_do_not_hide_real_cached_dates(self):
        self.assertEqual(latest_cached_date(cache("current", None, "2026-09-16", "2026-09-17")), date(2026, 9, 17))

    def test_recent_cache_does_not_skip_new_snapshot(self):
        snapshot = Mock(return_value={"005930": {"close_price": 1}})
        self.assertEqual(find_anchor_date(snapshot, cache("2026-09-17"), today=date(2026, 9, 19)), date(2026, 9, 18))
        snapshot.assert_called_once_with("20260918")

    def test_missing_new_snapshot_falls_back_without_requerying_cache(self):
        snapshot = Mock(return_value={})
        self.assertEqual(find_anchor_date(snapshot, cache("2026-09-17"), today=date(2026, 9, 19)), date(2026, 9, 17))
        snapshot.assert_called_once_with("20260918")

    def test_future_cache_is_not_used(self):
        with self.assertRaises(RuntimeError):
            find_anchor_date(lambda _: {}, cache("2027-01-01"), lookback_days=1, today=date(2026, 9, 19))

    def test_no_valid_cache(self):
        self.assertIsNone(latest_cached_date(cache("current", "invalid")))

    def test_customs_publication_window(self):
        self.assertEqual(default_end_month(date(2026, 9, 15)), "2026-07")
        self.assertEqual(default_end_month(date(2026, 9, 16)), "2026-08")
        self.assertEqual(default_end_month(date(2026, 1, 16)), "2025-12")
        self.assertEqual(default_end_month(date(2026, 1, 1)), "2025-11")

    def test_calendar_month_boundaries(self):
        self.assertEqual(period_start(date(2026, 3, 31), "month"), date(2026, 2, 28))
        self.assertEqual(period_start(date(2026, 9, 18), "half"), date(2026, 3, 18))

    def test_short_history_is_not_a_six_month_return(self):
        days = [("2026-09-17", {"A": {"close_price": 100, "trading_value": 0}}), ("2026-09-18", {"A": {"close_price": 110, "trading_value": 0}})]
        self.assertIsNone(build_company_market_series("A", days, "half")["returnPct"])
        daily = build_company_market_series("A", days, "day")
        self.assertEqual(daily["returnPct"], 10)
        self.assertEqual(daily["tradingValueIndex"][0]["value"], 0)

    def test_new_listing_or_missing_close_does_not_invent_return(self):
        days = [("2026-03-18", {}), ("2026-09-18", {"A": {"close_price": 100}})]
        result = build_company_market_series("A", days, "half")
        self.assertIsNone(result["returnPct"])
        self.assertFalse(result["coverage"]["complete"])
        self.assertEqual(result["tradingValueIndex"], [])

    def test_full_calendar_period_uses_baseline_close(self):
        days = [("2026-03-18", {"A": {"close_price": 100}}), ("2026-09-18", {"A": {"close_price": 120}})]
        self.assertEqual(build_company_market_series("A", days, "half")["returnPct"], 20)


if __name__ == "__main__":
    unittest.main()
