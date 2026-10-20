"""Runs the built bundle the way Alfred would, from a temporary folder."""

import json
import os
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timedelta
from pathlib import Path


def run(bundle, data, *args, **extra):
    env = {**os.environ, "alfred_workflow_data": data, "PYTHONPATH": "", **extra}
    done = subprocess.run(
        [sys.executable, "-m", "tally", *args],
        cwd=bundle,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    return done.stdout


def main(archive):
    with tempfile.TemporaryDirectory() as scratch:
        bundle = Path(scratch) / "bundle"
        with zipfile.ZipFile(archive) as packed:
            packed.extractall(bundle)
        data = str(Path(scratch) / "data")
        earlier = (datetime.now() - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M")
        assert " from " in run(bundle, data, "act", "start", "parser #lexer", at=earlier)
        rows = json.loads(run(bundle, data, "filter", ""))["items"]
        assert [r["title"] for r in rows][-2:] == ["Stop", "Today"], rows
        assert "parser #lexer" in run(bundle, data, "act", "stop")
        edit_env = {"target": "task:parser #lexer"}
        assert run(bundle, data, "act", "apply", "#w", **edit_env).strip() == "Add #w · 1 block"
        assert run(bundle, data, "act", "undo").startswith("Undone: Add #w")
        shown = json.loads(run(bundle, data, "view", "@today"))
        assert "#lexer" in shown["response"], shown
        print("ok: the bundle starts, lists, stops, edits, undoes and shows the day")


if __name__ == "__main__":
    main(sys.argv[1])
