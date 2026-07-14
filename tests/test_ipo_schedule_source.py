from __future__ import annotations

import unittest
import sys
import types


class IpoScheduleResultReportGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if "requests" not in sys.modules:
            requests = types.ModuleType("requests")
            requests.get = None
            requests.post = None
            requests.RequestException = Exception
            sys.modules["requests"] = requests

    def test_result_report_is_checked_on_subscription_end_date(self) -> None:
        from scripts.sources.ipo_schedule import _should_fetch_result_report

        item = {"sub_end": "2026-07-14", "withdrawn": False, "report_rcp": ""}

        self.assertTrue(_should_fetch_result_report(item, "2026-07-14"))

    def test_result_report_waits_until_subscription_end_date(self) -> None:
        from scripts.sources.ipo_schedule import _should_fetch_result_report

        item = {"sub_end": "2026-07-15", "withdrawn": False, "report_rcp": ""}

        self.assertFalse(_should_fetch_result_report(item, "2026-07-14"))

    def test_existing_result_report_is_not_fetched_again(self) -> None:
        from scripts.sources.ipo_schedule import _should_fetch_result_report

        item = {
            "sub_end": "2026-07-14",
            "withdrawn": False,
            "report_rcp": "20260714000001",
        }

        self.assertFalse(_should_fetch_result_report(item, "2026-07-14"))


if __name__ == "__main__":
    unittest.main()
