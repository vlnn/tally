"""What typing in the edit list means for a block, a task or a day, before ↩ does it.

The same text is planned twice: once to show the row, once by `act apply` to carry it out,
so what the row says is what happens.
"""

from __future__ import annotations

import sqlite3
from datetime import date, datetime, timedelta
from typing import NamedTuple

from tally import days, store, tags, timewords
from tally.journal import delete, insert, update
from tally.present import hm
from tally.scope import Scope

BLOCK, TASK, DAY = "block", "task", "day"


class Target(NamedTuple):
    kind: str
    value: str

    def encode(self) -> str:
        return f"{self.kind}:{self.value}"


def target(encoded: str) -> Target | None:
    kind, _, value = encoded.partition(":")
    return Target(kind, value) if kind in (BLOCK, TASK, DAY) and value else None


class Plan(NamedTuple):
    title: str
    subtitle: str = ""
    ops: tuple = ()
    complete: str = ""

    @property
    def valid(self) -> bool:
        return bool(self.ops)


def refused(title: str, subtitle: str = "") -> Plan:
    return Plan(title, subtitle)


class Tagging(NamedTuple):
    add: tuple[str, ...]
    remove: tuple[str, ...]


def tagging(text: str) -> Tagging | None:
    """`#w -#lexer` means add #w, remove #lexer; anything else is not a tagging."""
    words = text.split()
    if not words or not all(w.startswith(("#", "-#")) and len(w.lstrip("-#")) for w in words):
        return None
    add = tuple(tags.key(w) for w in words if w.startswith("#"))
    remove = tuple(tags.key(w[1:]) for w in words if w.startswith("-#"))
    return Tagging(add, remove)


def retagged(line: str, change: Tagging, scope: Scope) -> str:
    def spelled(tag: str) -> str:
        return f"#{scope.aliases.get(tag, tag)}"

    gone = {spelled(tag) for tag in change.remove}
    kept = [
        word
        for word in line.split()
        if not (tags.TAG.fullmatch(word) and spelled(tags.key(word)) in gone)
    ]
    have = set(tags.of(tags.canonical(" ".join(kept), scope.aliases)))
    added = [f"#{tag}" for tag in change.add if spelled(tag) not in have]
    return " ".join(kept + added)


def described(change: Tagging) -> str:
    parts = [f"add {' '.join('#' + t for t in change.add)}"] if change.add else []
    parts += [f"remove {' '.join('#' + t for t in change.remove)}"] if change.remove else []
    return ", ".join(parts).capitalize()


def counted(n: int) -> str:
    return "1 block" if n == 1 else f"{n} blocks"


def tag_plan(chosen: list[store.Block], change: Tagging, where: str, scope: Scope) -> Plan:
    ops = [
        update(b.id, line=retagged(b.line, change, scope))
        for b in chosen
        if retagged(b.line, change, scope) != b.line
    ]
    if not ops:
        return refused("Nothing to change", f"{where}: already as asked")
    return Plan(f"{described(change)} · {counted(len(ops))}", where, tuple(ops))


def rename_plan(chosen: list[store.Block], text: str, where: str) -> Plan:
    line = store.tidy(text)
    ops = [update(b.id, line=line) for b in chosen if b.line != line]
    if not ops:
        return refused("Nothing to change", f"{where}: already {line}")
    return Plan(f"Rename {counted(len(ops))} to {line}", where, tuple(ops))


class Around(NamedTuple):
    before: store.Transition | None
    this: store.Transition
    after: store.Transition | None
    later: store.Transition | None


def around(db: sqlite3.Connection, identity: int) -> Around | None:
    changes = store.transitions(db)
    found = [n for n, change in enumerate(changes) if change.id == identity]
    if not found:
        return None
    n = found[0]

    def at(k: int) -> store.Transition | None:
        return changes[k] if 0 <= k < len(changes) else None

    return Around(at(n - 1), changes[n], at(n + 1), at(n + 2))


def when(word: str, now: datetime, day: date) -> datetime | None:
    found = timewords.moment(word, now)
    if found is None or not timewords.CLOCK.match(word):
        return found
    return datetime.combine(day, found.time())


def start_plan(spot: Around, moment: datetime, now: datetime) -> Plan:
    this = spot.this
    lower = spot.before.at if spot.before else datetime.min
    upper = spot.after.at if spot.after else now
    if not lower < moment < upper:
        limit = f"{lower:%H:%M}" if spot.before else "the start"
        return refused(f"{moment:%H:%M} is outside {limit}–{upper:%H:%M}", this.line)
    if moment == this.at:
        return refused(f"Already starts at {moment:%H:%M}", this.line)
    neighbour = spot.before
    if neighbour is None or neighbour.stop:
        effect = "untracked before it" if moment > this.at else "takes from untracked time"
    elif moment < this.at:
        effect = f"{neighbour.line} now ends at {moment:%H:%M}"
    else:
        effect = f"{neighbour.line} runs on until {moment:%H:%M}"
    return Plan(
        f"Start {this.line} at {moment:%H:%M} instead of {this.at:%H:%M}",
        effect,
        (update(this.id, at=moment),),
    )


def end_plan(spot: Around, moment: datetime, now: datetime) -> Plan:
    this, after = spot.this, spot.after
    if moment <= this.at:
        return refused(f"{moment:%H:%M} is before it starts at {this.at:%H:%M}", this.line)
    if after is None:
        if moment > now:
            return refused(f"{moment:%H:%M} has not happened yet", this.line)
        return Plan(f"End {this.line} at {moment:%H:%M}", "it stops then", (insert(moment, ""),))
    if moment == after.at:
        return refused(f"Already ends at {moment:%H:%M}", this.line)
    title = f"End {this.line} at {moment:%H:%M} instead of {after.at:%H:%M}"
    if moment < after.at:
        if after.stop:
            return Plan(title, "untracked after it", (update(after.id, at=moment),))
        return Plan(
            title,
            f"untracked {moment:%H:%M}–{after.at:%H:%M}, then {after.line}",
            (insert(moment, ""),),
        )
    upper = spot.later.at if spot.later else now
    if moment >= upper:
        return refused(
            f"{moment:%H:%M} is past the next block, which ends {upper:%H:%M}", this.line
        )
    effect = (
        "takes from untracked time" if after.stop else f"{after.line} now starts at {moment:%H:%M}"
    )
    return Plan(title, effect, (update(after.id, at=moment),))


def delete_plan(spot: Around, now: datetime) -> Plan:
    this = spot.this
    end = f"{spot.after.at:%H:%M}" if spot.after else "now"
    op = delete(this.id) if spot.before is None or spot.before.stop else update(this.id, line="")
    return Plan(f"Delete {this.line}", f"{this.at:%H:%M}–{end} becomes untracked", (op,))


HINTS = (
    ("#tag", "#", "add a tag; -#tag removes one, both may be typed together"),
    ("start 14:05", "start ", "move the start (a time or -10m)"),
    ("end 14:40", "end ", "move the end"),
    ("delete", "delete", "the block's time becomes untracked"),
    ("anything else", "", "renames"),
)


def hints(kind: str) -> list[Plan]:
    usable = HINTS if kind == BLOCK else (HINTS[0], HINTS[-1])
    return [Plan(title, subtitle, complete=complete) for title, complete, subtitle in usable]


def block_plan(
    db: sqlite3.Connection, identity: int, text: str, now: datetime, scope: Scope
) -> Plan:
    spot = around(db, identity)
    if spot is None or spot.this.stop:
        return refused("That block is gone", "it was deleted or edited away")
    this = spot.this
    words = text.split()
    where = f"{this.line} · {this.at:%H:%M}"
    change = tagging(text)
    if change:
        block = store.Block(this.at, None, this.line, this.logged_at, this.id)
        return tag_plan([block], change, where, scope)
    if words[0] in ("start", "end") and len(words) == 2:
        moment = when(words[1], now, this.at.date())
        if moment is None:
            return refused(f"{words[1]} is not a time", "14:05, 9:30, -10m, -1h20m")
        return (start_plan if words[0] == "start" else end_plan)(spot, moment, now)
    if words == ["delete"]:
        return delete_plan(spot, now)
    block = store.Block(this.at, None, this.line, this.logged_at, this.id)
    return rename_plan([block], text, where)


def task_blocks(db: sqlite3.Connection, line: str, scope: Scope) -> list[store.Block]:
    return [b for b in store.blocks(store.transitions(db)) if scope.same(b.line, line)]


def task_plan(db: sqlite3.Connection, line: str, text: str, now: datetime, scope: Scope) -> Plan:
    chosen = task_blocks(db, line, scope)
    if not chosen:
        return refused("That task has no blocks left", line)
    total = sum((b.length(now) for b in chosen), timedelta())
    where = f"every block of {line} · {counted(len(chosen))}, {hm(total)}"
    change = tagging(text)
    if change:
        return tag_plan(chosen, change, where, scope)
    if text.split()[0] in ("start", "end", "delete"):
        return refused(f"{text.split()[0]} is for one block", "t edit lists them")
    return rename_plan(chosen, text, where)


def day_plan(
    db: sqlite3.Connection, day: str, text: str, now: datetime, starts: timedelta, scope: Scope
) -> Plan:
    shown = days.asked(day, now, starts)
    if shown is None:
        return refused(f"{day} is not a day")
    chosen = [
        b
        for b in store.blocks(store.transitions(db, shown.since, shown.until))
        if shown.since <= b.start < shown.until
    ]
    change = tagging(text)
    if not change:
        return refused("A day takes tags only", "#tag adds to every block that day, -#tag removes")
    return tag_plan(chosen, change, f"every block on {shown.day:%a %-d %b}", scope)


def plan(
    db: sqlite3.Connection,
    chosen: Target,
    text: str,
    now: datetime,
    starts: timedelta,
    scope: Scope,
) -> Plan:
    if chosen.kind == BLOCK:
        return block_plan(db, int(chosen.value), text, now, scope)
    if chosen.kind == TASK:
        return task_plan(db, chosen.value, text, now, scope)
    return day_plan(db, chosen.value, text, now, starts, scope)
