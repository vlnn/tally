from __future__ import annotations

import json
import os
import sqlite3
import sys
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path
from typing import Callable

from hoard.alfred import data_folder

from tally import bar, days, editrows, edits, journal, nudge, present, scope, store, tags, view

NAME = "tally"
DB_NAME = "tally.db"


class Usage(Exception):
    pass


class Context:
    def __init__(self, env: Mapping[str, str], now: datetime, db: sqlite3.Connection | None):
        self.env = env
        self.now = now
        self.starts = days.offset(env.get("day_starts", ""))
        self.aliases = tags.aliases(env.get("tag_aliases", tags.DEFAULT_ALIASES))
        self._db = db

    @property
    def db(self) -> sqlite3.Connection:
        if self._db is None:
            self._db = store.connect(str(db_path(self.env)))
        return self._db

    def at(self) -> datetime:
        typed = self.env.get("at", "").strip()
        return datetime.fromisoformat(typed) if typed else self.now


def db_path(env: Mapping[str, str]) -> Path:
    chosen = env.get("db_path", "").strip()
    folder = Path(os.path.expanduser(chosen)) if chosen else Path(data_folder(env, NAME))
    folder.mkdir(parents=True, exist_ok=True)
    return folder / DB_NAME


def emit(items: list[present.Row]) -> int:
    print(json.dumps({"items": items}, ensure_ascii=False))
    return 0


def say(text: str) -> int:
    print(text)
    return 0


def listed(text: str, ctx: Context, chosen: scope.Scope) -> int:
    plugin = lambda: bar.plugin_path(ctx.env)  # noqa: E731
    nudges = lambda: (nudge.installed(), nudge.describe(nudge.settings(ctx.env)))  # noqa: E731
    return emit(present.rows(text, ctx.db, ctx.now, ctx.starts, plugin, nudges, chosen))


def filter_command(args: list[str], ctx: Context) -> int:
    return listed(args[0] if args else "", ctx, everything(ctx))


def filter_work_command(args: list[str], ctx: Context) -> int:
    work = scope.work(ctx.env.get("work_tag", ""), ctx.aliases)
    return listed(args[0] if args else "", ctx, work)


def start_command(args: list[str], ctx: Context) -> int:
    line = " ".join(args).strip()
    if not line:
        raise Usage("start needs a line")
    at = ctx.at()
    active = store.running(ctx.db, ctx.now)
    if at == ctx.now and active and everything(ctx).same(line, active.line):
        return keep_command([line], ctx)
    store.record(ctx.db, at, line, ctx.now)
    bar.poke(ctx.env)
    return say(f"{line} from {at:%H:%M}")


def keep_command(args: list[str], ctx: Context) -> int:
    active = store.running(ctx.db, ctx.now)
    if active is None:
        return say("Nothing is running")
    return say(
        f"Still {active.line} · {present.hm(active.length(ctx.now))} since {active.start:%H:%M}"
    )


def stop_command(args: list[str], ctx: Context) -> int:
    active = store.running(ctx.db, ctx.now)
    if active is None:
        return say("Nothing was running")
    store.record(ctx.db, ctx.now, "", ctx.now)
    bar.poke(ctx.env)
    return say(f"{active.line} · {present.hm(active.length(ctx.now))}")


def bar_command(args: list[str], ctx: Context) -> int:
    plugin = args[0] if args else bar.PLUGIN
    return say(bar.menu(ctx.db, ctx.now, ctx.starts, plugin))


def install_bar_command(args: list[str], ctx: Context) -> int:
    try:
        return say(f"SwiftBar plugin installed · {bar.install(ctx.env)}")
    except FileNotFoundError as missing:
        return say(f"Not installed: {missing} not found")


def nudge_command(args: list[str], ctx: Context) -> int:
    said = nudge.message(ctx.db, ctx.now, nudge.settings(ctx.env), nudge.user_idle())
    if not said:
        return 0
    if bar.installed(ctx.env):
        bar.refresh()
        bar.notify(f"{said} {nudge.CLICK}", nudge.opening(ctx.db, ctx.now))
        return 0
    print(said)
    return 0


def nudges_command(args: list[str], ctx: Context) -> int:
    if nudge.installed():
        nudge.turn_off()
        return say("Nudges off")
    chosen = nudge.settings(ctx.env)
    nudge.turn_on(chosen)
    return say(f"Nudges on: {nudge.describe(chosen)}")


def everything(ctx: Context) -> scope.Scope:
    return scope.Scope("", ctx.aliases)


def edit_command(args: list[str], ctx: Context) -> int:
    text = args[0] if args else ""
    target = ctx.env.get("target", "")
    return emit(editrows.rows(target, text, ctx.db, ctx.now, ctx.starts, everything(ctx)))


def apply_command(args: list[str], ctx: Context) -> int:
    target = edits.target(ctx.env.get("target", ""))
    text = " ".join(args).strip()
    if target is None or not text:
        raise Usage("apply needs a target variable and the edit")
    plan = edits.plan(ctx.db, target, text, ctx.now, ctx.starts, everything(ctx))
    if not plan.valid:
        return say(plan.title)
    journal.apply(ctx.db, list(plan.ops), plan.title, ctx.now)
    bar.poke(ctx.env)
    return say(plan.title)


def undo_command(args: list[str], ctx: Context) -> int:
    batch = journal.undo(ctx.db)
    if batch is None:
        return say("Nothing to undo")
    bar.poke(ctx.env)
    return say(f"Undone: {batch.said}")


def act_command(args: list[str], ctx: Context) -> int:
    if not args or args[0] not in ACTIONS:
        raise Usage(f"act needs one of {', '.join(ACTIONS)}")
    return ACTIONS[args[0]](args[1:], ctx)


def view_command(args: list[str], ctx: Context) -> int:
    word = (args[0] if args else "").strip()
    print(
        json.dumps(view.showing(ctx.db, word, ctx.now, ctx.starts, ctx.aliases), ensure_ascii=False)
    )
    return 0


def today_command(args: list[str], ctx: Context) -> int:
    word = (args[0] if args else "").strip() or "@today"
    shown = view.showing(ctx.db, word, ctx.now, ctx.starts, ctx.aliases)
    return say(shown["response"])


Command = Callable[[list[str], Context], int]

ACTIONS: dict[str, Command] = {
    "start": start_command,
    "keep": keep_command,
    "stop": stop_command,
    "bar": install_bar_command,
    "nudges": nudges_command,
    "apply": apply_command,
    "undo": undo_command,
}

COMMANDS: dict[str, Command] = {
    "filter": filter_command,
    "filter-work": filter_work_command,
    **ACTIONS,
    "act": act_command,
    "view": view_command,
    "today": today_command,
    "bar": bar_command,
    "nudge": nudge_command,
    "edit": edit_command,
}

USAGE = "usage: tally " + "|".join(COMMANDS) + " ..."


def run(
    argv: list[str],
    env: Mapping[str, str],
    now: datetime | None = None,
    db: sqlite3.Connection | None = None,
) -> int:
    if not argv or argv[0] not in COMMANDS:
        print(USAGE, file=sys.stderr)
        return 2
    ctx = Context(env, now or datetime.now().replace(second=0, microsecond=0), db)
    try:
        return COMMANDS[argv[0]](argv[1:], ctx)
    except Usage as error:
        print(f"{USAGE}\n{error}", file=sys.stderr)
        return 2


def main() -> None:
    sys.exit(run(sys.argv[1:], os.environ))
