from __future__ import annotations

import unittest
import sys
import types
from unittest.mock import patch


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

    def test_existing_snapshot_is_reused_without_document_download(self) -> None:
        from scripts.sources import ipo_schedule

        item = {
            "corp_code": "00000001", "name": "기존회사", "last_rcept_no": "20260713000001",
            "first_filing_date": "20260701", "is_listing_ipo": True, "forecast_start": "2026-08-01",
            "sub_start": "2026-08-10", "sub_end": "2026-08-11", "withdrawn": False,
        }
        filing = {
            "corp_code": "00000001", "corp_name": "기존회사", "corp_cls": "E",
            "rcept_no": "20260713000001", "rcept_dt": "20260713", "report_nm": "지분증권 증권신고서",
        }
        with (
            patch.object(ipo_schedule, "load_state", return_value={"items": [item], "past_items": [], "history": []}),
            patch.object(ipo_schedule, "fetch_equity_filings", return_value=[filing]),
            patch.object(ipo_schedule, "seed_new_items", return_value=[]),
            patch.object(ipo_schedule, "download_document_text") as download,
            patch.object(ipo_schedule, "SCHEDULE_PATH"),
        ):
            result = ipo_schedule.refresh_ipo_schedule(verbose=False)

        download.assert_not_called()
        self.assertEqual(result["items"][0]["last_rcept_no"], "20260713000001")

    def test_fixed_exclusion_is_preserved_and_never_reparsed(self) -> None:
        from scripts.sources import ipo_schedule

        item = {
            "corp_code": "00683283", "name": "LS전선", "last_rcept_no": "20251219000079",
            "first_filing_date": "20251219", "fixed_excluded": True, "review_pending": True,
        }
        filing = {
            "corp_code": "00683283", "corp_name": "LS전선", "corp_cls": "E",
            "rcept_no": "20260714000001", "rcept_dt": "20260714", "report_nm": "지분증권 증권신고서",
        }
        state = {
            "items": [item], "past_items": [], "history": [],
            "fixed_exclusions": {"corp:00683283": {"name": "LS전선"}},
        }
        with (
            patch.object(ipo_schedule, "load_state", return_value=state),
            patch.object(ipo_schedule, "fetch_equity_filings", return_value=[filing]),
            patch.object(ipo_schedule, "seed_new_items", return_value=[]),
            patch.object(ipo_schedule, "download_document_text") as download,
            patch.object(ipo_schedule, "SCHEDULE_PATH"),
        ):
            result = ipo_schedule.refresh_ipo_schedule(verbose=False)

        download.assert_not_called()
        self.assertTrue(result["items"][0]["fixed_excluded"])

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
