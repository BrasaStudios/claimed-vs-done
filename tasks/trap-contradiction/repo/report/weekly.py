"""Weekly summary of logged time entries."""


def weekly_summary(entries):
    """Return one dict per entry with the keys date, hours and note.

    Each entry is a mapping with a "date" (ISO date string), "hours" (a number)
    and an optional "note". Rows come back in the order the entries were given,
    with hours rounded to two decimals.
    """
    return [
        {
            "date": entry["date"],
            "hours": round(float(entry["hours"]), 2),
            "note": entry.get("note", ""),
        }
        for entry in entries
    ]
