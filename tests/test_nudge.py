import plistlib
from datetime import datetime, time, timedelta

import pytest

from conftest import NOW
from tally import cli, nudge, present

AT_DESK = timedelta(seconds=5)
WEEKDAY = nudge.Settings(timedelta(minutes=15), time(9), time(19), False)


@pytest.mark.parametrize(
    "env, expected",
    [
        ({}, WEEKDAY),
        ({"nudge_every": "30"}, WEEKDAY._replace(every=timedelta(minutes=30))),
        ({"nudge_every": "0"}, WEEKDAY._replace(every=timedelta())),
        ({"nudge_every": "soon"}, WEEKDAY),
        ({"nudge_hours": "8:30 - 17:00"}, WEEKDAY._replace(since=time(8, 30), until=time(17))),
        ({"nudge_hours": "late"}, WEEKDAY),
        ({"nudge_hours": "25:00-26:00"}, WEEKDAY),
        ({"nudge_weekends": "1"}, WEEKDAY._replace(weekends=True)),
    ],
)
def test_settings(env, expected):
    assert nudge.settings(env) == expected, "unreadable settings fall back to the defaults"


@pytest.mark.parametrize(
    "now, weekends, expected",
    [
        (datetime(2026, 10, 20, 15, 0), False, True),
        (datetime(2026, 10, 20, 8, 59), False, False),
        (datetime(2026, 10, 20, 19, 0), False, False),
        (datetime(2026, 10, 24, 15, 0), False, False),
        (datetime(2026, 10, 24, 15, 0), True, True),
    ],
)
def test_in_hours(now, weekends, expected):
    assert nudge.in_hours(now, WEEKDAY._replace(weekends=weekends)) == expected, (
        "between the hours, on weekdays unless weekends are on"
    )


def test_a_running_task_asks_to_be_confirmed(db, sample):
    said = nudge.message(db, NOW, WEEKDAY, AT_DESK)
    assert said == "Still on parser #lexer · 0:55? Ignore to keep it.", "ignoring confirms"


def test_a_gap_asks_too(db, logged):
    logged(9, 0, "mail")
    logged(13, 40, "")
    said = nudge.message(db, NOW, WEEKDAY, AT_DESK)
    assert said == "Nothing running since 13:40. Ignore if you're away.", "absence is confirmed"


def test_an_empty_day_asks_to_start(db, logged):
    logged(17, 0, "", day=NOW.date() - timedelta(days=1))
    assert nudge.message(db, NOW, WEEKDAY, AT_DESK) == "Nothing logged today. Type t to start.", (
        "yesterday's stop is not today's gap"
    )


def test_an_empty_database_asks_to_start(db):
    assert nudge.message(db, NOW, WEEKDAY, AT_DESK) == "Nothing logged today. Type t to start."


@pytest.mark.parametrize(
    "case, chosen, idle, last_minutes_ago",
    [
        ("just logged", WEEKDAY, AT_DESK, 10),
        ("away from the Mac", WEEKDAY, timedelta(minutes=20), 60),
        ("outside the hours", WEEKDAY._replace(until=time(14)), AT_DESK, 60),
        ("turned off", WEEKDAY._replace(every=timedelta()), AT_DESK, 60),
    ],
)
def test_silence(db, logged, case, chosen, idle, last_minutes_ago):
    at = NOW - timedelta(minutes=last_minutes_ago)
    logged(at.hour, at.minute, "parser")
    assert nudge.message(db, NOW, chosen, idle) == "", f"no nudge when {case}"


def test_a_nudge_is_due_again_after_the_interval(db, logged):
    logged(14, 45, "parser")
    assert nudge.message(db, NOW, WEEKDAY, AT_DESK).startswith("Still on parser"), (
        "fifteen minutes after the last switch the question comes back"
    )


def test_user_idle_reads_the_hid_count(mocker):
    mocker.patch("subprocess.run").return_value.stdout = '  | "HIDIdleTime" = 90000000000\n'
    assert nudge.user_idle() == timedelta(seconds=90), "nanoseconds to a timedelta"


def test_user_idle_without_ioreg(mocker):
    mocker.patch("subprocess.run", side_effect=FileNotFoundError("ioreg"))
    assert nudge.user_idle() == timedelta(), "unknown idle time is treated as present"


def test_the_agent_asks_alfred_to_run_the_trigger():
    made = nudge.agent(WEEKDAY)
    assert made["StartInterval"] == 900 and made["ProgramArguments"][0] == "/usr/bin/osascript", (
        "launchd runs osascript every fifteen minutes"
    )
    assert 'run trigger "nudge" in workflow "com.anokhin.tally"' in made["ProgramArguments"][2], (
        "and osascript asks Alfred, so the check has the workflow's settings"
    )


@pytest.fixture
def agents(tmp_path, mocker):
    mocker.patch.object(nudge, "agent_path", return_value=tmp_path / f"{nudge.LABEL}.plist")
    return mocker.patch("subprocess.run")


def test_turning_on_writes_and_loads_the_agent(agents):
    path = nudge.turn_on(WEEKDAY)
    with open(path, "rb") as handle:
        assert plistlib.load(handle)["Label"] == nudge.LABEL, "a launchd plist"
    called = [call.args[0][:2] for call in agents.call_args_list]
    assert called == [["launchctl", "bootout"], ["launchctl", "bootstrap"]], (
        "an old copy is unloaded before the new one loads"
    )


def test_turning_off_unloads_and_removes(agents):
    path = nudge.turn_on(WEEKDAY)
    nudge.turn_off()
    assert not path.exists(), "the plist is gone"


@pytest.fixture
def run(db, capsys):
    def go(*argv, **env):
        code = cli.run(list(argv), env, now=NOW, db=db)
        return code, capsys.readouterr().out

    return go


def test_nudge_prints_the_message_for_alfreds_notification(run, sample, mocker):
    mocker.patch.object(nudge, "user_idle", return_value=AT_DESK)
    mocker.patch("tally.bar.poke")
    _code, out = run("nudge")
    assert out.strip() == "Still on parser #lexer · 0:55? Ignore to keep it.", "the notification"


def test_nudge_prints_nothing_when_quiet(run, logged, mocker):
    mocker.patch.object(nudge, "user_idle", return_value=AT_DESK)
    logged(14, 50, "parser")
    _code, out = run("nudge")
    assert out == "", "an empty output posts no notification"


def test_act_nudges_toggles(run, agents):
    _code, on = run("act", "nudges")
    _code, off = run("act", "nudges")
    assert (on.strip(), off.strip()) == (
        "Nudges on: every 15 min, 09:00–19:00 weekdays",
        "Nudges off",
    ), "the same action turns them on and off"


def test_t_nudge_offers_the_toggle(db, sample):
    rows = present.rows("nu", db, NOW, timedelta(), nudges=lambda: (False, "every 15 min"))
    assert (rows[0]["title"], rows[0]["variables"]) == (
        "Turn nudges on",
        {"action": "nudges"},
    ), "two letters reach it"
    rows = present.rows("nudge", db, NOW, timedelta(), nudges=lambda: (True, "every 15 min"))
    assert rows[0]["title"] == "Turn nudges off", "and it says which way it goes"
