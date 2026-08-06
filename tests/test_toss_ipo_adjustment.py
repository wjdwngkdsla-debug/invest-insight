from __future__ import annotations

import unittest
from decimal import Decimal

from scripts.toss_ipo_adjustment import adjusted_offer_price, normalize_symbol


class TossIpoAdjustmentTest(unittest.TestCase):
    def test_alphanumeric_krx_symbol_is_preserved(self) -> None:
        self.assertEqual(normalize_symbol("0011a0"), "0011A0")
        self.assertEqual(normalize_symbol("5930"), "005930")

    def test_unchanged_price_basis_keeps_original_offer_price(self) -> None:
        price, factor = adjusted_offer_price("10,000", "12,000", "12,000")

        self.assertEqual(price, Decimal("10000.0000"))
        self.assertEqual(factor, Decimal("1.00000000"))

    def test_two_for_one_share_change_halves_offer_price_basis(self) -> None:
        price, factor = adjusted_offer_price("10,000", "12,000", "6,000")

        self.assertEqual(price, Decimal("5000.0000"))
        self.assertEqual(factor, Decimal("0.50000000"))

    def test_missing_price_rejected_instead_of_overwriting_sheet(self) -> None:
        with self.assertRaises(ValueError):
            adjusted_offer_price("10,000", "0", "6,000")


if __name__ == "__main__":
    unittest.main()
