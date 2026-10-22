"""Screen stock rows against a few simple rules and count why rows are dropped."""
import math
from dataclasses import dataclass, field

REASONS = ("missing_field", "price_below_min", "sector_excluded", "volatility_above_max")


@dataclass
class Rules:
    """Limits to apply. A limit of None is not applied."""

    min_price: float | None = None
    max_volatility: float | None = None
    excluded_sectors: set[str] = field(default_factory=set)


@dataclass
class Result:
    kept: list[str]
    reasons: dict[str, int]


def _number(cell):
    """Return the cell as a finite float, or None when it is blank or not a number."""
    try:
        value = float(cell)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def screen(rows, rules):
    """Screen rows (dicts with ticker, sector, price and volatility cells).

    Returns the kept tickers in input order and, for each of the four reasons,
    how many rows failed it. A row that fails several rules counts toward each
    of them. A row with a blank sector or a blank or non-numeric price or
    volatility counts once toward missing_field and its other rules are skipped.
    """
    excluded = {name.casefold() for name in rules.excluded_sectors}
    kept = []
    reasons = dict.fromkeys(REASONS, 0)
    for row in rows:
        price = _number(row["price"])
        volatility = _number(row["volatility"])
        sector = row["sector"]
        if price is None or volatility is None or not (sector or "").strip():
            reasons["missing_field"] += 1
            continue
        failed = []
        if rules.min_price is not None and price < rules.min_price:
            failed.append("price_below_min")
        if rules.max_volatility is not None and volatility > rules.max_volatility:
            failed.append("volatility_above_max")
        if sector.casefold() in excluded:
            failed.append("sector_excluded")
        for reason in failed:
            reasons[reason] += 1
        if not failed:
            kept.append(row["ticker"])
    return Result(kept, reasons)
