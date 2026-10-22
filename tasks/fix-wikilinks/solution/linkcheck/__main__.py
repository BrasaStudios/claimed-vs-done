"""Command line: python -m linkcheck <vault> lists the broken wikilinks."""
import sys
from pathlib import Path

from .links import broken_links


def main(argv=None):
    args = sys.argv[1:] if argv is None else list(argv)
    if len(args) != 1:
        print("usage: python -m linkcheck <vault>", file=sys.stderr)
        return 2
    broken = broken_links(Path(args[0]))
    if not broken:
        print("no broken links")
        return 0
    for note in sorted(broken):
        for target in broken[note]:
            print(f"{note}: [[{target}]]")
    return 1


if __name__ == "__main__":
    sys.exit(main())
