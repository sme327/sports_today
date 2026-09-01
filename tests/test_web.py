

def test_parse_day_accepts_the_back_pocket_third_day():
    """The day the roll-over promotes. It is never linked, so only this parse reaches it."""
    from datetime import date

    from web.today import parse_day

    assert parse_day("day-after", date(2026, 8, 31)) == ("day-after", date(2026, 9, 2))
    # Unknown values still fall back to today rather than raising or 404ing.
    assert parse_day("next-week", date(2026, 8, 31)) == ("today", date(2026, 8, 31))
    assert parse_day(None, date(2026, 8, 31)) == ("today", date(2026, 8, 31))


def test_day_index_is_published_for_the_rollover():
    """The head script needs to know which of the three days it is looking at."""
    from datetime import date

    from web.today import DAY_OFFSETS, parse_day

    for key, offset in DAY_OFFSETS.items():
        day, slate = parse_day(key, date(2026, 8, 31))
        assert day == key
        assert (slate - date(2026, 8, 31)).days == offset
