import sys
import types
import unittest


if "gspread" not in sys.modules:
    try:
        import gspread  # noqa: F401
    except ModuleNotFoundError:
        gspread_stub = types.ModuleType("gspread")
        gspread_stub.Spreadsheet = object
        gspread_stub.Worksheet = object
        gspread_stub.WorksheetNotFound = type("WorksheetNotFound", (Exception,), {})
        gspread_stub.service_account_from_dict = lambda *_args, **_kwargs: None
        gspread_stub.service_account = lambda *_args, **_kwargs: None
        gspread_utils_stub = types.ModuleType("gspread.utils")
        gspread_utils_stub.rowcol_to_a1 = lambda row, column: f"R{row}C{column}"
        sys.modules["gspread"] = gspread_stub
        sys.modules["gspread.utils"] = gspread_utils_stub


from scripts.sheets_sync import (
    OBSOLETE_TABS,
    _review_fill_gaps,
    cleanup_obsolete_tabs,
    _review_pending_ranges,
)


class _Worksheet:
    def __init__(self, title: str):
        self.title = title


class _Spreadsheet:
    def __init__(self, titles: list[str]):
        self._worksheets = [_Worksheet(title) for title in titles]
        self.deleted: list[str] = []

    def worksheets(self):
        return list(self._worksheets)

    def del_worksheet(self, worksheet):
        self.deleted.append(worksheet.title)
        self._worksheets.remove(worksheet)


class SheetTabCleanupTest(unittest.TestCase):
    def test_removes_only_known_legacy_tabs(self):
        retained = [
            "종목관리", "IPO일정", "IPO기관", "기존주주", "휴장일", "로그",
        ]
        spreadsheet = _Spreadsheet(retained + list(OBSOLETE_TABS) + ["개인메모"])

        removed = cleanup_obsolete_tabs(spreadsheet)

        self.assertEqual(removed, list(OBSOLETE_TABS))
        self.assertEqual(spreadsheet.deleted, list(OBSOLETE_TABS))
        self.assertEqual(
            [worksheet.title for worksheet in spreadsheet.worksheets()],
            retained + ["개인메모"],
        )

    def test_review_pending_ranges_are_grouped_for_formatting(self):
        rows = [
            {"management_status": "자동"},
            {"management_status": "검토대기"},
            {"management_status": "검토대기"},
            {"management_status": "수동편입"},
            {"management_status": "검토대기"},
        ]

        self.assertEqual(_review_pending_ranges(rows), [(1, 3), (4, 5)])

    def test_all_application_tiers_below_allocation_appear_in_review_tab(self):
        periods = ["미확약", "15일", "1개월", "3개월", "6개월"]
        item = {
            "market": "코스닥",
            "final_price": 10000,
            "band_low": 9000,
            "band_high": 11000,
            "offer_shares": 1_000_000,
            "underwriter": "테스트증권",
            "forecast_start": "2026-01-01",
            "forecast_end": "2026-01-02",
            "sub_start": "2026-01-10",
            "sub_end": "2026-01-11",
            "demand_ratio": 100,
            "sub_ratio": 500,
            "commit_apply": [{"period": period, "qty": index + 1} for index, period in enumerate(periods)],
            "commit_alloc": [{"period": period, "qty": 100 + index} for index, period in enumerate(periods)],
        }

        self.assertIn(
            "확약신청 오류(신청건수 오인 의심)",
            _review_fill_gaps(item, has_float_rows=True),
        )


if __name__ == "__main__":
    unittest.main()
