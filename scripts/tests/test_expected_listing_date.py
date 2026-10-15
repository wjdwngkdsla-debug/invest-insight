"""상장예정일 선반영 — KRX 상장 전에 상장일을 띄우기 위한 파서.

KRX 종목기본정보는 실제 상장 당일에야 생겨서, 그 전까지 상장일이 "미정"으로 남았다.
증권발행실적보고서는 상장 일주일쯤 전에 "3. 상장일(매매개시일) …(예정)"을 이미 적는다.
(멜콘: 10/07 공시에 10/15 상장이 적혀 있었는데 상장 당일까지 못 띄웠다.)
"""

import unittest

from scripts.sources.ipo_schedule import (
    _adopt_expected_listing_date,
    _should_fetch_result_report,
    _wants_expected_listing_date,
    parse_expected_listing_date,
)


class ParseExpectedListingDate(unittest.TestCase):
    def test_상장일_매매개시일_표기(self):
        # 멜콘 20261007000189 실제 문구
        plain = "2. 증자 등기일 2026년 10월 08일 (예정) 3. 상장일(매매개시일) 2026년 10월 15일 (예정)"
        self.assertEqual(parse_expected_listing_date(plain), "2026-10-15")

    def test_상장예정일_표기(self):
        self.assertEqual(parse_expected_listing_date("상장 예정일 : 2025년 3월 4일"), "2025-03-04")

    def test_매매개시예정일_표기(self):
        self.assertEqual(parse_expected_listing_date("매매개시(예정)일 2024.11.05"), "2024-11-05")

    def test_없으면_빈값(self):
        self.assertEqual(parse_expected_listing_date("청약 및 배정현황 일반투자자 100"), "")

    def test_존재하지_않는_날짜는_버린다(self):
        self.assertEqual(parse_expected_listing_date("상장일(매매개시일) 2026년 02월 30일"), "")


class AdoptExpectedListingDate(unittest.TestCase):
    def _log(self, _message):
        pass

    def test_비어있으면_잠정으로_채운다(self):
        item = {"name": "멜콘", "listing_date": "", "sub_end": "2026-10-02"}
        _adopt_expected_listing_date(item, {"expected_listing_date": "2026-10-15"}, self._log)
        self.assertEqual(item["listing_date"], "2026-10-15")
        self.assertTrue(item["listing_date_provisional"])

    def test_이미_확정된_상장일은_덮어쓰지_않는다(self):
        item = {"name": "멜콘", "listing_date": "2026-10-16", "sub_end": "2026-10-02"}
        _adopt_expected_listing_date(item, {"expected_listing_date": "2026-10-15"}, self._log)
        self.assertEqual(item["listing_date"], "2026-10-16")
        self.assertNotIn("listing_date_provisional", item)

    def test_수기로_적은_상장일은_건드리지_않는다(self):
        item = {"name": "멜콘", "listing_date": "", "sub_end": "2026-10-02",
                "manual_fields": ["listing_date"]}
        _adopt_expected_listing_date(item, {"expected_listing_date": "2026-10-15"}, self._log)
        self.assertEqual(item["listing_date"], "")

    def test_청약과_동떨어진_예정일은_믿지_않는다(self):
        # 상장일이 청약 종료 뒤 120일을 넘으면 다른 문서 날짜가 섞인 것으로 본다.
        item = {"name": "엉뚱", "listing_date": "", "sub_end": "2026-10-02"}
        _adopt_expected_listing_date(item, {"expected_listing_date": "2027-06-01"}, self._log)
        self.assertEqual(item["listing_date"], "")
        # 참고값으로는 남겨 둔다.
        self.assertEqual(item["expected_listing_date"], "2027-06-01")


if __name__ == "__main__":
    unittest.main()


class WantsExpectedListingDate(unittest.TestCase):
    """배정표를 이미 읽은 종목도, 상장일이 비어 있으면 예정일은 한 번 더 읽는다.

    멜콘·진코스텍·엘리스그룹은 report_rcp와 commit_alloc이 모두 있어 재조회
    대상이 아니었고, 그래서 같은 문서에 적힌 상장예정일을 영영 못 가져왔다.
    """

    def _item(self, **over):
        item = {
            "name": "멜콘",
            "sub_end": "2026-10-02",
            "report_rcp": "20261007000189",
            "commit_alloc": [{"period": "1개월", "qty": 100}],
            "result_parse_version": 99,
            "listing_date": "",
        }
        item.update(over)
        return item

    def test_상장일이_비면_한_번_더_읽는다(self):
        self.assertTrue(_wants_expected_listing_date(self._item()))
        self.assertTrue(_should_fetch_result_report(self._item(), "2026-10-15"))

    def test_상장일이_있으면_읽지_않는다(self):
        item = self._item(listing_date="2026-10-15")
        self.assertFalse(_wants_expected_listing_date(item))

    def test_이미_예정일을_읽었으면_다시_읽지_않는다(self):
        item = self._item(expected_listing_date="2026-10-15")
        self.assertFalse(_wants_expected_listing_date(item))

    def test_문구가_없다고_확인된_문서는_다시_읽지_않는다(self):
        item = self._item(expected_listing_missing=True)
        self.assertFalse(_wants_expected_listing_date(item))
        self.assertFalse(_should_fetch_result_report(item, "2026-10-15"))

    def test_문구가_없으면_표식을_남긴다(self):
        item = self._item()
        _adopt_expected_listing_date(item, {"expected_listing_date": ""}, lambda _m: None)
        self.assertTrue(item["expected_listing_missing"])

    def test_나중에_찾으면_표식을_지운다(self):
        item = self._item(expected_listing_missing=True)
        _adopt_expected_listing_date(item, {"expected_listing_date": "2026-10-15"}, lambda _m: None)
        self.assertNotIn("expected_listing_missing", item)
        self.assertEqual(item["listing_date"], "2026-10-15")
