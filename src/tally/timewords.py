"""A time at either end of a line says when the block started: `-10m mail`, `mail 14:05`."""

from __future__ import annotations

import re
from datetime import datetime, time
from typing import NamedTuple

from tally import durations

CLOCK = re.compile(r"^(\d{1,2}):(\d{2})$")


class Typed(NamedTuple):
    line: str
    at: datetime | None
    problem: str = ""


def clock(word: str, now: datetime) -> datetime | None:
    found = CLOCK.match(word)
    if not found or int(found.group(1)) > 23 or int(found.group(2)) > 59:
        return None
    return datetime.combine(now.date(), time(int(found.group(1)), int(found.group(2))))


def ago(word: str, now: datetime) -> datetime | None:
    found = durations.parse(word, "-", bare=False)
    return now - found.length if found else None


def moment(word: str, now: datetime) -> datetime | None:
    return clock(word, now) or ago(word, now)


def started(words: list[str], now: datetime) -> tuple[datetime, list[str]] | None:
    """When the block started and the words left: a span first, or a clock or span last."""
    first = durations.leading(words, "-")
    if first:
        return now - first.length, words[first.taken :]
    at = clock(words[-1], now) if len(words) > 1 else None
    if at:
        return at, words[:-1]
    last = durations.trailing(words, "-")
    if last:
        return now - last.length, words[: -last.taken]
    return None


def parse(text: str, now: datetime) -> Typed:
    words = text.split()
    if not words:
        return Typed("", None)
    found = started(words, now)
    if found is None:
        alone = moment(words[0], now) if len(words) == 1 else None
        if alone:
            return Typed("", alone, "Type what you were doing before the time")
        return Typed(" ".join(words), None)
    at, rest = found
    line = " ".join(rest)
    if not line:
        return Typed("", at, "Type what you were doing before the time")
    if at > now:
        return Typed(
            line, at, f"{at:%H:%M} has not happened yet; for a reminder, put the time first"
        )
    return Typed(line, at.replace(second=0, microsecond=0))
