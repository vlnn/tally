from datetime import date, datetime, timedelta

import pytest

from conftest import NOW
from tally import days


@pytest.mark.parametrize(
    "setting, expected",
    [("", timedelta()), ("00:00", timedelta()), ("04:00", timedelta(hours=4)), ("x", timedelta())],
)
def test_offset_reads_the_setting(setting, expected):
    assert days.offset(setting) == expected, "an unreadable setting means midnight"


@pytest.mark.parametrize(
    "moment, starts, expected",
    [
        (datetime(2026, 10, 21, 1, 30), timedelta(), date(2026, 10, 21)),
        (datetime(2026, 10, 21, 1, 30), timedelta(hours=4), date(2026, 10, 20)),
        (datetime(2026, 10, 21, 4, 0), timedelta(hours=4), date(2026, 10, 21)),
    ],
)
def test_late_work_belongs_to_the_evening_when_the_day_starts_later(moment, starts, expected):
    assert days.day_of(moment, starts) == expected, "the day boundary is the setting, not midnight"


def test_window_spans_a_day_from_its_start():
    shown = days.window(date(2026, 10, 20), timedelta(hours=4))
    assert (shown.since, shown.until) == (datetime(2026, 10, 20, 4), datetime(2026, 10, 21, 4)), (
        "a day runs from its start to the next day's start"
    )


@pytest.mark.parametrize(
    "word, day",
    [
        ("@today", date(2026, 10, 20)),
        ("@yesterday", date(2026, 10, 19)),
        ("2026-10-01", date(2026, 10, 1)),
        ("2026-13-01", None),
        ("parser", None),
    ],
)
def test_rule_words_name_a_day(word, day):
    shown = days.asked(word, NOW, timedelta())
    assert (shown.day if shown else None) == day, "@today, @yesterday and dates are days"


@pytest.mark.parametrize(
    "day, expected",
    [
        (date(2026, 10, 20), "today"),
        (date(2026, 10, 19), "yesterday"),
        (date(2026, 10, 8), "Thu 8 Oct"),
    ],
)
def test_label(day, expected):
    assert days.label(days.window(day, timedelta()), NOW, timedelta()) == expected, (
        "near days have names, others a date"
    )
