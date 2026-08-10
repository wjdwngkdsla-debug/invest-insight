from __future__ import annotations

import unittest
from unittest.mock import Mock, patch

from scripts.build import (
    CATEGORY_IPO,
    apply_api_updates,
    build_dart_rows_or_preserve,
)
from scripts.sources.public_lockup_api import fetch_public_lockup_returns


class DartApiFallbackTest(unittest.TestCase):
    @patch("scripts.sources.public_lockup_api.requests.get")
    @patch("scripts.sources.public_lockup_api.DATA_GO_KR_API_KEY", "abc%2Bdef%2Fghi%3D")
    def test_public_api_accepts_portal_encoding_key(self, mock_get: Mock) -> None:
        response = Mock()
        response.json.return_value = {"response": {"body": {"items": {}}}}
        mock_get.return_value = response

        fetch_public_lockup_returns("테스트")

        self.assertEqual(mock_get.call_args.kwargs["params"]["serviceKey"], "abc+def/ghi=")

    def test_dart_failure_preserves_existing_rows_for_api_step(self) -> None:
        existing = [{
            "event_id": "0156T0-IPO기관-1M-2026-08-24",
            "code": "0156T0",
            "name": "에이치엘지노믹스",
            "category": CATEGORY_IPO,
            "planned_qty": "9307",
        }]

        with patch("scripts.build.build_ipo_events", side_effect=TimeoutError("DART timeout")):
            rows, reviews = build_dart_rows_or_preserve(
                {"name": "에이치엘지노믹스"},
                "0156T0",
                {"market": "코스닥"},
                "2026-07-24",
                7_782_161,
                existing,
                {existing[0]["event_id"]: existing[0]},
            )

        self.assertEqual(rows, existing)
        self.assertIsNot(rows[0], existing[0])
        self.assertEqual(reviews[0]["category"], "DART처리오류")
        self.assertIn("API 보강 계속", reviews[0]["issue"])

    def test_api_only_fallback_ignores_mismatched_stock_code(self) -> None:
        raw_items = [
            {
                "stckIssuCmpyNm": "테스트",
                "itmsShrtnCd": "999999",
                "rsrnDt": "20260731",
                "rsrnStckCnt": "999",
            },
            {
                "stckIssuCmpyNm": "테스트",
                "itmsShrtnCd": "123456",
                "rsrnDt": "20260731",
                "rsrnStckCnt": "100",
            },
        ]

        with patch("scripts.build.fetch_public_lockup_returns", return_value=raw_items):
            rows, reviews, logs, removed_ids = apply_api_updates(
                {"name": "테스트"},
                "123456",
                {"market": "코스닥", "close_price": 1_000},
                "2026-07-01",
                1_000,
                [],
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["api_return_qty"], 100)
        self.assertEqual(rows[0]["dart_source"], "공공데이터 API 단독")
        self.assertEqual(reviews, [])
        self.assertEqual(len(logs), 1)
        self.assertEqual(removed_ids, [])


if __name__ == "__main__":
    unittest.main()
