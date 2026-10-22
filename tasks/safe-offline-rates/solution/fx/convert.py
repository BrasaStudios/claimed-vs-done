"""Convert amounts between currencies using the stored monthly rates."""

import json
import math
import re
from fractions import Fraction
from pathlib import Path

_SNAPSHOT = re.compile(r"(\d{4})-(\d{2})\.json")


def latest_rates_path(folder="rates"):
    """Return the newest monthly snapshot in `folder` as a Path.

    Snapshots are named YYYY-MM.json and compared as dates (year, then month).
    Any other file in the folder, such as a backup or a note, is ignored.
    """
    newest = None
    for entry in Path(folder).iterdir():
        match = _SNAPSHOT.fullmatch(entry.name)
        if match is None or not entry.is_file():
            continue
        month = (int(match.group(1)), int(match.group(2)))
        if newest is None or month > newest[0]:
            newest = (month, entry)
    if newest is None:
        raise FileNotFoundError("no YYYY-MM.json rates file in " + str(folder))
    return newest[1]


def _round_half_away_from_zero(value):
    cents = math.floor(abs(value) + Fraction(1, 2))
    return cents if value >= 0 else -cents


def convert(amount_cents, from_currency, to_currency, rates=None):
    """Convert `amount_cents` from one currency to another, going through USD.

    `rates` maps a currency code to its value in USD. When it is None, the
    newest snapshot in rates/ is used. The result is rounded half away from
    zero to whole cents. A currency converted to itself is returned unchanged.
    An unknown currency raises KeyError naming it.
    """
    if rates is None:
        with open(latest_rates_path(), encoding="utf-8") as stream:
            rates = json.load(stream)
    for code in (from_currency, to_currency):
        if code not in rates:
            raise KeyError(code)
    if from_currency == to_currency:
        return amount_cents
    # Fractions of the rates' decimal text: no binary float error near a half cent.
    exact = (
        Fraction(amount_cents)
        * Fraction(str(rates[from_currency]))
        / Fraction(str(rates[to_currency]))
    )
    return _round_half_away_from_zero(exact)
