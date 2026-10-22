from linkcheck import broken_links, find_links


def test_find_links_returns_plain_targets():
    assert find_links("See [[Note]] and [[Other Note]].") == ["Note", "Other Note"]


def test_missing_note_is_reported(tmp_path):
    (tmp_path / "Note.md").write_text("Fine.\n", encoding="utf-8")
    (tmp_path / "Start.md").write_text("Go to [[Note]] or [[Ghost]].\n", encoding="utf-8")
    assert broken_links(tmp_path) == {"Start.md": ["Ghost"]}
