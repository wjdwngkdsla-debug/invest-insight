"""검토필요로 올라오던 것 중 사람이 볼 필요가 없던 두 가지.

① 제출사가 '개월'을 '월'로 줄여 쓴 칸 ("상장 후 1월")
   피앤에스미캐닉스는 11행이 전부 이 표기여서 통째로 보류됐다.
② 정정신고서가 "나머지는 OOOO년 O월 O일 신고서와 동일"이라고만 적은 경우
   원본 접수번호는 이미 손에 든 공시 목록에 있는데 가져오지 않았다.
"""

import unittest
from unittest import mock

from scripts.audit_ipo_quality import _resolve_correction_reference
from scripts.sources.dart_api import _holder_period


class MonthShorthand(unittest.TestCase):
    def test_기산_문구가_있으면_월을_개월로_읽는다(self):
        self.assertEqual(_holder_period("상장 후 1월"), "1개월")
        self.assertEqual(_holder_period("상장후 6월"), "6개월")
        self.assertEqual(_holder_period("매매개시일로부터 3월"), "3개월")

    def test_기산_문구가_없으면_읽지_않는다(self):
        # 그냥 '7월'은 기간이 아니라 달일 수 있다. 섣불리 7개월로 읽으면 안 된다.
        self.assertIsNone(_holder_period("7월"))
        self.assertIsNone(_holder_period("1월"))

    def test_날짜는_여전히_거른다(self):
        self.assertIsNone(_holder_period("2024년 7월"))
        self.assertIsNone(_holder_period("2025.05.19"))

    def test_한_칸에_기간이_둘이면_사람에게_넘긴다(self):
        # "상장 후 1월 /3월"은 수량 하나에 기간이 둘이라 나눌 수 없다.
        self.assertIsNone(_holder_period("상장 후 1월 /3월"))
        self.assertIsNone(_holder_period("상장 후 1월, 3월"))

    def test_기존_표기는_그대로_동작한다(self):
        self.assertEqual(_holder_period("상장일로부터 6개월"), "6개월")
        self.assertEqual(_holder_period("1개월"), "1개월")
        self.assertEqual(_holder_period("2년"), "2년")
        self.assertEqual(_holder_period("15일"), "15일")


class CorrectionReference(unittest.TestCase):
    REPORTS = [
        {"rcept_no": "20240807000173", "rcept_dt": "20240807", "report_nm": "[기재정정]투자설명서"},
        {"rcept_no": "20240712000470", "rcept_dt": "20240712", "report_nm": "투자설명서"},
    ]

    def _review(self):
        return {"status": "review", "rcept_no": "20240807000173",
                "reason": "정정사항만 수록: 원본문 대조 필요",
                "referenced_filing_date": "2024-07-12"}

    def test_원본문을_찾아_다시_읽는다(self):
        verified = {"status": "verified", "rcept_no": "20240712000470", "total": 4_712_442,
                    "rows": [{"period": "1개월", "qty": 888_888}]}
        with mock.patch("scripts.audit_ipo_quality.download_document_text", return_value="<doc>"), \
             mock.patch("scripts.audit_ipo_quality.holder_snapshot", return_value=verified):
            out = _resolve_correction_reference(self._review(), self.REPORTS)
        self.assertEqual(out["status"], "verified")
        self.assertEqual(out["rcept_no"], "20240712000470")
        self.assertEqual(out["resolved_from_correction"], "20240807000173")

    def test_원본도_못_읽으면_원래_판정을_유지한다(self):
        with mock.patch("scripts.audit_ipo_quality.download_document_text", return_value="<doc>"), \
             mock.patch("scripts.audit_ipo_quality.holder_snapshot",
                        return_value={"status": "review", "reason": "기존주주 표 미발견"}):
            out = _resolve_correction_reference(self._review(), self.REPORTS)
        self.assertEqual(out["reason"], "정정사항만 수록: 원본문 대조 필요")

    def test_참조_날짜가_없으면_건드리지_않는다(self):
        snap = {"status": "review", "rcept_no": "X", "reason": "기존주주 표 미발견"}
        self.assertIs(_resolve_correction_reference(snap, self.REPORTS), snap)

    def test_이미_verified면_건드리지_않는다(self):
        snap = {"status": "verified", "rcept_no": "X", "total": 1}
        self.assertIs(_resolve_correction_reference(snap, self.REPORTS), snap)

    def test_조회가_실패해도_죽지_않는다(self):
        with mock.patch("scripts.audit_ipo_quality.download_document_text",
                        side_effect=RuntimeError("DART 장애")):
            out = _resolve_correction_reference(self._review(), self.REPORTS)
        self.assertEqual(out["status"], "review")


if __name__ == "__main__":
    unittest.main()
