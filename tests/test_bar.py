from datetime import timedelta
from pathlib import Path

import pytest

from conftest import NO_OFFSET, NOW
from tally import bar, cli, gaps, nudge, present


def test_status_is_the_running_task_and_its_time(db, sample):
    assert bar.status(db, NOW) == "parser #lexer 0:55", "what the menu bar shows"


def test_status_when_idle(db, logged):
    logged(9, 0, "mail")
    logged(9, 30, "")
    assert bar.status(db, NOW) == bar.IDLE, "something clickable, nothing to report"


def test_long_lines_are_shortened_for_the_menu_bar(db, logged):
    logged(14, 0, "a task whose name goes on and on")
    assert bar.status(db, NOW) == "a task whose name… 1:00", "the bar is narrow, the time stays"


def test_menu_lists_stop_recent_and_today(db, sample):
    lines = bar.menu(db, NOW, NO_OFFSET, "/p/tally.30s.sh").splitlines()
    assert lines[0] == "parser #lexer 0:55", "the first line is the menu bar"
    assert lines[2] == (
        'Stop parser #lexer · 0:55 | bash="/p/tally.30s.sh" param1="stop" terminal=false'
        " refresh=true"
    ), "stop goes through the plugin itself"
    assert lines[4] == (
        "Resume review pr 212 · today 0:25 · last 13:40–14:05"
        ' | bash="/p/tally.30s.sh" param1="start" param2="review pr 212" terminal=false'
        " refresh=true"
    ), "a recent task resumes with its line as one quoted parameter"
    assert lines[-2].startswith("Today · 4:40 logged | ") and 'param2="@today"' in lines[-2], (
        "today opens the view in Alfred"
    )
    assert lines[-1].startswith("Open Tally | ") and 'param1="open" param2=""' in lines[-1], (
        "and the last line opens bare t"
    )


def test_menu_without_a_running_task_has_no_stop(db, logged):
    logged(9, 0, "mail")
    logged(9, 30, "")
    lines = bar.menu(db, NOW, NO_OFFSET, "/p/tally.30s.sh").splitlines()
    assert lines[0] == bar.IDLE and not any(line.startswith("Stop") for line in lines), "idle"


def test_quoted_escapes_quotes():
    assert bar.quoted('say "hi"') == '"say \\"hi\\""', "a quote inside a parameter survives"


def test_script_bakes_in_the_bundle_and_the_settings():
    env = {
        "alfred_preferences": "/prefs",
        "alfred_workflow_uid": "user.workflow.X",
        "alfred_workflow_data": "/data",
        "day_starts": "04:00",
    }
    text = bar.script(env)
    assert 'cd "/prefs/workflows/user.workflow.X"' in text, "the plugin runs from the bundle"
    assert 'export alfred_workflow_data="/data"' in text and 'export day_starts="04:00"' in text, (
        "the plugin sees the same database and day boundary as Alfred"
    )
    assert "export db_path" not in text, "unset settings are not exported"
    assert text.startswith("#!/bin/bash\n"), "executable by SwiftBar"


def test_plugin_folder_from_the_setting(tmp_path):
    env = {"swiftbar_plugins": str(tmp_path)}
    assert bar.plugin_path(env) == tmp_path / "tally.30s.sh", "the setting wins"


def test_plugin_folder_from_swiftbar(mocker):
    run = mocker.patch("subprocess.run")
    run.return_value.returncode = 0
    run.return_value.stdout = "~/Library/Application Support/SwiftBar/Plugins\n"
    found = bar.swiftbar_folder({})
    assert found == Path("~/Library/Application Support/SwiftBar/Plugins").expanduser(), (
        "SwiftBar's own default is read"
    )
    run.return_value.returncode = 1
    assert bar.swiftbar_folder({}) is None, "no SwiftBar, no folder"


def test_install_writes_the_plugin_and_refreshes(tmp_path, mocker):
    run = mocker.patch("subprocess.run")
    env = {"swiftbar_plugins": str(tmp_path / "plugins"), "alfred_workflow_data": "/data"}
    path = bar.install(env)
    assert path == tmp_path / "plugins" / "tally.30s.sh" and path.stat().st_mode & 0o111, (
        "written where SwiftBar looks, executable"
    )
    run.assert_called_once_with(
        ["open", "-g", "swiftbar://refreshplugin?name=tally"], capture_output=True, check=False
    )


def test_bar_row_offers_install_or_reinstall(tmp_path):
    missing = present.bar_row(tmp_path / "tally.30s.sh")
    assert missing["title"] == "Install the SwiftBar plugin" and missing["variables"] == {
        "action": "bar"
    }, "↩ installs"
    (tmp_path / "tally.30s.sh").write_text("")
    assert present.bar_row(tmp_path / "tally.30s.sh")["title"] == "Reinstall the SwiftBar plugin"
    assert present.bar_row(None)["valid"] is False, "without SwiftBar the row only explains"


@pytest.fixture
def run(db, capsys):
    def go(*argv, **env):
        code = cli.run(list(argv), env, now=NOW, db=db)
        return code, capsys.readouterr().out

    return go


def test_t_bar_is_the_install_row(run, tmp_path):
    import json

    _code, out = run("filter", "bar", swiftbar_plugins=str(tmp_path))
    assert json.loads(out)["items"][0]["title"] == "Install the SwiftBar plugin", "t bar"


def test_act_bar_installs(run, tmp_path, mocker):
    mocker.patch("subprocess.run")
    _code, out = run("act", "bar", swiftbar_plugins=str(tmp_path))
    assert out.strip() == f"SwiftBar plugin installed · {tmp_path / 'tally.30s.sh'}", "the line"


def test_act_bar_without_swiftbar(run, mocker):
    mocker.patch("subprocess.run").return_value.returncode = 1
    _code, out = run("act", "bar")
    assert out.strip() == "Not installed: SwiftBar's plugin folder not found", "says why"


def test_bar_prints_the_menu(run, sample):
    _code, out = run("bar", "/p/tally.30s.sh")
    assert out.startswith("parser #lexer 0:55\n---\n"), "the plugin's whole output"


def test_start_pokes_swiftbar_only_when_the_plugin_is_installed(run, tmp_path, mocker):
    run_ = mocker.patch("subprocess.run")
    run("act", "start", "mail", swiftbar_plugins=str(tmp_path))
    run_.assert_not_called()
    (tmp_path / "tally.30s.sh").write_text("")
    run("act", "stop", swiftbar_plugins=str(tmp_path))
    run_.assert_called_once_with(
        ["open", "-g", "swiftbar://refreshplugin?name=tally"], capture_output=True, check=False
    )


def test_start_and_stop_work_without_swiftbar(run, db, mocker):
    defaults = mocker.patch("subprocess.run")
    defaults.return_value.returncode = 1
    defaults.return_value.stdout = ""
    _code, started = run("act", "start", "mail")
    _code, stopped = run("act", "stop")
    assert (started.strip(), stopped.strip()) == ("mail from 15:00", "mail · 0:00"), (
        "without SwiftBar the actions print exactly what they print with it"
    )
    assert [call.args[0][0] for call in defaults.call_args_list] == ["defaults", "defaults"], (
        "they only ask whether SwiftBar is there, and never try to refresh it"
    )


def test_start_works_where_there_is_no_macos(run, db, mocker):
    mocker.patch("subprocess.run", side_effect=FileNotFoundError("defaults"))
    _code, out = run("act", "start", "mail")
    assert out.strip() == "mail from 15:00", "no defaults, no open: still a start"


def test_a_stale_plugin_with_swiftbar_gone_refreshes_quietly(run, tmp_path, mocker):
    (tmp_path / "tally.30s.sh").write_text("")
    opened = mocker.patch("subprocess.run")
    opened.return_value.returncode = 1
    _code, out = run("act", "start", "mail", swiftbar_plugins=str(tmp_path))
    assert out.strip() == "mail from 15:00", "a failed refresh adds nothing to the notification"
    assert opened.call_args.kwargs["capture_output"] is True, "open's complaint is swallowed"


def test_the_filter_never_asks_for_swiftbar_unless_bar_is_typed(run, sample, mocker):
    spawned = mocker.patch("subprocess.run")
    for text in ("", "par", "mail 14:30", "@week"):
        run("filter", text)
    spawned.assert_not_called()


def test_the_plugin_keeps_swiftbars_own_menu():
    text = bar.script({})
    assert "hideSwiftBar" not in text, "SwiftBar's submenu (preferences, refresh, quit) stays"
    assert "<swiftbar.hideAbout>true</swiftbar.hideAbout>" in text, "the rest stays tidy"


def gap_of(minutes):
    return gaps.Gap(NOW - timedelta(minutes=minutes), NOW)


@pytest.mark.parametrize(
    "minutes, expected",
    [
        (10, ""),
        (15, "15m unclaimed | color=#8E8E93"),
        (30, "30m unclaimed | color=#FFCC00"),
        (45, "45m unclaimed | color=#FF9500"),
        (95, "95m unclaimed | color=#FF3B30"),
    ],
)
def test_unclaimed_counter_climbs_the_ladder(minutes, expected):
    assert bar.unclaimed(gap_of(minutes), gaps.DEFAULT_LADDER) == expected, (
        "grey, yellow, orange, red; nothing under the first step"
    )


def test_status_counts_unclaimed_time_when_idle(db, logged):
    logged(9, 0, "mail")
    logged(14, 30, "")
    assert bar.status(db, NOW, gap_of(30)) == "30m unclaimed | color=#FFCC00", "the counter"


def test_status_shows_the_running_task_over_any_gap(db, sample):
    assert bar.status(db, NOW, gap_of(30)) == "parser #lexer 0:55", "running time is claimed"


def test_menu_offers_to_claim(db, logged):
    logged(9, 0, "mail")
    logged(14, 30, "")
    lines = bar.menu(db, NOW, NO_OFFSET, "/p/tally.30s.sh", gap_of(30)).splitlines()
    assert lines[2].startswith("Claim 30 min unclaimed since 14:30 | "), "the claim opens t"
    assert 'param1="open" param2=""' in lines[2], "bare t, where the gap is the top row"


def never_away():
    return False


@pytest.mark.parametrize(
    "minutes, sounds, said",
    [
        (15, True, ""),
        (30, True, "chimed"),
        (30, False, ""),
        (45, True, "told"),
        (60, False, "told"),
    ],
)
def test_alert_on_reaching_a_step(db, mocker, minutes, sounds, said):
    chime, notify = mocker.patch.object(bar, "chime"), mocker.patch.object(bar, "notify")
    assert bar.alert(db, gap_of(minutes), gaps.DEFAULT_LADDER, sounds, never_away) == said, (
        "a chime at the second step, a notification at the third and fourth"
    )
    assert chime.called is (said == "chimed") and notify.called is (said == "told"), "and only it"


def test_alert_once_per_step(db, mocker):
    mocker.patch.object(bar, "chime")
    gap = gap_of(30)
    first = bar.alert(db, gap, gaps.DEFAULT_LADDER, True, never_away)
    again = bar.alert(
        db, gaps.Gap(gap.start, NOW + timedelta(minutes=1)), (15, 30, 45, 60), True, never_away
    )
    assert (first, again) == ("chimed", ""), "the plugin runs every 30 s; a step rings once"


def test_a_new_gap_starts_the_ladder_again(db, mocker):
    mocker.patch.object(bar, "chime")
    bar.alert(db, gap_of(30), gaps.DEFAULT_LADDER, True, never_away)
    later = gaps.Gap(NOW, NOW + timedelta(minutes=30))
    assert bar.alert(db, later, gaps.DEFAULT_LADDER, True, never_away) == "chimed", "fresh gap"


def test_the_notification_says_since_when_and_opens_t(db, mocker):
    notify = mocker.patch.object(bar, "notify")
    bar.alert(db, gap_of(45), gaps.DEFAULT_LADDER, True, never_away)
    notify.assert_called_once_with("45 min unclaimed since 14:15", bar.OPEN_T)


def test_away_means_quiet_but_counted(db, mocker):
    chime, notify = mocker.patch.object(bar, "chime"), mocker.patch.object(bar, "notify")
    assert bar.alert(db, gap_of(45), gaps.DEFAULT_LADDER, True, lambda: True) == "", "away"
    assert not chime.called and not notify.called, "no sound, no notification"
    assert bar.unclaimed(gap_of(45), gaps.DEFAULT_LADDER).startswith("45m"), "still counting"


def test_the_bar_command_climbs_the_ladder(run, logged, mocker):
    logged(9, 0, "mail")
    logged(14, 30, "")
    chime = mocker.patch.object(bar, "chime")
    mocker.patch.object(nudge, "user_idle", return_value=timedelta())
    _code, out = run("bar", "/p/tally.30s.sh")
    assert out.startswith("30m unclaimed | color=#FFCC00\n"), "the counter in the menu bar"
    chime.assert_called_once_with()


def test_the_bar_command_honours_the_settings(run, logged, mocker):
    logged(9, 0, "mail")
    logged(14, 30, "")
    chime = mocker.patch.object(bar, "chime")
    mocker.patch.object(nudge, "user_idle", return_value=timedelta())
    _code, out = run("bar", "/p/x", unclaimed_ladder="10,20,40,50", unclaimed_sounds="0")
    assert out.startswith("30m unclaimed | color=#FFCC00\n"), "30 min is the second of 10,20,40,50"
    chime.assert_not_called()
