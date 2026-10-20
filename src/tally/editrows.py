"""Rows of the edit list: what the typed text would do to the block, task or day."""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta

from tally import edits, present
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


BLOCKS_SHOWN = 12


def block_rows(
    target: edits.Target, db: sqlite3.Connection, now: datetime, scope: Scope
) -> list[Row]:
    if target.kind != edits.TASK:
        return []
    found = edits.task_blocks(db, target.value, scope)
    return [present.block_row(b, now) for b in reversed(found[-BLOCKS_SHOWN:])]


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
            {
                "title": "Nothing chosen to edit",
                "subtitle": "start with ⌃↩ on a task",
                "valid": False,
            }
        ]
    if not text.strip():
        hinted = [hint_row(hint) for hint in edits.hints(target.kind)]
        return hinted + block_rows(target, db, now, scope)
    return [plan_row(edits.plan(db, target, text, now, starts, scope), text, target)]
