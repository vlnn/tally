"""Runs the built bundle the way Alfred would, from a temporary folder."""

import json
import os
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path


def run(bundle, data, *args):
    env = {**os.environ, "alfred_workflow_data": data, "PYTHONPATH": ""}
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
        assert " from " in run(bundle, data, "act", "start", "parser #lexer")
        rows = json.loads(run(bundle, data, "filter", ""))["items"]
        assert [r["title"] for r in rows][-2:] == ["Stop", "Today"], rows
        assert "parser #lexer" in run(bundle, data, "act", "stop")
        shown = json.loads(run(bundle, data, "view", "@today"))
        assert "#lexer" in shown["response"], shown
        print("ok: the bundle starts, lists, stops and shows the day")


if __name__ == "__main__":
    main(sys.argv[1])
