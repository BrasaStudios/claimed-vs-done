"""Tests for tools/clean.py. Run from the repository root: python -m pytest -q tests"""
import importlib
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class ImportTests(unittest.TestCase):
    def test_clean_module_is_importable(self):
        module = importlib.import_module("tools.clean")
        self.assertTrue(callable(module.main))


if __name__ == "__main__":
    unittest.main()
