"""Alfred rows."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from typing import TypedDict

from hoard.alfred import matches

from tally import commands, days, gaps, journal, remind, store, timewords
from tally.durations import hm
from tally.scope import Scope

EVERYTHING = Scope()

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
    autocomplete: str


NO_MODS: dict[str, Mod] = {
    mod: {"valid": False, "subtitle": ""} for mod in ("shift", "alt", "cmd", "ctrl")
}


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


def gap_mod(db: sqlite3.Connection, now: datetime, claim: gaps.Claim | None = None) -> Mod:
    last = store.last_before(db, now)
    if last is None or not last.stop:
        return {"valid": False, "subtitle": "⇧↩ nothing to fill: a task is running"}
    since = claim.gap.start if claim else last.at
    return {
        "subtitle": f"⇧↩ since {since:%H:%M} (fills {hm(now - since)})",
        "variables": start_variables(since),
    }


def stop_mod(db: sqlite3.Connection, now: datetime) -> Mod:
    active = store.running(db, now)
    if active is None:
        return {"valid": False, "subtitle": "⌥↩ nothing to stop"}
    return stop_mod_for(active, now)


def task_mods(
    db: sqlite3.Connection, now: datetime, fill: bool = True, claim: gaps.Claim | None = None
) -> dict[str, Mod]:
    shift = gap_mod(db, now, claim) if fill else NO_MODS["shift"]
    return {**NO_MODS, "shift": shift, "alt": stop_mod(db, now)}


def edit_mod(target: str, subtitle: str) -> Mod:
    return {"arg": "", "subtitle": subtitle, "variables": {"action": "edit", "target": target}}


def edit_mods(target: str, what: str) -> dict[str, Mod]:
    """⌃↩ edits; ⌘↩ opens the same list with delete typed in, so one more ↩ removes it."""
    removal: Mod = {
        "arg": "delete",
        "subtitle": "⌘↩ delete it: shows what goes, ↩ there removes it, t undo brings it back",
        "variables": {"action": "edit", "target": target},
    }
    return {"ctrl": edit_mod(target, f"⌃↩ {what}, its time stays"), "cmd": removal}


def task_edit_mods(line: str) -> dict[str, Mod]:
    return edit_mods(f"task:{line}", "rename or retag this task")


def resume_row(
    task: store.Task,
    day: Day,
    db: sqlite3.Connection,
    now: datetime,
    claim: gaps.Claim | None = None,
) -> Row:
    return {
        "title": f"Resume {task.line}",
        "subtitle": task_subtitle(task, day, db, now),
        "arg": task.line,
        "variables": start_variables(None),
        "text": {"copy": task.line, "largetype": task.line},
        "mods": {**task_mods(db, now, claim=claim), **task_edit_mods(task.line)},
    }


def effect(at: datetime, db: sqlite3.Connection, now: datetime) -> str:
    active = store.running(db, now)
    if active is None or at >= active.start:
        ended = f" · ends {active.line} at {at:%H:%M}" if active else ""
        return f"from {at:%H:%M}{ended}"
    before = store.last_before(db, at)
    cut = f" · cuts {before.line} at {at:%H:%M}" if before and not before.stop else ""
    return f"{at:%H:%M}–{active.start:%H:%M}, before {active.line} (which keeps running){cut}"


def start_row(
    typed: timewords.Typed,
    known: str | None,
    db: sqlite3.Connection,
    now: datetime,
    claim: gaps.Claim | None = None,
) -> Row:
    line = known or typed.line
    verb = "Resume" if known else "Start"
    subtitle = effect(typed.at, db, now) if typed.at else "↩ from now"
    mods = task_mods(db, now, fill=typed.at is None, claim=claim)
    if known:
        mods = {**mods, **task_edit_mods(known)}
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
        "mods": {**NO_MODS, **task_edit_mods(active.line)},
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


def scoped_total(blocks: list[store.Block], now: datetime, scope: Scope) -> str:
    under = [b for b in blocks if scope.holds(b.line)]
    return f" · {scope.label} {hm(sum((b.length(now) for b in under), timedelta()))}"


def view_row(
    shown: days.Window,
    db: sqlite3.Connection,
    now: datetime,
    starts: timedelta,
    word: str,
    scope: Scope = EVERYTHING,
) -> Row:
    name = days.label(shown, now, starts)
    blocks = store.blocks_within(db, shown.since, shown.until, now)
    logged = sum((b.length(now) for b in blocks), timedelta())
    what = "day" if shown.length == 1 else name.split()[-1]
    part = scoped_total(blocks, now, scope) if scope.tag else ""
    mods = NO_MODS
    if shown.length == 1:
        target = f"day:{shown.day.isoformat()}"
        mods = {**NO_MODS, **edit_mods(target, "tag every block of the day")}
    return {
        "title": name.capitalize(),
        "subtitle": f"{hm(logged)} logged{part} · ↩ shows the {what}",
        "arg": word,
        "variables": {"action": "view"},
        "mods": mods,
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


def nudge_row(on: bool, described: str) -> Row:
    return {
        "title": "Turn nudges off" if on else "Turn nudges on",
        "subtitle": f"now on: {described}" if on else f"{described}, set in the workflow settings",
        "arg": "",
        "variables": {"action": "nudges"},
        "mods": NO_MODS,
    }


def block_row(block: store.Block, now: datetime) -> Row:
    end = f"{block.end:%H:%M}" if block.end else "now"
    return {
        "title": f"{when(block.start, now)}–{end} · {hm(block.length(now))}",
        "subtitle": f"{block.line} · ↩ this block only: retime, tag, rename or delete",
        "arg": "",
        "variables": {"action": "edit", "target": f"block:{block.id}"},
        "mods": NO_MODS,
    }


def undo_row(db: sqlite3.Connection) -> Row:
    batch = journal.last(db)
    if batch is None:
        return {
            "title": "Nothing to undo",
            "subtitle": "edits made with ⌃↩ can be undone",
            "valid": False,
        }
    return {
        "title": f"Undo: {batch.said}",
        "subtitle": f"made {batch.at:%H:%M} {batch.at:%a %-d %b}",
        "arg": "",
        "variables": {"action": "undo"},
        "mods": NO_MODS,
    }


def reminder_row(
    text: str, chosen: remind.Wanted, now: datetime, replacing: remind.Reminder | None = None
) -> Row:
    if chosen.problem or chosen.at is None:
        return {"title": chosen.problem, "subtitle": "", "valid": False, "mods": NO_MODS}
    verb = "Replace with" if replacing else "Remind"
    first = "" if not chosen.rule.repeats else f"first {remind.spoken(chosen.at, now)}, "
    ending = f" · until {remind.spoken(chosen.until, now)}" if chosen.until else ""
    instead = f" · instead of {replacing.text}" if replacing else ""
    return {
        "title": f"{verb} {remind.timing(chosen, now)}: {chosen.text}",
        "subtitle": f"{first}{remind.until(chosen.at, now)}{ending}{instead}"
        " · in big letters then · ↩ sets it",
        "arg": text,
        "variables": {"action": "remember"},
        "mods": NO_MODS,
    }


def reminder_mods(chosen: remind.Reminder) -> dict[str, Mod]:
    one = "skip the next one, keep the rest" if chosen.rule.repeats else "cancel it"
    return {
        **NO_MODS,
        "alt": {"arg": str(chosen.id), "subtitle": f"⌥↩ {one}", "variables": {"action": "forget"}},
        "shift": {
            "arg": str(chosen.id),
            "subtitle": f"⇧↩ stop every reminder of “{chosen.text}”",
            "variables": {"action": "forget-all"},
        },
        "ctrl": {
            "arg": chosen.typed or chosen.text,
            "subtitle": "⌃↩ edit: what you typed, back in the list",
            "variables": {"action": "retype", "replace": str(chosen.id)},
        },
    }


def pending_row(chosen: remind.Reminder, now: datetime) -> Row:
    parts = [remind.until(chosen.at, now)]
    if chosen.rule.repeats:
        parts.insert(0, f"next {remind.spoken(chosen.at, now)}")
    if chosen.skip:
        parts.append("skipping that one")
    if chosen.until:
        parts.append(f"until {remind.spoken(chosen.until, now)}")
    return {
        "title": f"⏰ {remind.timing(chosen, now)} {chosen.text}",
        "subtitle": " · ".join([*parts, "↩ shows it now"]),
        "arg": chosen.text,
        "variables": {"action": "preview"},
        "mods": reminder_mods(chosen),
    }


REMINDERS = "reminders"


def asks_for_reminders(words: list[str]) -> bool:
    first = words[0]
    wanted = first[1:].lower()
    return (
        first.startswith("@") and len(wanted) >= commands.MIN_TYPED and REMINDERS.startswith(wanted)
    )


def reminder_rows(words: list[str], db: sqlite3.Connection, now: datetime) -> list[Row]:
    wanted = " ".join(words)
    found = [r for r in remind.pending(db) if matches(wanted, r.text)]
    if not found:
        return [
            {
                "title": "No reminders",
                "subtitle": "t +15m …, t 21:00 …, t daily 9:00 …, t every 45m …",
                "valid": False,
                "mods": NO_MODS,
            }
        ]
    return [pending_row(r, now) for r in found]


def at_words_rows(db: sqlite3.Connection, now: datetime, starts: timedelta) -> list[Row]:
    viewed = [
        view_row(days.asked(word, now, starts), db, now, starts, word)  # type: ignore[arg-type]
        for word in ("@today", "@yesterday", "@week", "@lastweek", "@month", "@lastmonth")
    ]
    count = len(remind.pending(db))
    listing: Row = {
        "title": "Reminders",
        "subtitle": f"{count} pending · ⇥ lists them",
        "valid": False,
        "autocomplete": "@reminders ",
        "mods": NO_MODS,
    }
    return [*viewed, listing]


def recent(db: sqlite3.Connection, now: datetime, scope: Scope = EVERYTHING) -> list[store.Task]:
    active = store.running(db, now)
    found = store.tasks(db, now - timedelta(days=RECENT_DAYS), now)
    others = [
        t
        for t in found
        if scope.holds(t.line) and not (active and store.same_task(t.line, active.line))
    ]
    return others[:RECENT_LIMIT]


def unclaimed_row(claim: gaps.Claim) -> Row:
    gap = claim.gap
    return {
        "title": f"Unclaimed {hm(gap.length)} since {gap.start:%H:%M}",
        "subtitle": "type what you are doing: it can start now, or since then",
        "valid": False,
        "mods": NO_MODS,
    }


def since_row(line: str, at: datetime, why: str, now: datetime, known: bool) -> Row:
    verb = "Resume" if known else "Start"
    return {
        "title": f"{verb} {line} since {at:%H:%M}",
        "subtitle": f"{why} · {hm(now - at)} · ↩ claims it, it keeps running",
        "arg": line,
        "variables": start_variables(at),
        "text": {"copy": line, "largetype": line},
        "mods": NO_MODS,
    }


def claim_rows(line: str, known: bool, claim: gaps.Claim, now: datetime) -> list[Row]:
    """The two starts back in time the first task after a gap may really have had."""
    woke = claim.woke()
    found = [since_row(line, woke, "display on", now, known)] if woke else []
    return [*found, since_row(line, claim.gap.start, "whole gap", now, known)]


def split_row(text: str, claim: gaps.Claim | None, scope: Scope) -> Row:
    parts = [p._replace(line=scope.apply(p.line)) for p in gaps.split(text) or []]
    if claim is None:
        return {
            "title": "A split claims unclaimed time; nothing is unclaimed now",
            "subtitle": "stop the running task first, or edit with ⌃↩",
            "valid": False,
            "mods": NO_MODS,
        }
    filled = gaps.fill(parts, claim.gap)
    if filled.problem:
        return {"title": filled.problem, "subtitle": "", "valid": False, "mods": NO_MODS}
    ends = [*(at for at, _ in filled.starts[1:]), None]
    said = ", ".join(
        f"{line} {at:%H:%M}–{end:%H:%M}" if end else f"{line} from {at:%H:%M}"
        for (at, line), end in zip(filled.starts, ends)
    )
    lengths = ", ".join(
        f"{p.line} {int(p.length.total_seconds() // 60)}" if p.length else p.line for p in parts
    )
    return {
        "title": f"Claim since {claim.gap.start:%H:%M}: {said}",
        "subtitle": f"{hm(claim.gap.length)} · ↩ fills the gap, the last part keeps running",
        "arg": lengths,
        "variables": {"action": "claim"},
        "mods": NO_MODS,
    }


def bare_rows(
    db: sqlite3.Connection,
    now: datetime,
    starts: timedelta,
    scope: Scope = EVERYTHING,
    claim: gaps.Claim | None = None,
) -> list[Row]:
    day = Day(db, now, starts)
    shown = [unclaimed_row(claim)] if claim and claim.worth_asking else []
    shown += [resume_row(task, day, db, now, claim) for task in recent(db, now, scope)]
    active = store.running(db, now)
    if active:
        shown.append(stop_row(active, now))
    shown += [pending_row(r, now) for r in remind.pending(db) if remind.soon(r, now)]
    return [*shown, view_row(day.window, db, now, starts, "@today", scope)]


def known_spelling(found: list[store.Task], line: str, scope: Scope) -> str | None:
    return next((task.line for task in found if scope.same(task.line, line)), None)


def running_row(active: store.Block, now: datetime) -> Row:
    """The task that runs, found by typing: ↩ leaves it running instead of restarting it."""
    return {
        "title": f"{active.line} is running",
        "subtitle": f"{hm(active.length(now))} since {active.start:%H:%M} · ↩ keeps it running",
        "arg": active.line,
        "variables": {"action": "keep"},
        "text": {"copy": active.line, "largetype": active.line},
        "mods": {**NO_MODS, "alt": stop_mod_for(active, now), **task_edit_mods(active.line)},
    }


def stop_mod_for(active: store.Block, now: datetime) -> Mod:
    return {
        "arg": "",
        "subtitle": f"⌥↩ stop {active.line} · {hm(active.length(now))}",
        "variables": {"action": "stop"},
    }


def is_running(line: str, active: store.Block | None, scope: Scope) -> bool:
    return active is not None and scope.same(line, active.line)


def typed_rows(
    text: str,
    db: sqlite3.Connection,
    now: datetime,
    starts: timedelta,
    scope: Scope = EVERYTHING,
    claim: gaps.Claim | None = None,
) -> list[Row]:
    if gaps.split(text):
        return [split_row(text, claim, scope)]
    typed = timewords.parse(text, now)
    if typed.problem:
        return [invalid_row(typed)]
    typed = typed._replace(line=scope.apply(typed.line))
    day = Day(db, now, starts)
    found = store.tasks(db, datetime.min, now)
    active = store.running(db, now)
    known = known_spelling(found, typed.line, scope)
    if typed.at is None and active and is_running(typed.line, active, scope):
        top = running_row(active, now)
    else:
        top = start_row(typed, known, db, now, claim)
    asking = claim if claim and claim.worth_asking and typed.at is None and not active else None
    backdated = claim_rows(known or typed.line, bool(known), asking, now) if asking else []
    wanted = timewords.parse(text, now).line
    similar = [
        running_row(active, now)
        if active and is_running(task.line, active, scope)
        else resume_row(task, day, db, now, claim)
        for task in found
        if scope.holds(task.line)
        and matches(wanted, task.line)
        and not scope.same(task.line, typed.line)
    ]
    return [top, *backdated, *similar]


def command_row(
    command: commands.Command,
    db: sqlite3.Connection,
    now: datetime,
    starts: timedelta,
    plugin: Callable[[], Path | None],
    nudges: Callable[[], tuple[bool, str]],
) -> Row:
    if command.kind == "nudge":
        return nudge_row(*nudges())
    if command.kind == "undo":
        return undo_row(db)
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
    nudges: Callable[[], tuple[bool, str]] = lambda: (False, ""),
    scope: Scope = EVERYTHING,
    replacing: remind.Reminder | None = None,
    claim: gaps.Claim | None = None,
) -> list[Row]:
    words = text.split()
    if not words:
        return bare_rows(db, now, starts, scope, claim)
    if words == ["@"]:
        return at_words_rows(db, now, starts)
    if asks_for_reminders(words):
        return reminder_rows(words[1:], db, now)
    if len(words) == 1 and days.DATE.match(words[0]):
        return date_rows(words[0], db, now, starts)
    later = remind.wanted(text, now)
    if later:
        return [reminder_row(text, later, now, replacing)]
    found = [command_row(c, db, now, starts, plugin, nudges) for c in commands.named(text)]
    if text.lstrip().startswith("@"):
        return found or [unknown_day_row(words[0])]
    return [*found, *typed_rows(text, db, now, starts, scope, claim)]
