import json
import plistlib
from datetime import datetime, timedelta

import pytest

from conftest import NO_OFFSET, NOW
from tally import cli, present, remind


@pytest.mark.parametrize(
    "text, at, said",
    [
        ("+15m stop the work", datetime(2026, 10, 20, 15, 15), "stop the work"),
        ("+15 stop the work", datetime(2026, 10, 20, 15, 15), "stop the work"),
        ("+15 min stop the work", datetime(2026, 10, 20, 15, 15), "stop the work"),
        ("+15 m stop the work", datetime(2026, 10, 20, 15, 15), "stop the work"),
        ("+15min stop", datetime(2026, 10, 20, 15, 15), "stop"),
        ("+15 minutes stop", datetime(2026, 10, 20, 15, 15), "stop"),
        ("+15 Min stop", datetime(2026, 10, 20, 15, 15), "stop"),
        ("+2 h review", datetime(2026, 10, 20, 17, 0), "review"),
        ("+1 hour 30 min call", datetime(2026, 10, 20, 16, 30), "call"),
        ("+1h 30m call", datetime(2026, 10, 20, 16, 30), "call"),
        ("+1h30 call", datetime(2026, 10, 20, 16, 30), "call"),
        ("+15 meeting notes", datetime(2026, 10, 20, 15, 15), "meeting notes"),
        ("+15 m", None, ""),
        ("+30s tea", datetime(2026, 10, 20, 15, 0, 30), "tea"),
        ("+30 sec tea", datetime(2026, 10, 20, 15, 0, 30), "tea"),
        ("+30 seconds tea", datetime(2026, 10, 20, 15, 0, 30), "tea"),
        ("+1m30s tea", datetime(2026, 10, 20, 15, 1, 30), "tea"),
        ("+1 min 30 sec tea", datetime(2026, 10, 20, 15, 1, 30), "tea"),
        ("+90s tea", datetime(2026, 10, 20, 15, 1, 30), "tea"),
        ("+1h stretch", datetime(2026, 10, 20, 16, 0), "stretch"),
        ("+1h30m call mum", datetime(2026, 10, 20, 16, 30), "call mum"),
        ("21:00 stand up", datetime(2026, 10, 20, 21, 0), "stand up"),
        ("9PM go out", datetime(2026, 10, 20, 21, 0), "go out"),
        ("9pm go out", datetime(2026, 10, 20, 21, 0), "go out"),
        ("9:30pm read", datetime(2026, 10, 20, 21, 30), "read"),
        ("12am sleep", datetime(2026, 10, 21, 0, 0), "sleep"),
        ("12pm lunch", datetime(2026, 10, 21, 12, 0), "lunch"),
        ("9:00 standup", datetime(2026, 10, 21, 9, 0), "standup"),
        ("14:30 review", datetime(2026, 10, 21, 14, 30), "review"),
    ],
)
def test_a_time_first_is_a_reminder(text, at, said):
    found = remind.wanted(text, NOW)
    if at is None:
        assert found.problem == "Type what to remind you of after the time", "a time alone asks"
        return
    assert found == remind.Wanted(at, said), (
        "+duration from now, with or without a unit, or a clock time today or else tomorrow"
    )


@pytest.mark.parametrize(
    "text",
    [
        "parser",
        "parser 14:30",
        "pr 212",
        "-15m coffee",
        "+ x",
        "+0m x",
        "+0 x",
        "+ m x",
        "25:00 x",
        "13pm x",
        "",
    ],
)
def test_anything_else_is_not_a_reminder(text):
    assert remind.wanted(text, NOW) is None, "a time last is a backfill, words are a task"


def test_a_time_alone_asks_for_the_text():
    assert remind.wanted("+15m", NOW).problem == "Type what to remind you of after the time"


def test_the_row_says_when(db):
    row = present.rows("21:00 stand up", db, NOW, NO_OFFSET)[0]
    assert (row["title"], row["subtitle"]) == (
        "Remind 21:00: stand up",
        "in 6:00 · in big letters then · ↩ sets it",
    ), "the time and how far away"
    assert (row["arg"], row["variables"]) == ("21:00 stand up", {"action": "remember"})


@pytest.mark.parametrize(
    "text, title, subtitle",
    [
        ("+15m stop", "Remind 15:15: stop", "in 15 min · in big letters then · ↩ sets it"),
        (
            "9:00 standup",
            "Remind tomorrow 09:00: standup",
            "in 18:00 · in big letters then · ↩ sets it",
        ),
    ],
)
def test_near_and_tomorrow(db, text, title, subtitle):
    row = present.rows(text, db, NOW, NO_OFFSET)[0]
    assert (row["title"], row["subtitle"]) == (title, subtitle), "minutes when close, tomorrow said"


def test_a_reminder_row_is_alone(db, sample):
    assert len(present.rows("+15m stop", db, NOW, NO_OFFSET)) == 1, "no Start rows below it"


def test_the_agent_fires_once_at_that_minute():
    made = remind.agent(remind.Reminder(7, datetime(2026, 10, 20, 21, 0), "stand up"), NOW)
    assert made["Label"] == "com.anokhin.tally.remind.7", "one agent per reminder"
    assert made["StartCalendarInterval"] == {"Month": 10, "Day": 20, "Hour": 21, "Minute": 0}, (
        "launchd's calendar time, fired on wake if the Mac slept through it"
    )
    assert (
        'run trigger "remind" in workflow "com.anokhin.tally" with argument "7"'
        in made["ProgramArguments"][2]
    ), "Alfred is asked to run the remind trigger with the id"


@pytest.fixture
def agents(tmp_path, mocker):
    mocker.patch.object(remind, "agent_folder", return_value=tmp_path)
    mocker.patch("tally.bar.poke")
    mocker.patch("tally.bar.installed", return_value=False)
    return mocker.patch("subprocess.run")


@pytest.fixture
def run(db, capsys):
    def go(*argv, **env):
        code = cli.run(list(argv), env, now=NOW, db=db)
        return code, capsys.readouterr().out

    return go


def test_remember_stores_and_schedules(run, db, agents, tmp_path):
    _code, out = run("act", "remember", "21:00 stand up")
    assert out.strip() == "Reminder set for 21:00: stand up", "the notification"
    with open(tmp_path / "com.anokhin.tally.remind.1.plist", "rb") as handle:
        assert plistlib.load(handle)["StartCalendarInterval"]["Hour"] == 21, "the agent is written"
    assert agents.call_args.args[0][:2] == ["launchctl", "bootstrap"], "and loaded"
    assert [r.text for r in remind.pending(db)] == ["stand up"], "and pending"


def test_pending_reminders_are_listed_and_cancelled(run, db, agents, sample, tmp_path):
    run("act", "remember", "21:00 stand up")
    rows = present.rows("", db, NOW, NO_OFFSET)
    row = next(r for r in rows if r["title"].startswith("⏰"))
    assert (row["title"], row["subtitle"]) == ("⏰ 21:00 stand up", "in 6:00 · ↩ shows it now")
    assert [r["title"] for r in rows][-1] == "Today", "above Today"
    _code, out = run("act", "forget", row["mods"]["alt"]["arg"])
    assert out.strip() == "Cancelled: stand up" and remind.pending(db) == [], "gone"
    assert not (tmp_path / "com.anokhin.tally.remind.1.plist").exists(), "and so is its agent"


def test_firing_prints_the_text_for_large_type_and_cleans_up(run, db, agents, tmp_path):
    run("act", "remember", "+15m stop the work")
    _code, out = run("remind", "1")
    assert out.strip() == "stop the work", "Large Type shows what was asked"
    assert remind.pending(db) == [] and not (tmp_path / "com.anokhin.tally.remind.1.plist").exists()


def test_firing_also_notifies_through_swiftbar(run, db, agents, mocker):
    mocker.patch("tally.bar.installed", return_value=True)
    notify = mocker.patch("tally.bar.notify")
    run("act", "remember", "+15m stop the work")
    run("remind", "1")
    assert notify.call_args.args[0] == "stop the work", "a clickable copy stays in the centre"


def test_firing_an_unknown_reminder_says_nothing(run, agents):
    _code, out = run("remind", "42")
    assert out == "", "no Large Type for nothing"


def test_remember_refuses_without_a_time(run, agents):
    code, _out = run("act", "remember", "stand up")
    assert code == 2, "a usage error, nothing stored"


def test_a_trailing_future_time_points_to_reminders(db, sample):
    row = present.rows("stand up 21:00", db, NOW, NO_OFFSET)[0]
    assert row["title"] == "21:00 has not happened yet; for a reminder, put the time first"


def test_cli_filter_end_to_end(run, agents):
    _code, out = run("filter", "9PM go out")
    assert json.loads(out)["items"][0]["title"] == "Remind 21:00: go out", "t 9PM go out"


def test_seconds_count_down_instead_of_a_calendar_minute():
    made = remind.agent(remind.Reminder(8, datetime(2026, 10, 20, 15, 0, 30), "tea"), NOW)
    assert made["StartInterval"] == 30 and "StartCalendarInterval" not in made, (
        "launchd's calendar has no seconds, so a countdown from when it was set"
    )


def test_seconds_in_the_row(db):
    row = present.rows("+30 sec tea", db, NOW, NO_OFFSET)[0]
    assert (row["title"], row["subtitle"]) == (
        "Remind 15:00:30: tea",
        "in 30 s · in big letters then · ↩ sets it",
    ), "seconds are said when they matter"


def test_minutes_land_on_the_minute():
    late = NOW.replace(second=40)
    assert remind.wanted("+15m stop", late).at == datetime(2026, 10, 20, 15, 15), (
        "without seconds a reminder keeps to the calendar minute"
    )
    assert remind.wanted("+15m 10s stop", late).at == datetime(2026, 10, 20, 15, 15, 50), (
        "with seconds it is exact"
    )


def test_a_seconds_reminder_is_stored_with_its_seconds(run, db, agents):
    run("act", "remember", "+30s tea")
    assert remind.pending(db)[0].at == datetime(2026, 10, 20, 15, 0, 30), "kept to the second"


def test_until():
    assert remind.until(NOW + timedelta(seconds=45), NOW) == "in 45 s", "seconds"
    assert remind.until(NOW + timedelta(minutes=5), NOW) == "in 5 min", "short"
    assert remind.until(NOW + timedelta(hours=2, minutes=5), NOW) == "in 2:05", "long"
