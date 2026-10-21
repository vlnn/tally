import json
import plistlib
from datetime import datetime, time

import pytest

from conftest import NO_OFFSET, NOW
from tally import bar, cli, present, remind, repeats
from tally.repeats import Rule

WEDNESDAY = datetime(2026, 10, 21, 15, 0)


@pytest.mark.parametrize(
    "text, rule, first, said",
    [
        ("daily 9:00 standup", Rule("daily"), datetime(2026, 10, 22, 9, 0), "standup"),
        ("daily 21:00 read", Rule("daily"), datetime(2026, 10, 21, 21, 0), "read"),
        (
            "weekdays 18:30 stop the work",
            Rule("days", (0, 1, 2, 3, 4)),
            datetime(2026, 10, 21, 18, 30),
            "stop the work",
        ),
        (
            "weekends 10:00 call mum",
            Rule("days", (5, 6)),
            datetime(2026, 10, 24, 10, 0),
            "call mum",
        ),
        ("mon,thu 19:00 gym", Rule("days", (0, 3)), datetime(2026, 10, 22, 19, 0), "gym"),
        ("mon+thu 19:00 gym", Rule("days", (0, 3)), datetime(2026, 10, 22, 19, 0), "gym"),
        ("mon thu 19:00 gym", Rule("days", (0, 3)), datetime(2026, 10, 22, 19, 0), "gym"),
        ("monday 7pm gym", Rule("days", (0,)), datetime(2026, 10, 26, 19, 0), "gym"),
        ("wed 14:00 retro", Rule("days", (2,)), datetime(2026, 10, 28, 14, 0), "retro"),
        (
            "every 45m drink water",
            Rule("every", every=2700),
            datetime(2026, 10, 21, 15, 45),
            "drink water",
        ),
        ("every 2h stretch", Rule("every", every=7200), datetime(2026, 10, 21, 17, 0), "stretch"),
        ("every 90 min eyes", Rule("every", every=5400), datetime(2026, 10, 21, 16, 30), "eyes"),
        ("every 90 eyes", Rule("every", every=5400), datetime(2026, 10, 21, 16, 30), "eyes"),
        ("every 30s tea", Rule("every", every=30), datetime(2026, 10, 21, 15, 0, 30), "tea"),
    ],
)
def test_a_repeat_first_is_a_repeating_reminder(text, rule, first, said):
    found = remind.wanted(text, WEDNESDAY)
    assert (found.rule, found.at, found.text) == (rule, first, said), (
        "the rule, its first firing after now, and what to say"
    )


@pytest.mark.parametrize(
    "text", ["daily standup", "weekdays review", "mon meeting notes", "every day", "sat"]
)
def test_a_repeat_word_without_a_time_is_a_task(text):
    assert remind.wanted(text, WEDNESDAY) is None, "daily standup is a task, not a reminder"


@pytest.mark.parametrize(
    "text, until, said",
    [
        ("every 45m drink water until 18:00", datetime(2026, 10, 21, 18, 0), "drink water"),
        ("every 45m drink water until 9:00", datetime(2026, 10, 22, 9, 0), "drink water"),
        ("daily 9:00 standup until fri", datetime(2026, 10, 24, 0, 0), "standup"),
        ("daily 9:00 standup until wed", datetime(2026, 10, 22, 0, 0), "standup"),
        ("daily 9:00 standup until 2026-11-30", datetime(2026, 12, 1, 0, 0), "standup"),
        ("daily 9:00 wait until review", None, "wait until review"),
    ],
)
def test_until_ends_at_the_nearest_coming_one(text, until, said):
    found = remind.wanted(text, WEDNESDAY)
    assert (found.until, found.text) == (until, said), (
        "a time is the next such time, a day the end of the coming one; other words stay text"
    )


def test_until_is_text_for_a_one_shot():
    assert remind.wanted("21:00 stay until 23:00", WEDNESDAY).text == "stay until 23:00", (
        "a one-shot reminder has nothing to end"
    )


@pytest.mark.parametrize(
    "rule, at, now, coming",
    [
        (
            Rule("daily"),
            datetime(2026, 10, 21, 9, 0),
            datetime(2026, 10, 21, 9, 0),
            datetime(2026, 10, 22, 9, 0),
        ),
        (
            Rule("days", (0, 3)),
            datetime(2026, 10, 22, 19, 0),
            datetime(2026, 10, 22, 19, 0),
            datetime(2026, 10, 26, 19, 0),
        ),
        (
            Rule("days", (4,)),
            datetime(2026, 10, 23, 9, 0),
            datetime(2026, 10, 25, 8, 0),
            datetime(2026, 10, 30, 9, 0),
        ),
        (
            Rule("every", every=2700),
            datetime(2026, 10, 21, 15, 45),
            datetime(2026, 10, 21, 15, 45),
            datetime(2026, 10, 21, 16, 30),
        ),
        (
            Rule("every", every=2700),
            datetime(2026, 10, 21, 15, 45),
            datetime(2026, 10, 21, 18, 0),
            datetime(2026, 10, 21, 18, 45),
        ),
    ],
)
def test_next_after(rule, at, now, coming):
    assert repeats.next_after(rule, at, now) == coming, "the firing after this one and after now"


@pytest.mark.parametrize(
    "rule, said",
    [
        (Rule("daily"), "daily"),
        (Rule("days", (0, 1, 2, 3, 4)), "weekdays"),
        (Rule("days", (5, 6)), "weekends"),
        (Rule("days", (0, 3)), "mon, thu"),
        (Rule("every", every=2700), "every 45 min"),
        (Rule("every", every=5400), "every 1 h 30 min"),
        (Rule("every", every=30), "every 30 s"),
    ],
)
def test_describe(rule, said):
    assert repeats.describe(rule) == said, "how a rule reads in a row"


@pytest.mark.parametrize(
    "rule",
    [Rule("daily"), Rule("days", (0, 3)), Rule("every", every=2700), repeats.ONCE],
)
def test_encode_round_trips(rule):
    assert repeats.decode(repeats.encode(rule)) == rule, "stored and read back the same"


def test_launchd_calendars():
    at = datetime(2026, 10, 22, 19, 0)
    assert repeats.launchd(Rule("daily"), at) == {
        "StartCalendarInterval": {"Hour": 19, "Minute": 0}
    }
    assert repeats.launchd(Rule("days", (0, 6)), at) == {
        "StartCalendarInterval": [
            {"Weekday": 1, "Hour": 19, "Minute": 0},
            {"Weekday": 0, "Hour": 19, "Minute": 0},
        ]
    }, "launchd counts Sunday as 0"
    assert repeats.launchd(Rule("every", every=2700), at) == {"StartInterval": 2700}


@pytest.fixture
def agents(tmp_path, mocker):
    mocker.patch.object(remind, "agent_folder", return_value=tmp_path)
    mocker.patch("tally.bar.poke")
    mocker.patch("tally.bar.installed", return_value=False)
    return mocker.patch("subprocess.run")


@pytest.fixture
def run(db, capsys):
    def go(*argv, now=WEDNESDAY, **env):
        code = cli.run(list(argv), env, now=now, db=db)
        return code, capsys.readouterr().out

    return go


def agent_of(tmp_path, identity=1):
    with open(tmp_path / f"com.anokhin.tally.remind.{identity}.plist", "rb") as handle:
        return plistlib.load(handle)


def test_setting_a_repeat_writes_a_recurring_agent(run, db, agents, tmp_path):
    _code, out = run("act", "remember", "weekdays 18:30 stop the work")
    assert out.strip() == "Reminder set for weekdays 18:30: stop the work", "the notification"
    assert len(agent_of(tmp_path)["StartCalendarInterval"]) == 5, "one calendar entry per day"
    assert remind.pending(db)[0].typed == "weekdays 18:30 stop the work", "kept as typed"


def test_a_firing_repeat_shows_and_moves_on(run, db, agents, tmp_path):
    run("act", "remember", "daily 9:00 standup")
    _code, out = run("remind", "1", now=datetime(2026, 10, 22, 9, 0))
    assert out.strip() == "standup", "Large Type"
    assert remind.pending(db)[0].at == datetime(2026, 10, 23, 9, 0), "next is tomorrow"
    assert (tmp_path / "com.anokhin.tally.remind.1.plist").exists(), "the agent stays"


def test_a_firing_after_waking_late_moves_to_the_next_one_after_now(run, db, agents):
    run("act", "remember", "every 45m water")
    run("remind", "1", now=datetime(2026, 10, 21, 18, 0))
    assert remind.pending(db)[0].at == datetime(2026, 10, 21, 18, 45), "missed ones are passed"


def test_until_stops_the_series(run, db, agents, tmp_path):
    run("act", "remember", "every 45m water until 16:00")
    _code, out = run("remind", "1", now=datetime(2026, 10, 21, 15, 45))
    assert out.strip() == "water" and remind.pending(db) == [], (
        "the last one shows; the next would pass 16:00, so it ends"
    )
    assert not (tmp_path / "com.anokhin.tally.remind.1.plist").exists(), "and its agent goes"


def test_a_firing_past_until_shows_nothing(run, db, agents):
    run("act", "remember", "daily 9:00 standup until wed")
    _code, out = run("remind", "1", now=datetime(2026, 10, 22, 9, 0))
    assert out == "" and remind.pending(db) == [], "already over"


def test_alt_skips_only_the_next_firing(run, db, agents):
    run("act", "remember", "daily 9:00 standup")
    _code, out = run("act", "forget", "1")
    assert out.strip() == "Skipping tomorrow 09:00: standup", "says which one"
    _code, out = run("remind", "1", now=datetime(2026, 10, 22, 9, 0))
    assert out == "", "that one is quiet"
    _code, out = run("remind", "1", now=datetime(2026, 10, 23, 9, 0))
    assert out.strip() == "standup", "the one after shows again"


def test_alt_on_a_one_shot_cancels(run, db, agents):
    run("act", "remember", "21:00 stand up")
    run("act", "forget", "1")
    assert remind.pending(db) == [], "gone"


def test_shift_stops_every_reminder_with_that_text(run, db, agents):
    run("act", "remember", "daily 9:00 standup")
    run("act", "remember", "+15m Standup")
    run("act", "remember", "21:00 other")
    _code, out = run("act", "forget-all", "1")
    assert out.strip() == "Stopped 2 reminders: standup", "the repeat and the one-shot"
    assert [r.text for r in remind.pending(db)] == ["other"], "others stay"


def test_ctrl_retypes_and_replaces(run, db, agents, capsys):
    run("act", "remember", "daily 9:00 standup")
    row = present.rows("@reminders", db, WEDNESDAY, NO_OFFSET)[0]
    ctrl = row["mods"]["ctrl"]
    assert (ctrl["arg"], ctrl["variables"]) == (
        "daily 9:00 standup",
        {"action": "retype", "replace": "1"},
    ), "what was typed goes back into t, with the reminder to replace"
    _code, out = run("filter", "daily 9:30 standup", replace="1")
    title = json.loads(out)["items"][0]["title"]
    assert title == "Replace with daily 09:30: standup", "the row says it replaces"
    _code, out = run("act", "remember", "daily 9:30 standup", replace="1")
    assert out.strip() == "Replaced with daily 09:30: standup", "done"
    assert [r.at.time() for r in remind.pending(db)] == [time(9, 30)], "only the new one is left"


def test_enter_previews_without_touching_the_schedule(db, agents, run):
    run("act", "remember", "daily 9:00 standup")
    row = present.rows("@reminders", db, WEDNESDAY, NO_OFFSET)[0]
    assert (row["arg"], row["variables"]) == ("standup", {"action": "preview"}), (
        "↩ hands the text to Large Type"
    )


def test_reminders_list_and_filter(run, db, agents):
    run("act", "remember", "daily 9:00 standup")
    run("act", "remember", "every 45m water")
    titles = [r["title"] for r in present.rows("@re", db, WEDNESDAY, NO_OFFSET)]
    assert titles == ["⏰ every 45 min water", "⏰ daily 09:00 standup"], "next first"
    filtered = present.rows("@reminders stand", db, WEDNESDAY, NO_OFFSET)
    assert [r["title"] for r in filtered] == ["⏰ daily 09:00 standup"], "words narrow"


def test_a_repeat_row_says_its_next_firing(run, db, agents):
    run("act", "remember", "daily 9:00 standup until fri")
    row = present.rows("@reminders", db, WEDNESDAY, NO_OFFSET)[0]
    assert row["subtitle"] == (
        "next tomorrow 09:00 · in 18:00 · until Sat 24 Oct 00:00 · ↩ shows it now"
    ), "when, how far, and when it ends"


def test_bare_t_shows_repeats_only_within_the_hour(run, db, agents):
    run("act", "remember", "daily 9:00 standup")
    run("act", "remember", "every 45m water")
    titles = [r["title"] for r in present.rows("", db, WEDNESDAY, NO_OFFSET)]
    assert "⏰ every 45 min water" in titles and "⏰ daily 09:00 standup" not in titles, (
        "the one due within the hour, not tomorrow's"
    )


def test_at_alone_lists_the_at_words(db):
    rows = present.rows("@", db, NOW, NO_OFFSET)
    assert [r["title"] for r in rows] == [
        "Today",
        "Yesterday",
        "This week",
        "Last week",
        "This month",
        "Last month",
        "Reminders",
    ], "every @word"
    assert rows[-1]["autocomplete"] == "@reminders ", "⇥ goes to the list"


def test_re_without_at_is_not_reminders(db, sample):
    assert present.rows("re", db, NOW, NO_OFFSET)[0]["title"] == "Start re", "re is a task"


def test_old_databases_get_the_new_columns(db):
    db.execute(
        "create table reminders"
        " (id integer primary key, at text, text text, state text default 'pending')"
    )
    db.execute("insert into reminders (at, text) values ('2026-10-21T21:00:00', 'old')")
    found = remind.pending(db)
    assert found[0].rule == repeats.ONCE and found[0].typed == "", "read as a one-shot"


def test_a_clicked_repeat_opens_its_row(run, db, agents, mocker):
    mocker.patch("tally.bar.installed", return_value=True)
    notify = mocker.patch("tally.bar.notify")
    run("act", "remember", "daily 9:00 standup")
    run("remind", "1", now=datetime(2026, 10, 22, 9, 0))
    assert notify.call_args.args[1].endswith("argument=%40reminders%20standup"), (
        "the click lands on @reminders standup, with its keys"
    )


def test_the_menu_bar_lists_reminders(db, run, agents):
    run("act", "remember", "daily 9:00 standup")
    lines = bar.menu(db, WEDNESDAY, NO_OFFSET, "/p").splitlines()
    assert "Reminders · 1" in lines, "a submenu header"
    entry = next(line for line in lines if line.startswith("--⏰"))
    assert 'param2="@reminders standup"' in entry, "a click opens it in Alfred"
