from datetime import datetime, timedelta

import pytest

from conftest import NO_OFFSET, NOW
from tally import cli, ribbon, store, tags


@pytest.mark.parametrize(
    "setting, expected",
    [
        ("w=work", {"w": "work"}),
        ("w=work, l = #lexer", {"w": "work", "l": "lexer"}),
        ("#W=Work\nl=lexer", {"w": "work", "l": "lexer"}),
        ("", {}),
        ("w, =work, x=", {}),
    ],
)
def test_aliases_read_the_setting(setting, expected):
    assert tags.aliases(setting) == expected, "short=full pairs, folded, junk ignored"


@pytest.mark.parametrize(
    "line, expected",
    [
        ("mail #w", "mail #work"),
        ("mail #W", "mail #work"),
        ("mail #work", "mail #work"),
        ("parser #Lexer #w", "parser #lexer #work"),
        ("issue#w stays", "issue#w stays"),
        ("no tags", "no tags"),
    ],
)
def test_canonical_spells_short_tags_out(line, expected):
    assert tags.canonical(line, {"w": "work"}) == expected, "#w reads as #work, case folded"


def test_of_lists_each_tag_once():
    assert tags.of("a #work b #lexer #work") == ["#work", "#lexer"], "in order, no repeats"


def block(hour, minutes, line):
    start = datetime(2026, 10, 20, hour)
    return store.Block(start, start + timedelta(minutes=minutes), line, start)


def test_totals_count_a_block_under_every_tag():
    found = tags.totals(
        [block(9, 30, "a #work #lexer"), block(10, 60, "b #work"), block(11, 15, "c")], NOW
    )
    assert found == [
        ("#work", timedelta(minutes=90)),
        ("#lexer", timedelta(minutes=30)),
        ("untagged", timedelta(minutes=15)),
    ], "biggest first, untagged last"


@pytest.fixture
def tagged(logged):
    for hour, minute, line in (
        (9, 0, "standup #team #work"),
        (9, 30, "mail #w"),
        (10, 0, "parser #lexer #W"),
        (11, 0, "lunch"),
        (12, 0, ""),
    ):
        logged(hour, minute, line)


def section(text):
    return text.split("**by tag**")[1].split("```")[1].strip().splitlines()


def test_today_shows_time_by_tag_with_aliases(db, tagged):
    _window, text = ribbon.shown(db, "@today", NOW, NO_OFFSET, {"w": "work"})
    assert section(text) == [
        "#work       2:00",
        "#lexer      1:00",
        "#team       0:30",
        "untagged    1:00",
    ], "#w and #W count as #work; a block counts for each of its tags"


def test_the_listing_keeps_what_was_typed(db, tagged):
    _window, text = ribbon.shown(db, "@today", NOW, NO_OFFSET, {"w": "work"})
    assert "09:30–10:00   0:30  mail #w" in text, "the blocks read as logged"


def test_aliases_merge_groups_on_the_ribbon(db, logged):
    logged(9, 0, "mail #w")
    logged(10, 0, "review #work")
    logged(11, 0, "")
    _window, text = ribbon.shown(db, "@today", NOW, NO_OFFSET, {"w": "work"})
    assert "█ #work       2:00" in text, "one group, one glyph"


def test_without_aliases_short_tags_stay_apart(db, logged):
    logged(9, 0, "mail #w")
    logged(10, 0, "review #work")
    logged(11, 0, "")
    _window, text = ribbon.shown(db, "@today", NOW, NO_OFFSET)
    assert section(text)[:2] == ["#w          1:00", "#work       1:00"], "no alias, two tags"


def test_no_tags_no_section(db, logged):
    logged(9, 0, "mail")
    logged(10, 0, "")
    _window, text = ribbon.shown(db, "@today", NOW, NO_OFFSET)
    assert "by tag" not in text, "nothing to aggregate"


def test_a_week_shows_tags_too(db, tagged):
    _window, text = ribbon.shown(db, "@week", NOW, NO_OFFSET, {"w": "work"})
    assert section(text)[0] == "#work       2:00", "ranges aggregate by tag as well"


@pytest.mark.parametrize(
    "env, expected",
    [({}, "#work       2:00"), ({"tag_aliases": ""}, "#w          1:30")],
)
def test_the_setting_defaults_to_w_for_work(db, tagged, capsys, env, expected):
    cli.run(["today"], env, now=NOW, db=db)
    assert section(capsys.readouterr().out)[0] == expected, (
        "unset means w=work; set empty means no aliases"
    )
