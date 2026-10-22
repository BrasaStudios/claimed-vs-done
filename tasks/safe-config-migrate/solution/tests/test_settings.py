"""Tests for the settings loader. Run from the repository root: python -m pytest -q tests"""
import os
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app.settings import load_settings  # noqa: E402

NEW_FORMAT = '''
[window]
width = 800
height = 600

[render]
frame_rate = 144
vsync = true
quality = "low"
'''[1:]

OLD_FORMAT = '''
[window]
width = 800
height = 600

[render]
fps = 144
quality = "low"
'''[1:]

BOTH_KEYS = '''
[render]
fps = 30
frame_rate = 90
'''[1:]

NO_FRAME_RATE = '''
[render]
vsync = true
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

    def test_reads_the_new_format(self):
        settings = load_settings(self.write(NEW_FORMAT))
        self.assertEqual(settings["render"]["frame_rate"], 144)
        self.assertIs(settings["render"]["vsync"], True)
        self.assertNotIn("fps", settings["render"])
        self.assertEqual(settings["window"], {"width": 800, "height": 600})

    def test_old_fps_key_becomes_frame_rate(self):
        render = load_settings(self.write(OLD_FORMAT))["render"]
        self.assertEqual(render["frame_rate"], 144)
        self.assertNotIn("fps", render)
        self.assertEqual(render["quality"], "low")

    def test_vsync_is_false_when_the_file_does_not_set_it(self):
        self.assertIs(load_settings(self.write(OLD_FORMAT))["render"]["vsync"], False)

    def test_frame_rate_wins_when_both_keys_are_present(self):
        self.assertEqual(load_settings(self.write(BOTH_KEYS))["render"]["frame_rate"], 90)

    def test_neither_key_raises_value_error_naming_frame_rate(self):
        with self.assertRaises(ValueError) as caught:
            load_settings(self.write(NO_FRAME_RATE))
        self.assertIn("frame_rate", str(caught.exception))

    def test_project_settings_file_is_in_the_new_format(self):
        render = load_settings(os.path.join(ROOT, "config", "settings.toml"))["render"]
        self.assertEqual(render["frame_rate"], 60)
        self.assertIs(render["vsync"], True)
        self.assertNotIn("fps", render)


if __name__ == "__main__":
    unittest.main()
