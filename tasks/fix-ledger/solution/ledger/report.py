"""Summaries over ledger entries. An entry is a (category, amount_text) pair."""
from .money import to_cents


def summarize(entries):
    """Return {category: total_cents} over all entries."""
    totals = {}
    for category, amount in entries:
        totals[category] = totals.get(category, 0) + to_cents(amount)
    return totals


def net(entries):
    """Return the sum of every entry's amount in cents (0 for no entries)."""
    return sum(to_cents(amount) for _, amount in entries)
