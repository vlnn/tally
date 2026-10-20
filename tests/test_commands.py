import pytest

from conftest import NO_OFFSET, NOW
from tally import commands, present


@pytest.mark.parametrize(
    "text, kinds",
    [
        ("stop", ["stop"]),
        ("st", ["stop"]),
        ("s", []),
        ("to", ["@today"]),
        ("Today", ["@today"]),
        ("@today", ["@today"]),
        ("yes", ["@yesterday"]),
        ("we", ["@week"]),
        ("this w", ["@week"]),
        ("la", ["@lastweek", "@lastmonth"]),
        ("last week", ["@lastweek"]),
        ("@lastweek", ["@lastweek"]),
        ("mo", ["@month"]),
        ("ba", ["bar"]),
        ("parser", []),
        ("stop now", []),
    ],
)
def test_a_command_is_named_from_two_letters(text, kinds):
    found = [c.word or c.kind for c in commands.named(text)]
    assert found == kinds, "a prefix of a command's name names it"


def titles(rows):
    return [row["title"] for row in rows]


def test_typing_stop_puts_stop_first(db, sample):
    rows = present.rows("stop", db, NOW, NO_OFFSET)
    assert titles(rows)[:2] == ["Stop", "Start stop"], "the command, then the task of that name"
    assert rows[0]["variables"] == {"action": "stop"}, "↩ stops"


def test_typing_st_stops_and_still_finds_standup(db, sample):
    rows = present.rows("st", db, NOW, NO_OFFSET)
    assert titles(rows) == ["Stop", "Start st", "Resume standup #team"], (
        "two letters reach stop; matching tasks stay below"
    )


def test_stop_with_nothing_running_says_so(db, logged):
    logged(9, 0, "mail")
    logged(9, 30, "")
    rows = present.rows("stop", db, NOW, NO_OFFSET)
    assert rows[0]["title"] == "Nothing to stop" and rows[0]["valid"] is False, "says, not acts"


@pytest.mark.parametrize(
    "text, title, word",
    [
        ("today", "Today", "@today"),
        ("to", "Today", "@today"),
        ("yesterday", "Yesterday", "@yesterday"),
        ("week", "This week", "@week"),
        ("last week", "Last week", "@lastweek"),
        ("month", "This month", "@month"),
    ],
)
def test_typing_a_day_word_opens_the_view(db, sample, text, title, word):
    rows = present.rows(text, db, NOW, NO_OFFSET)
    assert (rows[0]["title"], rows[0]["arg"], rows[0]["variables"]) == (
        title,
        word,
        {"action": "view"},
    ), "the view row comes first and ↩ opens it"


def test_an_at_word_lists_only_views(db, sample):
    assert titles(present.rows("@la", db, NOW, NO_OFFSET)) == ["Last week", "Last month"], (
        "@ is never a task, so no Start row"
    )


def test_an_unknown_at_word_explains(db, sample):
    rows = present.rows("@someday", db, NOW, NO_OFFSET)
    assert rows[0]["title"] == "@someday is not a day" and rows[0]["valid"] is False, "explains"


def test_a_bad_date_explains(db, sample):
    rows = present.rows("2026-13-01", db, NOW, NO_OFFSET)
    assert rows[0]["title"] == "2026-13-01 is not a day", "a date that is not one explains"


def test_alt_stops_from_any_task_row(db, sample):
    rows = present.rows("", db, NOW, NO_OFFSET)
    resume = [r for r in rows if r["title"].startswith("Resume")]
    assert all(
        r["mods"]["alt"]
        == {"arg": "", "subtitle": "⌥↩ stop parser #lexer · 0:55", "variables": {"action": "stop"}}
        for r in resume
    ), "t ⌥↩ stops whatever runs"
    typed = present.rows("write tests", db, NOW, NO_OFFSET)[0]
    assert typed["mods"]["alt"]["variables"] == {"action": "stop"}, "the start row too"


def test_alt_does_nothing_when_idle(db, logged):
    logged(9, 0, "mail")
    logged(9, 30, "")
    row = present.rows("", db, NOW, NO_OFFSET)[0]
    assert row["mods"]["alt"]["valid"] is False, "nothing to stop"
