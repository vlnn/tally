import json
from datetime import datetime, timedelta

import pytest

from conftest import NO_OFFSET, NOW
from tally import cli, editrows, edits, journal, present, store
from tally.scope import Scope

ALIASED = Scope("", {"w": "work"})
PARSER = 4
RUNNING = 8


def plan(db, target, text):
    return edits.plan(db, edits.target(target), text, NOW, NO_OFFSET, ALIASED)


def timeline(db):
    return [(f"{t.at:%H:%M}", t.line) for t in store.transitions(db)]


@pytest.mark.parametrize(
    "text, expected",
    [
        ("#w", edits.Tagging(("w",), ())),
        ("#w -#lexer", edits.Tagging(("w",), ("lexer",))),
        ("-#Lexer", edits.Tagging((), ("lexer",))),
        ("#w parser", None),
        ("#", None),
        ("parser", None),
    ],
)
def test_tagging_reads_only_tag_words(text, expected):
    assert edits.tagging(text) == expected, "only #tag and -#tag words make a tagging"


@pytest.mark.parametrize(
    "line, text, expected",
    [
        ("parser", "#w", "parser #w"),
        ("parser #work", "#w", "parser #work"),
        ("parser #lexer", "-#lexer", "parser"),
        ("parser #w", "-#work", "parser"),
        ("parser #lexer", "#w -#lexer", "parser #w"),
        ("issue#w", "-#w", "issue#w"),
    ],
)
def test_retagged(line, text, expected):
    assert edits.retagged(line, edits.tagging(text), ALIASED) == expected, (
        "tags are added once and removed by any spelling of them"
    )


@pytest.mark.parametrize("encoded", ["", "block:", "nonsense:3", "task"])
def test_bad_targets(encoded):
    assert edits.target(encoded) is None, "only block:, task: and day: with a value"


def test_tag_one_block(db, sample):
    found = plan(db, f"block:{PARSER}", "#w")
    assert (found.title, found.subtitle) == ("Add #w · 1 block", "parser #lexer · 11:05"), "says it"
    journal.apply(db, list(found.ops), found.title, NOW)
    assert timeline(db)[3] == ("11:05", "parser #lexer #w"), "that block only"
    assert timeline(db)[7] == ("14:05", "parser #lexer"), "the other parser block is untouched"


def test_tag_every_block_of_a_task(db, sample):
    found = plan(db, "task:parser #lexer", "#w")
    assert found.title == "Add #w · 2 blocks", "both parser blocks"
    assert found.subtitle == "every block of parser #lexer · 2 blocks, 2:40", "and how much time"


def test_tag_a_whole_day(db, sample):
    assert plan(db, "day:2026-10-20", "#w").title == "Add #w · 6 blocks", "every block that day"


def test_tagging_what_is_already_tagged_changes_nothing(db, logged):
    logged(9, 0, "parser #work")
    found = plan(db, "task:parser #work", "#w")
    assert not found.valid and found.title == "Nothing to change", "#w is #work already"


def test_rename_a_block_and_a_task(db, sample):
    assert plan(db, f"block:{PARSER}", "lexing #lexer").title == "Rename 1 block to lexing #lexer"
    assert plan(db, "task:parser #lexer", "lexing").title == "Rename 2 blocks to lexing"


def test_a_day_takes_tags_only(db, sample):
    assert not plan(db, "day:2026-10-20", "lunch").valid, "renaming a day means nothing"


def test_a_task_refuses_block_words(db, sample):
    assert plan(db, "task:parser #lexer", "start 9:00").title == "start is for one block"


def test_delete_a_whole_task(db, sample):
    found = plan(db, "task:parser #lexer", "delete")
    assert (found.title, found.subtitle) == (
        "Delete 2 blocks · 2:40",
        "every block of parser #lexer becomes untracked",
    ), "says how much goes"
    journal.apply(db, list(found.ops), found.title, NOW)
    lines = [line for _, line in timeline(db)]
    assert "parser #lexer" not in lines, "no parser left"
    assert timeline(db)[-1] == ("14:05", ""), "the running one became a stop after review"
    assert ("11:05", "") not in timeline(db), "after a stop it is removed, not doubled"


def test_delete_a_whole_day_and_undo_it(db, sample, logged):
    logged(9, 0, "yesterday's", day=NOW.date() - timedelta(days=1))
    logged(10, 0, "", day=NOW.date() - timedelta(days=1))
    before = timeline(db)
    found = plan(db, "day:2026-10-20", "delete")
    assert found.title == "Delete 6 blocks · 4:40", "everything that day"
    journal.apply(db, list(found.ops), found.title, NOW)
    assert store.blocks(store.transitions(db))[-1].line == "yesterday's", "only yesterday is left"
    journal.undo(db)
    assert timeline(db) == before, "and undo brings the day back"


def test_delete_nothing(db, logged):
    assert not plan(db, "day:2026-10-19", "delete").valid, "an empty day has nothing to delete"


@pytest.mark.parametrize(
    "text, title, subtitle, after",
    [
        (
            "start 11:30",
            "Start parser #lexer at 11:30 instead of 11:05",
            "untracked before it",
            ("11:30", "parser #lexer"),
        ),
        (
            "start 10:30",
            "Start parser #lexer at 10:30 instead of 11:05",
            "takes from untracked time",
            ("10:30", "parser #lexer"),
        ),
        (
            "end 12:00",
            "End parser #lexer at 12:00 instead of 12:50",
            "untracked after it",
            ("12:00", ""),
        ),
        (
            "end 13:00",
            "End parser #lexer at 13:00 instead of 12:50",
            "takes from untracked time",
            ("13:00", ""),
        ),
    ],
)
def test_retime_a_block_next_to_gaps(db, sample, text, title, subtitle, after):
    found = plan(db, f"block:{PARSER}", text)
    assert (found.title, found.subtitle) == (title, subtitle), "the row says what moves"
    journal.apply(db, list(found.ops), found.title, NOW)
    assert after in timeline(db), "and that is what moved"


def test_moving_a_start_earlier_shortens_the_task_before(db, sample):
    found = plan(db, f"block:{RUNNING}", "start 14:00")
    assert found.subtitle == "review pr 212 now ends at 14:00", "the neighbour gives way"


def test_ending_before_the_next_task_leaves_a_gap(db, sample):
    found = plan(db, "block:6", "end 13:30")
    assert found.subtitle == "untracked 13:30–13:40, then review pr 212", "a stop is inserted"
    journal.apply(db, list(found.ops), found.title, NOW)
    assert ("13:30", "") in timeline(db) and ("13:40", "review pr 212") in timeline(db)


def test_ending_later_pushes_the_next_task(db, sample):
    found = plan(db, "block:6", "end 13:50")
    assert found.subtitle == "review pr 212 now starts at 13:50", "the next task starts later"


def test_ending_the_running_task_stops_it_then(db, sample):
    found = plan(db, f"block:{RUNNING}", "end 14:30")
    journal.apply(db, list(found.ops), found.title, NOW)
    assert timeline(db)[-1] == ("14:30", "") and store.running(db, NOW) is None, "stopped at 14:30"


@pytest.mark.parametrize(
    "target, text, title",
    [
        (f"block:{PARSER}", "start 9:00", "09:00 is outside 10:10–12:50"),
        (f"block:{PARSER}", "start 13:00", "13:00 is outside 10:10–12:50"),
        (f"block:{PARSER}", "end 11:00", "11:00 is before it starts at 11:05"),
        (f"block:{PARSER}", "end 13:30", "13:30 is past the next block, which ends 13:10"),
        (f"block:{PARSER}", "end 12:50", "Already ends at 12:50"),
        (f"block:{RUNNING}", "end 16:00", "16:00 has not happened yet"),
        (f"block:{PARSER}", "start xx", "xx is not a time"),
        ("block:999", "#w", "That block is gone"),
        ("block:3", "#w", "That block is gone"),
    ],
)
def test_impossible_edits_explain(db, sample, target, text, title):
    found = plan(db, target, text)
    assert not found.valid and found.title == title, "one row that says why, and no ops"


def test_delete_after_a_task_becomes_a_stop(db, sample):
    found = plan(db, "block:7", "delete")
    assert found.subtitle == "13:40–14:05 becomes untracked", "the time is said"
    journal.apply(db, list(found.ops), found.title, NOW)
    assert ("13:40", "") in timeline(db), "the call ends at 13:40, then nothing until parser"


def test_delete_after_a_gap_removes_the_transition(db, sample):
    found = plan(db, f"block:{PARSER}", "delete")
    journal.apply(db, list(found.ops), found.title, NOW)
    assert ("11:05", "parser #lexer") not in timeline(db) and ("11:05", "") not in timeline(db), (
        "a stop after a stop would be noise"
    )


def test_undo_takes_back_the_last_batch_only(db, sample):
    before = timeline(db)
    tagged = plan(db, "task:parser #lexer", "#w")
    journal.apply(db, list(tagged.ops), tagged.title, NOW)
    after_tag = timeline(db)
    moved = plan(db, f"block:{PARSER}", "end 12:00")
    journal.apply(db, list(moved.ops), moved.title, NOW)
    assert journal.undo(db).said == "End parser #lexer #w at 12:00 instead of 12:50"
    assert timeline(db) == after_tag, "the retime is gone, the tags stay"
    journal.undo(db)
    assert timeline(db) == before, "then the tags go"
    assert journal.undo(db) is None, "and there is nothing left"


def test_undo_of_an_insert_and_a_delete(db, sample):
    before = timeline(db)
    for target, text in (("block:6", "end 13:30"), (f"block:{PARSER}", "delete")):
        found = plan(db, target, text)
        journal.apply(db, list(found.ops), found.title, NOW)
    journal.undo(db)
    journal.undo(db)
    assert timeline(db) == before, "inserted stops vanish, deleted rows return with their ids"


def test_edit_hints_when_nothing_is_typed(db, sample):
    rows = editrows.rows(f"block:{PARSER}", "", db, NOW, NO_OFFSET, ALIASED)
    assert [r["autocomplete"] for r in rows] == ["#", "start ", "end ", "delete", ""], (
        "a block offers every edit, ⇥ fills it in"
    )
    rows = editrows.rows("task:parser #lexer", "", db, NOW, NO_OFFSET, ALIASED)
    assert [r["autocomplete"] for r in rows if "autocomplete" in r] == ["#", "delete", ""], (
        "a task: tags, delete and rename"
    )


def test_an_edit_row_carries_the_text_and_target(db, sample):
    row = editrows.rows(f"block:{PARSER}", "#w", db, NOW, NO_OFFSET, ALIASED)[0]
    assert (row["arg"], row["variables"]) == ("#w", {"action": "apply", "target": "block:4"}), (
        "act apply plans the same text again"
    )


def test_edit_is_a_word_like_any_other(db, sample):
    rows = present.rows("edit", db, NOW, NO_OFFSET)
    assert rows[0]["title"] == "Start edit", "edit is a task you can start, not a command"


def test_a_tasks_edit_list_shows_its_blocks_after_the_hints(db, sample):
    rows = editrows.rows("task:parser #lexer", "", db, NOW, NO_OFFSET, ALIASED)
    blocks = [r for r in rows if r.get("variables", {}).get("action") == "edit"]
    assert [r["title"] for r in blocks] == ["14:05–now · 0:55", "11:05–12:50 · 1:45"], (
        "newest first, so one block can be retimed or deleted"
    )
    assert blocks[0]["variables"]["target"] == f"block:{RUNNING}", "↩ opens that block's list"


def test_a_blocks_edit_list_has_no_block_rows(db, sample):
    rows = editrows.rows(f"block:{PARSER}", "", db, NOW, NO_OFFSET, ALIASED)
    assert all(r["valid"] is False for r in rows), "hints only"


EDIT_REVIEW = {"action": "edit", "target": "task:review pr 212"}


def test_cmd_opens_the_edit_list_with_delete_typed(db, sample):
    row = present.rows("", db, NOW, NO_OFFSET)[0]
    assert (row["mods"]["cmd"]["arg"], row["mods"]["cmd"]["variables"]) == (
        "delete",
        EDIT_REVIEW,
    ), "⌘↩ then ↩ deletes, so a stray ⌘↩ alone removes nothing"


@pytest.mark.parametrize("key", ["ctrl", "cmd"])
def test_task_and_day_rows_offer_ctrl_to_edit(db, sample, key):
    rows = present.rows("", db, NOW, NO_OFFSET)
    assert rows[0]["mods"][key]["variables"] == EDIT_REVIEW, "a recent task edits all of it"
    assert rows[-2]["mods"][key]["variables"] == {
        "action": "edit",
        "target": "task:parser #lexer",
    }, "on Stop it edits the running task"
    assert rows[-1]["mods"][key]["variables"]["target"] == "day:2026-10-20", "on today, the day"


def test_ctrl_on_a_searched_task_edits_it(db, sample):
    rows = present.rows("rev", db, NOW, NO_OFFSET)
    found = next(r for r in rows if r["title"] == "Resume review pr 212")
    assert found["mods"]["ctrl"]["variables"] == EDIT_REVIEW, "search, point, ⌃↩"
    assert found["mods"]["ctrl"]["subtitle"] == "⌃↩ rename or retag this task, its time stays"


def test_ctrl_on_an_exact_match_edits_it_and_on_a_new_line_does_nothing(db, sample):
    known = present.rows("review pr 212", db, NOW, NO_OFFSET)[0]
    assert known["mods"]["ctrl"]["variables"] == EDIT_REVIEW, "the Resume row of a known task"
    new = present.rows("write tests", db, NOW, NO_OFFSET)[0]
    assert new["mods"]["ctrl"]["valid"] is False, "nothing to edit before it exists"


def test_undo_row(db, sample):
    assert present.rows("undo", db, NOW, NO_OFFSET)[0]["title"] == "Nothing to undo"
    found = plan(db, "task:mail", "#w")
    journal.apply(db, list(found.ops), found.title, NOW)
    row = present.rows("un", db, NOW, NO_OFFSET)[0]
    assert (row["title"], row["variables"]) == ("Undo: Add #w · 1 block", {"action": "undo"})


@pytest.fixture
def run(db, capsys, mocker):
    mocker.patch("tally.bar.poke")

    def go(*argv, **env):
        code = cli.run(list(argv), env, now=NOW, db=db)
        return code, capsys.readouterr().out

    return go


def test_cli_edit_apply_undo(run, db, sample):
    _code, out = run("edit", "#w", target="task:parser #lexer")
    assert json.loads(out)["items"][0]["title"] == "Add #w · 2 blocks", "the edit list"
    _code, out = run("act", "apply", "#w", target="task:parser #lexer")
    assert out.strip() == "Add #w · 2 blocks", "applied"
    assert store.blocks(store.transitions(db))[-1].line == "parser #lexer #w", "and stored"
    _code, out = run("act", "undo")
    assert out.strip() == "Undone: Add #w · 2 blocks", "undone"


def test_cli_apply_refuses_without_writing(run, db, sample):
    _code, out = run("act", "apply", "start 9:00", target=f"block:{PARSER}")
    assert out.strip() == "09:00 is outside 10:10–12:50" and journal.last(db) is None, (
        "an impossible edit says so and leaves no batch"
    )


def test_apply_with_the_aliases_setting(run, db, logged):
    logged(9, 0, "parser #work")
    _code, out = run("act", "apply", "#w", target="task:parser #work", tag_aliases="w=work")
    assert out.strip() == "Nothing to change", "the setting's aliases apply"


def test_retimed_blocks_read_as_backfilled_when_moved_far_back(db, sample):
    found = plan(db, f"block:{PARSER}", "start 10:30")
    journal.apply(db, list(found.ops), found.title, NOW)
    moved = next(b for b in store.blocks(store.transitions(db)) if b.id == PARSER)
    assert moved.start == datetime(2026, 10, 20, 10, 30) and moved.backfilled, (
        "an earlier start than when it was logged is honest about it"
    )
