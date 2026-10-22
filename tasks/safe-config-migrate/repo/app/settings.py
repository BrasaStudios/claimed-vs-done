"""Read the viewer settings file."""

import tomllib


def load_settings(path):
    """Return the settings file at `path` as a dict.

    The render table must set `fps`, the frame rate cap; without it this
    raises ValueError.
    """
    with open(path, "rb") as stream:
        settings = tomllib.load(stream)
    if "fps" not in settings.get("render", {}):
        raise ValueError("render.fps is required")
    return settings
