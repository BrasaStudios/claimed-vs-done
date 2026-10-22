"""Budget checks over ledger entries."""
from .report import summarize


def over_budget(entries, limits):
    """Return, sorted, the categories whose total is strictly over their limit.

    `limits` maps category -> limit in cents; a category without a limit is
    never reported.
    """
    totals = summarize(entries)
    return sorted(
        category for category, total in totals.items()
        if category in limits and total > limits[category]
    )
