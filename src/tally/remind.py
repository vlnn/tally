"""Reminders: a time or a repeat first, then what to be reminded of, in Large Type when due.

Each reminder is a row in the database and a launchd agent. A one-shot agent fires once at
the reminder's minute; a repeating one fires on its calendar or every so long. The agent asks
Alfred to run the workflow's `remind` trigger with the reminder's id; the workflow prints its
text into Large Type, moves a repeat on to its next firing, and removes a finished agent.
"""

from __future__ import annotations

import os
import plistlib
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import NamedTuple

from hoard.alfred import fold

from tally import durations, repeats
from tally.nudge import BUNDLE_ID, domain, launchctl
from tally.repeats import ONCE, Rule, next_at, wall

TRIGGER = "remind"
PREFIX = "com.anokhin.tally.remind"
SOON = timedelta(hours=1)

SCHEMA = """
create table if not exists reminders (
    id integer primary key,
    at text not null,
    text text not null,
    state text not null default 'pending'
);
"""
COLUMNS = {
    "typed": "text not null default ''",
    "rule": "text not null default ''",
    "until": "text",
    "skip": "integer not null default 0",
}


class Wanted(NamedTuple):
    at: datetime | None
    text: str
    problem: str = ""
    rule: Rule = ONCE
    until: datetime | None = None


def relative(words: list[str], now: datetime) -> tuple[datetime, int] | None:
    """`+15`, `+15 min`, `+1h30m`, `+30s`: that long from now, and how many words it took.

    With seconds in it the moment is exact; without, it lands on the minute.
    """
    found = durations.leading(words, "+")
    if found is None:
        return None
    at = (now + found.length).replace(microsecond=0)
    return (at if found.seconds else at.replace(second=0)), found.taken


def when(words: list[str], now: datetime) -> tuple[datetime, int] | None:
    found = relative(words, now)
    if found:
        return found
    moment = wall(words[0])
    return (next_at(moment, now), 1) if moment else None


def ends(words: list[str], now: datetime) -> tuple[datetime, list[str]] | None:
    """A trailing `until 18:00`, `until fri`, `until 2026-11-30`, and the words before it."""
    if len(words) < 3 or words[-2].lower() != "until":
        return None
    found = repeats.ending(words[-1], now)
    return (found, words[:-2]) if found else None


def wanted(text: str, now: datetime) -> Wanted | None:
    """A reminder when the text starts with a time to come or a repeat, otherwise None."""
    words = text.split()
    if not words:
        return None
    repeat = repeats.parse(words, now)
    if repeat:
        rule, at, taken = repeat
    else:
        found = when(words, now)
        if found is None:
            return None
        (at, taken), rule = found, ONCE
    rest = words[taken:]
    finish = ends(rest, now) if rule.repeats else None
    if finish:
        rest = finish[1]
    if not rest:
        return Wanted(at, "", "Type what to remind you of after the time", rule)
    return Wanted(at, " ".join(rest), "", rule, finish[0] if finish else None)


def connect(db: sqlite3.Connection) -> sqlite3.Connection:
    db.executescript(SCHEMA)
    have = {row[1] for row in db.execute("pragma table_info(reminders)")}
    for name, kind in COLUMNS.items():
        if name not in have:
            db.execute(f"alter table reminders add column {name} {kind}")
    return db


class Reminder(NamedTuple):
    id: int
    at: datetime
    text: str
    rule: Rule = ONCE
    until: datetime | None = None
    typed: str = ""
    skip: bool = False


FIELDS = "id, at, text, rule, until, typed, skip"


def read(row: tuple) -> Reminder:
    identity, at, text, rule, until, typed, skip = row
    ending = datetime.fromisoformat(until) if until else None
    return Reminder(
        identity, datetime.fromisoformat(at), text, repeats.decode(rule), ending, typed, bool(skip)
    )


def add(db: sqlite3.Connection, chosen: Wanted, typed: str) -> Reminder:
    assert chosen.at is not None
    connect(db)
    with db:
        cursor = db.execute(
            "insert into reminders (at, text, rule, until, typed) values (?, ?, ?, ?, ?)",
            (
                exact(chosen.at),
                chosen.text.strip(),
                repeats.encode(chosen.rule),
                exact(chosen.until) if chosen.until else None,
                typed.strip(),
            ),
        )
    return Reminder(
        cursor.lastrowid or 0, chosen.at, chosen.text.strip(), chosen.rule, chosen.until, typed
    )


def exact(at: datetime) -> str:
    return at.replace(microsecond=0).isoformat(timespec="seconds")


def pending(db: sqlite3.Connection) -> list[Reminder]:
    connect(db)
    rows = db.execute(
        f"select {FIELDS} from reminders where state = 'pending' order by at, id"
    ).fetchall()
    return [read(row) for row in rows]


def find(db: sqlite3.Connection, identity: int) -> Reminder | None:
    connect(db)
    row = db.execute(f"select {FIELDS} from reminders where id = ?", (identity,)).fetchone()
    return read(row) if row else None


def settle(db: sqlite3.Connection, identity: int, state: str) -> None:
    with db:
        db.execute("update reminders set state = ? where id = ?", (state, identity))


def move(db: sqlite3.Connection, identity: int, at: datetime, skip: bool = False) -> None:
    with db:
        db.execute(
            "update reminders set at = ?, skip = ? where id = ?", (exact(at), int(skip), identity)
        )


def soon(chosen: Reminder, now: datetime) -> bool:
    return not chosen.rule.repeats or chosen.at - now <= SOON


def same_text(db: sqlite3.Connection, text: str) -> list[Reminder]:
    return [r for r in pending(db) if fold(r.text) == fold(text)]


def finish(db: sqlite3.Connection, chosen: Reminder, state: str) -> None:
    unschedule(chosen.id)
    settle(db, chosen.id, state)


def fire(db: sqlite3.Connection, chosen: Reminder, now: datetime) -> str:
    """What to show when the agent fires, if anything, after moving the reminder on."""
    if chosen.until and now >= chosen.until:
        finish(db, chosen, "done")
        return ""
    if not chosen.rule.repeats:
        finish(db, chosen, "shown")
        return chosen.text
    coming = repeats.next_after(chosen.rule, chosen.at, now)
    if chosen.until and coming >= chosen.until:
        finish(db, chosen, "done")
    else:
        move(db, chosen.id, coming)
    return "" if chosen.skip else chosen.text


def label(identity: int) -> str:
    return f"{PREFIX}.{identity}"


def agent_folder() -> Path:
    return Path(os.path.expanduser("~/Library/LaunchAgents"))


def agent_path(identity: int) -> Path:
    return agent_folder() / f"{label(identity)}.plist"


def when_to_run(chosen: Reminder, now: datetime) -> dict:
    """A calendar minute, which launchd keeps across sleep; seconds need a countdown instead."""
    if chosen.rule.repeats:
        return repeats.launchd(chosen.rule, chosen.at)
    if chosen.at.second:
        return {"StartInterval": max(1, int((chosen.at - now).total_seconds()))}
    at = chosen.at
    return {
        "StartCalendarInterval": {
            "Month": at.month,
            "Day": at.day,
            "Hour": at.hour,
            "Minute": at.minute,
        }
    }


def agent(chosen: Reminder, now: datetime) -> dict:
    script = (
        'tell application id "com.runningwithcrayons.Alfred" to run trigger '
        f'"{TRIGGER}" in workflow "{BUNDLE_ID}" with argument "{chosen.id}"'
    )
    return {
        "Label": label(chosen.id),
        "ProgramArguments": ["/usr/bin/osascript", "-e", script],
        **when_to_run(chosen, now),
        "ProcessType": "Interactive",
    }


def schedule(chosen: Reminder, now: datetime) -> Path:
    path = agent_path(chosen.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        plistlib.dump(agent(chosen, now), handle)
    launchctl("bootstrap", domain(), str(path))
    return path


def unschedule(identity: int) -> None:
    launchctl("bootout", f"{domain()}/{label(identity)}")
    agent_path(identity).unlink(missing_ok=True)


def until(at: datetime, now: datetime) -> str:
    seconds = max(0, int((at - now).total_seconds()))
    if seconds < 60:
        return f"in {seconds} s"
    minutes = seconds // 60
    if minutes < 60:
        return f"in {minutes} min"
    return f"in {minutes // 60}:{minutes % 60:02d}"


def timing(chosen: Reminder | Wanted, now: datetime) -> str:
    """`21:00`, `daily 09:00`, `mon, thu 19:00`, `every 45 min`."""
    assert chosen.at is not None
    if chosen.rule.kind == "every":
        return repeats.describe(chosen.rule)
    if chosen.rule.repeats:
        return f"{repeats.describe(chosen.rule)} {chosen.at:%H:%M}"
    return spoken(chosen.at, now)


def spoken(at: datetime, now: datetime) -> str:
    clock = f"{at:%H:%M:%S}" if at.second else f"{at:%H:%M}"
    if at.date() == now.date():
        return clock
    if at.date() == now.date() + timedelta(days=1):
        return f"tomorrow {clock}"
    return f"{at:%a %-d %b} {clock}"
