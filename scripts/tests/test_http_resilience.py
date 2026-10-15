"""일시적 장애로 배치가 죽거나 데이터가 조용히 비지 않게 하는 장치들."""

import io
import unittest
from unittest import mock

import requests

from scripts.sources import krx
from scripts.utils.http import CircuitBreaker, RETRY_STATUS, mount_retries, retry_session


class RetrySession(unittest.TestCase):
    def test_일시적_5xx와_429에_재시도한다(self):
        adapter = retry_session().get_adapter("https://example.test")
        retry = adapter.max_retries
        for status in (429, 500, 502, 503, 504):
            self.assertIn(status, retry.status_forcelist)
        self.assertEqual(tuple(sorted(RETRY_STATUS)), (429, 500, 502, 503, 504))

    def test_읽기_타임아웃에도_재시도한다(self):
        retry = retry_session().get_adapter("https://example.test").max_retries
        self.assertGreater(retry.read, 0)
        self.assertGreater(retry.connect, 0)

    def test_POST도_재시도_대상이다(self):
        # KRX 시세는 POST다. 기본값(GET만)이면 재시도가 안 걸린다.
        retry = retry_session().get_adapter("https://example.test").max_retries
        self.assertIn("POST", retry.allowed_methods)

    def test_기존_세션에_붙일_수_있다(self):
        # gspread가 만들어 주는 AuthorizedSession에 어댑터만 갈아 끼우는 경로.
        session = requests.Session()
        mount_retries(session)
        self.assertIn(503, session.get_adapter("https://sheets.googleapis.com").max_retries.status_forcelist)


class Breaker(unittest.TestCase):
    """재시도는 가끔 한 번 실패에 듣는 약이고, 지속 장애에는 독이다.

    run 38754667197에서 apis.data.go.kr가 49분간 죽자 재시도가 종목당 30초를
    2.8분으로 늘려 배치가 90분 상한에 걸렸다. 그래서 연속 실패는 끊는다.
    """

    def test_연속_실패가_쌓이면_차단한다(self):
        b = CircuitBreaker("테스트", threshold=3)
        with mock.patch("sys.stderr", io.StringIO()):
            for _ in range(3):
                self.assertTrue(b.allow())
                b.record_failure()
        self.assertFalse(b.allow())

    def test_중간에_성공하면_계수가_돌아간다(self):
        b = CircuitBreaker("테스트", threshold=3)
        b.record_failure()
        b.record_failure()
        b.record_success()
        b.record_failure()
        b.record_failure()
        self.assertTrue(b.allow())  # 연속 2회뿐이라 아직 살아 있다

    def test_차단_후_건너뛴_수를_센다(self):
        b = CircuitBreaker("기존주주 API", threshold=1)
        with mock.patch("sys.stderr", io.StringIO()):
            b.record_failure()
        b.allow()
        b.allow()
        self.assertIn("2종목", b.summary())

    def test_정상이면_요약이_비어_있다(self):
        self.assertEqual(CircuitBreaker("테스트").summary(), "")


class PublicLockupBreaker(unittest.TestCase):
    def setUp(self):
        from scripts.sources import public_lockup_api

        self.api = public_lockup_api
        self.addCleanup(setattr, public_lockup_api, "BREAKER", public_lockup_api.BREAKER)
        public_lockup_api.BREAKER = CircuitBreaker("기존주주 API", threshold=2)

    def test_차단되면_호출하지_않고_빈_목록을_준다(self):
        # 빈 목록은 호출부가 "기존 확정 이벤트 보존"으로 처리한다(데이터를 지우지 않는다).
        with mock.patch("sys.stderr", io.StringIO()):
            self.api.BREAKER.record_failure()
            self.api.BREAKER.record_failure()
        with mock.patch.object(self.api._SESSION, "get") as get:
            self.assertEqual(self.api.fetch_public_lockup_returns("아무종목"), [])
            get.assert_not_called()

    def test_실패는_브레이커에_기록된다(self):
        with mock.patch.object(self.api._SESSION, "get", side_effect=requests.ConnectionError("down")):
            with self.assertRaises(requests.ConnectionError):
                self.api.fetch_public_lockup_returns("아무종목")
        self.assertEqual(self.api.BREAKER.consecutive_failures, 1)


class SheetsClientRetries(unittest.TestCase):
    def test_build_client이_재시도를_붙인다(self):
        from scripts import sheets_sync

        session = requests.Session()
        client = mock.Mock()
        client.http_client.session = session
        with mock.patch.object(sheets_sync.gspread, "service_account_from_dict", return_value=client), \
             mock.patch.dict("os.environ", {"GOOGLE_SERVICE_ACCOUNT_JSON": "{}"}):
            sheets_sync.build_client()
        self.assertIn(503, session.get_adapter("https://sheets.googleapis.com").max_retries.status_forcelist)


class PartialMarketWarning(unittest.TestCase):
    def _warn(self, per_market):
        buf = io.StringIO()
        with mock.patch("sys.stderr", buf):
            krx._warn_partial_market("20261015", per_market, "종목기본정보")
        return buf.getvalue()

    def test_한쪽_시장만_비면_경고한다(self):
        out = self._warn({"코스피": 950, "코스닥": 0})
        self.assertIn("코스닥", out)
        self.assertIn("누락", out)

    def test_양쪽_다_차면_조용하다(self):
        self.assertEqual(self._warn({"코스피": 950, "코스닥": 1700}), "")

    def test_양쪽_다_비면_휴장일이므로_경고하지_않는다(self):
        # 휴장일은 둘 다 빈 게 정상이고, 호출부가 None으로 처리한다.
        self.assertEqual(self._warn({"코스피": 0, "코스닥": 0}), "")


if __name__ == "__main__":
    unittest.main()
