from datetime import datetime, timedelta

import pytest

from conftest import NOW
from tally import store


def test_a_block_ends_where_the_next_transition_starts(db, sample):
    found = store.blocks(store.transitions(db))
    assert [(b.start.hour, b.start.minute, b.end.hour, b.end.minute) for b in found[:2]] == [
        (9, 5, 9, 40),
        (9, 40, 10, 10),
    ], "each block runs until whatever came next, a task or a stop"


def test_a_stop_is_not_a_block(db, sample):
    found = store.blocks(store.transitions(db))
    assert [b.line for b in found] == [
        "standup #team",
        "mail",
        "parser #lexer",
        "call with ola",
        "review pr 212",
        "parser #lexer",
    ], "empty lines end blocks but are not blocks"


def test_the_last_block_is_open(db, sample):
    assert store.blocks(store.transitions(db))[-1].end is None, "nothing has ended it yet"


def test_running_is_the_open_block(db, sample):
    active = store.running(db, NOW)
    assert active is not None and active.line == "parser #lexer", "the newest transition runs"
    assert active.length(NOW) == timedelta(minutes=55), "it has run since 14:05"


def test_nothing_runs_after_a_stop(db, logged):
    logged(9, 0, "mail")
    logged(9, 30, "")
    assert store.running(db, NOW) is None, "a stop leaves nothing running"


def test_a_block_before_now_does_not_run(db, logged):
    logged(9, 0, "mail")
    assert store.running(db, datetime(2026, 10, 20, 8, 0)) is None, (
        "what starts later than now is not running now"
    )


def test_tasks_are_distinct_and_newest_first(db, sample):
    found = store.tasks(db, NOW - timedelta(days=7), NOW)
    assert [t.line for t in found] == [
        "parser #lexer",
        "review pr 212",
        "call with ola",
        "mail",
        "standup #team",
    ], "one row per task, ordered by its latest start"


def test_tasks_fold_spelling(db, logged):
    logged(9, 0, "Parser")
    logged(9, 30, "")
    logged(10, 0, "parser")
    found = store.tasks(db, NOW - timedelta(days=1), NOW)
    assert [t.line for t in found] == ["parser"], "case does not make a second task"


@pytest.mark.parametrize(
    "typed, expected",
    [("PARSER #LEXER", "parser #lexer"), ("parser  #lexer", "parser #lexer"), ("nothing", None)],
)
def test_spelled_finds_the_stored_line(db, sample, typed, expected):
    assert store.spelled(db, typed) == expected, "a known task is resumed as it was written"


def test_blocks_within_clip_to_the_window(db, logged):
    logged(23, 0, "late", day=NOW.date() - timedelta(days=1))
    logged(1, 0, "")
    since = datetime(2026, 10, 20, 0, 0)
    found = store.blocks_within(db, since, since + timedelta(days=1), NOW)
    assert [(b.start, b.end) for b in found] == [(since, datetime(2026, 10, 20, 1, 0))], (
        "a block crossing midnight contributes only its part inside the day"
    )


def test_backfill_is_visible(db, logged):
    change = logged(9, 0, "mail", logged_at=datetime(2026, 10, 20, 9, 30))
    assert store.blocks([change])[0].backfilled, "logged half an hour after it started"
    prompt = logged(10, 0, "mail", logged_at=datetime(2026, 10, 20, 10, 5))
    assert not store.blocks([prompt])[0].backfilled, "five minutes late is not a backfill"


def test_record_rounds_to_the_minute(db):
    store.record(db, datetime(2026, 10, 20, 9, 0, 42), "mail", NOW)
    assert store.transitions(db)[0].at == datetime(2026, 10, 20, 9, 0), "seconds are dropped"


def timeline(db):
    return [(f"{t.at:%H:%M}", t.line) for t in store.transitions(db)]


def test_the_same_task_right_after_itself_is_one_block(db, logged):
    logged(17, 53, "swiftbar setup")
    logged(19, 28, "swiftbar setup")
    assert timeline(db) == [("17:53", "swiftbar setup")], "17:53–now, not two blocks"


def test_switching_within_a_minute_leaves_no_zero_blocks(db, logged):
    logged(19, 28, "swiftbar setup")
    logged(20, 5, "zx-pk")
    logged(20, 5, "swiftbar setup")
    logged(20, 5, "zx-pk")
    assert timeline(db) == [("19:28", "swiftbar setup"), ("20:05", "zx-pk")], (
        "only the last switch in a minute counts"
    )


def test_a_stop_after_a_stop_is_dropped(db, logged):
    logged(9, 0, "mail")
    logged(9, 30, "")
    logged(9, 45, "")
    assert timeline(db) == [("09:00", "mail"), ("09:30", "")], "the second stop changed nothing"


def test_a_gap_keeps_repeats_apart(db, logged):
    logged(13, 31, "#talk to @JC")
    logged(13, 32, "")
    logged(13, 33, "#talk to @JC")
    assert len(store.blocks(store.transitions(db))) == 2, "with a gap between, two blocks"


def test_redundant_finds_the_lot_in_old_data(db):
    rows = [
        (17, 53, "swiftbar setup"),
        (19, 28, "swiftbar setup"),
        (20, 5, "zx-pk"),
        (20, 5, "swiftbar setup"),
        (20, 5, "zx-pk"),
    ]
    for hour, minute, line in rows:
        at = datetime(2026, 10, 20, hour, minute)
        db.execute(
            "insert into transitions (at, line, logged_at) values (?, ?, ?)",
            (store.stamp(at), line, store.stamp(at)),
        )
    assert store.redundant(store.transitions(db)) == [3, 4, 2], (
        "two zero-minute switches and the repeated start"
    )
