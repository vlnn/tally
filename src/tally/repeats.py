"""How a reminder repeats: once, daily, on some weekdays, or every so long.

A rule is read from the first words of what was typed (`daily 9:00`, `mon,thu 19:00`,
`every 45m`), says when it fires next, describes itself, and tells launchd when to run.
"""

from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from typing import NamedTuple

from tally import durations

CLOCK = re.compile(r"^(\d{1,2}):(\d{2})$")
MERIDIEM = re.compile(r"^(\d{1,2})(?::(\d{2}))?(am|pm)$", re.IGNORECASE)
WEEK = tuple(range(7))
WEEKDAYS, WEEKENDS = (0, 1, 2, 3, 4), (5, 6)
SHORT = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
NAMES = {
    **{name: n for n, name in enumerate(SHORT)},
    **{
        name: n
        for n, names in enumerate(
            (
                ("monday",),
                ("tues", "tuesday"),
                ("wednesday",),
                ("thur", "thurs", "thursday"),
                ("friday",),
                ("saturday",),
                ("sunday",),
            )
        )
        for name in names
    },
}
GROUPS = {"daily": WEEK, "weekdays": WEEKDAYS, "weekends": WEEKENDS}


class Rule(NamedTuple):
    kind: str
    days: tuple[int, ...] = ()
    every: int = 0

    @property
    def repeats(self) -> bool:
        return self.kind != "once"


ONCE = Rule("once")


def encode(rule: Rule) -> str:
    if rule.kind == "days":
        return "days:" + ",".join(str(d) for d in rule.days)
    if rule.kind == "every":
        return f"every:{rule.every}"
    return "" if rule.kind == "once" else rule.kind


def decode(text: str) -> Rule:
    kind, _, value = (text or "").partition(":")
    if kind == "days":
        return Rule("days", tuple(int(d) for d in value.split(",")))
    if kind == "every":
        return Rule("every", every=int(value))
    return Rule(kind) if kind == "daily" else ONCE


def clock(hour: int, minute: int) -> time | None:
    return time(hour, minute) if hour < 24 and minute < 60 else None


def wall(word: str) -> time | None:
    """`21:00`, `9pm`, `9:30PM` as a time of day."""
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


def on_days(word: str) -> tuple[int, ...] | None:
    """`mon,thu`, `mon+thu`, `monday`: the weekdays a word names, or None."""
    lowered = word.lower()
    if lowered in GROUPS:
        return GROUPS[lowered]
    parts = [part for part in re.split(r"[,+]", lowered) if part]
    if not parts or any(part not in NAMES for part in parts):
        return None
    return tuple(sorted({NAMES[part] for part in parts}))


def calendar(words: list[str]) -> tuple[tuple[int, ...], time, int] | None:
    """Leading day words then a clock: the days, the time, and the words taken."""
    chosen: set[int] = set()
    taken = 0
    while taken < len(words) and on_days(words[taken]) is not None:
        chosen |= set(on_days(words[taken]) or ())
        taken += 1
    if not taken or taken >= len(words):
        return None
    moment = wall(words[taken])
    return (tuple(sorted(chosen)), moment, taken + 1) if moment else None


def calendar_rule(days: tuple[int, ...]) -> Rule:
    return Rule("daily") if days == WEEK else Rule("days", days)


def first_on(days: tuple[int, ...], moment: time, now: datetime) -> datetime:
    for ahead in range(8):
        candidate = datetime.combine(now.date() + timedelta(days=ahead), moment)
        if candidate > now and candidate.weekday() in days:
            return candidate
    raise ValueError("no day in the coming week")


def interval(words: list[str], now: datetime) -> tuple[Rule, datetime, int] | None:
    """`every 45m`, `every 2 hours`, `every 90`: the rule, its first firing, the words taken."""
    if len(words) < 2 or words[0].lower() != "every":
        return None
    found = durations.leading([f"+{words[1]}", *words[2:]], "+")
    if found is None:
        return None
    seconds = int(found.length.total_seconds())
    first = (now + found.length).replace(microsecond=0)
    return (
        Rule("every", every=seconds),
        first if found.seconds else first.replace(second=0),
        1 + found.taken,
    )


def parse(words: list[str], now: datetime) -> tuple[Rule, datetime, int] | None:
    """A repeat at the start of the words, its first firing and how many words it took."""
    every = interval(words, now)
    if every:
        return every
    found = calendar(words)
    if found is None:
        return None
    days, moment, taken = found
    return calendar_rule(days), first_on(days, moment, now), taken


def days_of(rule: Rule) -> tuple[int, ...]:
    return WEEK if rule.kind == "daily" else rule.days


def next_after(rule: Rule, at: datetime, now: datetime) -> datetime:
    """The firing after this one, and after now."""
    if rule.kind == "every":
        step = timedelta(seconds=rule.every)
        coming = at + step
        while coming <= now:
            coming += step
        return coming
    return first_on(days_of(rule), at.time(), max(at, now))


def spoken_days(days: tuple[int, ...]) -> str:
    for name, group in GROUPS.items():
        if days == group:
            return name
    return ", ".join(SHORT[d] for d in days)


def spoken_every(seconds: int) -> str:
    hours, rest = divmod(seconds, 3600)
    minutes, seconds = divmod(rest, 60)
    parts = [f"{hours} h" if hours else "", f"{minutes} min" if minutes else ""]
    parts.append(f"{seconds} s" if seconds else "")
    return "every " + " ".join(part for part in parts if part)


def describe(rule: Rule) -> str:
    if rule.kind == "every":
        return spoken_every(rule.every)
    if rule.kind == "once":
        return ""
    return spoken_days(days_of(rule))


def launchd(rule: Rule, at: datetime) -> dict:
    """When launchd runs a repeating reminder's agent."""
    if rule.kind == "every":
        return {"StartInterval": rule.every}
    if rule.kind == "daily":
        return {"StartCalendarInterval": {"Hour": at.hour, "Minute": at.minute}}
    return {
        "StartCalendarInterval": [
            {"Weekday": (day + 1) % 7, "Hour": at.hour, "Minute": at.minute} for day in rule.days
        ]
    }


DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def ending(word: str, now: datetime) -> datetime | None:
    """`until` what: the nearest coming such time, the end of a date or of the coming day."""
    moment = wall(word)
    if moment:
        return next_at(moment, now)
    if DATE.match(word):
        try:
            return datetime.combine(date.fromisoformat(word) + timedelta(days=1), time())
        except ValueError:
            return None
    days = on_days(word)
    if days and len(days) == 1:
        ahead = (days[0] - now.weekday()) % 7
        return datetime.combine(now.date() + timedelta(days=ahead + 1), time())
    return None
