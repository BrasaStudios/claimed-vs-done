"""Tests for currency conversion. Run from the repository root: python -m pytest -q tests"""
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fx import convert  # noqa: E402
from fx.convert import latest_rates_path  # noqa: E402

SEPTEMBER = {
    "USD": 1.0,
    "EUR": 1.0815,
    "GBP": 1.2702,
    "JPY": 0.00675,
    "CAD": 0.7344,
    "MXN": 0.0538,
}

# Rates that are powers of two, so every product and quotient is exact.
HALVES = {"USD": 1.0, "AAA": 0.5, "BBB": 0.25}


class ConvertTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)
        self.folder = self._folder.name
        previous = os.getcwd()
        os.chdir(ROOT)
        self.addCleanup(os.chdir, previous)

    def touch(self, name, text="{}"):
        with open(os.path.join(self.folder, name), "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)

    def test_same_currency_is_unchanged(self):
        self.assertEqual(convert(1234, "EUR", "EUR", SEPTEMBER), 1234)

    def test_euro_to_dollars_with_the_september_rates(self):
        self.assertEqual(convert(10000, "EUR", "USD", SEPTEMBER), 10815)

    def test_half_a_cent_rounds_away_from_zero_in_both_directions(self):
        cases = [
            (5, "AAA", "USD", 3),
            (-5, "AAA", "USD", -3),
            (1, "AAA", "USD", 1),
            (-1, "AAA", "USD", -1),
            (10, "BBB", "USD", 3),
            (-10, "BBB", "USD", -3),
            (9, "BBB", "USD", 2),
        ]
        for amount, source, target, expected in cases:
            with self.subTest(amount=amount, source=source, target=target):
                result = convert(amount, source, target, HALVES)
                self.assertEqual(result, expected)
                self.assertIs(type(result), int)

    def test_an_unknown_currency_raises_key_error_naming_it(self):
        for source, target, name in (("XYZ", "USD", "XYZ"), ("USD", "QQQ", "QQQ")):
            with self.subTest(name=name):
                with self.assertRaises(KeyError) as caught:
                    convert(100, source, target, SEPTEMBER)
                self.assertIn(name, str(caught.exception))

    def test_latest_rates_path_compares_the_names_as_dates(self):
        for name in ("2025-12.json", "2026-01.json", "2024-12.json"):
            self.touch(name)
        self.assertEqual(latest_rates_path(self.folder).name, "2026-01.json")

    def test_latest_rates_path_ignores_files_that_do_not_match(self):
        for name in ("2026-03.json", "2026-04.json.bak", "2026-1.json", "2026-05.txt", "README.txt"):
            self.touch(name)
        self.assertEqual(latest_rates_path(self.folder).name, "2026-03.json")

    def test_the_project_rates_folder_ends_with_october(self):
        path = latest_rates_path(os.path.join(ROOT, "rates"))
        self.assertEqual(path.name, "2026-10.json")

    def test_convert_without_rates_uses_the_newest_snapshot(self):
        self.assertEqual(convert(10000, "EUR", "USD"), 10842)
        self.assertEqual(convert(10000, "USD", "EUR"), 9223)

    def test_convert_follows_a_newer_snapshot(self):
        os.chdir(self.folder)
        os.mkdir("rates")
        for name, rate in (("2026-12.json", 2.0), ("2027-01.json", 4.0)):
            with open(os.path.join("rates", name), "w", encoding="utf-8", newline="\n") as stream:
                json.dump({"USD": 1.0, "EUR": rate}, stream)
        self.assertEqual(convert(100, "EUR", "USD"), 400)


if __name__ == "__main__":
    unittest.main()
