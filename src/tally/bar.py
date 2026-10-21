"""A SwiftBar plugin: the running task in the menu bar, the recent ones in its menu."""

from __future__ import annotations

import os
import sqlite3
from collections.abc import Mapping
from datetime import datetime, timedelta
from pathlib import Path

from tally import present, remind, store

PLUGIN = "tally.30s.sh"
IDLE = "tally"
WIDTH = 18
PASSED = ("alfred_workflow_data", "db_path", "day_starts", "tag_aliases")

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


def status(db: sqlite3.Connection, now: datetime) -> str:
    active = store.running(db, now)
    return f"{shorten(active.line)} {present.hm(active.length(now))}" if active else IDLE


def quoted(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def action(title: str, plugin: str, *args: str) -> str:
    params = " ".join(f"param{n}={quoted(arg)}" for n, arg in enumerate(args, 1))
    return f"{title} | bash={quoted(plugin)} {params} terminal=false refresh=true"


def menu(db: sqlite3.Connection, now: datetime, starts: timedelta, plugin: str) -> str:
    lines = [status(db, now), "---"]
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
