"""Which day a moment belongs to, given when the day starts."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import NamedTuple

DEFAULT_START = "00:00"
CLOCK = re.compile(r"^(\d{1,2}):(\d{2})$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RULES = {"@today": 0, "@yesterday": 1}


def offset(setting: str) -> timedelta:
    found = CLOCK.match(setting.strip() or DEFAULT_START)
    if not found or int(found.group(1)) > 23 or int(found.group(2)) > 59:
        return timedelta()
    return timedelta(hours=int(found.group(1)), minutes=int(found.group(2)))


class Window(NamedTuple):
    day: date
    since: datetime
    until: datetime


def day_of(moment: datetime, starts: timedelta) -> date:
    return (moment - starts).date()


def window(day: date, starts: timedelta) -> Window:
    since = datetime.combine(day, time()) + starts
    return Window(day, since, since + timedelta(days=1))


def today(now: datetime, starts: timedelta) -> Window:
    return window(day_of(now, starts), starts)


def asked(word: str, now: datetime, starts: timedelta) -> Window | None:
    """The window a rule word names: @today, @yesterday or a date."""
    if word in RULES:
        return window(day_of(now, starts) - timedelta(days=RULES[word]), starts)
    if DATE.match(word):
        try:
            return window(date.fromisoformat(word), starts)
        except ValueError:
            return None
    return None


def is_rule(word: str) -> bool:
    return word in RULES or bool(DATE.match(word))


def label(shown: Window, now: datetime, starts: timedelta) -> str:
    distance = (day_of(now, starts) - shown.day).days
    if distance == 0:
        return "today"
    if distance == 1:
        return "yesterday"
    return f"{shown.day:%a %-d %b}"
