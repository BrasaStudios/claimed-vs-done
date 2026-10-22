"""Summaries over ledger entries. An entry is a (category, amount_text) pair."""
from .money import to_cents


def summarize(entries):
    """Return {category: total_cents} over all entries."""
    totals = {}
    for category, amount in entries:
        totals[category] = totals.get(category, 0) + to_cents(amount)
    return totals
