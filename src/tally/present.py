"""Alfred rows."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import TypedDict

from hoard.alfred import matches

from tally import commands, days, store, timewords

RECENT_DAYS = 7
RECENT_LIMIT = 7


class Mod(TypedDict, total=False):
    arg: str
    subtitle: str
    valid: bool
    variables: dict[str, str]


class Row(TypedDict, total=False):
    title: str
    subtitle: str
    arg: str
    valid: bool
    variables: dict[str, str]
    mods: dict[str, Mod]
    text: dict[str, str]


NO_MODS: dict[str, Mod] = {mod: {"valid": False, "subtitle": ""} for mod in ("shift", "alt", "cmd")}


def hm(span: timedelta) -> str:
    minutes = int(span.total_seconds() // 60)
    return f"{minutes // 60}:{minutes % 60:02d}"


def when(moment: datetime, now: datetime) -> str:
    distance = (now.date() - moment.date()).days
    if distance == 0:
        return f"{moment:%H:%M}"
    if distance == 1:
        return f"yesterday {moment:%H:%M}"
    if moment.year == now.year:
        return f"{moment:%a %-d %b %H:%M}"
    return f"{moment:%-d %b %Y %H:%M}"


def span(block: store.Block, now: datetime) -> str:
    end = f"{block.end:%H:%M}" if block.end else "now"
    return f"{block.start:%H:%M}–{end}"


class Day:
    def __init__(self, db: sqlite3.Connection, now: datetime, starts: timedelta):
        self.now = now
        self.window = days.today(now, starts)
        self.blocks = store.blocks_within(db, self.window.since, self.window.until, now)

    def total(self, line: str | None = None) -> timedelta:
        chosen = [b for b in self.blocks if line is None or store.same_task(b.line, line)]
        return sum((b.length(self.now) for b in chosen), timedelta())

    def last(self, line: str) -> store.Block | None:
        mine = [b for b in self.blocks if store.same_task(b.line, line)]
        return mine[-1] if mine else None


def task_subtitle(task: store.Task, day: Day, db: sqlite3.Connection, now: datetime) -> str:
    today = day.total(task.line)
    last = day.last(task.line)
    if last and today:
        return f"today {hm(today)} · last {span(last, now)}"
    return f"last {when(task.last_start, now)}"


def start_variables(at: datetime | None) -> dict[str, str]:
    variables = {"action": "start"}
    if at:
        variables["at"] = store.stamp(at)
    return variables


def gap_mod(db: sqlite3.Connection, now: datetime) -> Mod:
    last = store.last_before(db, now)
    if last is None or not last.stop:
        return {"valid": False, "subtitle": "⇧↩ nothing to fill: a task is running"}
    return {
        "subtitle": f"⇧↩ since {last.at:%H:%M} (fills {hm(now - last.at)})",
        "variables": start_variables(last.at),
    }


def stop_mod(db: sqlite3.Connection, now: datetime) -> Mod:
    active = store.running(db, now)
    if active is None:
        return {"valid": False, "subtitle": "⌥↩ nothing to stop"}
    return {
        "arg": "",
        "subtitle": f"⌥↩ stop {active.line} · {hm(active.length(now))}",
        "variables": {"action": "stop"},
    }


def task_mods(db: sqlite3.Connection, now: datetime, fill: bool = True) -> dict[str, Mod]:
    shift = gap_mod(db, now) if fill else NO_MODS["shift"]
    return {**NO_MODS, "shift": shift, "alt": stop_mod(db, now)}


def resume_row(task: store.Task, day: Day, db: sqlite3.Connection, now: datetime) -> Row:
    return {
        "title": f"Resume {task.line}",
        "subtitle": task_subtitle(task, day, db, now),
        "arg": task.line,
        "variables": start_variables(None),
        "text": {"copy": task.line, "largetype": task.line},
        "mods": task_mods(db, now),
    }


def effect(at: datetime, db: sqlite3.Connection, now: datetime) -> str:
    active = store.running(db, now)
    if active is None or at >= active.start:
        ended = f" · ends {active.line} at {at:%H:%M}" if active else ""
        return f"from {at:%H:%M}{ended}"
    before = store.last_before(db, at)
    cut = f" · cuts {before.line} at {at:%H:%M}" if before and not before.stop else ""
    return f"{at:%H:%M}–{active.start:%H:%M}, before {active.line} (which keeps running){cut}"


def start_row(typed: timewords.Typed, db: sqlite3.Connection, now: datetime) -> Row:
    known = store.spelled(db, typed.line)
    line = known or typed.line
    verb = "Resume" if known else "Start"
    subtitle = effect(typed.at, db, now) if typed.at else "↩ from now"
    mods = task_mods(db, now, fill=typed.at is None)
    return {
        "title": f"{verb} {line}",
        "subtitle": subtitle,
        "arg": line,
        "variables": start_variables(typed.at),
        "text": {"copy": line, "largetype": line},
        "mods": mods,
    }


def invalid_row(typed: timewords.Typed) -> Row:
    return {"title": typed.problem, "subtitle": "", "valid": False, "mods": NO_MODS}


def stop_row(active: store.Block, now: datetime) -> Row:
    return {
        "title": "Stop",
        "subtitle": f"{active.line} · {hm(active.length(now))} since {active.start:%H:%M}",
        "arg": "",
        "variables": {"action": "stop"},
        "mods": NO_MODS,
    }


def idle_row() -> Row:
    return {"title": "Nothing to stop", "subtitle": "no task is running", "valid": False}


def unknown_day_row(word: str) -> Row:
    return {
        "title": f"{word} is not a day",
        "subtitle": "@today, @yesterday, @week, @lastweek, @month, @lastmonth or 2026-10-19",
        "valid": False,
        "mods": NO_MODS,
    }


def view_row(
    shown: days.Window, db: sqlite3.Connection, now: datetime, starts: timedelta, word: str
) -> Row:
    name = days.label(shown, now, starts)
    blocks = store.blocks_within(db, shown.since, shown.until, now)
    logged = sum((b.length(now) for b in blocks), timedelta())
    what = "day" if shown.length == 1 else name.split()[-1]
    return {
        "title": name.capitalize(),
        "subtitle": f"{hm(logged)} logged · ↩ shows the {what}",
        "arg": word,
        "variables": {"action": "view"},
        "mods": NO_MODS,
    }


def bar_row(installed: Path | None) -> Row:
    if installed is None:
        return {
            "title": "SwiftBar not found",
            "subtitle": "brew install swiftbar, or set its plugin folder in the workflow settings",
            "valid": False,
            "mods": NO_MODS,
        }
    verb = "Reinstall" if installed.exists() else "Install"
    return {
        "title": f"{verb} the SwiftBar plugin",
        "subtitle": f"{installed} · the running task in the menu bar, recent ones in its menu",
        "arg": "",
        "variables": {"action": "bar"},
        "mods": NO_MODS,
    }


def recent(db: sqlite3.Connection, now: datetime) -> list[store.Task]:
    active = store.running(db, now)
    found = store.tasks(db, now - timedelta(days=RECENT_DAYS), now)
    others = [t for t in found if not (active and store.same_task(t.line, active.line))]
    return others[:RECENT_LIMIT]


def bare_rows(db: sqlite3.Connection, now: datetime, starts: timedelta) -> list[Row]:
    day = Day(db, now, starts)
    shown = [resume_row(task, day, db, now) for task in recent(db, now)]
    active = store.running(db, now)
    if active:
        shown.append(stop_row(active, now))
    return [*shown, view_row(day.window, db, now, starts, "@today")]


def typed_rows(text: str, db: sqlite3.Connection, now: datetime, starts: timedelta) -> list[Row]:
    typed = timewords.parse(text, now)
    if typed.problem:
        return [invalid_row(typed)]
    day = Day(db, now, starts)
    top = start_row(typed, db, now)
    found = store.tasks(db, datetime.min, now)
    similar = [
        resume_row(task, day, db, now)
        for task in found
        if matches(typed.line, task.line) and not store.same_task(task.line, typed.line)
    ]
    return [top, *similar]


def command_row(
    command: commands.Command,
    db: sqlite3.Connection,
    now: datetime,
    starts: timedelta,
    plugin: Callable[[], Path | None],
) -> Row:
    if command.kind == "stop":
        active = store.running(db, now)
        return stop_row(active, now) if active else idle_row()
    if command.kind == "bar":
        return bar_row(plugin())
    shown = days.asked(command.word, now, starts)
    assert shown is not None
    return view_row(shown, db, now, starts, command.word)


def date_rows(word: str, db: sqlite3.Connection, now: datetime, starts: timedelta) -> list[Row]:
    shown = days.asked(word, now, starts)
    return [view_row(shown, db, now, starts, word)] if shown else [unknown_day_row(word)]


def rows(
    text: str,
    db: sqlite3.Connection,
    now: datetime,
    starts: timedelta,
    plugin: Callable[[], Path | None] = lambda: None,
) -> list[Row]:
    words = text.split()
    if not words:
        return bare_rows(db, now, starts)
    if len(words) == 1 and days.DATE.match(words[0]):
        return date_rows(words[0], db, now, starts)
    found = [command_row(c, db, now, starts, plugin) for c in commands.named(text)]
    if text.lstrip().startswith("@"):
        return found or [unknown_day_row(words[0])]
    return [*found, *typed_rows(text, db, now, starts)]
