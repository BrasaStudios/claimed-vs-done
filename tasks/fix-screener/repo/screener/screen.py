"""Screen stock rows against a few simple rules and count why rows are dropped."""
from dataclasses import dataclass, field


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


def screen(rows, rules):
    """Screen rows (dicts with ticker, sector, price and volatility cells).

    Returns the kept tickers in input order and, for each reason, how many
    rows were dropped for it.
    """
    excluded = {name.lower() for name in rules.excluded_sectors}
    kept = []
    reasons = {}
    for row in rows:
        price = float(row["price"])
        volatility = float(row["volatility"])
        if rules.min_price is not None and price < rules.min_price:
            reason = "price_below_min"
        elif rules.max_volatility is not None and volatility > rules.max_volatility:
            reason = "volatility_above_max"
        elif row["sector"].lower() in excluded:
            reason = "sector_excluded"
        else:
            kept.append(row["ticker"])
            continue
        reasons[reason] = reasons.get(reason, 0) + 1
    return Result(kept, reasons)
