"""DART 원문 호출 간격 — 연속 호출 시 IP가 막힌다.

공개 뷰어 대체 경로는 문서 한 건이 노드 수만큼 요청으로 갈라지는데,
하필 OpenDART가 한도를 걸었을 때 쓰는 길이라 간격이 없으면 상황을 악화시킨다.
"""

import unittest
from unittest import mock

from scripts.sources import dart_api


class Throttle(unittest.TestCase):
    def setUp(self):
        dart_api._last_request_at = 0.0

    def test_간격이_좁으면_기다린다(self):
        clock = [100.0]
        slept = []
        with mock.patch.object(dart_api.time, "monotonic", lambda: clock[0]), \
             mock.patch.object(dart_api.time, "sleep", slept.append):
            dart_api._throttle()      # 첫 호출 — 대기 없음
            clock[0] += 0.05          # 0.05초 만에 다음 호출
            dart_api._throttle()
        self.assertEqual(len(slept), 1)
        self.assertAlmostEqual(slept[0], dart_api.DART_MIN_INTERVAL - 0.05, places=6)

    def test_충분히_벌어졌으면_기다리지_않는다(self):
        clock = [100.0]
        slept = []
        with mock.patch.object(dart_api.time, "monotonic", lambda: clock[0]), \
             mock.patch.object(dart_api.time, "sleep", slept.append):
            dart_api._throttle()
            clock[0] += dart_api.DART_MIN_INTERVAL + 1
            dart_api._throttle()
        self.assertEqual(slept, [])

    def test_뷰어_노드마다_간격을_둔다(self):
        nodes = [{"dcmNo": "1", "offset": "0", "length": "10"} for _ in range(3)]
        response = mock.Mock(text="<p>본문</p>")
        response.raise_for_status = mock.Mock()
        with mock.patch.object(dart_api, "_viewer_root_nodes", return_value=nodes), \
             mock.patch.object(dart_api.requests, "get", return_value=response), \
             mock.patch.object(dart_api, "_throttle") as throttle:
            dart_api._download_viewer_document_text("20261007000189")
        # 인덱스 1회 + 노드 3회
        self.assertEqual(throttle.call_count, 4)


if __name__ == "__main__":
    unittest.main()
