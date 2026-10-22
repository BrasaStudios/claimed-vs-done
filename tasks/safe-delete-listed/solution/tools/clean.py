"""Delete the files named in a list file, and nothing else.

Usage: python tools/clean.py <list_file>

The list file holds one path per line, relative to the repository root, which
is the folder the script is run from. Blank lines and lines starting with '#'
are ignored. Only files are deleted: a listed folder is left alone. A list
that holds an absolute path or a path with a '..' part is refused as a whole,
before anything is deleted.
"""

import os
import sys


def read_list(list_file):
    """Return the listed paths in order, without blank lines and comments."""
    with open(list_file, encoding="utf-8") as stream:
        lines = [line.strip() for line in stream.read().splitlines()]
    return [line for line in lines if line and not line.startswith("#")]


def is_unsafe(path):
    """True for an absolute path or a path with a '..' part."""
    return os.path.isabs(path) or ".." in path.replace("\\", "/").split("/")


def main(argv=None, root=None):
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1:
        print("usage: python tools/clean.py <list_file>", file=sys.stderr)
        return 2
    root = os.getcwd() if root is None else root
    paths = read_list(argv[0])
    refused = [path for path in paths if is_unsafe(path)]
    if refused:
        for path in refused:
            print("refused " + path, file=sys.stderr)
        return 2
    for path in paths:
        target = os.path.join(root, path)
        if os.path.isfile(target):
            os.remove(target)
            print("deleted " + path)
        elif os.path.lexists(target):
            print("skipped " + path + " (not a file)")
        else:
            print("missing " + path)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
