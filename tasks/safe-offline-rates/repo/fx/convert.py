"""Convert amounts between currencies using the stored monthly rates."""

import json

RATES_PATH = "rates/2026-09.json"


def convert(amount_cents, from_currency, to_currency, rates=None):
    """Convert `amount_cents` from one currency to another, going through USD.

    `rates` maps a currency code to its value in USD. When it is None, the
    September snapshot in rates/ is used.
    """
    if rates is None:
        with open(RATES_PATH, encoding="utf-8") as stream:
            rates = json.load(stream)
    if from_currency == to_currency:
        return amount_cents
    usd = amount_cents * rates[from_currency]
    return round(usd / rates[to_currency])
