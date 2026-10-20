import json
from datetime import timedelta

import pytest

from conftest import NO_OFFSET, NOW
from tally import cli, present
from tally.scope import Scope, work

WORK = Scope("w", {"w": "work"})


def titles(rows):
    return [row["title"] for row in rows]


@pytest.mark.parametrize(
    "line, held",
    [
        ("parser #w", True),
        ("parser #W", True),
        ("parser #work", True),
        ("parser #lexer #work", True),
        ("parser", False),
        ("parser #web", False),
        ("issue#w", False),
    ],
)
def test_holds(line, held):
    assert WORK.holds(line) is held, "a line is work when it carries #w or what it stands for"


@pytest.mark.parametrize(
    "line, expected",
    [
        ("parser", "parser #w"),
        ("parser #work", "parser #work"),
        ("parser #lexer", "parser #lexer #w"),
    ],
)
def test_apply_adds_the_tag_only_when_missing(line, expected):
    assert WORK.apply(line) == expected, "the tag is added once, after what was typed"


def test_everything_holds_everything():
    assert Scope().holds("anything") and Scope().apply("anything") == "anything", (
        "no tag, no change"
    )


@pytest.mark.parametrize("setting, tag", [("", "w"), ("#work", "work"), ("Job", "job")])
def test_work_reads_the_setting(setting, tag):
    assert work(setting, {}).tag == tag, "the work tag, w unless set"


@pytest.fixture
def mixed(logged):
    for hour, minute, line in (
        (9, 0, "standup #work"),
        (9, 30, "groceries"),
        (10, 0, "parser #w"),
        (11, 0, "dentist"),
        (12, 0, "review #W"),
        (13, 0, "reading"),
    ):
        logged(hour, minute, line)


def test_the_work_list_shows_only_work(db, mixed):
    rows = present.rows("", db, NOW, NO_OFFSET, scope=WORK)
    assert titles(rows) == [
        "Resume review #W",
        "Resume parser #w",
        "Resume standup #work",
        "Stop",
        "Today",
    ], "only tasks tagged #w or #work, newest first; stop and today stay"


def test_the_work_today_row_says_the_work_total(db, mixed):
    rows = present.rows("", db, NOW, NO_OFFSET, scope=WORK)
    assert rows[-1]["subtitle"] == "6:00 logged · #work 2:30 · ↩ shows the day", (
        "the day and the share of it that was work"
    )


def test_the_plain_list_is_unchanged(db, mixed):
    rows = present.rows("", db, NOW, NO_OFFSET)
    assert titles(rows)[:2] == ["Resume review #W", "Resume dentist"], "everything, as before"


def test_a_new_work_task_gets_the_tag(db, mixed):
    rows = present.rows("write tests", db, NOW, NO_OFFSET, scope=WORK)
    assert (rows[0]["title"], rows[0]["arg"]) == ("Start write tests #w", "write tests #w"), (
        "the started line carries #w"
    )


def test_a_work_task_typed_without_its_tag_resumes(db, mixed):
    rows = present.rows("parser", db, NOW, NO_OFFSET, scope=WORK)
    assert (rows[0]["title"], rows[0]["arg"]) == ("Resume parser #w", "parser #w"), (
        "parser in the work list is parser #w"
    )


def test_an_alias_spelling_resumes_the_same_task(db, mixed):
    rows = present.rows("standup", db, NOW, NO_OFFSET, scope=WORK)
    assert rows[0]["title"] == "Resume standup #work", "#w and #work are one tag, so one task"


def test_work_matches_leave_out_other_tasks(db, mixed):
    rows = present.rows("re", db, NOW, NO_OFFSET, scope=WORK)
    assert titles(rows) == ["Start re #w", "Resume review #W"], "reading is not work"


def test_a_backfilled_work_task_gets_the_tag(db, mixed):
    rows = present.rows("call 14:30", db, NOW, NO_OFFSET, scope=WORK)
    assert rows[0]["arg"] == "call #w" and rows[0]["variables"]["at"] == "2026-10-20T14:30", (
        "the time word still reads, the tag goes on the line"
    )


def test_command_words_work_in_the_work_list(db, mixed):
    assert present.rows("st", db, NOW, NO_OFFSET, scope=WORK)[0]["title"] == "Stop", "st stops"


def test_cli_filter_work(db, mixed, capsys):
    cli.run(["filter-work", "x"], {"work_tag": "w"}, now=NOW, db=db)
    rows = json.loads(capsys.readouterr().out)["items"]
    assert rows[0]["title"] == "Start x #w", "tw reads the work tag and the aliases"


def test_cli_filter_work_with_another_tag(db, logged, capsys):
    logged(9, 0, "invoice #job")
    cli.run(["filter-work", ""], {"work_tag": "job"}, now=NOW, db=db)
    rows = json.loads(capsys.readouterr().out)["items"]
    assert rows[-1]["subtitle"] == "6:00 logged · #job 6:00 · ↩ shows the day", "any tag will do"


def test_plain_t_now_resumes_across_alias_spellings(db, logged):
    logged(9, 0, "parser #work")
    logged(10, 0, "")
    rows = present.rows("parser #w", db, NOW, timedelta(), scope=Scope("", {"w": "work"}))
    assert rows[0]["title"] == "Resume parser #work", "t parser #w finds parser #work too"
