"""Find [[wikilinks]] in Markdown notes and report the ones that point nowhere."""
import re
from pathlib import Path

LINK = re.compile(r"\[\[(.+?)\]\]")
INLINE_CODE = re.compile(r"`[^`\n]*`")


def _lines_outside_fences(text):
    """Yield the lines of a note that are not inside a fenced code block."""
    in_fence = False
    for line in text.splitlines():
        if line.startswith("```"):
            in_fence = not in_fence
        elif not in_fence:
            yield line


def find_links(text):
    """Return the target of every [[...]] link, in order of appearance.

    The alias (after "|") and the heading (after "#") are dropped, links to a
    heading of the same note are skipped, and links inside code are ignored.
    """
    targets = []
    for line in _lines_outside_fences(text):
        for inner in LINK.findall(INLINE_CODE.sub(" ", line)):
            target = inner.split("|", 1)[0].split("#", 1)[0].strip()
            if target:
                targets.append(target)
    return targets


def _resolves(target, note_names, file_names):
    suffix = Path(target).suffix
    if not suffix or suffix == ".md":
        name = target[:-3] if suffix else target
        return name.casefold() in note_names
    return target in file_names


def broken_links(vault):
    """Return {note path: [broken targets]} for every note in the vault.

    Paths are relative to the vault, with forward slashes. Notes with no broken
    links are left out. A target with no extension, or ending in .md, must match
    a note name (case-insensitively); any other target must match a file name
    exactly. Both are looked up anywhere in the vault.
    """
    vault = Path(vault)
    files = sorted(path for path in vault.rglob("*") if path.is_file())
    notes = [path for path in files if path.suffix == ".md"]
    note_names = {path.stem.casefold() for path in notes}
    file_names = {path.name for path in files}
    broken = {}
    for note in notes:
        missing = [
            target for target in find_links(note.read_text(encoding="utf-8"))
            if not _resolves(target, note_names, file_names)
        ]
        if missing:
            broken[note.relative_to(vault).as_posix()] = missing
    return broken
