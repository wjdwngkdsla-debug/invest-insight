from __future__ import annotations

import unittest

from scripts.sources.dart_api import _period_from_label, extract_float_summary_tables


class DartFloatSummaryTest(unittest.TestCase):
    def test_compound_year_month_period_is_normalized_to_months(self) -> None:
        self.assertEqual(_period_from_label("상장 후 2년 6개월 뒤 유통가능"), "30개월")

    def test_multirow_header_and_pre_option_scenario_are_parsed(self) -> None:
        doc = """
        <TABLE>
          <TR><TD>구분</TD><TD>공모 후 기준</TD><TD>주식매수선택권 행사 시</TD></TR>
          <TR><TD>구분</TD><TD>유통가능 주식수</TD><TD>유통가능 주식수 비율</TD><TD>유통가능 주식수</TD><TD>유통가능 주식수 비율</TD></TR>
          <TR><TD>상장일 유통가능</TD><TD>8,071,582</TD><TD>36.89%</TD><TD>8,465,962</TD><TD>37.20%</TD></TR>
          <TR><TD>상장 후 1개월 뒤 유통가능</TD><TD>10,360,861</TD><TD>47.36%</TD><TD>10,755,241</TD><TD>47.26%</TD></TR>
          <TR><TD>상장 후 2년 뒤 유통가능</TD><TD>15,918,020</TD><TD>72.75%</TD><TD>16,799,048</TD><TD>73.81%</TD></TR>
          <TR><TD>상장 후 3년 뒤 유통가능</TD><TD>21,878,960</TD><TD>100.00%</TD><TD>22,759,988</TD><TD>100.00%</TD></TR>
        </TABLE>
        """

        candidates = extract_float_summary_tables(doc)

        self.assertEqual(len(candidates), 1)
        rows = candidates[0]["rows"]
        self.assertEqual([row["cumulative_float"] for row in rows], [8_071_582, 10_360_861, 15_918_020, 21_878_960])


if __name__ == "__main__":
    unittest.main()
