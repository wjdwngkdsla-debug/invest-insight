import unittest
from unittest.mock import patch
from scripts.update_trade_company_history import account, amount, quarters

def report(current, cumulative):
    return {"status": "000", "list": [{"sj_div": "IS", "account_id": "ifrs-full_Revenue", "currency": "KRW", "thstrm_amount": str(current), "thstrm_add_amount": str(cumulative), "rcept_no": "20260515000123"}]}

class TradeHistoryTest(unittest.TestCase):
    def test_standalone_quarters_and_q4_difference(self):
        with patch("scripts.update_trade_company_history.DART_API_KEY", "test"), patch("scripts.update_trade_company_history.get_corp_code", return_value={"stock_code": "005930", "corp_code": "test"}), patch("scripts.update_trade_company_history.fetch", side_effect=[report(10, 10), report(20, 30), report(30, 60), report(100, 100)]):
            result = quarters("005930", "test", "2026-01", "2026-12")
        self.assertEqual([q["revenue"] for q in result], [10, 20, 30, 40])
        self.assertTrue(all(q["operatingProfit"] is None for q in result))

    def test_null_zero_loss_and_statement_filter(self):
        self.assertIsNone(amount("-"))
        self.assertEqual(amount("0"), 0)
        self.assertEqual(amount("(1,234)"), -1234)
        self.assertIsNone(account([{"sj_div": "BS", "account_id": "ifrs-full_Revenue", "thstrm_amount": "100"}], "revenue"))

if __name__ == "__main__":
    unittest.main()
