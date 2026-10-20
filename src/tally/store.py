"""The table of transitions and the blocks read from it.

A transition says "from this time, this line"; an empty line is a stop. A block
runs from its transition to the next one, so nothing else is stored.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import NamedTuple

from hoard.alfred import fold

SCHEMA = """
create table if not exists transitions (
    id integer primary key,
    at text not null,
    line text not null default '',
    logged_at text not null
);
create index if not exists transitions_at on transitions(at);
create table if not exists batches (
    id integer primary key,
    said text not null,
    at text not null,
    undone integer not null default 0
);
create table if not exists before (
    batch integer not null,
    id integer not null,
    at text,
    line text,
    logged_at text,
    existed integer not null
);
"""

BACKFILL_SLACK = timedelta(minutes=10)


class Transition(NamedTuple):
    id: int
    at: datetime
    line: str
    logged_at: datetime

    @property
    def stop(self) -> bool:
        return self.line == ""


class Block(NamedTuple):
    start: datetime
    end: datetime | None
    line: str
    logged_at: datetime
    id: int = 0

    def length(self, now: datetime) -> timedelta:
        return (self.end or now) - self.start

    @property
    def backfilled(self) -> bool:
        return self.logged_at - self.start > BACKFILL_SLACK

    def clipped(self, since: datetime, until: datetime, now: datetime) -> Block:
        still_open = self.end is None and now < until
        end = None if still_open else min(self.end or now, until)
        return self._replace(start=max(self.start, since), end=end)


def connect(path: str) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.executescript(SCHEMA)
    return db


def stamp(moment: datetime) -> str:
    return moment.replace(second=0, microsecond=0).isoformat(timespec="minutes")


def record(db: sqlite3.Connection, at: datetime, line: str, now: datetime) -> Transition:
    cursor = db.execute(
        "insert into transitions (at, line, logged_at) values (?, ?, ?)",
        (stamp(at), tidy(line), stamp(now)),
    )
    db.commit()
    return Transition(cursor.lastrowid or 0, at, tidy(line), now)


def read(row: tuple) -> Transition:
    identity, at, line, logged_at = row
    return Transition(identity, datetime.fromisoformat(at), line, datetime.fromisoformat(logged_at))


def transitions(
    db: sqlite3.Connection, since: datetime | None = None, until: datetime | None = None
) -> list[Transition]:
    rows = db.execute(
        "select id, at, line, logged_at from transitions"
        " where (? is null or at >= ?) and (? is null or at < ?) order by at, id",
        (stamp_or_none(since), stamp_or_none(since), stamp_or_none(until), stamp_or_none(until)),
    )
    return [read(row) for row in rows]


def stamp_or_none(moment: datetime | None) -> str | None:
    return stamp(moment) if moment else None


def last_before(db: sqlite3.Connection, moment: datetime) -> Transition | None:
    row = db.execute(
        "select id, at, line, logged_at from transitions where at <= ? order by at desc, id desc",
        (stamp(moment),),
    ).fetchone()
    return read(row) if row else None


def blocks(changes: Iterable[Transition]) -> list[Block]:
    ordered = list(changes)
    ends = [after.at for after in ordered[1:]] + [None]
    return [
        Block(change.at, end, change.line, change.logged_at, change.id)
        for change, end in zip(ordered, ends)
        if not change.stop
    ]


def blocks_within(
    db: sqlite3.Connection, since: datetime, until: datetime, now: datetime
) -> list[Block]:
    return [
        block.clipped(since, until, now)
        for block in blocks(transitions(db, None, until))
        if (block.end or now) > since and block.start < until
    ]


def running(db: sqlite3.Connection, now: datetime) -> Block | None:
    last = last_before(db, now)
    if last is None or last.stop:
        return None
    return Block(last.at, None, last.line, last.logged_at)


def last_task(db: sqlite3.Connection, now: datetime) -> Transition | None:
    row = db.execute(
        "select id, at, line, logged_at from transitions"
        " where line != '' and at <= ? order by at desc, id desc",
        (stamp(now),),
    ).fetchone()
    return read(row) if row else None


class Task(NamedTuple):
    line: str
    last_start: datetime


def tasks(db: sqlite3.Connection, since: datetime, now: datetime) -> list[Task]:
    """Distinct lines started since `since`, newest start first, each spelled as last seen."""
    seen: dict[str, Task] = {}
    for change in transitions(db, since, now + timedelta(minutes=1)):
        if not change.stop:
            seen[fold(change.line)] = Task(change.line, change.at)
    return sorted(seen.values(), key=lambda task: task.last_start, reverse=True)


def tidy(line: str) -> str:
    return " ".join(line.split())


def same_task(one: str, other: str) -> bool:
    return fold(tidy(one)) == fold(tidy(other))


def spelled(db: sqlite3.Connection, line: str) -> str | None:
    """The line as it was last logged, if this task has been seen before."""
    row = db.execute(
        "select line from transitions where line != '' order by at desc, id desc"
    ).fetchall()
    for (known,) in row:
        if same_task(known, line):
            return known
    return None
