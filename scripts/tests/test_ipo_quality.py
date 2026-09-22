import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import Mock, patch

from scripts.ipo_quality import PERIODS, quality_gaps, security_type, tier_quantity
from scripts.sources.dart_api import holder_snapshot, _holder_period
from scripts.sources.ipo_schedule import _application_tiers, _allocation_tiers, _is_confirmed_ipo, parse_offering_doc
from scripts.sources.listing_dates import dart_listing_candidates, reconcile_listing_date
from scripts.sheets_sync import verify_institution_sheet, IPO_INSTITUTION_HEADERS
from scripts.sheets_sync import push_simple_event_tabs
from scripts.audit_ipo_quality import retry_targets, refresh_result, merge_tiers
from scripts.ipo_quality import result_waiting
from scripts.sources.dart_api import get_reports
from scripts.sources.dart_api import select_latest_investment_report, merge_holder_snapshot
from scripts.ipo_quality import holder_review_note
from scripts.sources import ipo_schedule


def application_table(total="100", total_subheaders=True):
    header = '<TR><TH ROWSPAN="2">구분</TH><TH COLSPAN="3">국내</TH><TH COLSPAN="3"' + ('>' if total_subheaders else ' ROWSPAN="2">') + '합 계</TH></TR>'
    header += '<TR><TH>건수</TH><TH>수량</TH><TH>신청가격</TH>' + ('<TH>건수</TH><TH>수량</TH><TH>신청가격</TH>' if total_subheaders else '') + '</TR>'
    rows = []
    for period, qty in (("6개월 확약", "10"), ("3개월 확약", "20"), ("1개월 확약", "30"), ("15일 확약", "-"), ("미확약", "40"), ("합 계", total)):
        rows.append(f'<TR><TD>{period}</TD><TD>2</TD><TD>{qty}</TD><TD>8500</TD><TD>2</TD><TD>{qty}</TD><TD>-</TD></TR>')
    return '<TABLE>' + header + ''.join(rows) + '</TABLE>'


HOLDER = '''<TABLE>
<TR><TH ROWSPAN="2">주주명</TH><TH COLSPAN="2">매각제한물량</TH><TH COLSPAN="2">유통가능물량</TH><TH ROWSPAN="2">매각제한기간</TH></TR>
<TR><TH>주식수</TH><TH>지분율</TH><TH>주식수</TH><TH>지분율</TH></TR>
<TR><TD ROWSPAN="2">투자자</TD><TD>100</TD><TD>10%</TD><TD ROWSPAN="2">900</TD><TD ROWSPAN="2">90%</TD><TD>1개월</TD></TR>
<TR><TD>200</TD><TD>20%</TD><TD>2개월</TD></TR>
<TR><TD>합계</TD><TD>300</TD><TD>30%</TD><TD>900</TD><TD>90%</TD><TD>-</TD></TR>
</TABLE>'''


class IpoQualityTests(unittest.TestCase):
    def test_review_explains_partial_correction_and_exact_difference(self):
        partial = holder_snapshot("위 정정사항외에 모든 사항은 2026년 02월 04일자로 당사가 제출한 신고서와 동일하오니 이를 참고하시기 바랍니다.", "123")
        self.assertEqual(partial["referenced_filing_date"], "2026-02-04")
        self.assertIn("2026-02-04", holder_review_note({"holder_lockup": partial}))
        bad = holder_snapshot(HOLDER.replace('300', '301'), "2")
        self.assertIn("차이 +1주", holder_review_note({"holder_lockup": bad}))

    def test_latest_registration_correction_beats_older_prospectus(self):
        older = {"rcept_no": "20260901000001", "rcept_dt": "20260901", "report_nm": "투자설명서"}
        newer = {"rcept_no": "20260920000001", "rcept_dt": "20260920", "report_nm": "[기재정정]증권신고서(지분증권)"}
        self.assertEqual(select_latest_investment_report([older, newer]), newer)
        excluded = [dict(newer, rcept_no="20260922000001", rcept_dt="20260922", report_nm=title)
                    for title in ("[첨부정정]증권신고서(지분증권)", "증권발행실적보고서", "증권신고서(채무증권)", "간이투자설명서")]
        self.assertEqual(select_latest_investment_report(excluded + [newer, older]), newer)

    def test_full_distribution_not_replaced_by_later_shareholder_subset(self):
        full = HOLDER.replace('매각제한물량', '공모 후 매각제한물량')
        subset = HOLDER.replace('300', '301')
        self.assertEqual(holder_snapshot(full + subset, "1")["total"], 300)
        self.assertEqual(holder_snapshot(full + full.replace('300', '301'), "1")["status"], "review")

    def test_total_label_and_unknown_period_are_validated(self):
        self.assertEqual(holder_snapshot(HOLDER.replace('합계', '총 계'), "1")["total"], 300)
        unknown = holder_snapshot(HOLDER.replace('2개월', '주7)'), "1")
        self.assertEqual(unknown["status"], "review")
        self.assertEqual(unknown["unresolved"][0]["qty"], 200)
        deposited = holder_snapshot(HOLDER.replace('2개월', '예탁일로부터 2개월'), "1")
        self.assertEqual(deposited["status"], "review")

    def test_failed_correction_retains_last_verified_without_hiding_review(self):
        old = holder_snapshot(HOLDER, "1")
        bad = holder_snapshot(HOLDER.replace('300', '301'), "2")
        merged = merge_holder_snapshot(old, bad)
        self.assertEqual(merged["status"], "review")
        self.assertEqual(merged["last_verified"]["total"], 300)
        self.assertEqual(merge_holder_snapshot(merged, bad)["last_verified"], old)
        self.assertNotIn("last_verified", merge_holder_snapshot(merged, old))

    def test_full_refresh_keeps_holder_source_across_result_reports(self):
        offering = {"corp_code": "12345678", "corp_name": "Fixture", "corp_cls": "E",
                    "rcept_no": "20260901000100", "rcept_dt": "20260901", "report_nm": "투자설명서"}
        result = dict(offering, rcept_no="20260921000100", rcept_dt="20260921", report_nm="증권발행실적보고서")
        state = {"items": [], "past_items": []}
        fields = {"market": "코스닥", "band_low": 1000, "band_high": 2000, "offer_shares": 100,
                  "underwriter": "Fixture", "forecast_start": "2030-01-01", "forecast_end": "2030-01-02",
                  "sub_start": "2030-01-03", "sub_end": "2030-01-04", "final_price": 1500}
        with tempfile.TemporaryDirectory() as temp, ExitStack() as stack:
            stack.enter_context(patch.object(ipo_schedule, "SCHEDULE_PATH", Path(temp) / "schedule.json"))
            stack.enter_context(patch.object(ipo_schedule, "MANAGEMENT_PATH", Path(temp) / "absent.json"))
            stack.enter_context(patch.object(ipo_schedule, "load_state", side_effect=lambda: state))
            filings = stack.enter_context(patch.object(ipo_schedule, "fetch_equity_filings", return_value=[result, offering]))
            stack.enter_context(patch.object(ipo_schedule, "load_listing_map", return_value={}))
            stack.enter_context(patch.object(ipo_schedule, "seed_new_items", return_value=[]))
            stack.enter_context(patch.object(ipo_schedule, "_should_fetch_result_report", return_value=False))
            stack.enter_context(patch.object(ipo_schedule, "parse_offering_doc", return_value=fields))
            download = stack.enter_context(patch.object(ipo_schedule, "download_document_text",
                side_effect=lambda receipt: HOLDER if receipt == offering["rcept_no"] else "result report"))
            state = ipo_schedule.refresh_ipo_schedule(verbose=False)
            snap = state["items"][0]["holder_lockup"]
            self.assertEqual((snap["status"], snap["total"], snap["rcept_no"]), ("verified", 300, offering["rcept_no"]))
            # A subsequent batch with a new result receipt must not erase the holder table.
            filings.return_value = [dict(result, rcept_no="20260922000100", rcept_dt="20260922"), offering]
            state = ipo_schedule.refresh_ipo_schedule(verbose=False)
            self.assertEqual(state["items"][0]["holder_lockup"], snap)
            self.assertIn(unittest.mock.call(offering["rcept_no"]), download.call_args_list)

    def test_holder_source_never_falls_back_from_invalid_correction(self):
        filings = [{"rcept_no": "2", "report_nm": "[기재정정]투자설명서"},
                   {"rcept_no": "1", "report_nm": "투자설명서"}]
        snapshot = ipo_schedule._holder_from_offering_filings(filings, {"2": HOLDER.replace("300", "301"), "1": HOLDER})
        self.assertEqual(snapshot["status"], "review")
        self.assertEqual(snapshot["rcept_no"], "2")

    def test_result_only_list_does_not_supply_a_holder_snapshot(self):
        with patch.object(ipo_schedule, "download_document_text") as download:
            self.assertIsNone(ipo_schedule._holder_from_offering_filings(
                [{"rcept_no": "2", "report_nm": "증권발행실적보고서"}], {}))
            download.assert_not_called()

    def test_holder_source_failure_is_visible_even_with_verified_values(self):
        gaps = quality_gaps({"holder_source_error": "timeout", "holder_lockup": {
            "status": "verified", "total": 100, "rows": [{"period": "1개월", "qty": 100}]}}, today="2026-09-22")
        self.assertIn("구주물량 원문 조회 실패", gaps)

    def test_allocation_without_suffix_and_absent_period(self):
        table = '<TABLE><TR><TH ROWSPAN="2">확약기간</TH><TH COLSPAN="2">합계</TH></TR><TR><TH>수량</TH><TH>비중</TH></TR>'
        for period, qty in (("6개월", 19030), ("3개월", 153735), ("1개월", 20717), ("미확약", 1081518), ("계", 1275000)):
            table += f'<TR><TD>{period}</TD><TD>{qty}</TD><TD>0.01</TD></TR>'
        table += '</TABLE>'
        tiers = {r['period']: r for r in _allocation_tiers(table)}
        self.assertEqual(tiers['미확약']['qty'], 1081518)
        self.assertIsNone(tier_quantity(tiers['15일']))
        self.assertEqual(_allocation_tiers(table.replace('1275000', '1275001')), [])

    def test_disclosure_api_error_is_not_no_filing(self):
        response = Mock()
        with patch("scripts.sources.dart_api.DART_API_KEY", "test"), patch("scripts.sources.dart_api.requests.get", return_value=response):
            response.json.return_value = {"status": "020"}
            with self.assertRaises(RuntimeError):
                get_reports("123")
            response.json.return_value = {"status": "013"}
            self.assertEqual(get_reports("123"), [])

    def test_waiting_and_parser_failure_are_distinct(self):
        item = {"sub_end": "2026-09-20"}
        refresh_result(item, [], "2026-09-22")
        self.assertTrue(result_waiting(item, "2026-09-22"))
        self.assertFalse(result_waiting(item, "2026-09-24"))
        self.assertIn("공시 대기: 개인청약경쟁률", quality_gaps(item, today="2026-09-22"))
        with patch("scripts.audit_ipo_quality.download_document_text", return_value="missing table"):
            refresh_result(item, [{"rcept_no": "123", "rcept_dt": "20260921", "report_nm": "증권발행실적보고서"}], "2026-09-22")
        self.assertEqual(item["result_source_check"]["status"], "parse_incomplete")
        self.assertFalse(result_waiting(item, "2026-09-22"))

    def test_bounded_retry_does_not_starve_recently_listed_or_failed(self):
        items = [{"corp_code": "1", "listing_date": "2026-09-21", "quality_attempted_at": "2026-09-21"},
                 {"corp_code": "2", "listing_date": "2026-10-01", "quality_attempted_at": "2026-09-22"},
                 {"corp_code": "3", "listing_date": "2025-01-01", "result_source_check": {"status": "parse_incomplete"}}]
        self.assertEqual([i["corp_code"] for i in retry_targets(items, "2026-09-22")], ["3", "1"])

    def test_repair_preserves_fixed_manual_quantities(self):
        item = {"manual_commit_alloc": {"1개월": {"qty": 123, "locked": True}}}
        merge_tiers(item, "commit_alloc", [{"period": "1개월", "qty": 999}], "receipt")
        self.assertEqual(item["commit_alloc"][0]["qty"], 123)
        self.assertEqual(item["commit_alloc"][0]["source"], "manual_fixed")

    def test_null_zero_invalid_are_distinct(self):
        for v in (None, "", -1, "NaN", "12.5", True):
            self.assertIsNone(tier_quantity({"qty": v}))
        self.assertEqual(tier_quantity({"qty": 0}), 0)
        self.assertIsNone(tier_quantity({"qty": 0, "source": "zero_missing"}))

    def test_application_whitespace_and_total(self):
        tiers = _application_tiers(application_table())
        self.assertEqual(sum(t["qty"] for t in tiers), 100)
        self.assertEqual(tier_quantity(tiers[3]), 0)
        self.assertEqual(_application_tiers(application_table("101")), [])

    def test_split_application_header(self):
        tiers = _application_tiers(application_table(total_subheaders=False))
        self.assertEqual(sum(t["qty"] for t in tiers), 100)

    def test_holder_column_and_rowspan(self):
        snap = holder_snapshot(HOLDER, "123")
        self.assertEqual(snap["status"], "verified")
        self.assertEqual(snap["total"], 300)
        self.assertEqual([r["qty"] for r in snap["rows"]], [100, 200])

    def test_holder_bad_total_not_published(self):
        self.assertEqual(holder_snapshot(HOLDER.replace('<TD>300</TD>', '<TD>301</TD>'), "123")["status"], "review")
        corrected = HOLDER + HOLDER.replace('<TD>300</TD>', '<TD>301</TD>')
        self.assertEqual(holder_snapshot(corrected, "123")["status"], "review")

    def test_footnotes_are_not_shareholder_tables(self):
        notes = '<TABLE><TR><TD>주주명부 기준</TD></TR><TR><TD>주1)</TD><TD>주주는 26조에 따라 3년 의무보유</TD></TR><TR><TD>주2)</TD><TD>주주는 26조에 따라 1년 의무보유</TD></TR><TR><TD>주3)</TD><TD>26조 의무보유</TD></TR></TABLE>'
        self.assertEqual(holder_snapshot(HOLDER + notes, "123")["total"], 300)

    def test_holder_compound_period(self):
        self.assertEqual(_holder_period("상장일로부터 2년 6개월"), "30개월")

    def test_non_equity_classification_uses_identity(self):
        self.assertEqual(security_type("[정정]증권신고서(투자계약증권)"), "non_equity")
        self.assertEqual(security_type("증권신고서(지분증권)", "사업위험: 투자계약증권 시장 침체"), "equity")
        self.assertEqual(parse_offering_doc("증권의 종류: 투자계약증권 상장예비심사")['is_listing_ipo'], False)
        self.assertEqual(security_type("투자설명서", "투자설명서 가축투자계약증권 제9호: 18,166주 1. 증권신고의 효력발생일"), "non_equity")

    def test_konex_transfer_is_preserved(self):
        self.assertFalse(_is_confirmed_ipo({"market": "코넥스", "is_listing_ipo": True}))
        self.assertFalse(_is_confirmed_ipo({"market": "코스닥", "security_type": "non_equity", "forecast_start": "2026-01-01"}))
        self.assertTrue(_is_confirmed_ipo({"market": "코스닥", "issuer_market": "코넥스", "transfer_market": "코스닥", "band_low": 1000, "band_high": 2000, "forecast_start": "2026-01-01", "forecast_end": "2026-01-02", "sub_start": "2026-01-03", "sub_end": "2026-01-04", "offer_shares": 10000, "underwriter": "증권사"}))

    def test_stage_aware_gaps_ignore_listing_date_gate(self):
        item = {"forecast_end": "2026-09-01", "sub_end": "2026-09-10", "review_pending": True}
        gaps = quality_gaps(item, today="2026-09-20")
        self.assertIn("상장일 미정", gaps)
        self.assertTrue(any(g.startswith("확약신청") for g in gaps))
        self.assertIn("구주물량", gaps)
        early = quality_gaps({"forecast_end": "2026-10-01"}, today="2026-09-20")
        self.assertFalse(any(g.startswith("확약") for g in early))

    def test_missing_one_tier_is_not_complete(self):
        item = {"report_rcp": "123", "commit_apply": [{"period": p, "qty": 0} for p in PERIODS[:-1]]}
        self.assertTrue(any("6개월" in g for g in quality_gaps(item)))

    def test_listing_candidates_never_overwrite_manual_date(self):
        item = {"listing_date": "2026-10-01", "manual_fields": ["listing_date"]}
        candidates = dart_listing_candidates("상장예정일: 2026년 10월 2일", "123")
        self.assertEqual(reconcile_listing_date(item, candidates)["status"], "conflict")
        self.assertEqual(item["listing_date"], "2026-10-01")

    def test_sheet_readback_zero_missing_mismatch(self):
        headers = IPO_INSTITUTION_HEADERS
        row = [""] * len(headers)
        row[headers.index("이벤트ID")] = "event-1"
        row[headers.index("신청물량")] = 0
        worksheet = Mock()
        with tempfile.TemporaryDirectory() as temp, patch("scripts.sheets_sync.ROOT_DIR", Path(temp)):
            (Path(temp) / "data").mkdir()
            worksheet.get_all_values.return_value = [headers, [str(v) for v in row]]
            verify_institution_sheet(worksheet, headers, [row])
            actual = [str(v) for v in row]
            actual[headers.index("신청물량")] = ""
            worksheet.get_all_values.return_value = [headers, actual]
            with self.assertRaises(RuntimeError):
                verify_institution_sheet(worksheet, headers, [row])
            worksheet.batch_update.assert_called_once()

    def test_sheet_projection_warns_missing_application_and_includes_prelisting_holders(self):
        item = {"name": "테스트기업", "corp_code": "00123456", "stock_code": "", "listing_date": "2030-01-01",
                "demand_ratio": 100, "commit_alloc": [{"period": "1개월", "qty": 100}],
                "holder_lockup": {"status": "verified", "rcept_no": "123", "total": 300, "rows": [{"period": "3개월", "qty": 300}]}}
        captured = {}
        def capture(_sheet, title, headers, rows, *args):
            captured[title] = [dict(zip(headers, r)) for r in rows]
            return Mock()
        with tempfile.TemporaryDirectory() as temp, \
                patch("scripts.sheets_sync.read_schedule_data", return_value={"items": [item]}), \
                patch("scripts.sheets_sync.read_csv_dicts", return_value=[]), \
                patch("scripts.sheets_sync.read_json_list", return_value=[]), \
                patch("scripts.sheets_sync.load_simple_sheet_state", return_value={}), \
                patch("scripts.sheets_sync.SIMPLE_SHEET_STATE_PATH", Path(temp) / "state.json"), \
                patch("scripts.sheets_sync._push_simple_table", side_effect=capture):
            push_simple_event_tabs(Mock())
        self.assertEqual(captured["IPO기관"][0]["검증상태"], "확인필요")
        self.assertEqual(captured["IPO기관"][0]["신청물량"], "")
        self.assertEqual(captured["기존주주"][0]["물량"], 300)
        self.assertEqual(captured["기존주주"][0]["DART기업코드"], "00123456")


if __name__ == "__main__":
    unittest.main()
