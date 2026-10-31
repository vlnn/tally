from datetime import datetime, timedelta

import pytest

from conftest import NOW, TODAY
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


def planted(db, hour, minute, line, day=TODAY):
    at = datetime(day.year, day.month, day.day, hour, minute)
    db.execute(
        "insert into transitions (at, line, logged_at) values (?, ?, ?)",
        (store.stamp(at), line, store.stamp(at)),
    )


def test_neighbours_are_a_window_around_a_moment(db, logged):
    for hour in range(8, 18):
        logged(hour, 0, f"task {hour}")
    found = store.neighbours(db, datetime(2026, 10, 20, 13, 0), reach=2)
    assert [t.at.hour for t in found] == [11, 12, 13, 14, 15], (
        "two before, the moment itself and two after"
    )


def test_neighbours_start_on_a_task_not_a_stop(db, logged):
    logged(9, 0, "mail")
    logged(9, 30, "")
    logged(10, 0, "parser")
    found = store.neighbours(db, datetime(2026, 10, 20, 10, 0), reach=1)
    assert [(t.at.hour, t.line) for t in found] == [(9, "mail"), (9, ""), (10, "parser")], (
        "the window opens on a task, so a stop inside it has its predecessor"
    )


@pytest.mark.parametrize(
    "planted_rows, expected",
    [
        ([(9, 0, "mail"), (9, 30, ""), (9, 45, "")], [("09:00", "mail"), ("09:30", "")]),
        ([(9, 0, "mail"), (10, 0, "mail")], [("09:00", "mail")]),
        ([(9, 0, "mail"), (9, 0, "parser")], [("09:00", "parser")]),
    ],
)
def test_record_tidies_what_it_touches(db, logged, planted_rows, expected):
    for hour, minute, line in planted_rows:
        planted(db, hour, minute, line)
    logged(15, 0, "review")
    assert timeline(db)[:-1] == expected, "the neighbourhood of a write is left tidy"


def test_record_leaves_distant_history_alone(db, logged):
    long_ago = TODAY - timedelta(days=400)
    planted(db, 9, 0, "mail", long_ago)
    planted(db, 10, 0, "mail", long_ago)
    for hour in range(8, 8 + store.REACH + 1):
        planted(db, hour, 0, f"task {hour}")
    logged(15, 0, "review")
    assert len(store.transitions(db)) == store.REACH + 4, (
        "a start only tidies around itself, so an old duplicate is not its business"
    )


def test_record_reads_a_window_not_the_table(db, logged, mocker):
    for hour in range(8, 15):
        logged(hour, 0, f"task {hour}")
    read = mocker.spy(store, "transitions")
    logged(15, 0, "review")
    bounded = [call for call in read.call_args_list if call.args[1] is not None]
    assert bounded and len(read.call_args_list) == len(bounded), (
        "every read made by a start is bounded below"
    )


def test_blocks_within_read_from_the_block_straddling_the_window(db, logged, mocker):
    long_ago = TODAY - timedelta(days=400)
    logged(9, 0, "ancient", long_ago)
    logged(10, 0, "", long_ago)
    logged(23, 30, "night shift", TODAY - timedelta(days=1))
    logged(9, 0, "mail")
    read = mocker.spy(store, "transitions")
    found = store.blocks_within(db, datetime.combine(TODAY, datetime.min.time()), NOW, NOW)
    assert [b.line for b in found] == ["night shift", "mail"], (
        "a block that started yesterday and ran into today is clipped in, not lost"
    )
    assert all(call.args[1] is not None for call in read.call_args_list), (
        "the read starts at the straddling block, not at the beginning of history"
    )
