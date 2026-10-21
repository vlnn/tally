"""Spans of time as typed: `+15`, `-10m`, `+1 hour 30 min`, `+30s`."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import NamedTuple

HOURS = r"(?:(\d+)\s*(?:hours|hour|hrs|hr|h))"
MINUTES = r"(?:(\d+)\s*(?:minutes|minute|mins|min|m))"
SECONDS = r"(?:(\d+)\s*(?:seconds|second|secs|sec|s))"
UNITS = re.compile(rf"^([+-])\s*{HOURS}?\s*{MINUTES}?\s*{SECONDS}?$", re.IGNORECASE)
BARE = re.compile(rf"^([+-])\s*{HOURS}?\s*(\d+)$", re.IGNORECASE)
MOST_WORDS = 4


class Span(NamedTuple):
    length: timedelta
    seconds: bool
    taken: int = 1


def parse(phrase: str, sign: str, bare: bool = True) -> Span | None:
    """The span a phrase with this sign means; a bare number is minutes when allowed."""
    found = UNITS.match(phrase)
    groups = found.groups() if found else None
    if groups is None and bare:
        plain = BARE.match(phrase)
        groups = (*plain.groups(), None) if plain else None
    if groups is None or groups[0] != sign:
        return None
    hours, minutes, seconds = (int(part) if part else 0 for part in groups[1:])
    length = timedelta(hours=hours, minutes=minutes, seconds=seconds)
    return Span(length, bool(groups[3])) if length else None


def leading(words: list[str], sign: str) -> Span | None:
    """The longest run of first words that is a span, and how many words it took."""
    for taken in range(min(MOST_WORDS, len(words)), 0, -1):
        found = parse(" ".join(words[:taken]), sign)
        if found:
            return found._replace(taken=taken)
    return None


def trailing(words: list[str], sign: str) -> Span | None:
    """The same at the end; a bare number there stays part of the text."""
    for taken in range(min(MOST_WORDS, len(words) - 1), 0, -1):
        found = parse(" ".join(words[-taken:]), sign, bare=False)
        if found:
            return found._replace(taken=taken)
    return None


def hm(span: timedelta) -> str:
    minutes = int(span.total_seconds() // 60)
    return f"{minutes // 60}:{minutes % 60:02d}"
