from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

from scripts.sources import ipo_schedule as ipo


class TransferListingTests(unittest.TestCase):
    def test_discovery_includes_konex_but_not_listed_capital_raises(self):
        filings = [{"corp_code": cls, "corp_cls": cls} for cls in ["E", "N", "Y", "K"]]
        self.assertEqual(set(ipo.group_upcoming_ipos(filings)), {"E", "N"})

    def test_transfer_requires_public_offering_signals(self):
        base = {"issuer_market": "코넥스", "market": "코스닥", "is_listing_ipo": True}
        self.assertFalse(ipo._is_confirmed_ipo(base))
        base.update(transfer_market="코스닥", band_low=19500, forecast_start="2026-09-16",
                    sub_start="2026-10-02", underwriter="하나증권")
        self.assertTrue(ipo._is_confirmed_ipo(base))
        base.pop("forecast_start")
        self.assertFalse(ipo._is_confirmed_ipo(base))

    def test_transfer_target_market_is_not_historical_market(self):
        for market, expected in [("코스닥", "코스닥"), ("유가증권", "코스피")]:
            doc = f"당사는 금번 공모를 통해 {market}시장 이전상장을 추진합니다."
            result = ipo.parse_offering_doc(doc)
            self.assertEqual(result["transfer_market"], expected)
            self.assertEqual(result["market"], expected)

    def test_original_konex_listing_date_cannot_archive_upcoming_transfer(self):
        item = {"transfer_market": "코스닥", "sub_end": "2026-10-06", "first_filing_date": "20260827"}
        self.assertFalse(ipo._listing_date_is_plausible(item, "2019-11-29"))
        self.assertTrue(ipo._listing_date_is_plausible(item, "2026-10-19"))
        self.assertFalse(ipo._listing_date_is_plausible(item, "2027-10-19"))
        item.update(name="진코스텍", stock_code="250030", listing_date="")
        history = []
        ipo.detect_listings_from_krx({"01158632": item}, {}, "2026-09-14", history, lambda _: None,
                                    base_info={"250030": {"name": "진코스텍", "list_dd": "2019-11-29", "market": "코넥스"}})
        self.assertEqual(item["listing_date"], "")
        self.assertEqual(history, [])

    def test_targeted_refresh_preserves_other_companies_and_uses_real_parser(self):
        state = {"items": [{"corp_code": "other", "name": "다른회사", "manual_fields": ["sub_start"]}],
                 "past_items": [{"corp_code": "past", "name": "과거회사"}], "history": [],
                 "seed_pending": [{"name": "보류회사"}]}
        original = copy.deepcopy(state)
        filing = {"corp_code": "01158632", "corp_cls": "N", "corp_name": "진코스텍",
                  "stock_code": "250030", "rcept_no": "20260911000530", "rcept_dt": "20260911", "report_nm": "투자설명서"}
        doc = """<P>코스닥시장 이전상장. 희망공모가액은 19,500원 ~ 23,500원.
        수요예측 기간은 2026년 09월 16일 ~ 2026년 09월 22일.
        청약일: 2026년 10월 02일 ~ 2026년 10월 06일. 대표주관회사는 하나증권.</P>"""
        with (patch.object(ipo, "load_state", return_value=state),
              patch.object(ipo, "MANAGEMENT_PATH") as management,
              patch.object(ipo, "SCHEDULE_PATH"),
              patch.object(ipo, "_fetch_corp_filings", return_value=[filing]) as fetch,
              patch.object(ipo, "fetch_equity_filings") as all_filings,
              patch.object(ipo, "seed_new_items") as seed,
              patch.object(ipo, "download_document_text", return_value=doc),
              patch.object(ipo, "load_listing_map", return_value={"진코스텍": {"code": "250030", "listing_date": "2019-11-29"}})):
            management.exists.return_value = False
            result = ipo.refresh_ipo_schedule(verbose=False, corp_codes={"01158632"})
        all_filings.assert_not_called()
        seed.assert_not_called()
        fetch.assert_called_once_with("01158632", ipo.LOOKBACK_DAYS)
        self.assertIn(original["items"][0], result["items"])
        self.assertEqual(result["past_items"], original["past_items"])
        self.assertEqual(result["seed_pending"], original["seed_pending"])
        item = next(i for i in result["items"] if i["corp_code"] == "01158632")
        self.assertFalse(item["review_pending"])
        self.assertEqual(item["listing_date"], "")
        self.assertEqual(item["stock_code"], "250030")
        self.assertEqual(item["forecast_start"], "2026-09-16")
        self.assertEqual(item["sub_end"], "2026-10-06")


if __name__ == "__main__":
    unittest.main()
