import os
from datetime import datetime, time, timedelta

import pytest

from conftest import NOW
from tally import gaps
from tally.nudge import Settings

HOURS = Settings(timedelta(minutes=15), time(9, 0), time(19, 0), False)
GAP = gaps.Gap(datetime(2026, 10, 20, 14, 30), NOW)
SATURDAY = datetime(2026, 10, 24, 15, 0)
YESTERDAY = (NOW - timedelta(days=1)).date()


def at(hour, minute, day=20):
    return datetime(2026, 10, day, hour, minute)


def test_no_gap_while_a_task_runs(db, sample):
    assert gaps.find(db, NOW, HOURS) is None, "running time is claimed already"


def test_the_gap_starts_at_the_last_stop(db, logged):
    logged(9, 0, "mail")
    logged(14, 30, "")
    assert gaps.find(db, NOW, HOURS) == gaps.Gap(at(14, 30), NOW), "from the stop to now"


def test_a_day_with_nothing_yet_starts_with_the_hours(db, logged):
    logged(16, 0, "mail", day=YESTERDAY)
    logged(17, 0, "", day=YESTERDAY)
    assert gaps.find(db, NOW, HOURS) == gaps.Gap(at(9, 0), NOW), (
        "yesterday's stop does not carry over: today's gap opens with the hours"
    )


def test_an_empty_database_has_a_gap_from_the_start_of_the_hours(db):
    assert gaps.find(db, NOW, HOURS) == gaps.Gap(at(9, 0), NOW), "nothing logged at all"


@pytest.mark.parametrize(
    "now, hours",
    [
        (at(20, 0), HOURS),
        (at(8, 30), HOURS),
        (SATURDAY, HOURS),
    ],
)
def test_no_gap_outside_the_hours(db, now, hours):
    assert gaps.find(db, now, hours) is None, "unclaimed time only counts within the hours"


def test_weekends_count_when_asked(db):
    weekends = HOURS._replace(weekends=True)
    assert gaps.find(db, SATURDAY, weekends) == gaps.Gap(at(9, 0, day=24), SATURDAY), (
        "with weekends on, Saturday has hours too"
    )


@pytest.mark.parametrize(
    "setting, expected",
    [
        ("15,30,45,60", (15, 30, 45, 60)),
        ("10, 20, 40, 90", (10, 20, 40, 90)),
        ("", gaps.DEFAULT_LADDER),
        ("a,b,c,d", gaps.DEFAULT_LADDER),
        ("30,15,45,60", gaps.DEFAULT_LADDER),
        ("15,30", gaps.DEFAULT_LADDER),
        ("0,30,45,60", gaps.DEFAULT_LADDER),
    ],
)
def test_ladder(setting, expected):
    assert gaps.ladder(setting) == expected, "four rising minutes, else the default"


@pytest.mark.parametrize(
    "minutes, expected",
    [(10, 0), (15, 1), (44, 2), (45, 3), (60, 4), (90, 4)],
)
def test_level(minutes, expected):
    gap = gaps.Gap(NOW - timedelta(minutes=minutes), NOW)
    assert gaps.level(gap, gaps.DEFAULT_LADDER) == expected, "how many steps the gap has reached"


def test_no_gap_is_level_zero():
    assert gaps.level(None, gaps.DEFAULT_LADDER) == 0, "nothing to count"


def pmset(*moments):
    return [f"{moment} +0200 Notification  \tDisplay is turned on" for moment in moments]


@pytest.mark.parametrize(
    "lines, expected",
    [
        (pmset("2026-10-20 14:42:13"), at(14, 42)),
        (pmset("2026-10-20 14:35:00", "2026-10-20 14:48:59"), at(14, 48)),
        (pmset("2026-10-20 14:10:00"), None),
        (pmset("2026-10-20 15:10:00"), None),
        (["2026-10-20 14:42:13 +0200 Sleep  \tEntering Sleep"], None),
        ([], None),
    ],
)
def test_display_on(lines, expected):
    assert gaps.display_on(lines, GAP) == expected, (
        "the last time the display came on inside the gap, to the minute"
    )


def test_pmset_lines_use_a_fresh_cache(tmp_path, mocker):
    cache = tmp_path / "display-on.log"
    cache.write_text("cached\n")
    spawned = mocker.patch("subprocess.run")
    now = datetime.fromtimestamp(cache.stat().st_mtime) + timedelta(seconds=10)
    assert gaps.pmset_lines(cache, now) == ["cached"], "typing stays quick"
    spawned.assert_not_called()


def test_pmset_lines_refresh_a_stale_cache(tmp_path, mocker):
    cache = tmp_path / "cache" / "display-on.log"
    mocker.patch("subprocess.run").return_value.stdout = "fresh\n"
    assert gaps.pmset_lines(cache, NOW) == ["fresh"], "read from pmset"
    assert cache.read_text() == "fresh\n", "and kept for the next keystroke"


def test_pmset_lines_after_a_minute_ask_again(tmp_path, mocker):
    cache = tmp_path / "display-on.log"
    cache.write_text("old\n")
    os.utime(cache, (0, 0))
    mocker.patch("subprocess.run").return_value.stdout = "new\n"
    assert gaps.pmset_lines(cache, NOW) == ["new"], "a cache older than a minute is stale"


def test_pmset_lines_without_a_shell(mocker):
    mocker.patch("subprocess.run", side_effect=FileNotFoundError("sh"))
    assert gaps.pmset_lines(None, NOW) == [], "no power log, no display-on row"


@pytest.mark.parametrize(
    "text, expected",
    [
        (
            "standup 30, api-design",
            [gaps.Part("standup", timedelta(minutes=30)), gaps.Part("api-design", None)],
        ),
        (
            "call with ola 1h30m, mail 10m, parser #lexer",
            [
                gaps.Part("call with ola", timedelta(hours=1, minutes=30)),
                gaps.Part("mail", timedelta(minutes=10)),
                gaps.Part("parser #lexer", None),
            ],
        ),
        ("30, mail", [gaps.Part("30", None), gaps.Part("mail", None)]),
        (
            "lunch 30, review pr 212",
            [gaps.Part("lunch", timedelta(minutes=30)), gaps.Part("review pr 212", None)],
        ),
        ("standup 30 api-design", None),
    ],
)
def test_split(text, expected):
    assert gaps.split(text) == expected, "parts by comma, each with an optional last-word length"


def test_fill_runs_the_parts_one_after_another():
    parts = gaps.split("standup 10, mail 5m, api-design")
    assert gaps.fill(parts, GAP) == gaps.Filled(
        ((at(14, 30), "standup"), (at(14, 40), "mail"), (at(14, 45), "api-design"))
    ), "each part starts where the one before ends, from the start of the gap"


@pytest.mark.parametrize(
    "text, problem",
    [
        (", mail", "Every part needs a name: standup 30, api-design"),
        ("standup, mail", "Give every part but the last a length: standup 30, api-design"),
        ("standup 20, mail 10, review", "0:30 of parts is more than the 0:30 gap"),
    ],
)
def test_fill_refuses(text, problem):
    assert gaps.fill(gaps.split(text), GAP).problem == problem, "a split that cannot fill says why"


@pytest.mark.parametrize("minutes, expected", [(15, True), (14, False)])
def test_a_claim_is_worth_asking_from_the_threshold(minutes, expected):
    gap = gaps.Gap(NOW - timedelta(minutes=minutes), NOW)
    claim = gaps.Claim(gap, timedelta(minutes=15))
    assert claim.worth_asking is expected, "short gaps are not worth a row"
