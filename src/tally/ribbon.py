"""The day drawn as a line of quarter-hour cells, with its totals."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import NamedTuple

from tally import days, store, tags
from tally.present import hm

CELL = timedelta(minutes=15)
FIRST_HOUR, LAST_HOUR = 6, 22
EMPTY, UNTRACKED, NOW, BACKFILLED = "·", "░", "▶", "▚"
GLYPHS = "█▓▒▞▙▟▛▜"
SPARE = "▪"


def group_of(line: str) -> str:
    found = tags.of(line)
    return found[0] if found else line


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
    window: days.Window,
    blocks: list[store.Block],
    glyphs: dict[str, str],
    now: datetime,
    span: tuple[int, int] | None = None,
) -> str:
    first, last = span or hours(window, blocks, now)
    cells = []
    moment = window.since + timedelta(hours=first)
    until = window.since + timedelta(hours=last)
    while moment < until:
        is_now = window.since <= now < window.until and moment <= now < moment + CELL
        cells.append(NOW if is_now else cell_glyph(moment, blocks, glyphs, now))
        moment += CELL
    return "".join(cells)


def scale(
    window: days.Window,
    blocks: list[store.Block],
    now: datetime,
    span: tuple[int, int] | None = None,
) -> str:
    first, last = span or hours(window, blocks, now)
    marks = ""
    for hour in range(first, last, 2):
        marks = marks.ljust((hour - first) * 4) + f"{(window.since + timedelta(hours=hour)):%H}"
    return marks


def untracked(blocks: list[store.Block], now: datetime) -> timedelta:
    if not blocks:
        return timedelta()
    covered = sum((b.length(now) for b in blocks), timedelta())
    return min(blocks[-1].end or now, now) - blocks[0].start - covered


def totals(
    found: list[Group], blocks: list[store.Block], now: datetime, gap: timedelta | None = None
) -> str:
    width = max([len(g.name) for g in found] + [9])
    lines = [f"{g.glyph} {g.name.ljust(width)}  {hm(g.total):>5}" for g in found]
    gap = untracked(blocks, now) if gap is None else gap
    if gap:
        lines.append(f"{UNTRACKED} {'untracked'.ljust(width)}  {hm(gap):>5}")
    if any(b.backfilled for b in blocks):
        lines.append(f"{BACKFILLED} backfilled")
    return "\n".join(lines)


def by_tag(blocks: list[store.Block], now: datetime) -> str:
    found = tags.totals(blocks, now)
    width = max([len(tag) for tag, _ in found] + [9])
    return "\n".join(f"{tag.ljust(width)}  {hm(total):>5}" for tag, total in found)


def tag_part(blocks: list[store.Block], now: datetime) -> list[str]:
    return [f"**by tag**\n\n```\n{by_tag(blocks, now)}\n```"] if tags.any_tagged(blocks) else []


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


def render(
    window: days.Window,
    blocks: list[store.Block],
    now: datetime,
    starts: timedelta,
    aliases: dict[str, str] | None = None,
) -> str:
    if not blocks:
        return f"{heading(window, blocks, now, starts)}\n\nNothing logged."
    spelled = spelled_out(blocks, aliases or {})
    found = groups(spelled, now)
    glyphs = {g.name: g.glyph for g in found}
    parts = [
        heading(window, blocks, now, starts),
        f"```\n{scale(window, spelled, now)}\n{strip(window, spelled, glyphs, now)}\n```",
        f"```\n{totals(found, spelled, now)}\n```",
        *tag_part(spelled, now),
        f"```\n{listing(blocks, now)}\n```",
    ]
    return "\n\n".join(parts)


def inside(blocks: list[store.Block], day: days.Window, now: datetime) -> list[store.Block]:
    return [
        b.clipped(day.since, day.until, now)
        for b in blocks
        if (b.end or now) > day.since and b.start < day.until
    ]


def range_heading(window: days.Window, blocks: list[store.Block], now: datetime, starts) -> str:
    logged = sum((b.length(now) for b in blocks), timedelta())
    last = window.day + timedelta(days=window.length - 1)
    name = days.label(window, now, starts)
    return f"**{name} · {window.day:%-d %b} – {last:%-d %b}** · {hm(logged)} logged"


def day_line(
    day: days.Window,
    mine: list[store.Block],
    glyphs: dict[str, str],
    now: datetime,
    span: tuple[int, int],
) -> str:
    logged = sum((b.length(now) for b in mine), timedelta())
    total = hm(logged) if mine else ""
    return f"{day.day:%a} {day.day.day:>2}  {strip(day, mine, glyphs, now, span)}  {total:>5}"


def common_span(
    per_day: list[tuple[days.Window, list[store.Block]]], now: datetime
) -> tuple[int, int]:
    spans = [hours(day, mine, now) for day, mine in per_day]
    return min(s[0] for s in spans), max(s[1] for s in spans)


def spelled_out(blocks: list[store.Block], aliases: dict[str, str]) -> list[store.Block]:
    return [b._replace(line=tags.canonical(b.line, aliases)) for b in blocks]


def render_range(
    window: days.Window,
    blocks: list[store.Block],
    now: datetime,
    starts: timedelta,
    aliases: dict[str, str] | None = None,
) -> str:
    if not blocks:
        return f"{range_heading(window, blocks, now, starts)}\n\nNothing logged."
    blocks = spelled_out(blocks, aliases or {})
    found = groups(blocks, now)
    glyphs = {g.name: g.glyph for g in found}
    per_day = [(d, inside(blocks, d, now)) for d in window.days() if d.since <= now]
    span = common_span(per_day, now)
    lines = [day_line(d, mine, glyphs, now, span) for d, mine in per_day]
    scale_line = " " * 8 + scale(window, [], now, span)
    gap = sum((untracked(mine, now) for _, mine in per_day), timedelta())
    parts = [
        range_heading(window, blocks, now, starts),
        "```\n" + "\n".join([scale_line, *lines]) + "\n```",
        f"```\n{totals(found, blocks, now, gap)}\n```",
        *tag_part(blocks, now),
    ]
    return "\n\n".join(parts)


def shown(
    db, word: str, now: datetime, starts: timedelta, aliases: dict[str, str] | None = None
) -> tuple[days.Window, str] | None:
    window = days.asked(word, now, starts)
    if window is None:
        return None
    blocks = store.blocks_within(db, window.since, window.until, now)
    draw = render_range if window.length > 1 else render
    return window, draw(window, blocks, now, starts, aliases)
