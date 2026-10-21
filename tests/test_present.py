from datetime import datetime, timedelta

import pytest

from conftest import NO_OFFSET, NOW
from tally import gaps, present
from tally.scope import Scope


def titles(rows):
    return [row["title"] for row in rows]


@pytest.mark.parametrize(
    "span, expected",
    [
        (timedelta(minutes=42), "0:42"),
        (timedelta(hours=1, minutes=58), "1:58"),
        (timedelta(), "0:00"),
    ],
)
def test_hm(span, expected):
    assert present.hm(span) == expected, "durations read as h:mm"


@pytest.mark.parametrize(
    "moment, expected",
    [
        (datetime(2026, 10, 20, 14, 5), "14:05"),
        (datetime(2026, 10, 19, 16, 0), "yesterday 16:00"),
        (datetime(2026, 10, 8, 9, 5), "Thu 8 Oct 09:05"),
        (datetime(2025, 12, 31, 23, 59), "31 Dec 2025 23:59"),
    ],
)
def test_when(moment, expected):
    assert present.when(moment, NOW) == expected, "a time reads relative to today"


def test_bare_list_puts_the_previous_task_first(db, sample):
    rows = present.rows("", db, NOW, NO_OFFSET)
    assert titles(rows)[0] == "Resume review pr 212", "↩ on bare t goes back to the previous task"
    assert "Resume parser #lexer" not in titles(rows), "the running task is not offered"


def test_bare_list_ends_with_stop_and_today(db, sample):
    rows = present.rows("", db, NOW, NO_OFFSET)
    assert titles(rows)[-2:] == ["Stop", "Today"], "stop, then the day, after the tasks"
    assert rows[-2]["subtitle"] == "parser #lexer · 0:55 since 14:05", "stop says what it ends"
    assert rows[-2]["variables"] == {"action": "stop"}, "stop is its own action"
    assert rows[-1]["subtitle"] == "4:40 logged · ↩ shows the day", "the day's tally"
    assert rows[-1]["variables"] == {"action": "view"} and rows[-1]["arg"] == "@today", (
        "↩ opens the view on that date"
    )


def test_bare_list_has_no_stop_when_nothing_runs(db, logged):
    logged(9, 0, "mail")
    logged(9, 30, "")
    assert titles(present.rows("", db, NOW, NO_OFFSET)) == ["Resume mail", "Today"], (
        "nothing to stop, so no Stop row"
    )


def test_bare_list_caps_recent_tasks(db, logged):
    for minute, name in enumerate("abcdefghij"):
        logged(9, minute, name)
    rows = present.rows("", db, NOW, NO_OFFSET)
    assert len([r for r in rows if r["title"].startswith("Resume")]) == present.RECENT_LIMIT, (
        "only the last few tasks are offered"
    )


def test_bare_list_forgets_old_tasks(db, logged):
    logged(9, 0, "ancient", day=NOW.date() - timedelta(days=8))
    logged(9, 0, "recent")
    logged(9, 30, "")
    assert titles(present.rows("", db, NOW, NO_OFFSET)) == ["Resume recent", "Today"], (
        "a task older than a week is reached by typing, not from the bare list"
    )


def test_resume_subtitle_tells_today_and_last(db, sample):
    rows = present.rows("", db, NOW, NO_OFFSET)
    assert rows[0]["subtitle"] == "today 0:25 · last 13:40–14:05", "how much today and when last"


def test_resume_subtitle_without_time_today(db, logged):
    logged(9, 0, "mail", day=NOW.date() - timedelta(days=2))
    logged(9, 30, "", day=NOW.date() - timedelta(days=2))
    rows = present.rows("", db, NOW, NO_OFFSET)
    assert rows[0]["subtitle"] == "last Sun 18 Oct 09:00", "a task not seen today shows when"


def test_typed_words_start_a_new_task(db, sample):
    rows = present.rows("write tests", db, NOW, NO_OFFSET)
    assert rows[0]["title"] == "Start write tests" and rows[0]["subtitle"] == "↩ from now", (
        "an unknown line is started"
    )
    assert rows[0]["variables"] == {"action": "start"} and rows[0]["arg"] == "write tests", (
        "start carries the line and no time"
    )


def test_typed_words_resume_a_known_task_as_it_was_spelled(db, sample):
    rows = present.rows("MAIL", db, NOW, NO_OFFSET)
    assert rows[0]["title"] == "Resume mail" and rows[0]["arg"] == "mail", (
        "an exact match resumes with the stored spelling"
    )


def test_typed_words_list_matching_tasks_below(db, sample):
    rows = present.rows("pa", db, NOW, NO_OFFSET)
    assert titles(rows) == ["Start pa", "parser #lexer is running"], (
        "every task matching by word prefix is listed, the running one as running"
    )
    assert "Resume mail" not in titles(present.rows("pa", db, NOW, NO_OFFSET)), (
        "tasks that do not match are not listed"
    )


def test_typed_words_reach_old_tasks(db, logged):
    logged(9, 0, "ancient", day=NOW.date() - timedelta(days=30))
    logged(10, 0, "", day=NOW.date() - timedelta(days=30))
    assert titles(present.rows("anc", db, NOW, NO_OFFSET)) == ["Start anc", "Resume ancient"], (
        "typing searches all history"
    )


def test_backfill_ends_the_running_task_at_that_time(db, sample):
    rows = present.rows("mail 14:30", db, NOW, NO_OFFSET)
    assert rows[0]["subtitle"] == "from 14:30 · ends parser #lexer at 14:30", "the effect is said"
    assert rows[0]["variables"] == {"action": "start", "at": "2026-10-20T14:30"}, "the time travels"


def test_backfill_before_the_running_task_inserts_a_past_block(db, sample):
    rows = present.rows("mail 11:30", db, NOW, NO_OFFSET)
    assert rows[0]["subtitle"] == (
        "11:30–14:05, before parser #lexer (which keeps running) · cuts parser #lexer at 11:30"
    ), "an earlier start is a past block and the row says what it cuts"


def test_backfill_into_a_gap_cuts_nothing(db, sample):
    rows = present.rows("coffee 13:00", db, NOW, NO_OFFSET)
    assert rows[0]["subtitle"] == "13:00–14:05, before parser #lexer (which keeps running)", (
        "a stop before the time means nothing is cut"
    )


def test_backfill_with_nothing_running(db, logged):
    logged(9, 0, "mail")
    logged(9, 30, "")
    rows = present.rows("coffee 10:00", db, NOW, NO_OFFSET)
    assert rows[0]["subtitle"] == "from 10:00", "no running task, nothing to end"


@pytest.mark.parametrize("text", ["mail 16:30", "14:30"])
def test_impossible_backfill_is_an_invalid_row(db, sample, text):
    rows = present.rows(text, db, NOW, NO_OFFSET)
    assert len(rows) == 1 and rows[0]["valid"] is False, "one row, saying why"


def test_shift_fills_the_gap_since_the_last_stop(db, logged):
    logged(9, 0, "mail")
    logged(9, 30, "")
    rows = present.rows("", db, NOW, NO_OFFSET)
    assert rows[0]["mods"]["shift"] == {
        "subtitle": "⇧↩ since 09:30 (fills 5:30)",
        "variables": {"action": "start", "at": "2026-10-20T09:30"},
    }, "⇧↩ starts where the last block ended"


def test_shift_does_nothing_while_a_task_runs(db, sample):
    rows = present.rows("", db, NOW, NO_OFFSET)
    assert rows[0]["mods"]["shift"]["valid"] is False, "no gap to fill"


def test_a_rule_word_offers_the_view(db, sample):
    rows = present.rows("@yesterday", db, NOW, NO_OFFSET)
    assert rows == [
        {
            "title": "Yesterday",
            "subtitle": "0:00 logged · ↩ shows the day",
            "arg": "@yesterday",
            "variables": {"action": "view"},
            "mods": {
                **present.NO_MODS,
                **present.edit_mods("day:2026-10-19", "tag every block of the day"),
            },
        }
    ], "@yesterday is the one row that opens that day"


def test_the_day_boundary_moves_the_tally(db, logged):
    logged(1, 0, "night")
    logged(2, 0, "")
    midnight = present.rows("", db, NOW, NO_OFFSET)[-1]["subtitle"]
    four = present.rows("", db, NOW, timedelta(hours=4))[-1]["subtitle"]
    assert (midnight, four) == ("1:00 logged · ↩ shows the day", "0:00 logged · ↩ shows the day"), (
        "with the day starting at 04:00, one o'clock belongs to yesterday"
    )


def test_a_range_word_offers_the_range(db, sample):
    rows = present.rows("@week", db, NOW, NO_OFFSET)
    assert (rows[0]["title"], rows[0]["subtitle"], rows[0]["arg"]) == (
        "This week",
        "4:40 logged · ↩ shows the week",
        "@week",
    ), "the week's tally and its view"


def test_a_leading_span_backfills(db, sample):
    row = present.rows("-10m get scrubber from courier", db, NOW, NO_OFFSET)[0]
    assert (row["title"], row["arg"], row["variables"]) == (
        "Start get scrubber from courier",
        "get scrubber from courier",
        {"action": "start", "at": "2026-10-20T14:50"},
    ), "-10m first means it started ten minutes ago, not a task called -10m"


GAP_START = datetime(2026, 10, 20, 14, 30)


@pytest.fixture
def idle(db, logged):
    logged(9, 0, "mail")
    logged(14, 30, "")


def claimed(start=GAP_START, woke=None):
    return gaps.Claim(gaps.Gap(start, NOW), timedelta(minutes=15), lambda: woke)


def test_bare_list_says_how_much_is_unclaimed(db, idle):
    rows = present.bare_rows(db, NOW, NO_OFFSET, claim=claimed())
    assert rows[0]["title"] == "Unclaimed 0:30 since 14:30", "the gap first, as a fact"
    assert rows[0]["valid"] is False, "it is not a thing to press: type the task"


def test_bare_list_keeps_quiet_about_short_gaps(db, idle):
    rows = present.bare_rows(db, NOW, NO_OFFSET, claim=claimed(NOW - timedelta(minutes=10)))
    assert not titles(rows)[0].startswith("Unclaimed"), "under the first step, nothing to say"


def test_typed_task_after_a_gap_offers_three_starts(db, idle):
    woke = datetime(2026, 10, 20, 14, 42)
    rows = present.typed_rows("api-design", db, NOW, NO_OFFSET, claim=claimed(woke=woke))
    assert titles(rows)[:3] == [
        "Start api-design",
        "Start api-design since 14:42",
        "Start api-design since 14:30",
    ], "now, since the display came on, since the gap began"
    assert rows[0]["subtitle"] == "↩ from now", "↩ on the top row still means now"
    assert rows[1]["subtitle"].startswith("display on · 0:18"), "why this time, and how long"
    assert rows[2]["variables"]["at"] == "2026-10-20T14:30", "the whole gap starts at its start"


def test_without_a_display_on_time_the_gap_is_the_only_alternative(db, idle):
    rows = present.typed_rows("mail", db, NOW, NO_OFFSET, claim=claimed())
    assert titles(rows)[:2] == ["Resume mail", "Resume mail since 14:30"], (
        "a known task resumes, from now or from the start of the gap"
    )


@pytest.mark.parametrize("text", ["api-design 14:40", "api-design -10m"])
def test_a_typed_time_needs_no_alternatives(db, idle, text):
    rows = present.typed_rows(text, db, NOW, NO_OFFSET, claim=claimed())
    assert not any("since" in title for title in titles(rows)), "the time is already chosen"


def test_shift_fills_from_the_start_of_todays_gap(db, logged):
    logged(16, 0, "mail", day=(NOW - timedelta(days=1)).date())
    logged(17, 0, "", day=(NOW - timedelta(days=1)).date())
    opening = datetime(2026, 10, 20, 9, 0)
    rows = present.bare_rows(db, NOW, NO_OFFSET, claim=claimed(opening))
    shift = rows[1]["mods"]["shift"]
    assert shift["subtitle"] == "⇧↩ since 09:00 (fills 6:00)", (
        "yesterday's stop is not today's gap: it opens with the hours"
    )


def test_a_split_claims_the_gap_in_parts(db, idle):
    [row] = present.typed_rows(
        "standup 10, mail 5, api-design", db, NOW, NO_OFFSET, claim=claimed()
    )
    assert row["title"] == (
        "Claim since 14:30: standup 14:30–14:40, mail 14:40–14:45, api-design from 14:45"
    ), "each part with its times, the last running on"
    assert (row["arg"], row["variables"]) == (
        "standup 10, mail 5, api-design",
        {"action": "claim"},
    ), "the act re-reads the parts"


def test_a_split_in_the_work_list_tags_every_part(db, idle):
    work = Scope("work", {})
    [row] = present.typed_rows("standup 10, api", db, NOW, NO_OFFSET, work, claimed())
    assert row["arg"] == "standup #work 10, api #work", "every part is work"


def test_a_split_that_does_not_fit_says_so(db, idle):
    [row] = present.typed_rows("standup 40, api", db, NOW, NO_OFFSET, claim=claimed())
    assert (row["title"], row["valid"]) == ("0:40 of parts is more than the 0:30 gap", False), (
        "one row, saying why"
    )


def test_a_split_with_nothing_unclaimed(db, sample):
    [row] = present.typed_rows("standup 10, api", db, NOW, NO_OFFSET)
    assert row["valid"] is False and row["title"].startswith("A split claims unclaimed time"), (
        "with a task running there is no gap to split"
    )
