"""Rows of the edit list: what the typed text would do to the block, task or day."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from tally import edits
from tally.present import NO_MODS, Row
from tally.scope import Scope


def hint_row(hint: edits.Plan) -> Row:
    return {
        "title": hint.title,
        "subtitle": hint.subtitle,
        "valid": False,
        "autocomplete": hint.complete,
        "mods": NO_MODS,
    }


def plan_row(plan: edits.Plan, text: str, target: edits.Target) -> Row:
    if not plan.valid:
        return {"title": plan.title, "subtitle": plan.subtitle, "valid": False, "mods": NO_MODS}
    return {
        "title": plan.title,
        "subtitle": f"{plan.subtitle} · ↩ does it, t undo takes it back",
        "arg": text,
        "variables": {"action": "apply", "target": target.encode()},
        "mods": NO_MODS,
    }


def rows(
    encoded: str,
    text: str,
    db: sqlite3.Connection,
    now: datetime,
    starts: timedelta,
    scope: Scope,
) -> list[Row]:
    target = edits.target(encoded)
    if target is None:
        return [
            {"title": "Nothing chosen to edit", "subtitle": "start from t edit", "valid": False}
        ]
    if not text.strip():
        return [hint_row(hint) for hint in edits.hints(target.kind)]
    return [plan_row(edits.plan(db, target, text, now, starts, scope), text, target)]
