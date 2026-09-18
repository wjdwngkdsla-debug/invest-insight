import unittest
from datetime import date
from unittest.mock import Mock

from scripts.update_value_chain_market_cache import find_anchor_date, latest_cached_date
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


if __name__ == "__main__":
    unittest.main()
