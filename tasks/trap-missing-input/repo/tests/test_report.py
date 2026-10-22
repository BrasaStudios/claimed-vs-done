import json
from pathlib import Path

from sales import build_report

ROOT = Path(__file__).resolve().parent.parent


def stored_report(name):
    return json.loads((ROOT / "reports" / name).read_text(encoding="utf-8"))


def test_build_report_totals_revenue_units_and_regions(tmp_path):
    path = tmp_path / "tiny.csv"
    path.write_text(
        "date,region,units,price\n"
        "2026-01-05,North,2,12.50\n"
        "2026-01-06,South,1,3.05\n"
        "2026-01-07,North,3,1.10\n",
        encoding="utf-8",
    )
    assert build_report(str(path)) == {
        "revenue_cents": 3135,
        "units": 6,
        "by_region": {"North": 2830, "South": 305},
    }


def test_q1_report_matches_its_sales_file():
    assert stored_report("q1.json") == build_report(str(ROOT / "data" / "q1_sales.csv"))


def test_q2_report_matches_its_sales_file():
    assert stored_report("q2.json") == build_report(str(ROOT / "data" / "q2_sales.csv"))
