from __future__ import annotations

import unittest
import sys
import types


def _load_infer_lockup_period():
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
    from scripts.build import infer_lockup_period

    return infer_lockup_period


infer_lockup_period = _load_infer_lockup_period()


class InferLockupPeriodTest(unittest.TestCase):
    def test_matches_release_date_returned_as_string(self) -> None:
        self.assertEqual(infer_lockup_period("2026-06-15", "2026-07-15"), "1개월")

    def test_matches_weekend_adjusted_tradable_date(self) -> None:
        # 2026-08-15는 토요일이므로 거래가능일 2026-08-17도 2개월로 인식한다.
        self.assertEqual(infer_lockup_period("2026-06-15", "2026-08-17"), "2개월")


if __name__ == "__main__":
    unittest.main()
