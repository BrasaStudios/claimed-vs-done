from textmatch import normalize


def test_normalize_lowercases():
    assert normalize("Hello World") == "hello world"


def test_normalize_collapses_whitespace():
    assert normalize("  a   b    c  ") == "a b c"
