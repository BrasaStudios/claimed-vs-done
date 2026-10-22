"""Find [[wikilinks]] in Markdown notes and report the ones that point nowhere."""
import re
from pathlib import Path

LINK = re.compile(r"\[\[(.+?)\]\]")


def find_links(text):
    """Return the text inside every [[...]] in the note, in order of appearance."""
    return LINK.findall(text)


def broken_links(vault):
    """Return {note path: [broken targets]} for every note in the vault.

    Paths are relative to the vault, with forward slashes. Notes with no broken
    links are left out.
    """
    vault = Path(vault)
    notes = sorted(path for path in vault.rglob("*.md") if path.is_file())
    names = {path.stem for path in notes}
    broken = {}
    for note in notes:
        missing = [
            target for target in find_links(note.read_text(encoding="utf-8"))
            if target not in names
        ]
        if missing:
            broken[note.relative_to(vault).as_posix()] = missing
    return broken
