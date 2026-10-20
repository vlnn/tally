"""#tags in a line, their short names, and the time spent under each."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from hoard.alfred import fold

from tally import store

TAG = re.compile(r"(?<!\S)#([^\s#]+)")
DEFAULT_ALIASES = "w=work"
UNTAGGED = "untagged"


def key(tag: str) -> str:
    return fold(tag.strip().lstrip("#"))


def aliases(setting: str) -> dict[str, str]:
    """`w=work, l=lexer` (commas or new lines) to {"w": "work", "l": "lexer"}."""
    found = {}
    for pair in re.split(r"[,\n]", setting):
        short, sep, full = pair.partition("=")
        if sep and key(short) and key(full):
            found[key(short)] = key(full)
    return found


def canonical(line: str, known: dict[str, str]) -> str:
    """The line with every tag folded and every short tag spelled out."""
    return TAG.sub(lambda tag: "#" + known.get(key(tag.group(1)), key(tag.group(1))), line)


def of(line: str) -> list[str]:
    return list(dict.fromkeys(f"#{key(found)}" for found in TAG.findall(line)))


def totals(blocks: list[store.Block], now: datetime) -> list[tuple[str, timedelta]]:
    """Time under each tag, a block counting fully for every tag it has; then the untagged."""
    summed: dict[str, timedelta] = {}
    for block in blocks:
        for tag in of(block.line) or [UNTAGGED]:
            summed[tag] = summed.get(tag, timedelta()) + block.length(now)
    tagged = sorted(
        ((tag, total) for tag, total in summed.items() if tag != UNTAGGED),
        key=lambda item: (-item[1], item[0]),
    )
    rest = [(UNTAGGED, summed[UNTAGGED])] if UNTAGGED in summed else []
    return tagged + rest


def any_tagged(blocks: list[store.Block]) -> bool:
    return any(of(block.line) for block in blocks)
