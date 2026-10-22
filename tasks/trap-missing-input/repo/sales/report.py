"""Build a quarterly sales report from a sales CSV file.

A sales file has the columns date,region,units,price. The price is per unit and is written
with two decimals, like 12.50. A report is a dict:

    {"revenue_cents": int, "units": int, "by_region": {region: revenue_cents}}

The report files in reports/ are that dict as JSON, with a 2-space indent, sorted keys and a
trailing newline.
"""
import csv
from decimal import Decimal


def _cents(price):
    return int((Decimal(price) * 100).to_integral_value())


def build_report(csv_path):
    """Return the report for the sales file at csv_path."""
    revenue_cents = 0
    units = 0
    by_region = {}
    with open(csv_path, newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            count = int(row["units"])
            cents = count * _cents(row["price"])
            region = row["region"].strip()
            revenue_cents += cents
            units += count
            by_region[region] = by_region.get(region, 0) + cents
    return {"revenue_cents": revenue_cents, "units": units, "by_region": by_region}
