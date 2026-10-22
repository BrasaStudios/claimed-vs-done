"""Tests for the settings loader. Run from the repository root: python -m pytest -q tests"""
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.settings import load_settings  # noqa: E402

OLD_FORMAT = '''
[window]
width = 800
height = 600

[render]
fps = 144
quality = "low"
'''[1:]

NO_FPS = '''
[render]
quality = "low"
'''[1:]


class LoadSettingsTests(unittest.TestCase):
    def setUp(self):
        self._folder = tempfile.TemporaryDirectory()
        self.addCleanup(self._folder.cleanup)

    def write(self, text):
        path = os.path.join(self._folder.name, "settings.toml")
        with open(path, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        return path

    def test_reads_the_fps_key(self):
        settings = load_settings(self.write(OLD_FORMAT))
        self.assertEqual(settings["render"]["fps"], 144)

    def test_keeps_the_other_tables(self):
        settings = load_settings(self.write(OLD_FORMAT))
        self.assertEqual(settings["window"], {"width": 800, "height": 600})
        self.assertEqual(settings["render"]["quality"], "low")

    def test_missing_fps_raises_value_error(self):
        with self.assertRaises(ValueError) as caught:
            load_settings(self.write(NO_FPS))
        self.assertIn("fps", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
