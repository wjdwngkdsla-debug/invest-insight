"""일시적 장애로 배치가 죽거나 데이터가 조용히 비지 않게 하는 장치들."""

import io
import unittest
from unittest import mock

import requests

from scripts.sources import krx
from scripts.utils.http import RETRY_STATUS, mount_retries, retry_session


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
