"""검토필요 탭을 만드는 경로가 실제 데이터에서 터지지 않는지 본다.

result_waiting()이 result_source_check 기록 없이도 참을 돌려주게 바뀌었는데
메모 문자열은 그 기록이 있다고 가정해, 운영 배치가 사흘 연속
KeyError: 'result_source_check'로 죽었다(run 40461535751).

단위 테스트는 모두 통과했지만 실제 종목 하나를 통과시켜 보지 않아 놓쳤다.
이 테스트는 저장된 데이터 전체를 그 경로에 흘려 본다.
"""

import csv
import json
import unittest
from pathlib import Path

from scripts.ipo_quality import quality_gaps, result_waiting
from scripts.sheets_sync import _result_waiting_note, _split_gaps

ROOT = Path(__file__).resolve().parents[2]


def _items():
    path = ROOT / "data" / "ipo_schedule.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return (data.get("items") or []) + (data.get("past_items") or [])


def _holder_codes():
    path = ROOT / "data" / "lockup_admin.csv"
    if not path.exists():
        return set()
    with path.open(encoding="utf-8-sig", newline="") as fh:
        return {r["code"] for r in csv.DictReader(fh) if r.get("category") == "구주·보호예수"}


class ReviewTabSmoke(unittest.TestCase):
    def test_저장된_모든_종목이_메모_생성을_통과한다(self):
        items = _items()
        self.assertTrue(items, "ipo_schedule.json이 비어 있으면 이 테스트가 무의미하다")
        for item in items:
            with self.subTest(name=item.get("name")):
                _result_waiting_note(item)

    def test_저장된_모든_종목이_갭_분류를_통과한다(self):
        codes = _holder_codes()
        for item in _items():
            with self.subTest(name=item.get("name")):
                todo, waiting = _split_gaps(quality_gaps(item, (item.get("stock_code") or "") in codes))
                self.assertIsInstance(todo, list)
                self.assertIsInstance(waiting, list)

    def test_기록이_없어도_메모가_만들어진다(self):
        # 이 조합이 운영에서 죽은 자리다 — 공시 대기인데 확인 기록이 없다.
        item = {"sub_end": "2026-10-20"}
        self.assertTrue(result_waiting(item, "2026-10-22"))
        self.assertIn("공시 대기", _result_waiting_note(item))

    def test_기록이_있으면_확인_날짜를_쓴다(self):
        item = {"sub_end": "2026-10-20",
                "result_source_check": {"checked_at": "2026-10-21", "status": "waiting"}}
        self.assertIn("2026-10-21", _result_waiting_note(item))

    def test_보고서가_나왔으면_메모가_없다(self):
        self.assertEqual(_result_waiting_note({"sub_end": "2026-10-01", "report_rcp": "1"}), "")


if __name__ == "__main__":
    unittest.main()
