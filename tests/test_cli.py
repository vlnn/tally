import json
from datetime import datetime

import pytest

from conftest import NOW
from tally import cli, gaps, store


@pytest.fixture
def env(tmp_path):
    return {"alfred_workflow_data": str(tmp_path / "data")}


@pytest.fixture
def run(env, db, capsys):
    def go(*argv, **extra):
        code = cli.run(list(argv), {**env, **extra}, now=NOW, db=db)
        return code, capsys.readouterr().out

    return go


def rows(out):
    return json.loads(out)["items"]


def test_filter_lists_rows(run, sample):
    code, out = run("filter", "")
    assert code == 0 and rows(out)[0]["title"] == "Resume review pr 212", "the bare list"


def test_filter_without_an_argument_is_the_bare_list(run, sample):
    _code, out = run("filter")
    assert rows(out)[-1]["title"] == "Today", "no argument is no text"


def test_start_records_a_transition_now(run, db):
    code, out = run("act", "start", "parser #lexer")
    assert code == 0 and out.strip() == "parser #lexer from 15:00", "start says what and when"
    assert store.running(db, NOW).line == "parser #lexer", "and it runs"


def test_start_at_a_time_from_the_variable(run, db, sample):
    run("act", "start", "mail", at="2026-10-20T14:30")
    found = store.blocks(store.transitions(db))
    assert [(b.line, b.start.hour, b.start.minute) for b in found[-2:]] == [
        ("parser #lexer", 14, 5),
        ("mail", 14, 30),
    ], "the backfilled start lands where the row said"
    assert found[-2].end == datetime(2026, 10, 20, 14, 30), "and ends what was running there"


def test_start_before_the_running_task_leaves_it_running(run, db, sample):
    run("act", "start", "coffee", at="2026-10-20T13:00")
    assert store.running(db, NOW).line == "parser #lexer", "the insert is in the past"
    lines = [b.line for b in store.blocks(store.transitions(db))]
    assert lines == [
        "standup #team",
        "mail",
        "parser #lexer",
        "coffee",
        "call with ola",
        "review pr 212",
        "parser #lexer",
    ], "coffee sits between the stop at 12:50 and the call at 13:10"


def test_start_needs_a_line(run, capsys):
    code, _ = run("act", "start", "")
    assert code == 2, "an empty line is a usage error, not a stop"


def test_stop_ends_the_running_task(run, db, sample):
    code, out = run("act", "stop")
    assert code == 0 and out.strip() == "parser #lexer · 0:55", "stop says what it ended"
    assert store.running(db, NOW) is None, "nothing runs after"


def test_stop_with_nothing_running(run, db):
    code, out = run("act", "stop")
    assert code == 0 and out.strip() == "Nothing was running", "a harmless no-op"
    assert store.transitions(db) == [], "and no transition is written"


def test_view_shows_the_day_and_polls_today(run, sample):
    _code, out = run("view", "2026-10-20")
    shown = json.loads(out)
    assert shown["rerun"] == 60.0 and shown["footer"] == "↩ copies the text", "today refreshes"
    assert shown["response"].startswith("**today"), "and shows today"


def test_view_of_a_past_day_does_not_poll(run, sample):
    _, out = run("view", "@yesterday")
    assert "rerun" not in json.loads(out), "yesterday will not change"


def test_view_of_a_non_day(run):
    _, out = run("view", "parser")
    assert "is not a day" in json.loads(out)["response"], "the view explains instead of failing"


def test_today_prints_the_text(run, sample):
    code, out = run("today")
    assert code == 0 and out.startswith("**today"), "the terminal gets the same text"


def test_day_starts_setting_is_read(run, db, logged):
    logged(1, 0, "night")
    logged(2, 0, "")
    _, out = run("filter", "", day_starts="04:00")
    assert rows(out)[-1]["subtitle"] == "0:00 logged · ↩ shows the day", "one o'clock was yesterday"


def test_unknown_command(run):
    code, _ = run("dance")
    assert code == 2, "usage"


def test_db_path_defaults_to_the_data_folder(env, tmp_path):
    assert cli.db_path(env) == tmp_path / "data" / "tally.db", "Alfred's data folder"
    chosen = {**env, "db_path": str(tmp_path / "mine")}
    assert cli.db_path(chosen) == tmp_path / "mine" / "tally.db", "the setting overrides"


def test_a_real_database_is_created_and_reused(env, tmp_path, capsys):
    cli.run(["act", "start", "parser"], env, now=NOW)
    cli.run(["filter", ""], env, now=NOW)
    out = capsys.readouterr().out.splitlines()[-1]
    assert rows(out)[0]["title"] == "Stop", "the second call sees the first call's transition"


@pytest.fixture
def idle(logged):
    logged(9, 0, "mail")
    logged(14, 30, "")


def test_claim_fills_the_gap_and_the_last_part_runs(run, db, idle, mocker):
    mocker.patch("subprocess.run").return_value.returncode = 1
    _code, out = run("act", "claim", "standup 10, review 5, api-design")
    assert out.strip() == "standup from 14:30, review from 14:40, api-design from 14:45", "said"
    active = store.running(db, NOW)
    assert (active.line, active.start) == ("api-design", datetime(2026, 10, 20, 14, 45)), (
        "the last part keeps running"
    )


@pytest.mark.parametrize(
    "text, said",
    [
        ("standup 40, api", "0:40 of parts is more than the 0:30 gap"),
        ("standup, api", "Give every part but the last a length: standup 30, api-design"),
    ],
)
def test_claim_refuses_what_does_not_fit(run, db, idle, text, said):
    _code, out = run("act", "claim", text)
    assert out.strip() == said and store.running(db, NOW) is None, "nothing written"


def test_claim_with_a_task_running(run, sample):
    _code, out = run("act", "claim", "standup 10, api")
    assert out.strip() == "Nothing unclaimed to split", "a running task leaves no gap"


def test_filter_offers_the_display_on_time(run, idle, mocker):
    lines = ["2026-10-20 14:42:13 +0200 Notification  \tDisplay is turned on"]
    mocker.patch.object(gaps, "pmset_lines", return_value=lines)
    _code, out = run("filter", "api-design")
    assert [row["title"] for row in rows(out)][:3] == [
        "Start api-design",
        "Start api-design since 14:42",
        "Start api-design since 14:30",
    ], "the power log's display-on time, inside the gap"


def test_filter_never_reads_the_power_log_for_bare_t(run, idle, mocker):
    read = mocker.patch.object(gaps, "pmset_lines")
    _code, out = run("filter", "")
    assert rows(out)[0]["title"] == "Unclaimed 0:30 since 14:30", "the gap on top"
    read.assert_not_called()


def test_the_first_step_of_the_ladder_is_the_threshold_in_t(run, idle):
    _code, out = run("filter", "", unclaimed_ladder="40,50,60,70")
    assert not rows(out)[0]["title"].startswith("Unclaimed"), "30 min is under a 40 min first step"


def test_the_start_of_a_split_ends_the_gap(run, db, idle, mocker):
    mocker.patch("subprocess.run").return_value.returncode = 1
    run("act", "claim", "standup 10, api")
    _code, out = run("filter", "")
    assert not rows(out)[0]["title"].startswith("Unclaimed"), "claimed time is not unclaimed"
