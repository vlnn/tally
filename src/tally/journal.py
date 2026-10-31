"""Changes to past transitions, each batch kept so it can be undone."""

from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import NamedTuple

from tally import store


class Op(NamedTuple):
    kind: str
    id: int = 0
    at: datetime | None = None
    line: str | None = None


def update(identity: int, at: datetime | None = None, line: str | None = None) -> Op:
    return Op("update", identity, at, line)


def insert(at: datetime, line: str) -> Op:
    return Op("insert", 0, at, line)


def delete(identity: int) -> Op:
    return Op("delete", identity)


def remember(db: sqlite3.Connection, batch: int, identity: int) -> None:
    db.execute(
        "insert into before (batch, id, at, line, logged_at, existed)"
        " select ?, id, at, line, logged_at, 1 from transitions where id = ?",
        (batch, identity),
    )


def carry_out(db: sqlite3.Connection, op: Op, batch: int, now: datetime) -> None:
    if op.kind == "insert":
        assert op.at is not None and op.line is not None
        cursor = db.execute(
            "insert into transitions (at, line, logged_at) values (?, ?, ?)",
            (store.stamp(op.at), store.tidy(op.line), store.stamp(now)),
        )
        db.execute(
            "insert into before (batch, id, existed) values (?, ?, 0)", (batch, cursor.lastrowid)
        )
        return
    remember(db, batch, op.id)
    if op.kind == "delete":
        db.execute("delete from transitions where id = ?", (op.id,))
        return
    if op.at is not None:
        db.execute("update transitions set at = ? where id = ?", (store.stamp(op.at), op.id))
    if op.line is not None:
        db.execute("update transitions set line = ? where id = ?", (store.tidy(op.line), op.id))


def moment_of(db: sqlite3.Connection, op: Op) -> datetime | None:
    if not op.id:
        return None
    row = db.execute("select at from transitions where id = ?", (op.id,)).fetchone()
    return datetime.fromisoformat(row[0]) if row else None


def touched(db: sqlite3.Connection, ops: list[Op]) -> list[datetime]:
    """Every moment an op reaches: where a row was, and where it goes."""
    moments = [moment_of(db, op) for op in ops] + [op.at for op in ops]
    return list(dict.fromkeys(m for m in moments if m is not None))


def tidy(db: sqlite3.Connection, moments: list[datetime], batch: int, now: datetime) -> None:
    gone: set[int] = set()
    for moment in moments:
        gone.update(store.redundant(store.neighbours(db, moment)))
    for identity in gone:
        carry_out(db, delete(identity), batch, now)


def apply(db: sqlite3.Connection, ops: list[Op], said: str, now: datetime) -> int:
    with db:
        batch = db.execute(
            "insert into batches (said, at) values (?, ?)", (said, store.stamp(now))
        ).lastrowid
        assert batch is not None
        moments = touched(db, ops)
        for op in ops:
            carry_out(db, op, batch, now)
        tidy(db, moments, batch, now)
    return batch


class Batch(NamedTuple):
    id: int
    said: str
    at: datetime


def last(db: sqlite3.Connection) -> Batch | None:
    row = db.execute(
        "select id, said, at from batches where undone = 0 order by id desc limit 1"
    ).fetchone()
    return Batch(row[0], row[1], datetime.fromisoformat(row[2])) if row else None


def undo(db: sqlite3.Connection) -> Batch | None:
    batch = last(db)
    if batch is None:
        return None
    rows = db.execute(
        "select id, at, line, logged_at, existed from before where batch = ? order by rowid desc",
        (batch.id,),
    ).fetchall()
    with db:
        for identity, at, line, logged_at, existed in rows:
            db.execute("delete from transitions where id = ?", (identity,))
            if existed:
                db.execute(
                    "insert into transitions (id, at, line, logged_at) values (?, ?, ?, ?)",
                    (identity, at, line, logged_at),
                )
        db.execute("update batches set undone = 1 where id = ?", (batch.id,))
    return batch
