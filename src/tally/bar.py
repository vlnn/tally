"""A SwiftBar plugin: the running task in the menu bar, the recent ones in its menu."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from tally import gaps, present, remind, store

PLUGIN = "tally.30s.sh"
OPEN_T = "alfred://runtrigger/com.anokhin.tally/open/?argument="
IDLE = "tally"
WIDTH = 18
PASSED = (
    "alfred_workflow_data",
    "db_path",
    "day_starts",
    "tag_aliases",
    "nudge_every",
    "nudge_hours",
    "nudge_weekends",
    "unclaimed_ladder",
    "unclaimed_sounds",
)
COLOURS = ("#8E8E93", "#FFCC00", "#FF9500", "#FF3B30")
CHIME = "/System/Library/Sounds/Tink.aiff"
SOUNDED, TOLD = 2, 3

SCRIPT = """#!/bin/bash
# <swiftbar.hideAbout>true</swiftbar.hideAbout>
# <swiftbar.hideRunInTerminal>true</swiftbar.hideRunInTerminal>
# <swiftbar.hideLastUpdated>true</swiftbar.hideLastUpdated>
# <swiftbar.hideDisablePlugin>true</swiftbar.hideDisablePlugin>
{exports}
ALFRED=com.runningwithcrayons.Alfred
cd "{bundle}" || exit 1
case "$1" in
  start) shift; /usr/bin/python3 -m tally act start "$*" >/dev/null ;;
  stop) /usr/bin/python3 -m tally act stop >/dev/null ;;
  open) /usr/bin/osascript -e "tell application id \\"$ALFRED\\" to search \\"t $2\\"" ;;
  *) /usr/bin/python3 -m tally bar "$0" ;;
esac
"""


def shorten(line: str) -> str:
    return line if len(line) <= WIDTH else line[: WIDTH - 1].rstrip() + "…"


def status(
    db: sqlite3.Connection,
    now: datetime,
    gap: gaps.Gap | None = None,
    steps: tuple[int, ...] = gaps.DEFAULT_LADDER,
) -> str:
    active = store.running(db, now)
    if active:
        return f"{shorten(active.line)} {present.hm(active.length(now))}"
    return unclaimed(gap, steps) or IDLE


def unclaimed(gap: gaps.Gap | None, steps: tuple[int, ...]) -> str:
    """The counter, coloured by how far up the ladder the gap is; nothing below the first step."""
    reached = gaps.level(gap, steps)
    if gap is None or not reached:
        return ""
    return f"{int(gap.length.total_seconds() // 60)}m unclaimed | color={COLOURS[reached - 1]}"


def told(gap: gaps.Gap) -> str:
    return f"{int(gap.length.total_seconds() // 60)} min unclaimed since {gap.start:%H:%M}"


def climbed(db: sqlite3.Connection, gap: gaps.Gap | None, reached: int) -> bool:
    """Whether this gap has just reached a step it had not reached before; remembers it."""
    db.execute("CREATE TABLE IF NOT EXISTS ladder (start TEXT PRIMARY KEY, level INTEGER)")
    if gap is None:
        db.execute("DELETE FROM ladder")
        db.commit()
        return False
    start = gap.start.isoformat(timespec="minutes")
    db.execute("DELETE FROM ladder WHERE start != ?", (start,))
    row = db.execute("SELECT level FROM ladder WHERE start = ?", (start,)).fetchone()
    before = row[0] if row else 0
    db.execute("INSERT OR REPLACE INTO ladder VALUES (?, ?)", (start, max(before, reached)))
    db.commit()
    return reached > before


def chime() -> None:
    import subprocess

    try:
        subprocess.Popen(["afplay", CHIME])
    except FileNotFoundError:
        pass


def alert(
    db: sqlite3.Connection,
    gap: gaps.Gap | None,
    steps: tuple[int, ...],
    sounds: bool,
    away: Callable[[], bool],
) -> str:
    """The sound at the second step, a notification at the third and fourth; not while away."""
    reached = gaps.level(gap, steps)
    if not climbed(db, gap, reached) or gap is None or reached < SOUNDED or away():
        return ""
    if reached >= TOLD:
        notify(told(gap), OPEN_T)
        return "told"
    if sounds:
        chime()
        return "chimed"
    return ""


def quoted(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def action(title: str, plugin: str, *args: str) -> str:
    params = " ".join(f"param{n}={quoted(arg)}" for n, arg in enumerate(args, 1))
    return f"{title} | bash={quoted(plugin)} {params} terminal=false refresh=true"


def menu(
    db: sqlite3.Connection,
    now: datetime,
    starts: timedelta,
    plugin: str,
    gap: gaps.Gap | None = None,
    steps: tuple[int, ...] = gaps.DEFAULT_LADDER,
) -> str:
    lines = [status(db, now, gap, steps), "---"]
    if unclaimed(gap, steps):
        assert gap is not None
        lines += [action(f"Claim {told(gap)}", plugin, "open", ""), "---"]
    active = store.running(db, now)
    if active:
        lines += [
            action(f"Stop {active.line} · {present.hm(active.length(now))}", plugin, "stop"),
            "---",
        ]
    day = present.Day(db, now, starts)
    for task in present.recent(db, now):
        subtitle = present.task_subtitle(task, day, db, now)
        lines.append(action(f"Resume {task.line} · {subtitle}", plugin, "start", task.line))
    waiting = remind.pending(db)
    if waiting:
        lines += ["---", f"Reminders · {len(waiting)}"]
        lines += [
            "--"
            + action(f"⏰ {remind.timing(r, now)} {r.text}", plugin, "open", f"@reminders {r.text}")
            for r in waiting
        ]
    lines += [
        "---",
        action(f"Today · {present.hm(day.total())} logged", plugin, "open", "@today"),
        action("Open Tally", plugin, "open", ""),
    ]
    return "\n".join(lines)


def bundle(env: Mapping[str, str]) -> Path:
    preferences, uid = env.get("alfred_preferences", ""), env.get("alfred_workflow_uid", "")
    if preferences and uid:
        return Path(preferences) / "workflows" / uid
    return Path(os.getcwd())


def exports(env: Mapping[str, str]) -> str:
    return "\n".join(f"export {name}={quoted(env[name])}" for name in PASSED if env.get(name))


def script(env: Mapping[str, str]) -> str:
    return SCRIPT.format(exports=exports(env), bundle=bundle(env))


def swiftbar_folder(env: Mapping[str, str]) -> Path | None:
    chosen = env.get("swiftbar_plugins", "").strip()
    if chosen:
        return Path(os.path.expanduser(chosen))
    import subprocess

    try:
        read = subprocess.run(
            ["defaults", "read", "com.ameba.SwiftBar", "PluginDirectory"],
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError:
        return None
    found = read.stdout.strip()
    return Path(os.path.expanduser(found)) if read.returncode == 0 and found else None


def plugin_path(env: Mapping[str, str]) -> Path | None:
    folder = swiftbar_folder(env)
    return folder / PLUGIN if folder else None


def refresh() -> None:
    import subprocess

    try:
        subprocess.run(
            ["open", "-g", "swiftbar://refreshplugin?name=tally"], capture_output=True, check=False
        )
    except FileNotFoundError:
        pass


def installed(env: Mapping[str, str]) -> bool:
    path = plugin_path(env)
    return bool(path and path.exists())


def notification(body: str, href: str) -> str:
    from urllib.parse import quote, urlencode

    fields = {"plugin": "tally", "title": "Tally", "body": body, "href": href}
    return "swiftbar://notify?" + urlencode(fields, quote_via=quote)


def notify(body: str, href: str) -> None:
    """A notification from SwiftBar, which opens href when clicked."""
    import subprocess

    try:
        subprocess.run(["open", "-g", notification(body, href)], capture_output=True, check=False)
    except FileNotFoundError:
        pass


def poke(env: Mapping[str, str]) -> None:
    """Refresh the menu bar after a change from Alfred, if the plugin is installed."""
    if installed(env):
        refresh()


def install(env: Mapping[str, str]) -> Path:
    path = plugin_path(env)
    if path is None:
        raise FileNotFoundError("SwiftBar's plugin folder")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(script(env), encoding="utf-8")
    path.chmod(0o755)
    refresh()
    return path
