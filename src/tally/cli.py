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

from tally import days, present, store, view

NAME = "tally"
DB_NAME = "tally.db"


class Usage(Exception):
    pass


class Context:
    def __init__(self, env: Mapping[str, str], now: datetime, db: sqlite3.Connection | None):
        self.env = env
        self.now = now
        self.starts = days.offset(env.get("day_starts", ""))
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


def filter_command(args: list[str], ctx: Context) -> int:
    text = args[0] if args else ""
    return emit(present.rows(text, ctx.db, ctx.now, ctx.starts))


def start_command(args: list[str], ctx: Context) -> int:
    line = " ".join(args).strip()
    if not line:
        raise Usage("start needs a line")
    at = ctx.at()
    store.record(ctx.db, at, line, ctx.now)
    return say(f"{line} from {at:%H:%M}")


def stop_command(args: list[str], ctx: Context) -> int:
    active = store.running(ctx.db, ctx.now)
    if active is None:
        return say("Nothing was running")
    store.record(ctx.db, ctx.now, "", ctx.now)
    return say(f"{active.line} · {present.hm(active.length(ctx.now))}")


def act_command(args: list[str], ctx: Context) -> int:
    if not args or args[0] not in ACTIONS:
        raise Usage(f"act needs one of {', '.join(ACTIONS)}")
    return ACTIONS[args[0]](args[1:], ctx)


def view_command(args: list[str], ctx: Context) -> int:
    word = (args[0] if args else "").strip()
    print(json.dumps(view.showing(ctx.db, word, ctx.now, ctx.starts), ensure_ascii=False))
    return 0


def today_command(args: list[str], ctx: Context) -> int:
    word = (args[0] if args else "").strip() or "@today"
    shown = view.showing(ctx.db, word, ctx.now, ctx.starts)
    return say(shown["response"])


Command = Callable[[list[str], Context], int]

ACTIONS: dict[str, Command] = {"start": start_command, "stop": stop_command}

COMMANDS: dict[str, Command] = {
    "filter": filter_command,
    **ACTIONS,
    "act": act_command,
    "view": view_command,
    "today": today_command,
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
