"""Which day a moment belongs to, given when the day starts."""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import NamedTuple

DEFAULT_START = "00:00"
CLOCK = re.compile(r"^(\d{1,2}):(\d{2})$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RULES = {"@today": 0, "@yesterday": 1}
RANGES = ("@week", "@lastweek", "@month", "@lastmonth")


def offset(setting: str) -> timedelta:
    found = CLOCK.match(setting.strip() or DEFAULT_START)
    if not found or int(found.group(1)) > 23 or int(found.group(2)) > 59:
        return timedelta()
    return timedelta(hours=int(found.group(1)), minutes=int(found.group(2)))


class Window(NamedTuple):
    day: date
    since: datetime
    until: datetime

    @property
    def length(self) -> int:
        return (self.until - self.since).days

    def days(self) -> list[Window]:
        starts = self.since - datetime.combine(self.day, time())
        return [window(self.day + timedelta(days=n), starts) for n in range(self.length)]


def day_of(moment: datetime, starts: timedelta) -> date:
    return (moment - starts).date()


def window(day: date, starts: timedelta) -> Window:
    since = datetime.combine(day, time()) + starts
    return Window(day, since, since + timedelta(days=1))


def today(now: datetime, starts: timedelta) -> Window:
    return window(day_of(now, starts), starts)


def span(first: date, last: date, starts: timedelta) -> Window:
    return Window(first, window(first, starts).since, window(last, starts).until)


def month_before(day: date) -> date:
    return (day.replace(day=1) - timedelta(days=1)).replace(day=1)


def month_after(day: date) -> date:
    return (day.replace(day=28) + timedelta(days=4)).replace(day=1)


def ranged(word: str, today: date, starts: timedelta) -> Window:
    monday = today - timedelta(days=today.weekday())
    first = today.replace(day=1)
    if word == "@week":
        return span(monday, monday + timedelta(days=6), starts)
    if word == "@lastweek":
        return span(monday - timedelta(days=7), monday - timedelta(days=1), starts)
    if word == "@month":
        return span(first, month_after(first) - timedelta(days=1), starts)
    return span(month_before(first), first - timedelta(days=1), starts)


def asked(word: str, now: datetime, starts: timedelta) -> Window | None:
    """The window a rule word names: @today, @yesterday, @week, @month, their last, or a date."""
    if word in RULES:
        return window(day_of(now, starts) - timedelta(days=RULES[word]), starts)
    if word in RANGES:
        return ranged(word, day_of(now, starts), starts)
    if DATE.match(word):
        try:
            return window(date.fromisoformat(word), starts)
        except ValueError:
            return None
    return None


def is_rule(word: str) -> bool:
    return word in RULES or word in RANGES or bool(DATE.match(word))


def range_label(shown: Window, today: date) -> str:
    last = shown.day + timedelta(days=shown.length - 1)
    if shown.day.day == 1 and last == month_after(shown.day) - timedelta(days=1):
        unit = "month"
        current = shown.day == today.replace(day=1)
    else:
        unit = "week"
        current = shown.day <= today <= last
    return f"{'this' if current else 'last'} {unit}"


def label(shown: Window, now: datetime, starts: timedelta) -> str:
    if shown.length > 1:
        return range_label(shown, day_of(now, starts))
    distance = (day_of(now, starts) - shown.day).days
    if distance == 0:
        return "today"
    if distance == 1:
        return "yesterday"
    return f"{shown.day:%a %-d %b}"
