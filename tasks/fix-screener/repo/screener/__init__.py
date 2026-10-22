"""Stock screener: keep the rows of a CSV that pass a few simple rules."""
from .screen import Result, Rules, screen

__all__ = ["screen", "Rules", "Result"]
