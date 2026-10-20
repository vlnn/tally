from datetime import datetime, timedelta

import pytest

from conftest import NO_OFFSET, NOW
from tally import days, ribbon, store

TODAY = days.window(NOW.date(), NO_OFFSET)


def rendered(db, now=NOW):
    return ribbon.render(
        TODAY, store.blocks_within(db, TODAY.since, TODAY.until, now), now, NO_OFFSET
    )


def strip_of(text):
    return text.split("```")[1].splitlines()[2]


@pytest.mark.parametrize(
    "line, group", [("parser #lexer", "#lexer"), ("Call #Team now", "#team"), ("mail", "mail")]
)
def test_groups_by_first_tag_else_line(line, group):
    assert ribbon.group_of(line) == group, "a tag groups, a bare line is its own group"


def test_glyphs_go_by_rank_of_the_days_total(db, sample):
    found = ribbon.groups(store.blocks_within(db, TODAY.since, TODAY.until, NOW), NOW)
    assert [(g.name, g.glyph) for g in found[:2]] == [("#lexer", "█"), ("#team", "▓")], (
        "the biggest group is the darkest glyph"
    )


def test_strip_is_a_cell_per_quarter_hour(db, sample):
    strip = strip_of(rendered(db))
    assert len(strip) == (22 - 6) * 4, "06 to 22 is 64 cells"
    assert strip[(9 - 6) * 4 + 1] == "▓", "09:15 is standup, the second group"
    assert strip[(10 - 6) * 4 + 1] == "░", "10:15 is untracked, between blocks"
    assert strip[(15 - 6) * 4] == "▶", "15:00 is now"
    assert strip[-1] == "·", "the evening is empty, not untracked"


def test_strip_widens_for_late_work(db, logged):
    logged(22, 30, "late")
    logged(23, 15, "")
    strip = strip_of(rendered(db, datetime(2026, 10, 20, 23, 30)))
    assert len(strip) == (24 - 6) * 4, "a block past 22 extends the strip to midnight"


def test_strip_widens_for_early_work(db, logged):
    logged(5, 0, "early")
    logged(6, 0, "")
    assert len(strip_of(rendered(db))) == (22 - 5) * 4, "a block before 06 extends the strip back"


def test_backfilled_blocks_have_their_own_glyph(db, logged):
    logged(9, 0, "mail", logged_at=datetime(2026, 10, 20, 10, 0))
    logged(10, 0, "")
    text = rendered(db)
    assert strip_of(text)[(9 - 6) * 4] == "▚", "a backfilled block is honest about it"
    assert "▚ backfilled" in text, "and the legend says so"


def test_totals_and_listing(db, sample):
    text = rendered(db)
    assert "█ #lexer          2:40" in text, "totals by group"
    assert "░ untracked       1:15" in text, "the gaps between blocks are counted"
    assert "14:05–now     0:55  parser #lexer" in text, "the open block ends at now"


def test_heading_tallies_the_day(db, sample):
    assert rendered(db).startswith("**today · Tue 20 Oct** · 4:40 logged"), "the day and its sum"


def test_empty_day(db):
    assert rendered(db).endswith("Nothing logged."), "an empty day says so instead of drawing"


def test_shown_names_a_day(db, sample):
    window, text = ribbon.shown(db, "@yesterday", NOW, NO_OFFSET)
    assert window.day == NOW.date() - timedelta(days=1) and "Nothing logged." in text, (
        "yesterday is empty in the sample"
    )
    assert ribbon.shown(db, "parser", NOW, NO_OFFSET) is None, "a non-day word is refused"


def test_a_week_is_a_line_per_day_with_shared_totals(db, sample, logged):
    logged(10, 0, "mail", day=NOW.date() - timedelta(days=1))
    logged(12, 0, "", day=NOW.date() - timedelta(days=1))
    _window, text = ribbon.shown(db, "@week", NOW, NO_OFFSET)
    lines = text.split("```")[1].splitlines()
    assert lines[2].startswith("Mon 19  ") and lines[2].endswith("   2:00"), "yesterday's line"
    assert lines[3].startswith("Tue 20  ") and lines[3].endswith("   4:40"), "today's line"
    assert len(lines) == 4, "future days are not drawn"
    assert "▓ mail            2:30" in text, "totals span the days"
    assert "░ untracked       1:15" in text, "untracked is counted within each day, not between"
    assert text.startswith("**this week · 19 Oct – 25 Oct** · 6:40 logged"), "the range heading"


def test_an_empty_range(db):
    assert ribbon.shown(db, "@lastmonth", NOW, NO_OFFSET)[1].endswith("Nothing logged."), "empty"
