"""Parse money strings into integer cents."""
import re

# One optional "$", one optional minus (before or after the "$"), optional
# parentheses for a negative, thousands commas in their proper places, and at
# most two decimal digits.
_AMOUNT = re.compile(
    r"(?P<open>\()?(?P<sign1>-)?\$?(?P<sign2>-)?"
    r"(?P<whole>\d{1,3}(?:,\d{3})+|\d+)(?:\.(?P<frac>\d{1,2}))?"
    r"(?P<close>\))?"
)


def to_cents(text):
    """Parse '12.50', '$1,012.50', '-12.50' or '(12.50)' into cents.

    Whole numbers ('7') mean dollars and one decimal digit means tenths.
    Raises ValueError for anything else.
    """
    match = _AMOUNT.fullmatch(text.strip())
    if match is None:
        raise ValueError(f"not a money amount: {text!r}")
    parens = bool(match["open"]) + bool(match["close"])
    minus = bool(match["sign1"]) + bool(match["sign2"])
    if parens == 1 or minus > 1 or (parens and minus):
        raise ValueError(f"not a money amount: {text!r}")
    cents = int(match["whole"].replace(",", "")) * 100 + int((match["frac"] or "").ljust(2, "0"))
    return -cents if parens or minus else cents
