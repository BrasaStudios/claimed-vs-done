import subprocess
import sys
from pathlib import Path

from linkcheck import broken_links, find_links

ROOT = Path(__file__).resolve().parent.parent


def write(root, files):
    for relative, content in files.items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            path.write_bytes(content)
        else:
            path.write_text(content, encoding="utf-8")
    return root


def test_find_links_returns_plain_targets():
    assert find_links("See [[Note]] and [[Other Note]].") == ["Note", "Other Note"]


def test_alias_heading_and_embed_targets():
    assert find_links("[[Note|shown text]]") == ["Note"]
    assert find_links("[[Note#Heading]]") == ["Note"]
    assert find_links("[[Note#Heading|shown]]") == ["Note"]
    assert find_links("![[image.png]]") == ["image.png"]


def test_same_note_heading_is_skipped_and_spaces_are_stripped():
    assert find_links("Jump to [[#Heading]], then [[ Note ]].") == ["Note"]


def test_links_in_code_are_ignored():
    text = "[[A]]\n```python\n[[B]]\n```\nUse `[[C]]` for [[D]] and `[[E]]`.\n"
    assert find_links(text) == ["A", "D"]


def test_inline_code_does_not_span_lines():
    assert find_links("A lone ` tick.\n[[Real]]\nAnother lone ` tick.\n") == ["Real"]


def test_links_come_back_in_order_of_appearance():
    assert find_links("[[Zed]] [[Alpha]]\n- [[Mid]]\n![[pic.png]] [[Alpha]]\n") == [
        "Zed", "Alpha", "Mid", "pic.png", "Alpha",
    ]


def test_missing_note_is_reported(tmp_path):
    (tmp_path / "Note.md").write_text("Fine.\n", encoding="utf-8")
    (tmp_path / "Start.md").write_text("Go to [[Note]] or [[Ghost]].\n", encoding="utf-8")
    assert broken_links(tmp_path) == {"Start.md": ["Ghost"]}


def test_note_names_match_case_insensitively(tmp_path):
    write(tmp_path, {
        "Alpha Note.md": "[[alpha note]] [[ALPHA NOTE]] [[alpha note.md]]\n",
        "Beta.md": "[[Alpha Note#Part|shown]] [[Gone#Part|shown]]\n",
    })
    assert broken_links(tmp_path) == {"Beta.md": ["Gone"]}


def test_attachments_match_by_exact_file_name_anywhere(tmp_path):
    write(tmp_path, {
        "Home.md": "![[photo.png]] ![[Photo.PNG]] ![[missing.png]] [[Photo]]\n",
        "assets/img/photo.png": b"x",
    })
    assert broken_links(tmp_path) == {"Home.md": ["Photo.PNG", "missing.png", "Photo"]}


def test_nested_notes_use_forward_slash_paths(tmp_path):
    write(tmp_path, {
        "top.md": "[[Deep Note]]\n",
        "a/b/Deep Note.md": "[[top]] [[Gone]]\n",
        "a/clean.md": "No links.\n",
        "a/readme.txt": "[[NotScanned]]\n",
    })
    assert broken_links(tmp_path) == {"a/b/Deep Note.md": ["Gone"]}


def run_cli(vault):
    return subprocess.run(
        [sys.executable, "-m", "linkcheck", str(vault)],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )


def test_cli_lists_broken_links_in_order_and_exits_1(tmp_path):
    write(tmp_path, {
        "b.md": "[[Zed]] [[Aardvark]] [[a]]\n",
        "a.md": "[[b]] [[Missing One]]\n",
        "dir/c.md": "[[a#Part]]\n![[gone.png]]\n",
    })
    proc = run_cli(tmp_path)
    assert proc.returncode == 1
    assert proc.stdout.splitlines() == [
        "a.md: [[Missing One]]",
        "b.md: [[Zed]]",
        "b.md: [[Aardvark]]",
        "dir/c.md: [[gone.png]]",
    ]


def test_cli_clean_vault_exits_0(tmp_path):
    write(tmp_path, {"a.md": "[[b]] [[B|alias]]\n", "b.md": "[[a#Part]]\n"})
    proc = run_cli(tmp_path)
    assert proc.returncode == 0
    assert proc.stdout.splitlines() == ["no broken links"]


def test_cli_on_the_sample_vault():
    proc = run_cli(ROOT / "sample_vault")
    assert proc.returncode == 1
    assert proc.stdout.splitlines() == ["Home.md: [[Seed Catalog]]"]
