from report import weekly_summary


def test_hours_are_rounded_to_two_decimals():
    rows = weekly_summary([{"date": "2026-03-02", "hours": 1.23456, "note": "standup"}])
    assert rows == [{"date": "2026-03-02", "hours": 1.23, "note": "standup"}]
