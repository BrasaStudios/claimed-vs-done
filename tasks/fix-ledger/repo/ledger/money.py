"""Parse money strings into integer cents."""


def to_cents(text):
    """Parse '12.50' or '$1,012.50' into cents. Whole numbers ('7') mean dollars."""
    s = text.strip().replace("$", "").replace(",", "")
    if "." in s:
        dollars, cents = s.split(".", 1)
        cents = (cents + "00")[:2]
    else:
        dollars, cents = s, "00"
    return int(dollars or "0") * 100 + int(cents)
