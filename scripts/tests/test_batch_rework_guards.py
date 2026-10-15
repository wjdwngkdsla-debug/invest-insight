"""배치가 같은 일을 매번 다시 하지 않게 막는 장치들.

run #265(71.8분)에서 60분이 아래 두 가지 헛일이었다.
  - 수량 0인 빈 칸을 "미확정 수기값"으로 읽어 25종목을 매 배치 재파싱 (약 30분)
  - 유통가능 문장을 못 찾은 종목을 기록하지 않아 50종목을 매 배치 재조회 (약 30분)
"""

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import scripts.build as build


def _has_temporary(manual_commit_apply):
    """ipo_schedule.refresh_ipo_schedule의 판정과 같은 식."""
    return any(
        (value or {}).get("qty") and not bool((value or {}).get("locked"))
        for value in dict(manual_commit_apply or {}).values()
    )


class TemporaryCommitApplyDetection(unittest.TestCase):
    def test_수량0_빈칸은_재파싱_대상이_아니다(self):
        # 그래피 실제 데이터 모양 — 미확약만 확정이고 나머지는 안 적은 빈 칸
        manual = {
            "미확약": {"qty": 248635000, "locked": True},
            "15일": {"qty": 0, "locked": False},
            "1개월": {"qty": 0, "locked": False},
            "3개월": {"qty": 0, "locked": False},
            "6개월": {"qty": 0, "locked": False},
        }
        self.assertFalse(_has_temporary(manual))

    def test_수량이_있는_미확정값은_재파싱_대상이다(self):
        manual = {"1개월": {"qty": 120000, "locked": False}}
        self.assertTrue(_has_temporary(manual))

    def test_전부_확정이면_재파싱하지_않는다(self):
        manual = {"1개월": {"qty": 120000, "locked": True}}
        self.assertFalse(_has_temporary(manual))


class ListingFloatNegativeCache(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.path = Path(self._tmp.name) / "listing_float.json"
        patcher = mock.patch.object(build, "LISTING_FLOAT_PATH", self.path)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.rows = [{"code": "123456", "name": "없는종목", "listing_date": "2025-01-02"}]

    def test_문장을_못찾으면_없음으로_기록한다(self):
        with mock.patch.object(
            build, "parse_listing_float_sentence", return_value=(0, 0, 0.0, "")
        ) as parse:
            build.refresh_listing_float(self.rows)
            self.assertEqual(parse.call_count, 1)
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(
            saved["123456"]["missing_version"], build.LISTING_FLOAT_PARSER_VERSION
        )

    def test_다음_배치는_다시_조회하지_않는다(self):
        self.path.write_text(
            json.dumps({"123456": {"missing_version": build.LISTING_FLOAT_PARSER_VERSION}}),
            encoding="utf-8",
        )
        with mock.patch.object(build, "parse_listing_float_sentence") as parse:
            build.refresh_listing_float(self.rows)
            parse.assert_not_called()

    def test_파서_버전이_오르면_다시_조회한다(self):
        self.path.write_text(
            json.dumps({"123456": {"missing_version": build.LISTING_FLOAT_PARSER_VERSION - 1}}),
            encoding="utf-8",
        )
        with mock.patch.object(
            build, "parse_listing_float_sentence", return_value=(1000, 300, 30.0, "")
        ) as parse:
            build.refresh_listing_float(self.rows)
            parse.assert_called_once()
        saved = json.loads(self.path.read_text(encoding="utf-8"))
        self.assertEqual(saved["123456"]["float_shares"], 300)

    def test_네트워크_오류는_없음으로_굳히지_않는다(self):
        with mock.patch.object(
            build, "parse_listing_float_sentence", side_effect=TimeoutError("read timeout")
        ):
            build.refresh_listing_float(self.rows)
        self.assertFalse(self.path.exists())

    def test_이미_값이_있으면_건너뛴다(self):
        self.path.write_text(
            json.dumps({"123456": {"float_shares": 300, "float_pct": 30.0}}), encoding="utf-8"
        )
        with mock.patch.object(build, "parse_listing_float_sentence") as parse:
            build.refresh_listing_float(self.rows)
            parse.assert_not_called()


if __name__ == "__main__":
    unittest.main()
