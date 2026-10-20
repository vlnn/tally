"""The Text View that shows a day."""

from __future__ import annotations

from datetime import datetime, timedelta

from tally import ribbon

RERUN = 60.0
FOOTER = "↩ copies the text"


def showing(
    db, word: str, now: datetime, starts: timedelta, aliases: dict[str, str] | None = None
) -> dict:
    found = ribbon.shown(db, word or "@today", now, starts, aliases)
    if found is None:
        return {"response": f"**{word} is not a day**: try @today, @yesterday or 2026-10-20"}
    window, text = found
    shown: dict = {"response": text, "footer": FOOTER, "behaviour": {"response": "replace"}}
    if window.since <= now < window.until:
        shown["rerun"] = RERUN
    return shown
