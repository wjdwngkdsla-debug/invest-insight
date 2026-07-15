from __future__ import annotations

import unittest
import sys
import types


def _load_build_functions():
    if "requests" not in sys.modules:
        requests = types.ModuleType("requests")
        requests.get = None
        requests.post = None
        requests.RequestException = Exception
        sys.modules["requests"] = requests
    adapters = types.ModuleType("requests.adapters")
    adapters.HTTPAdapter = object
    sys.modules.setdefault("requests.adapters", adapters)
    urllib3 = types.ModuleType("urllib3")
    urllib3_util = types.ModuleType("urllib3.util")
    urllib3_retry = types.ModuleType("urllib3.util.retry")

    class Retry:
        def __init__(self, *args, **kwargs):
            pass

    urllib3_retry.Retry = Retry
    sys.modules.setdefault("urllib3", urllib3)
    sys.modules.setdefault("urllib3.util", urllib3_util)
    sys.modules.setdefault("urllib3.util.retry", urllib3_retry)
    pdfplumber = types.ModuleType("pdfplumber")
    sys.modules.setdefault("pdfplumber", pdfplumber)
    from scripts.build import infer_lockup_period, rows_to_site_data

    return infer_lockup_period, rows_to_site_data


infer_lockup_period, rows_to_site_data = _load_build_functions()


class InferLockupPeriodTest(unittest.TestCase):
    def test_matches_release_date_returned_as_string(self) -> None:
        self.assertEqual(infer_lockup_period("2026-06-15", "2026-07-15"), "1개월")

    def test_matches_weekend_adjusted_tradable_date(self) -> None:
        # 2026-08-15는 토요일이므로 거래가능일 2026-08-17도 2개월로 인식한다.
        self.assertEqual(infer_lockup_period("2026-06-15", "2026-08-17"), "2개월")


class SiteDataVisibilityTest(unittest.TestCase):
    def test_site_data_build_handles_company_name_normalization(self) -> None:
        rows = [{
            "event_id": "123456-IPO-1개월", "code": "123456", "name": "주식회사 테스트",
            "market": "코스닥", "listing_date": "2026-07-01", "shares": "1000",
            "current_shares": "1100", "close_price": "10000", "ipo_price": "8000",
            "category": "IPO기관", "period": "1개월", "final_date": "2026-08-01",
            "final_qty": "100", "sheet_visible": "Y",
        }]

        result = rows_to_site_data(rows, "2026-07-15")

        self.assertEqual(result["stocks"][0]["name"], "주식회사 테스트")
        self.assertEqual(result["stocks"][0]["shares"], 1100)


if __name__ == "__main__":
    unittest.main()
