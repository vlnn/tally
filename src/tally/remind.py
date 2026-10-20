"""Reminders: a time first, then what to be reminded of, shown in Large Type when it comes.

Each reminder is a row in the database and a one-shot launchd agent whose calendar time is
the reminder's minute. The agent asks Alfred to run the workflow's `remind` trigger with the
reminder's id; the workflow prints its text into Large Type and removes the agent.
"""

from __future__ import annotations

import os
import plistlib
import re
import sqlite3
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import NamedTuple

from tally import store
from tally.nudge import BUNDLE_ID, domain, launchctl

TRIGGER = "remind"
PREFIX = "com.anokhin.tally.remind"
IN = re.compile(
    r"^\+\s*(?:(\d+)\s*(?:h|hr|hrs|hour|hours))?\s*(?:(\d+)\s*(?:m|min|mins|minute|minutes)?)?$",
    re.IGNORECASE,
)
MOST_WORDS = 4
CLOCK = re.compile(r"^(\d{1,2}):(\d{2})$")
MERIDIEM = re.compile(r"^(\d{1,2})(?::(\d{2}))?(am|pm)$", re.IGNORECASE)

SCHEMA = """
create table if not exists reminders (
    id integer primary key,
    at text not null,
    text text not null,
    state text not null default 'pending'
);
"""


class Wanted(NamedTuple):
    at: datetime | None
    text: str
    problem: str = ""


def after(phrase: str, now: datetime) -> datetime | None:
    """`+15`, `+15m`, `+15 min`, `+1h30m`, `+1 hour 30 min`: that long from now."""
    found = IN.match(phrase)
    if not found:
        return None
    hours, minutes = (int(part) if part else 0 for part in found.groups())
    span = timedelta(hours=hours, minutes=minutes)
    return (now + span).replace(second=0, microsecond=0) if span else None


def relative(words: list[str], now: datetime) -> tuple[datetime, int] | None:
    """The longest run of leading words that reads as a duration, and how many it took."""
    for taken in range(min(MOST_WORDS, len(words)), 0, -1):
        at = after(" ".join(words[:taken]), now)
        if at:
            return at, taken
    return None


def clock(hour: int, minute: int) -> time | None:
    return time(hour, minute) if hour < 24 and minute < 60 else None


def wall(word: str) -> time | None:
    found = CLOCK.match(word)
    if found:
        return clock(int(found.group(1)), int(found.group(2)))
    found = MERIDIEM.match(word)
    if not found or not 1 <= int(found.group(1)) <= 12:
        return None
    hour = int(found.group(1)) % 12 + (12 if found.group(3).lower() == "pm" else 0)
    return clock(hour, int(found.group(2) or 0))


def next_at(moment: time, now: datetime) -> datetime:
    today = datetime.combine(now.date(), moment)
    return today if today > now else today + timedelta(days=1)


def when(words: list[str], now: datetime) -> tuple[datetime, int] | None:
    found = relative(words, now)
    if found:
        return found
    moment = wall(words[0])
    return (next_at(moment, now), 1) if moment else None


def wanted(text: str, now: datetime) -> Wanted | None:
    """A reminder when the text starts with a time to come, otherwise None."""
    words = text.split()
    if not words:
        return None
    found = when(words, now)
    if found is None:
        return None
    at, taken = found
    rest = " ".join(words[taken:])
    if not rest:
        return Wanted(at, "", "Type what to remind you of after the time")
    return Wanted(at, rest)


def connect(db: sqlite3.Connection) -> sqlite3.Connection:
    db.executescript(SCHEMA)
    return db


class Reminder(NamedTuple):
    id: int
    at: datetime
    text: str


def add(db: sqlite3.Connection, at: datetime, text: str) -> Reminder:
    connect(db)
    with db:
        cursor = db.execute(
            "insert into reminders (at, text) values (?, ?)", (store.stamp(at), text.strip())
        )
    return Reminder(cursor.lastrowid or 0, at, text.strip())


def pending(db: sqlite3.Connection) -> list[Reminder]:
    connect(db)
    rows = db.execute(
        "select id, at, text from reminders where state = 'pending' order by at, id"
    ).fetchall()
    return [Reminder(i, datetime.fromisoformat(at), text) for i, at, text in rows]


def find(db: sqlite3.Connection, identity: int) -> Reminder | None:
    connect(db)
    row = db.execute("select id, at, text from reminders where id = ?", (identity,)).fetchone()
    return Reminder(row[0], datetime.fromisoformat(row[1]), row[2]) if row else None


def settle(db: sqlite3.Connection, identity: int, state: str) -> None:
    with db:
        db.execute("update reminders set state = ? where id = ?", (state, identity))


def label(identity: int) -> str:
    return f"{PREFIX}.{identity}"


def agent_folder() -> Path:
    return Path(os.path.expanduser("~/Library/LaunchAgents"))


def agent_path(identity: int) -> Path:
    return agent_folder() / f"{label(identity)}.plist"


def agent(chosen: Reminder) -> dict:
    script = (
        'tell application id "com.runningwithcrayons.Alfred" to run trigger '
        f'"{TRIGGER}" in workflow "{BUNDLE_ID}" with argument "{chosen.id}"'
    )
    at = chosen.at
    return {
        "Label": label(chosen.id),
        "ProgramArguments": ["/usr/bin/osascript", "-e", script],
        "StartCalendarInterval": {
            "Month": at.month,
            "Day": at.day,
            "Hour": at.hour,
            "Minute": at.minute,
        },
        "ProcessType": "Interactive",
    }


def schedule(chosen: Reminder) -> Path:
    path = agent_path(chosen.id)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as handle:
        plistlib.dump(agent(chosen), handle)
    launchctl("bootstrap", domain(), str(path))
    return path


def unschedule(identity: int) -> None:
    launchctl("bootout", f"{domain()}/{label(identity)}")
    agent_path(identity).unlink(missing_ok=True)


def until(at: datetime, now: datetime) -> str:
    minutes = max(0, int((at - now).total_seconds() // 60))
    if minutes < 60:
        return f"in {minutes} min"
    return f"in {minutes // 60}:{minutes % 60:02d}"


def spoken(at: datetime, now: datetime) -> str:
    if at.date() == now.date():
        return f"{at:%H:%M}"
    if at.date() == now.date() + timedelta(days=1):
        return f"tomorrow {at:%H:%M}"
    return f"{at:%a %-d %b} {at:%H:%M}"
