import json
from datetime import timedelta

import pytest

from conftest import NO_OFFSET, NOW
from tally import cli, present, store
from tally.scope import Scope


def test_typing_the_running_task_shows_it_running_with_its_time(db, sample):
    row = present.rows("parser #lexer", db, NOW, NO_OFFSET)[0]
    assert (row["title"], row["subtitle"]) == (
        "parser #lexer is running",
        "0:55 since 14:05 · ↩ keeps it running",
    ), "the length so far, not a fresh start"
    assert row["variables"] == {"action": "keep"}, "↩ does not restart it"


def test_a_partial_match_on_the_running_task_shows_it_running(db, sample):
    rows = present.rows("pa", db, NOW, NO_OFFSET)
    assert [r["title"] for r in rows] == ["Start pa", "parser #lexer is running"], (
        "found by search, still running"
    )


def test_the_running_row_stops_and_edits(db, sample):
    row = present.rows("parser #lexer", db, NOW, NO_OFFSET)[0]
    assert row["mods"]["alt"]["variables"] == {"action": "stop"}, "⌥↩ stops it"
    assert row["mods"]["ctrl"]["variables"] == {
        "action": "edit",
        "target": "task:parser #lexer",
    }, "⌃↩ edits it"


def test_the_work_list_sees_the_running_task_without_its_tag(db, logged):
    logged(14, 0, "parser #w")
    row = present.rows("parser", db, NOW, NO_OFFSET, scope=Scope("w", {}))[0]
    assert row["title"] == "parser #w is running", "parser in tw is parser #w"


def test_backfilling_the_running_task_still_plans(db, sample):
    row = present.rows("parser #lexer 14:00", db, NOW, NO_OFFSET)[0]
    assert (
        row["title"] == "Resume parser #lexer" and row["variables"]["at"] == "2026-10-20T14:00"
    ), "a time word is still a backfill"


@pytest.fixture
def run(db, capsys, mocker):
    mocker.patch("tally.bar.poke")

    def go(*argv, **env):
        code = cli.run(list(argv), env, now=NOW, db=db)
        return code, capsys.readouterr().out

    return go


def test_starting_the_running_task_again_keeps_it(run, db, sample):
    before = store.transitions(db)
    _code, out = run("act", "start", "parser #lexer")
    assert out.strip() == "Still parser #lexer · 0:55 since 14:05", "says how long it has run"
    assert store.transitions(db) == before, "and writes nothing, so its time is not reset"


def test_keep_says_so(run, sample):
    _code, out = run("act", "keep", "parser #lexer")
    assert out.strip() == "Still parser #lexer · 0:55 since 14:05", "the notification"


def test_starting_another_task_still_switches(run, db, sample):
    run("act", "start", "mail")
    assert store.running(db, NOW).line == "mail", "only the same task is kept"


def test_resume_rows_of_stopped_tasks_are_unchanged(db, sample):
    rows = present.rows("", db, NOW, NO_OFFSET)
    assert rows[0]["title"] == "Resume review pr 212", "only the running task changes"


def test_cli_filter_shows_the_running_time(run, sample):
    _code, out = run("filter", "parser #lexer")
    assert json.loads(out)["items"][0]["subtitle"].startswith("0:55 since 14:05"), "end to end"


def test_one_minute_in_is_one_minute(db, logged):
    logged(14, 59, "mail")
    assert present.rows("mail", db, NOW, timedelta())[0]["subtitle"].startswith("0:01"), "not 0"
