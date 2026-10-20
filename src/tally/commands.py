"""Words that name a command rather than a task: stop, today, week, bar…"""

from __future__ import annotations

from typing import NamedTuple

from hoard.alfred import fold

MIN_TYPED = 2


class Command(NamedTuple):
    names: tuple[str, ...]
    kind: str
    word: str = ""


COMMANDS = (
    Command(("stop",), "stop"),
    Command(("today",), "view", "@today"),
    Command(("yesterday",), "view", "@yesterday"),
    Command(("week", "this week"), "view", "@week"),
    Command(("last week", "lastweek"), "view", "@lastweek"),
    Command(("month", "this month"), "view", "@month"),
    Command(("last month", "lastmonth"), "view", "@lastmonth"),
    Command(("bar", "swiftbar"), "bar"),
    Command(("nudge", "nudges"), "nudge"),
)


def typed(text: str) -> str:
    return " ".join(fold(text).lstrip("@").split())


def named(text: str) -> list[Command]:
    """Commands whose name starts with what was typed, two letters at least."""
    wanted = typed(text)
    if len(wanted) < MIN_TYPED:
        return []
    return [command for command in COMMANDS if any(n.startswith(wanted) for n in command.names)]
