"""Tests for the Antigravity (agy CLI + IDE) plugin installer.

Antigravity hooks load from a plugin, not from project files: we write a local
plugin folder (plugin.json + hooks.json), mirror it under ~/.clawd-tank and run
`agy plugin install <dir>`. Uninstall runs `agy plugin uninstall margarita-tank`
and removes our mirror. Tests redirect every path to tmp_path and replace the
agy runner, so the real ~/.gemini and the real agy are never touched.
"""

import json
import re

import pytest

from clawd_tank_menubar import hooks

NOTIFY_PY = r"C:\Users\Matt\.clawd-tank\clawd-tank-notify.py"
PYTHON = r"C:\Python311\python.exe"
TRAY_EXE = r"C:\Users\Matt\AppData\Local\Programs\MargaritaTank\MargaritaTank.exe"
WRAPPER = r"C:\Users\Matt\.clawd-tank\clawd-tank-antigravity.cmd"


# --- the hook command string --------------------------------------------------
#
# agy's runner wraps and quotes commands badly on Windows (it produced
# `node "C:\...\"C:\...\hook.js""` for a quoted path in a plugin command), so the
# command string must never contain double quotes or an unescaped space there.

def test_windows_command_for_a_dev_install_is_unquoted_and_names_the_event():
    cmd = hooks.build_antigravity_hook_command(
        "win32", False, PYTHON, NOTIFY_PY, WRAPPER, "PreToolUse")
    assert cmd == f"{PYTHON} {NOTIFY_PY} antigravity PreToolUse"


def test_windows_command_for_a_frozen_install_uses_the_notify_exe():
    cmd = hooks.build_antigravity_hook_command(
        "win32", True, TRAY_EXE, NOTIFY_PY, WRAPPER, "Stop")
    assert cmd == (r"C:\Users\Matt\AppData\Local\Programs\MargaritaTank"
                   r"\margarita-notify.exe antigravity Stop")


def test_windows_command_swaps_pythonw_for_the_console_interpreter():
    cmd = hooks.build_antigravity_hook_command(
        "win32", False, r"C:\Python311\pythonw.exe", NOTIFY_PY, WRAPPER, "Stop")
    assert cmd.startswith(r"C:\Python311\python.exe ")


def test_windows_command_uses_a_space_free_wrapper_when_paths_have_spaces():
    cmd = hooks.build_antigravity_hook_command(
        "win32", False, r"C:\Program Files\Python311\python.exe",
        r"C:\Users\Ana Maria\.clawd-tank\clawd-tank-notify.py", WRAPPER, "PostToolUse")
    assert cmd == f"{WRAPPER} PostToolUse"


def test_windows_command_refuses_when_even_the_wrapper_path_has_spaces():
    with pytest.raises(ValueError):
        hooks.build_antigravity_hook_command(
            "win32", False, r"C:\Program Files\Python311\python.exe",
            r"C:\Users\Ana Maria\.clawd-tank\notify.py",
            r"C:\Users\Ana Maria\.clawd-tank\clawd-tank-antigravity.cmd", "Stop")


@pytest.mark.parametrize("event", ["PreToolUse", "PostToolUse", "PreInvocation", "Stop"])
@pytest.mark.parametrize("case", ["dev", "frozen", "spaces"])
def test_windows_commands_never_contain_quotes_or_loose_spaces(case, event):
    if case == "dev":
        args = (False, PYTHON, NOTIFY_PY)
    elif case == "frozen":
        args = (True, TRAY_EXE, NOTIFY_PY)
    else:
        args = (False, r"C:\Program Files\Py\python.exe", r"C:\A B\notify.py")
    cmd = hooks.build_antigravity_hook_command("win32", *args, WRAPPER, event)
    assert '"' not in cmd and "'" not in cmd
    # Every space separates a whole path/argument: the executable and the
    # script path themselves contain none.
    program = cmd.split(" antigravity")[0] if " antigravity" in cmd else cmd.split(" " + event)[0]
    assert all(" " not in part for part in re.split(r"\s+", program.strip()))
    assert cmd.endswith(event)
    assert ";" not in cmd  # cmd.exe would hand "event;" to the program


def test_posix_command_runs_the_script_directly_and_always_exits_zero():
    cmd = hooks.build_antigravity_hook_command(
        "darwin", False, "/usr/bin/python3", "/Users/a/.clawd-tank/clawd-tank-notify",
        "/unused", "PreToolUse")
    assert cmd == "/Users/a/.clawd-tank/clawd-tank-notify antigravity PreToolUse; exit 0"


def test_posix_command_shell_quotes_a_path_with_spaces():
    cmd = hooks.build_antigravity_hook_command(
        "linux", False, "/usr/bin/python3", "/home/a b/.clawd-tank/clawd-tank-notify",
        "/unused", "Stop")
    assert cmd == "'/home/a b/.clawd-tank/clawd-tank-notify' antigravity Stop; exit 0"


# --- the .cmd wrapper ---------------------------------------------------------

def test_wrapper_script_runs_the_interpreter_with_the_event_and_exits_zero():
    text = hooks.antigravity_wrapper_script(False, r"C:\Program Files\Py\pythonw.exe",
                                            r"C:\A B\notify.py")
    lines = text.split("\r\n")
    assert lines[0] == "@echo off"
    assert r'"C:\Program Files\Py\python.exe" "C:\A B\notify.py" antigravity %1' in lines
    assert lines[-2:] == ["exit /b 0", ""]


def test_wrapper_script_for_a_frozen_build_runs_the_notify_exe():
    text = hooks.antigravity_wrapper_script(
        True, r"C:\Users\Ana Maria\AppData\Local\Programs\MargaritaTank\MargaritaTank.exe",
        NOTIFY_PY)
    assert (r'"C:\Users\Ana Maria\AppData\Local\Programs\MargaritaTank'
            r'\margarita-notify.exe" antigravity %1') in text.split("\r\n")


# --- plugin files -------------------------------------------------------------

def _commands(prefix="run"):
    return {event: f"{prefix} {event}" for event, _ in hooks.ANTIGRAVITY_EVENTS}


def test_hooks_json_follows_the_plugin_schema():
    cmds = _commands()
    data = hooks.build_antigravity_hooks_json(cmds)
    assert list(data) == ["margarita-tank"]
    body = data["margarita-tank"]
    assert body["enabled"] is True

    def entry(event):
        return {"type": "command", "command": cmds[event], "timeout": 10}

    assert body["PreToolUse"] == [{"matcher": "*", "hooks": [entry("PreToolUse")]}]
    assert body["PostToolUse"] == [{"matcher": "*", "hooks": [entry("PostToolUse")]}]
    assert body["PreInvocation"] == [entry("PreInvocation")]
    assert body["Stop"] == [entry("Stop")]
    assert set(body) == {"enabled", "PreToolUse", "PostToolUse", "PreInvocation", "Stop"}


def test_plugin_json_has_name_and_version():
    assert hooks.build_antigravity_plugin_json("1.2.3") == {
        "name": "margarita-tank", "version": "1.2.3",
    }


# --- plugin version -----------------------------------------------------------

@pytest.mark.parametrize("raw,expected", [
    ("v1.2.3", "1.2.3"),
    ("v1.2.3-dirty", "1.2.3"),
    ("1.10.0", "1.10.0"),
    ("opencode-product-pr1+514@ae8e065-dirty", "0.0.0"),
    ("", "0.0.0"),
])
def test_plugin_version_is_a_stable_semver(raw, expected):
    assert hooks.antigravity_plugin_version(raw) == expected


# --- finding and running agy --------------------------------------------------

def test_find_agy_uses_the_path_lookup(monkeypatch):
    monkeypatch.setattr(hooks.shutil, "which", lambda name: "/opt/agy" if name == "agy" else None)
    assert hooks._find_agy() == "/opt/agy"


def test_find_agy_returns_none_when_agy_is_not_installed(monkeypatch, tmp_path):
    monkeypatch.setattr(hooks.shutil, "which", lambda name: None)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))  # no agy/bin/agy.exe in it
    assert hooks._find_agy() is None


class _Done:
    def __init__(self, returncode):
        self.returncode = returncode
        self.stdout = ""
        self.stderr = ""


def test_run_agy_reports_success_by_exit_code(monkeypatch):
    seen = {}

    def fake_run(argv, **kwargs):
        seen["argv"], seen["kwargs"] = argv, kwargs
        return _Done(0)

    monkeypatch.setattr(hooks.subprocess, "run", fake_run)
    assert hooks._run_agy(["agy", "plugin", "install", "/d"]) is True
    assert seen["argv"] == ["agy", "plugin", "install", "/d"]
    assert seen["kwargs"].get("shell", False) is False
    assert seen["kwargs"]["timeout"] == hooks.AGY_COMMAND_TIMEOUT_SECONDS


def test_run_agy_is_false_on_a_nonzero_exit(monkeypatch):
    monkeypatch.setattr(hooks.subprocess, "run", lambda *a, **k: _Done(1))
    assert hooks._run_agy(["agy", "plugin", "install", "/d"]) is False


@pytest.mark.parametrize("exc", [
    FileNotFoundError("no agy"), PermissionError("denied"),
    hooks.subprocess.TimeoutExpired("agy", 60),
])
def test_run_agy_never_raises(monkeypatch, exc):
    def boom(*a, **k):
        raise exc

    monkeypatch.setattr(hooks.subprocess, "run", boom)
    assert hooks._run_agy(["agy", "plugin", "install", "/d"]) is False


# --- install / uninstall ------------------------------------------------------

@pytest.fixture
def agy(tmp_path, monkeypatch):
    clawd = tmp_path / "clawd"
    plugin_dir = clawd / "antigravity-plugin" / "margarita-tank"
    wrapper = clawd / "clawd-tank-antigravity.cmd"
    monkeypatch.setattr(hooks, "ANTIGRAVITY_PLUGIN_DIR", plugin_dir)
    monkeypatch.setattr(hooks, "ANTIGRAVITY_WRAPPER_PATH", wrapper)
    monkeypatch.setattr(hooks, "get_version", lambda: "v1.2.3")
    state = {"calls": [], "ok": True, "found": "agy-bin"}
    monkeypatch.setattr(hooks, "_find_agy", lambda: state["found"])

    def fake_run(argv):
        state["calls"].append(argv)
        return state["ok"]

    monkeypatch.setattr(hooks, "_run_agy", fake_run)
    state.update(plugin_dir=plugin_dir, wrapper=wrapper, clawd=clawd)
    return state


def _read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_install_without_agy_does_nothing_and_does_not_crash(agy):
    agy["found"] = None
    assert hooks.install_antigravity_hooks() is False
    assert not agy["plugin_dir"].exists()
    assert agy["calls"] == []
    assert hooks.are_antigravity_hooks_installed() is False


def test_install_writes_the_plugin_and_registers_it_with_agy(agy):
    assert hooks.install_antigravity_hooks() is True
    plugin_dir = agy["plugin_dir"]
    assert _read(plugin_dir / "plugin.json") == {"name": "margarita-tank", "version": "1.2.3"}
    body = _read(plugin_dir / "hooks.json")["margarita-tank"]
    assert body["enabled"] is True
    for event in ("PreInvocation", "PreToolUse", "PostToolUse", "Stop"):
        commands = json.dumps(body[event])
        assert f"antigravity {event}" in commands
    assert agy["calls"] == [["agy-bin", "plugin", "install", str(plugin_dir)]]
    assert hooks.are_antigravity_hooks_installed() is True


def test_install_is_idempotent_and_does_not_rerun_agy(agy):
    assert hooks.install_antigravity_hooks() is True
    first = (agy["plugin_dir"] / "hooks.json").read_bytes()
    assert hooks.install_antigravity_hooks() is True
    assert (agy["plugin_dir"] / "hooks.json").read_bytes() == first
    assert len(agy["calls"]) == 1


def test_install_refreshes_an_outdated_plugin_and_reregisters_it(agy):
    hooks.install_antigravity_hooks()
    (agy["plugin_dir"] / "hooks.json").write_text("{}", encoding="utf-8")
    assert hooks.are_antigravity_hooks_installed() is False
    assert hooks.install_antigravity_hooks() is True
    assert hooks.are_antigravity_hooks_installed() is True
    assert len(agy["calls"]) == 2


def test_install_leaves_no_mirror_behind_when_agy_refuses(agy):
    agy["ok"] = False
    assert hooks.install_antigravity_hooks() is False
    assert not agy["plugin_dir"].exists()
    assert hooks.are_antigravity_hooks_installed() is False


def test_install_refuses_when_no_safe_command_exists(agy, monkeypatch):
    def impossible(*args, **kwargs):
        raise ValueError("spaces everywhere")

    monkeypatch.setattr(hooks, "_antigravity_plan", impossible)
    assert hooks.install_antigravity_hooks() is False
    assert agy["calls"] == []
    assert not agy["plugin_dir"].exists()


def test_install_writes_the_wrapper_only_when_the_plan_needs_one(agy, monkeypatch):
    commands = {e: f"{agy['wrapper']} {e}" for e, _ in hooks.ANTIGRAVITY_EVENTS}
    monkeypatch.setattr(hooks, "_antigravity_plan", lambda *a, **k: (commands, "@echo off\r\n"))
    assert hooks.install_antigravity_hooks() is True
    assert agy["wrapper"].read_bytes() == b"@echo off\r\n"
    hooks.uninstall_antigravity_hooks()
    assert not agy["wrapper"].exists()


def test_install_without_a_wrapper_leaves_no_wrapper(agy):
    hooks.install_antigravity_hooks()
    assert not agy["wrapper"].exists()


def test_plan_uses_a_wrapper_only_for_paths_with_spaces():
    commands, wrapper = hooks._antigravity_plan(
        "win32", False, PYTHON, NOTIFY_PY, WRAPPER)
    assert wrapper is None
    assert commands["Stop"] == f"{PYTHON} {NOTIFY_PY} antigravity Stop"
    commands, wrapper = hooks._antigravity_plan(
        "win32", False, r"C:\Program Files\Py\python.exe", NOTIFY_PY, WRAPPER)
    assert commands["Stop"] == f"{WRAPPER} Stop"
    assert wrapper == hooks.antigravity_wrapper_script(
        False, r"C:\Program Files\Py\python.exe", NOTIFY_PY)


def test_uninstall_unregisters_with_agy_and_removes_our_mirror(agy):
    hooks.install_antigravity_hooks()
    agy["calls"].clear()
    assert hooks.uninstall_antigravity_hooks() is True
    assert agy["calls"] == [["agy-bin", "plugin", "uninstall", "margarita-tank"]]
    assert not agy["plugin_dir"].exists()
    assert hooks.are_antigravity_hooks_installed() is False


def test_uninstall_is_a_noop_when_we_never_installed(agy):
    assert hooks.uninstall_antigravity_hooks() is True
    assert agy["calls"] == []


def test_uninstall_is_idempotent(agy):
    hooks.install_antigravity_hooks()
    assert hooks.uninstall_antigravity_hooks() is True
    agy["calls"].clear()
    assert hooks.uninstall_antigravity_hooks() is True
    assert agy["calls"] == []


def test_uninstall_without_agy_still_removes_the_mirror(agy):
    hooks.install_antigravity_hooks()
    agy["found"] = None
    agy["calls"].clear()
    assert hooks.uninstall_antigravity_hooks() is True
    assert agy["calls"] == []
    assert not agy["plugin_dir"].exists()


def test_uninstall_reports_failure_but_still_clears_our_mirror(agy):
    hooks.install_antigravity_hooks()
    agy["ok"] = False
    assert hooks.uninstall_antigravity_hooks() is False
    assert not agy["plugin_dir"].exists()


def test_we_only_ever_touch_our_own_plugin(agy):
    other = agy["clawd"] / "antigravity-plugin" / "googlecloudtools.datacloud_telemetry"
    other.mkdir(parents=True)
    (other / "plugin.json").write_text('{"name":"googlecloudtools.datacloud_telemetry"}')
    unrelated = agy["clawd"] / "keep.txt"
    unrelated.write_text("keep")
    hooks.install_antigravity_hooks()
    hooks.uninstall_antigravity_hooks()
    assert (other / "plugin.json").read_text().startswith('{"name"')
    assert unrelated.read_text() == "keep"
    for argv in agy["calls"]:
        assert "googlecloudtools.datacloud_telemetry" not in " ".join(argv)
        assert argv[1] == "plugin" and argv[2] in ("install", "uninstall")
        assert argv[3] in ("margarita-tank", str(agy["plugin_dir"]))


# --- the Windows uninstaller path (`MargaritaTank.exe --uninstall-hooks`) -------

@pytest.fixture
def uninstall_env(tmp_path, monkeypatch):
    from clawd_tank_menubar import __main__ as entry

    monkeypatch.setattr(entry, "LOG_DIR", tmp_path / "logs")
    calls = []
    results = {"claude": True, "codex": True, "kiro": True, "antigravity": True}

    def fake(name):
        def run():
            calls.append(name)
            return results[name]
        return run

    monkeypatch.setattr(hooks, "uninstall_hooks", fake("claude"))
    monkeypatch.setattr(hooks, "uninstall_codex_hooks", fake("codex"))
    monkeypatch.setattr(hooks, "uninstall_tracked_kiro_hooks", fake("kiro"))
    monkeypatch.setattr(hooks, "uninstall_antigravity_hooks", fake("antigravity"))
    # Other agents' uninstallers must never run for real from these tests.
    monkeypatch.setattr(hooks, "uninstall_opencode_hooks", lambda: True)
    return entry, calls, results


def test_uninstall_hooks_flag_also_removes_the_antigravity_plugin(uninstall_env):
    entry, calls, _ = uninstall_env
    assert entry._uninstall_hooks() == 0
    assert "antigravity" in calls


def test_uninstall_hooks_flag_fails_when_the_antigravity_plugin_stays(uninstall_env):
    entry, calls, results = uninstall_env
    results["antigravity"] = False
    assert entry._uninstall_hooks() == 1


def test_uninstall_hooks_flag_still_removes_the_rest_when_antigravity_fails(uninstall_env):
    entry, calls, results = uninstall_env
    results["antigravity"] = False
    entry._uninstall_hooks()
    assert {"claude", "codex", "kiro"} <= set(calls)


# --- tray controller wiring (same pattern as the OpenCode toggle) --------------

@pytest.fixture
def tray(tmp_path, monkeypatch):
    from tests.test_controller import make_controller

    state = {"installed": False, "install_ok": True, "uninstall_ok": True,
             "calls": []}
    monkeypatch.setattr(hooks, "are_antigravity_hooks_installed",
                        lambda: state["installed"])
    monkeypatch.setattr(hooks, "install_notify_script",
                        lambda: state["calls"].append("notify"))

    def install():
        state["calls"].append("install")
        if state["install_ok"]:
            state["installed"] = True
        return state["install_ok"]

    def uninstall():
        state["calls"].append("uninstall")
        if state["uninstall_ok"]:
            state["installed"] = False
        return state["uninstall_ok"]

    monkeypatch.setattr(hooks, "install_antigravity_hooks", install)
    monkeypatch.setattr(hooks, "uninstall_antigravity_hooks", uninstall)

    def build():
        controller, view = make_controller(tmp_path / "preferences.json")
        return controller, view

    state["build"] = build
    return state


def test_tray_state_defaults_antigravity_to_not_installed():
    from clawd_tank_menubar.controller import TrayState

    fields = TrayState.__dataclass_fields__
    assert fields["antigravity_hooks_installed"].default is False


def test_controller_reads_the_installed_state_at_startup(tray):
    tray["installed"] = True
    controller, _ = tray["build"]()
    assert controller.antigravity_hooks_installed is True


def test_toggle_installs_when_missing_and_reports_it(tray):
    controller, view = tray["build"]()
    controller.toggle_antigravity_hooks()
    assert tray["calls"] == ["notify", "install"]
    assert controller.antigravity_hooks_installed is True
    assert view.renders[-1].antigravity_hooks_installed is True
    assert [title for title, _ in view.alerts] == ["Antigravity Plugin Installed"]


def test_toggle_reports_an_install_failure_without_claiming_success(tray):
    tray["install_ok"] = False
    controller, view = tray["build"]()
    controller.toggle_antigravity_hooks()
    assert controller.antigravity_hooks_installed is False
    assert view.renders[-1].antigravity_hooks_installed is False
    assert [title for title, _ in view.alerts] == ["Antigravity Plugin Not Installed"]


def test_toggle_uninstalls_when_present(tray):
    tray["installed"] = True
    controller, view = tray["build"]()
    controller.toggle_antigravity_hooks()
    assert tray["calls"] == ["uninstall"]
    assert controller.antigravity_hooks_installed is False
    assert view.renders[-1].antigravity_hooks_installed is False
    assert [title for title, _ in view.alerts] == ["Antigravity Plugin Removed"]


def test_toggle_reports_an_uninstall_failure(tray):
    tray["installed"] = True
    tray["uninstall_ok"] = False
    controller, view = tray["build"]()
    controller.toggle_antigravity_hooks()
    assert [title for title, _ in view.alerts] == ["Antigravity Plugin Not Removed"]
