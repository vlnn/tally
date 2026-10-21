"""Unclaimed time: the gap since the last stop, and what can be claimed in it.

A gap starts at the later of today's last stop and the start of the nudge hours, and only
exists while nothing runs and the hours are on. A claim fills it: one task backdated to a
start inside the gap, or a split of several, the last of which keeps running.
"""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import NamedTuple, Protocol

from tally import durations, store

SATURDAY = 5
DEFAULT_LADDER = (15, 30, 45, 60)
DISPLAY_ON = re.compile(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}).*Display is turned on")
FRESH = timedelta(seconds=60)


class Hours(Protocol):
    @property
    def since(self) -> time: ...
    @property
    def until(self) -> time: ...
    @property
    def weekends(self) -> bool: ...


class Gap(NamedTuple):
    start: datetime
    now: datetime

    @property
    def length(self) -> timedelta:
        return self.now - self.start


def in_hours(now: datetime, hours: Hours) -> bool:
    if now.weekday() >= SATURDAY and not hours.weekends:
        return False
    return hours.since <= now.time() < hours.until


def find(db: sqlite3.Connection, now: datetime, hours: Hours) -> Gap | None:
    """The gap now, if nothing runs and it is within the hours."""
    if not in_hours(now, hours) or store.running(db, now):
        return None
    opening = datetime.combine(now.date(), hours.since)
    last = store.last_before(db, now)
    start = max(opening, last.at) if last else opening
    return Gap(start, now) if start < now else None


def ladder(setting: str) -> tuple[int, ...]:
    """`15,30,45,60` as minutes, rising; anything unreadable is the default."""
    try:
        steps = tuple(int(part) for part in setting.split(",") if part.strip())
    except ValueError:
        return DEFAULT_LADDER
    rising = len(steps) == len(DEFAULT_LADDER) and all(0 < a < b for a, b in zip(steps, steps[1:]))
    return steps if rising else DEFAULT_LADDER


def level(gap: Gap | None, steps: tuple[int, ...]) -> int:
    """0 below the first step, then 1 to 4."""
    if gap is None:
        return 0
    minutes = gap.length.total_seconds() / 60
    return sum(1 for step in steps if minutes >= step)


def display_on(lines: list[str], gap: Gap) -> datetime | None:
    """The last time the display came on inside the gap, from `pmset -g log` lines."""
    found = None
    for line in lines:
        matched = DISPLAY_ON.match(line)
        if matched:
            moment = datetime.fromisoformat(matched.group(1)).replace(second=0)
            if gap.start < moment < gap.now:
                found = moment
    return found


def pmset_lines(cache: Path | None, now: datetime) -> list[str]:
    """The recent display-on lines of the power log, kept a minute so typing stays quick."""
    if cache and cache.exists() and now - datetime.fromtimestamp(cache.stat().st_mtime) < FRESH:
        return cache.read_text(encoding="utf-8").splitlines()
    import subprocess

    try:
        read = subprocess.run(
            ["/bin/sh", "-c", "pmset -g log | grep 'Display is turned on' | tail -n 50"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return []
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        cache.write_text(read.stdout, encoding="utf-8")
    return read.stdout.splitlines()


class Claim(NamedTuple):
    gap: Gap
    threshold: timedelta
    woke: Callable[[], datetime | None] = lambda: None

    @property
    def worth_asking(self) -> bool:
        return self.gap.length >= self.threshold


class Part(NamedTuple):
    line: str
    length: timedelta | None


def part(text: str) -> Part:
    words = text.split()
    found = durations.parse(f"+{words[-1]}", "+") if len(words) > 1 else None
    return Part(" ".join(words[:-1]), found.length) if found else Part(" ".join(words), None)


def split(text: str) -> list[Part] | None:
    """`standup 30, api-design` as parts, or None when there is no comma.

    The last part runs on, so its words are all line: `review pr 212` is not 212 minutes.
    """
    if "," not in text:
        return None
    *timed, last = text.split(",")
    return [*(part(piece) for piece in timed), Part(" ".join(last.split()), None)]


class Filled(NamedTuple):
    starts: tuple[tuple[datetime, str], ...] = ()
    problem: str = ""


def fill(parts: list[Part], gap: Gap) -> Filled:
    """Where each part starts, from the start of the gap; the last part runs on."""
    if any(not p.line for p in parts):
        return Filled(problem="Every part needs a name: standup 30, api-design")
    if any(p.length is None for p in parts[:-1]):
        return Filled(problem="Give every part but the last a length: standup 30, api-design")
    total = sum((p.length or timedelta() for p in parts), timedelta())
    if total >= gap.length:
        over = f"{durations.hm(total)} of parts is more than the {durations.hm(gap.length)} gap"
        return Filled(problem=over)
    starts = []
    moment = gap.start
    for each in parts:
        starts.append((moment, each.line))
        moment += each.length or timedelta()
    return Filled(tuple(starts))
