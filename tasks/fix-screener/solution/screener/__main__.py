"""Command line: python -m screener <csv_path> [options]."""
import argparse
import csv
import sys

from .screen import Rules, screen


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="python -m screener",
        description="Screen a CSV of stocks and report why rows were dropped.",
    )
    parser.add_argument("csv_path")
    parser.add_argument("--min-price", type=float, default=None)
    parser.add_argument("--max-volatility", type=float, default=None)
    parser.add_argument("--exclude-sector", action="append", default=[], metavar="NAME")
    args = parser.parse_args(argv)
    try:
        with open(args.csv_path, newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
    except FileNotFoundError:
        print(f"error: {args.csv_path} not found", file=sys.stderr)
        return 2
    rules = Rules(
        min_price=args.min_price,
        max_volatility=args.max_volatility,
        excluded_sectors=set(args.exclude_sector),
    )
    result = screen(rows, rules)
    print(f"kept: {len(result.kept)}")
    for reason in sorted(result.reasons):
        print(f"{reason}: {result.reasons[reason]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
