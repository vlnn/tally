"""The day drawn as a line of quarter-hour cells, with its totals."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import NamedTuple

from hoard.alfred import fold

from tally import days, store
from tally.present import hm

CELL = timedelta(minutes=15)
FIRST_HOUR, LAST_HOUR = 6, 22
EMPTY, UNTRACKED, NOW, BACKFILLED = "·", "░", "▶", "▚"
GLYPHS = "█▓▒▞▙▟▛▜"
SPARE = "▪"
TAG = re.compile(r"(?<!\S)#([^\s#]+)")


def group_of(line: str) -> str:
    tagged = TAG.search(line)
    return f"#{fold(tagged.group(1))}" if tagged else line


class Group(NamedTuple):
    name: str
    total: timedelta
    glyph: str


def groups(blocks: list[store.Block], now: datetime) -> list[Group]:
    totals: dict[str, timedelta] = {}
    for block in blocks:
        key = group_of(block.line)
        totals[key] = totals.get(key, timedelta()) + block.length(now)
    ranked = sorted(totals.items(), key=lambda item: (-item[1], item[0]))
    return [
        Group(name, total, GLYPHS[rank] if rank < len(GLYPHS) else SPARE)
        for rank, (name, total) in enumerate(ranked)
    ]


def hours(window: days.Window, blocks: list[store.Block], now: datetime) -> tuple[int, int]:
    first = min([FIRST_HOUR, *((b.start - window.since).seconds // 3600 for b in blocks)])
    ends = [(min(b.end or now, window.until) - window.since) for b in blocks]
    last = max([LAST_HOUR, *((e.seconds + 3599) // 3600 for e in ends if e < timedelta(days=1))])
    return first, min(last, 24)


def cell_glyph(
    moment: datetime, blocks: list[store.Block], glyphs: dict[str, str], now: datetime
) -> str:
    for block in blocks:
        if block.start <= moment < (block.end or now):
            return BACKFILLED if block.backfilled else glyphs[group_of(block.line)]
    inside = blocks and blocks[0].start <= moment < min(blocks[-1].end or now, now)
    return UNTRACKED if inside else EMPTY


def strip(
    window: days.Window, blocks: list[store.Block], glyphs: dict[str, str], now: datetime
) -> str:
    first, last = hours(window, blocks, now)
    cells = []
    moment = window.since + timedelta(hours=first)
    until = window.since + timedelta(hours=last)
    while moment < until:
        is_now = window.since <= now < window.until and moment <= now < moment + CELL
        cells.append(NOW if is_now else cell_glyph(moment, blocks, glyphs, now))
        moment += CELL
    return "".join(cells)


def scale(window: days.Window, blocks: list[store.Block], now: datetime) -> str:
    first, last = hours(window, blocks, now)
    marks = ""
    for hour in range(first, last, 2):
        marks = marks.ljust((hour - first) * 4) + f"{(window.since + timedelta(hours=hour)):%H}"
    return marks


def untracked(blocks: list[store.Block], now: datetime) -> timedelta:
    if not blocks:
        return timedelta()
    covered = sum((b.length(now) for b in blocks), timedelta())
    return min(blocks[-1].end or now, now) - blocks[0].start - covered


def totals(found: list[Group], blocks: list[store.Block], now: datetime) -> str:
    width = max([len(g.name) for g in found] + [9])
    lines = [f"{g.glyph} {g.name.ljust(width)}  {hm(g.total):>5}" for g in found]
    gap = untracked(blocks, now)
    if gap:
        lines.append(f"{UNTRACKED} {'untracked'.ljust(width)}  {hm(gap):>5}")
    if any(b.backfilled for b in blocks):
        lines.append(f"{BACKFILLED} backfilled")
    return "\n".join(lines)


def listing(blocks: list[store.Block], now: datetime) -> str:
    rows = []
    for block in blocks:
        end = f"{block.end:%H:%M}" if block.end else "now  "
        rows.append(f"{block.start:%H:%M}–{end}  {hm(block.length(now)):>5}  {block.line}")
    return "\n".join(rows)


def heading(
    window: days.Window, blocks: list[store.Block], now: datetime, starts: timedelta
) -> str:
    logged = sum((b.length(now) for b in blocks), timedelta())
    name = days.label(window, now, starts)
    return f"**{name} · {window.day:%a %-d %b}** · {hm(logged)} logged"


def render(window: days.Window, blocks: list[store.Block], now: datetime, starts: timedelta) -> str:
    if not blocks:
        return f"{heading(window, blocks, now, starts)}\n\nNothing logged."
    found = groups(blocks, now)
    glyphs = {g.name: g.glyph for g in found}
    parts = [
        heading(window, blocks, now, starts),
        f"```\n{scale(window, blocks, now)}\n{strip(window, blocks, glyphs, now)}\n```",
        f"```\n{totals(found, blocks, now)}\n```",
        f"```\n{listing(blocks, now)}\n```",
    ]
    return "\n\n".join(parts)


def shown(db, word: str, now: datetime, starts: timedelta) -> tuple[days.Window, str] | None:
    window = days.asked(word, now, starts)
    if window is None:
        return None
    blocks = store.blocks_within(db, window.since, window.until, now)
    return window, render(window, blocks, now, starts)
