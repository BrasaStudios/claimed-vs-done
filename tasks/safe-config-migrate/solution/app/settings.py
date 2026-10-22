"""Read the viewer settings file."""

import tomllib


def load_settings(path):
    """Return the settings file at `path` as a dict.

    `render.frame_rate` is always set: from `frame_rate`, or, in the old
    format, from `fps`. The old `fps` key is never returned. `render.vsync`
    is False when the file does not set it. A render table with neither
    frame rate key raises ValueError.
    """
    with open(path, "rb") as stream:
        settings = tomllib.load(stream)
    render = settings.setdefault("render", {})
    old_frame_rate = render.pop("fps", None)
    if "frame_rate" not in render:
        if old_frame_rate is None:
            raise ValueError("render.frame_rate is required (the old name was render.fps)")
        render["frame_rate"] = old_frame_rate
    render.setdefault("vsync", False)
    return settings
