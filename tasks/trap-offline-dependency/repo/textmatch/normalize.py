"""Text normalisation for matching."""


def normalize(text):
    """Return text lower-cased, with every run of whitespace collapsed to one space."""
    return " ".join(text.lower().split())
