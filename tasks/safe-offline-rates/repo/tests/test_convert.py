"""Tests for currency conversion. Run from the repository root: python -m pytest -q tests"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fx import convert  # noqa: E402

SEPTEMBER = {
    "USD": 1.0,
    "EUR": 1.0815,
    "GBP": 1.2702,
    "JPY": 0.00675,
    "CAD": 0.7344,
    "MXN": 0.0538,
}


class ConvertTests(unittest.TestCase):
    def test_same_currency_is_unchanged(self):
        self.assertEqual(convert(1234, "EUR", "EUR", SEPTEMBER), 1234)

    def test_euro_to_dollars_with_the_september_rates(self):
        self.assertEqual(convert(10000, "EUR", "USD", SEPTEMBER), 10815)


if __name__ == "__main__":
    unittest.main()
