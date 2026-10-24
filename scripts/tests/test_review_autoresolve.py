"""검토필요 자동 해소 — 일시적 통신 오류가 영원히 쌓이지 않게.

공공데이터포털이 죽은 날 152종목이 통째로 '건너뜀'으로 기록됐는데,
해소 규칙이 공모가·데이터확인 두 종류만 다뤄서 그 144건이 몇 달째
'미해결'로 남아 검토 목록을 덮어 버렸다.
"""

import csv
import tempfile
import unittest
from pathlib import Path

from scripts.build import REVIEW_COLUMNS, _is_transient, merge_review_history

TRANSIENT = ("종목 처리 중 오류로 건너뜀: HTTPSConnectionPool(host='apis.data.go.kr', "
             "port=443): Max retries exceeded")
REAL = "DART 공모가 파싱 실패 — IPO종목 탭의 수동공모가 입력 필요"


class TransientDetection(unittest.TestCase):
    def test_네트워크_오류를_알아본다(self):
        self.assertTrue(_is_transient(TRANSIENT))
        self.assertTrue(_is_transient("Read timed out. (read timeout=30)"))
        self.assertTrue(_is_transient("Connection refused"))

    def test_진짜_문제는_일시적이_아니다(self):
        self.assertFalse(_is_transient(REAL))
        self.assertFalse(_is_transient("상장 후 유통가능 주식수 현황 표 미발견"))
        self.assertFalse(_is_transient(""))


class AutoResolve(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "review_needed.csv"

    def _write(self, rows):
        with self.path.open("w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=REVIEW_COLUMNS)
            w.writeheader()
            for r in rows:
                w.writerow({c: r.get(c, "") for c in REVIEW_COLUMNS})

    def _row(self, rid, issue, status="미해결"):
        return {"review_id": rid, "status": status, "name": "테스트", "code": "000000",
                "review_type": "처리실패", "target": "", "issue": issue,
                "first_detected": "2026-07-10", "last_detected": "2026-07-10"}

    def test_재발하지_않은_통신오류는_해소된다(self):
        self._write([self._row("A-처리실패", TRANSIENT)])
        out = merge_review_history(self.path, [])
        row = next(r for r in out if r["review_id"] == "A-처리실패")
        self.assertEqual(row["status"], "해결")
        self.assertTrue(row["resolved_at"])
        self.assertIn("자동 해소", row["operator_memo"])

    def test_이번에도_잡히면_미해결로_둔다(self):
        self._write([self._row("A-처리실패", TRANSIENT)])
        out = merge_review_history(self.path, [
            {"review_id": "A-처리실패", "name": "테스트", "code": "000000",
             "review_type": "처리실패", "issue": TRANSIENT},
        ])
        row = next(r for r in out if r["review_id"] == "A-처리실패")
        self.assertEqual(row["status"], "미해결")

    def test_진짜_문제는_자동_해소하지_않는다(self):
        self._write([self._row("B-공모가파싱실패", REAL)])
        out = merge_review_history(self.path, [])
        row = next(r for r in out if r["review_id"] == "B-공모가파싱실패")
        self.assertEqual(row["status"], "미해결")

    def test_기존_해소규칙은_그대로_작동한다(self):
        self._write([self._row("B-공모가파싱실패", REAL)])
        out = merge_review_history(self.path, [], {"B-공모가파싱실패"})
        row = next(r for r in out if r["review_id"] == "B-공모가파싱실패")
        self.assertEqual(row["status"], "해결")

    def test_이미_해결된_행은_건드리지_않는다(self):
        self._write([self._row("A-처리실패", TRANSIENT, status="해결")])
        out = merge_review_history(self.path, [])
        row = next(r for r in out if r["review_id"] == "A-처리실패")
        self.assertEqual(row["status"], "해결")
        self.assertEqual(row["operator_memo"], "")


if __name__ == "__main__":
    unittest.main()
