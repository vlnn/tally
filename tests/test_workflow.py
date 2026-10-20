import plistlib
import re
from pathlib import Path

import pytest

from tally import cli, present

WORKFLOW = Path(__file__).parent.parent / "workflow"
SOURCE = Path(__file__).parent.parent / "src" / "tally"
ROUTED = {
    "alfred_workflow_data",
    "alfred_workflow_cache",
    "alfred_preferences",
    "alfred_workflow_uid",
    "action",
    "at",
    "target",
}


@pytest.fixture(scope="module")
def plist():
    with open(WORKFLOW / "info.plist", "rb") as handle:
        return plistlib.load(handle)


@pytest.fixture(scope="module")
def objects(plist):
    return {obj["uid"]: obj for obj in plist["objects"]}


def scripts(objects):
    return [obj["config"].get("script", "") for obj in objects.values()]


def test_every_script_calls_a_known_command(objects):
    called = {
        match.group(1)
        for script in scripts(objects)
        for match in re.finditer(r"-m tally (\S+)", script)
    }
    assert called <= set(cli.COMMANDS), "the canvas only calls commands the package has"


def test_every_action_the_rows_emit_is_routed(objects):
    emitted = {"start", "keep", "stop", "view", "bar", "nudges", "edit", "apply", "undo"}
    branches = {
        cond["matchstring"]
        for obj in objects.values()
        if obj["type"] == "alfred.workflow.utility.conditional"
        for cond in obj["config"]["conditions"]
    }
    assert emitted - branches <= set(cli.ACTIONS), (
        "an action is either a conditional branch or something act dispatches"
    )
    assert branches <= emitted, "no conditional waits for an action nobody emits"


def test_conditionals_match_the_action_exactly(objects):
    for obj in objects.values():
        if obj["type"] == "alfred.workflow.utility.conditional":
            for cond in obj["config"]["conditions"]:
                assert (cond["inputstring"], cond["matchmode"]) == ("{var:action}", 0), (
                    "the one number written from memory: 0 is 'is equal to'"
                )


def test_every_connection_lands_on_an_object(plist, objects):
    for source, links in plist["connections"].items():
        assert source in objects, f"{source} connects from nowhere"
        for link in links:
            assert link["destinationuid"] in objects, f"{source} connects to nothing"


def test_every_source_object_has_a_way_out(plist, objects):
    needs_out = {
        "alfred.workflow.trigger.hotkey",
        "alfred.workflow.input.scriptfilter",
        "alfred.workflow.utility.conditional",
        "alfred.workflow.userinterface.text",
        "alfred.workflow.action.script",
    }
    for uid, obj in objects.items():
        if obj["type"] in needs_out:
            assert plist["connections"].get(uid), f"{obj['type']} {uid} leads nowhere"


def test_hotkeys_open_t_or_stop(plist, objects):
    hotkeys = [u for u, o in objects.items() if o["type"] == "alfred.workflow.trigger.hotkey"]
    targets = [objects[plist["connections"][h][0]["destinationuid"]] for h in hotkeys]
    kinds = sorted(
        target["config"].get("keyword") or target["config"]["script"].strip() for target in targets
    )
    assert kinds == ["/usr/bin/python3 -m tally act stop", "t", "tw"], (
        "HYPER+] opens t, HYPER+[ opens tw, the third stops without opening Alfred"
    )


def test_the_two_list_hotkeys_are_the_brackets(plist, objects):
    keys = {
        objects[plist["connections"][uid][0]["destinationuid"]]["config"]["keyword"]: obj["config"][
            "hotstring"
        ]
        for uid, obj in objects.items()
        if obj["type"] == "alfred.workflow.trigger.hotkey" and obj["config"]["hotstring"]
    }
    assert keys == {"t": "]", "tw": "["}, "] for everything, [ for work"


def test_alt_return_from_the_filter_reaches_act(plist, objects):
    filters = [
        u
        for u, o in objects.items()
        if o["type"] == "alfred.workflow.input.scriptfilter" and o["config"]["keyword"]
    ]
    for uid in filters:
        modifiers = {link["modifiers"] for link in plist["connections"][uid]}
        assert modifiers == {0, 131072, 524288, 1048576, 262144}, (
            "↩, ⇧↩, ⌥↩, ⌘↩ and ⌃↩ pass through from both lists"
        )


def test_the_text_view_runs_the_shipped_script(objects):
    views = [o for o in objects.values() if o["type"] == "alfred.workflow.userinterface.text"]
    assert len(views) == 1 and (WORKFLOW / views[0]["config"]["inputfile"]).exists(), (
        "the Text View's script file is an asset in workflow/"
    )
    assert "tally view" in (WORKFLOW / views[0]["config"]["inputfile"]).read_text(), (
        "and it calls the view command"
    )


def test_configured_variables_are_the_ones_the_package_reads(plist):
    configured = {entry["variable"] for entry in plist["userconfigurationconfig"]}
    read = {
        match.group(1)
        for path in SOURCE.glob("*.py")
        for match in re.finditer(r'env\.get\("([a-z_]+)"', path.read_text())
    }
    assert read - ROUTED == configured, "every setting is read and every read has a setting"


def test_rows_never_emit_a_modifier_the_canvas_does_not_route():
    assert set(present.NO_MODS) == {"shift", "alt", "cmd", "ctrl"}, "the four modifier keys"


def test_the_edit_list_is_reached_from_the_conditional(plist, objects):
    edit = [
        u
        for u, o in objects.items()
        if o["type"] == "alfred.workflow.input.scriptfilter"
        and "tally edit" in o["config"]["script"]
    ]
    assert len(edit) == 1 and objects[edit[0]]["config"]["keyword"] == "", "a keywordless list"
    sources = [
        s
        for s, links in plist["connections"].items()
        for link in links
        if link["destinationuid"] == edit[0]
    ]
    assert [objects[s]["type"] for s in sources] == ["alfred.workflow.utility.conditional"], (
        "only the action conditional opens it"
    )
