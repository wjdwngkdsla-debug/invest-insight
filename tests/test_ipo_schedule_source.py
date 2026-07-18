from __future__ import annotations

import unittest
import sys
import types
from pathlib import Path
from unittest.mock import patch


def ensure_fake_requests() -> None:
    if "requests" not in sys.modules:
        requests = types.ModuleType("requests")
        requests.get = None
        requests.post = None
        requests.RequestException = Exception
        sys.modules["requests"] = requests


class IpoScheduleDemandTableTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ensure_fake_requests()

    def test_multirow_header_and_split_label_are_parsed(self) -> None:
        from scripts.sources.ipo_schedule import _parse_demand_tables

        doc = """
        <TABLE>
          <TR><TD>구분</TD><TD>건수</TD><TD>수량</TD><TD>신청가격</TD></TR>
          <TR><TD>의무보유</TD><TD>합계</TD><TD>수량</TD><TD>가격</TD></TR>
          <TR><TD>6개월</TD><TD>확약</TD><TD>10</TD><TD>600</TD><TD>10000</TD></TR>
          <TR><TD>3개월 확약</TD><TD>20</TD><TD>300</TD><TD>10000</TD></TR>
          <TR><TD>1개월 확약</TD><TD>30</TD><TD>100</TD><TD>10000</TD></TR>
          <TR><TD>미확약</TD><TD>40</TD><TD>1000</TD><TD>10000</TD></TR>
          <TR><TD>합계</TD><TD>100</TD><TD>2000</TD><TD>10000</TD></TR>
        </TABLE>
        """

        _, apply = _parse_demand_tables(doc)

        # 표에 없는 구간(15일)은 0 + zero_missing 표식으로 항상 5구간을 채운다
        self.assertEqual({row["period"]: row["qty"] for row in apply}, {
            "6개월": 600, "3개월": 300, "1개월": 100, "15일": 0, "미확약": 1000,
        })
        self.assertEqual(
            [row["period"] for row in apply if row.get("source") == "zero_missing"],
            ["15일"],
        )


class IpoScheduleResultReportGateTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        ensure_fake_requests()

    def test_result_report_is_checked_on_subscription_end_date(self) -> None:
        from scripts.sources.ipo_schedule import _should_fetch_result_report

        item = {"sub_end": "2026-07-14", "withdrawn": False, "report_rcp": ""}

        self.assertTrue(_should_fetch_result_report(item, "2026-07-14"))

    def test_result_report_waits_until_subscription_end_date(self) -> None:
        from scripts.sources.ipo_schedule import _should_fetch_result_report

        item = {"sub_end": "2026-07-15", "withdrawn": False, "report_rcp": ""}

        self.assertFalse(_should_fetch_result_report(item, "2026-07-14"))

    def test_current_parser_snapshot_is_reused_without_document_download(self) -> None:
        from scripts.sources import ipo_schedule

        item = {
            "corp_code": "00000001", "name": "기존회사", "last_rcept_no": "20260713000001",
            "first_filing_date": "20260701", "is_listing_ipo": True, "forecast_start": "2026-08-01",
            "sub_start": "2026-08-10", "sub_end": "2026-08-11", "withdrawn": False,
            "ipo_parse_version": ipo_schedule.IPO_PARSE_VERSION,
            "band_low": 10000, "band_high": 12000, "final_price": 12000,
            "forecast_end": "2026-08-01", "underwriter": "테스트증권", "market": "코스닥",
            "offer_shares": 1000000, "demand_ratio": 100.0,
            "commit_apply": [{"period": "미확약", "qty": 1}],
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

    def test_unlocked_manual_commit_does_not_replace_existing_official_value(self) -> None:
        from scripts.sources import ipo_schedule

        item = {
            "corp_code": "00000001", "name": "기존회사", "last_rcept_no": "20260713000001",
            "first_filing_date": "20260701", "forecast_start": "2026-08-01",
            "sub_start": "2026-08-10", "sub_end": "2026-08-11", "withdrawn": False,
            "ipo_parse_version": ipo_schedule.IPO_PARSE_VERSION,
            "band_low": 10000, "band_high": 12000, "final_price": 12000,
            "forecast_end": "2026-08-01", "underwriter": "테스트증권", "market": "코스닥",
            "offer_shares": 1000000, "demand_ratio": 100.0,
            "commit_apply": [{"period": "1개월", "qty": 100, "pct": 100.0}],
            "manual_commit_apply": {"1개월": {"qty": 999, "locked": False}},
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
        self.assertEqual(result["items"][0]["commit_apply"][0]["qty"], 100)

    def test_old_parser_snapshot_is_reparsed_once_even_when_receipt_is_same(self) -> None:
        from scripts.sources import ipo_schedule

        item = {
            "corp_code": "00000001", "name": "과거회사", "last_rcept_no": "20260713000001",
            "first_filing_date": "20260701", "is_listing_ipo": True, "forecast_start": "2026-07-01",
            "sub_start": "2026-07-05", "sub_end": "2026-07-06", "listing_date": "2026-07-10",
            "withdrawn": False, "report_rcp": "20260707000001",
        }
        filing = {
            "corp_code": "00000001", "corp_name": "과거회사", "corp_cls": "E",
            "rcept_no": "20260713000001", "rcept_dt": "20260713",
            "report_nm": "[발행조건확정] 증권신고서(지분증권)",
        }
        parsed = {
            "band_low": 10000, "band_high": 12000, "final_price": 12000,
            "forecast_start": "2026-07-01", "forecast_end": "2026-07-02",
            "sub_start": "2026-07-05", "sub_end": "2026-07-06", "underwriter": "테스트증권",
            "commit_apply": [{"period": "미확약", "qty": 1000, "pct": 100.0}],
        }
        state = {"items": [], "past_items": [item], "history": []}
        with (
            patch.object(ipo_schedule, "load_state", return_value=state),
            patch.object(ipo_schedule, "fetch_equity_filings", return_value=[]),
            patch.object(ipo_schedule, "_fetch_corp_filings", return_value=[filing]),
            patch.object(ipo_schedule, "seed_new_items", return_value=[]),
            patch.object(ipo_schedule, "download_document_text", return_value="document") as download,
            patch.object(ipo_schedule, "parse_offering_doc", return_value=parsed),
            patch.object(ipo_schedule, "MANAGEMENT_PATH", Path("/tmp/nonexistent-stock-management.json")),
            patch.object(ipo_schedule, "SCHEDULE_PATH"),
        ):
            result = ipo_schedule.refresh_ipo_schedule(verbose=False)

        download.assert_called_once_with("20260713000001")
        self.assertEqual(result["past_items"][0]["commit_apply"][0]["qty"], 1000)
        self.assertEqual(result["past_items"][0]["ipo_parse_version"], ipo_schedule.IPO_PARSE_VERSION)

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

    def test_krx_snapshot_date_is_not_used_as_listing_date(self) -> None:
        from scripts.sources.ipo_schedule import detect_listings_from_krx

        items = {
            "00366438": {
                "corp_code": "00366438",
                "name": "산일전기",
                "stock_code": "062040",
                "listing_date": "2024-07-29",
            }
        }

        detect_listings_from_krx(
            items,
            {"062040": {"name": "산일전기", "market": "코스피"}},
            "2026-07-14",
            [],
            lambda _msg: None,
        )

        self.assertEqual(items["00366438"]["listing_date"], "2024-07-29")

    def test_krx_base_info_list_dd_can_correct_listing_date(self) -> None:
        from scripts.sources.ipo_schedule import detect_listings_from_krx

        items = {
            "00366438": {
                "corp_code": "00366438",
                "name": "산일전기",
                "stock_code": "062040",
                "listing_date": "2026-07-14",
            }
        }

        detect_listings_from_krx(
            items,
            {"062040": {"name": "산일전기", "market": "코스피"}},
            "2026-07-14",
            [],
            lambda _msg: None,
            base_info={"062040": {"name": "산일전기", "market": "코스피", "list_dd": "2024-07-29"}},
        )

        self.assertEqual(items["00366438"]["listing_date"], "2024-07-29")

    def test_krx_base_info_matches_by_stock_code_before_name(self) -> None:
        from scripts.sources.ipo_schedule import detect_listings_from_krx

        items = {
            "00182696": {
                "corp_code": "00182696",
                "name": "대한조선",
                "stock_code": "439260",
                "listing_date": "2026-07-15",
            }
        }

        detect_listings_from_krx(
            items,
            {},
            "2026-07-16",
            [],
            lambda _msg: None,
            base_info={
                "439260": {
                    "name": "다른표기대한조선",
                    "market": "코스피",
                    "list_dd": "2025-07-25",
                }
            },
        )

        self.assertEqual(items["00182696"]["listing_date"], "2025-07-25")

    def test_missing_offering_fields_force_reparse_even_when_version_is_current(self) -> None:
        from scripts.sources.ipo_schedule import _needs_offering_backfill

        item = {
            "name": "대한조선",
            "ipo_parse_version": 999,
            "band_low": 42000,
            "band_high": 50000,
            "final_price": 50000,
            "forecast_start": "2025-07-08",
            "forecast_end": "2025-07-14",
            "sub_start": "2025-07-22",
            "sub_end": "2025-07-23",
            "underwriter": "대표증권",
            "market": "코스피",
            "offer_shares": 0,
            "demand_ratio": 275.66,
            "commit_apply": [{"period": "미확약", "qty": 1}],
        }

        self.assertTrue(_needs_offering_backfill(item))

    def test_suspicious_listing_date_is_cleared_for_retry(self) -> None:
        from scripts.sources.ipo_schedule import _clear_suspicious_listing_date

        item = {
            "name": "시프트업",
            "listing_date": "2026-07-14",
            "sub_end": "2024-07-03",
            "result_report_missing": True,
        }

        changed = _clear_suspicious_listing_date(item, [], "2026-07-16", lambda _msg: None)

        self.assertTrue(changed)
        self.assertEqual(item["listing_date"], "")
        self.assertNotIn("result_report_missing", item)


if __name__ == "__main__":
    unittest.main()
