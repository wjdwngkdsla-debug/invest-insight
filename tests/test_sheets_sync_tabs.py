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


from scripts.sheets_sync import OBSOLETE_TABS, cleanup_obsolete_tabs


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
            "종목관리", "보정작업", "휴장일", "IPO일정_현황",
            "IPO기관_현황", "기존주주_현황", "정정이력", "변경로그",
        ]
        spreadsheet = _Spreadsheet(retained + list(OBSOLETE_TABS) + ["개인메모"])

        removed = cleanup_obsolete_tabs(spreadsheet)

        self.assertEqual(removed, list(OBSOLETE_TABS))
        self.assertEqual(spreadsheet.deleted, list(OBSOLETE_TABS))
        self.assertEqual(
            [worksheet.title for worksheet in spreadsheet.worksheets()],
            retained + ["개인메모"],
        )


if __name__ == "__main__":
    unittest.main()
