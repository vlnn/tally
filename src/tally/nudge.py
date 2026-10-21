"""Every few minutes, a notification saying what tally thinks you are doing.

Ignoring it confirms: the running task keeps running, the gap stays a gap. Anything else is a
switch in Alfred. A launchd agent asks Alfred to run the workflow's `nudge` trigger, so the
check runs with the workflow's own settings and the notification is Alfred's.
"""

from __future__ import annotations

import os
import re
import sqlite3
from collections.abc import Mapping
from datetime import datetime, time, timedelta
from pathlib import Path
from typing import NamedTuple

from hoard.alfred import is_on

from tally import durations, store

LABEL = "com.anokhin.tally.nudge"
TRIGGER = "nudge"
BUNDLE_ID = "com.anokhin.tally"
DEFAULT_EVERY = 15
DEFAULT_HOURS = "09:00-19:00"
HOURS = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})\s*$")
SATURDAY = 5


class Settings(NamedTuple):
    every: timedelta
    since: time
    until: time
    weekends: bool


def minutes(text: str) -> int:
    try:
        return max(0, int(text.strip()))
    except ValueError:
        return DEFAULT_EVERY


def hours(text: str) -> tuple[time, time]:
    found = HOURS.match(text) or HOURS.match(DEFAULT_HOURS)
    assert found is not None
    h1, m1, h2, m2 = (int(part) for part in found.groups())
    try:
        return time(h1, m1), time(h2, m2)
    except ValueError:
        return hours(DEFAULT_HOURS)


def settings(env: Mapping[str, str]) -> Settings:
    since, until = hours(env.get("nudge_hours", DEFAULT_HOURS))
    every = minutes(env.get("nudge_every", str(DEFAULT_EVERY)))
    return Settings(timedelta(minutes=every), since, until, is_on(env.get("nudge_weekends", "")))


def in_hours(now: datetime, chosen: Settings) -> bool:
    if now.weekday() >= SATURDAY and not chosen.weekends:
        return False
    return chosen.since <= now.time() < chosen.until


def away(user_idle: timedelta, chosen: Settings) -> bool:
    return user_idle >= chosen.every


def recently_logged(db: sqlite3.Connection, now: datetime, chosen: Settings) -> bool:
    last = store.last_before(db, now)
    return last is not None and now - last.at < chosen.every


def wording(db: sqlite3.Connection, now: datetime) -> str:
    active = store.running(db, now)
    if active:
        return f"Still on {active.line} · {durations.hm(active.length(now))}? Ignore to keep it."
    last = store.last_before(db, now)
    if last is None or last.at.date() != now.date():
        return "Nothing logged today. Type t to start."
    return f"Nothing running since {last.at:%H:%M}. Ignore if you're away."


def message(db: sqlite3.Connection, now: datetime, chosen: Settings, user_idle: timedelta) -> str:
    """What to say now, or nothing."""
    if not chosen.every or not in_hours(now, chosen) or away(user_idle, chosen):
        return ""
    if recently_logged(db, now, chosen):
        return ""
    return wording(db, now)


OPEN_TRIGGER = "open"
CLICK = "Click to switch."


def link(typed: str) -> str:
    """An Alfred link that opens t with this typed in."""
    from urllib.parse import quote

    return f"alfred://runtrigger/{BUNDLE_ID}/{OPEN_TRIGGER}/?argument={quote(typed)}"


def opening(db: sqlite3.Connection, now: datetime) -> str:
    """The link a nudge's click follows: t, with the running task typed in so it is on top."""
    active = store.running(db, now)
    return link(active.line if active else "")


HID_IDLE = re.compile(r'"HIDIdleTime"\s*=\s*(\d+)')


def user_idle() -> timedelta:
    """How long since the last key press or mouse move, by the HID system's own count."""
    import subprocess

    try:
        read = subprocess.run(
            ["ioreg", "-c", "IOHIDSystem"], capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return timedelta()
    found = HID_IDLE.search(read.stdout)
    return timedelta(microseconds=int(found.group(1)) // 1000) if found else timedelta()


def agent_path() -> Path:
    return Path(os.path.expanduser("~/Library/LaunchAgents")) / f"{LABEL}.plist"


def agent(chosen: Settings) -> dict:
    script = (
        'tell application id "com.runningwithcrayons.Alfred" to run trigger '
        f'"{TRIGGER}" in workflow "{BUNDLE_ID}"'
    )
    return {
        "Label": LABEL,
        "ProgramArguments": ["/usr/bin/osascript", "-e", script],
        "StartInterval": int(chosen.every.total_seconds()),
        "RunAtLoad": False,
        "ProcessType": "Background",
    }


def installed() -> bool:
    return agent_path().exists()


def launchctl(*args: str) -> None:
    import subprocess

    subprocess.run(["launchctl", *args], capture_output=True, check=False)


def domain() -> str:
    return f"gui/{os.getuid()}"


def turn_on(chosen: Settings) -> Path:
    import plistlib

    path = agent_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    launchctl("bootout", f"{domain()}/{LABEL}")
    with open(path, "wb") as handle:
        plistlib.dump(agent(chosen), handle)
    launchctl("bootstrap", domain(), str(path))
    return path


def turn_off() -> None:
    launchctl("bootout", f"{domain()}/{LABEL}")
    agent_path().unlink(missing_ok=True)


def describe(chosen: Settings) -> str:
    days = "every day" if chosen.weekends else "weekdays"
    every = int(chosen.every.total_seconds() // 60)
    return f"every {every} min, {chosen.since:%H:%M}–{chosen.until:%H:%M} {days}"
