"""The last word of a line may say when the block started."""

from __future__ import annotations

import re
from datetime import datetime, time, timedelta
from typing import NamedTuple

CLOCK = re.compile(r"^(\d{1,2}):(\d{2})$")
AGO = re.compile(r"^-(?:(\d+)h)?(?:(\d+)m)?$")


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
    found = AGO.match(word)
    if not found or word == "-":
        return None
    hours, minutes = (int(part) if part else 0 for part in found.groups())
    return now - timedelta(hours=hours, minutes=minutes)


def moment(word: str, now: datetime) -> datetime | None:
    return clock(word, now) or ago(word, now)


def parse(text: str, now: datetime) -> Typed:
    words = text.split()
    if not words:
        return Typed("", None)
    at = moment(words[-1], now)
    if at is None:
        return Typed(" ".join(words), None)
    line = " ".join(words[:-1])
    if not line:
        return Typed("", at, "Type what you were doing before the time")
    if at > now:
        return Typed(line, at, f"{at:%H:%M} has not happened yet")
    return Typed(line, at.replace(second=0, microsecond=0))
