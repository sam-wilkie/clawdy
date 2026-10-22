"""Codex subscription reads use an isolated fake JSON-RPC process."""
import io
import json
import subprocess
import threading
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest
from clawd_tank_daemon import plan_usage as usage

NOW = datetime(2026, 10, 16, tzinfo=timezone.utc)
RATES = {"rateLimitsByLimitId": {"codex": {
    "primary": {"usedPercent": 21, "windowDurationMins": 300, "resetsAt": 0},
    "secondary": {"usedPercent": 47, "windowDurationMins": 10080, "resetsAt": 0}}},
    "rateLimitResetCredits": {"availableCount": 2}}


@pytest.mark.parametrize("layout", ["override", "path", "release", "local", "vendor", "package"])
def test_lookup(tmp_path, layout):
    env = {"PATH": str(tmp_path / "path"), "CODEX_HOME": str(tmp_path / "cx"),
           "LOCALAPPDATA": str(tmp_path / "local"), "APPDATA": str(tmp_path / "roaming")}
    pkg = "roaming/npm/node_modules/@openai/codex"
    relative = {"override": "custom.exe", "path": "path/codex.exe",
                "release": "cx/packages/app-server-daemon/releases/10/bin/codex.exe",
                "local": "local/OpenAI/Codex/bin/10/codex.exe",
                "vendor": pkg + "/vendor/target/codex/codex.exe",
                "package": pkg + "/node_modules/@openai/codex-win/vendor/target/codex/codex.exe"}[layout]
    exe = tmp_path / relative
    exe.parent.mkdir(parents=True, exist_ok=True)
    exe.touch()
    if layout == "override":
        env["CLAWDY_CODEX_BIN"] = str(exe)
    assert usage.find_codex_exe(env=env, home=tmp_path, platform="win32") == str(exe)
    env["CLAWDY_CODEX_BIN"] = str(tmp_path / "missing.exe")
    assert usage.find_codex_exe(env=env, home=tmp_path, platform="win32") is None


@pytest.mark.parametrize("name", ["codex.cmd", "codex.bat", "codex.ps1", "relative.exe"])
def test_reject_shims_and_relative_override(tmp_path, name):
    (tmp_path / name).touch()
    env = {"PATH": str(tmp_path), "CLAWDY_CODEX_BIN": name if name == "relative.exe" else str(tmp_path / name)}
    assert usage.find_codex_exe(env=env, home=tmp_path, platform="win32") is None
    env.pop("CLAWDY_CODEX_BIN")
    assert usage.find_codex_exe(env=env, home=tmp_path, platform="win32") is None


class Child:
    def __init__(self, account="chatgpt", rates=RATES, bad=None, block=False):
        messages = [{"id": 90, "method": "token/refresh"}, {"id": 0, "result": {}},
                    {"id": 1, "result": {"account": {"type": account} if account else None}},
                    {"id": 2, "result": rates}]
        self.stdout = io.BytesIO(bad if bad is not None else b"".join(
            (json.dumps(m) + "\n").encode() for m in messages))
        self.stdin = io.BytesIO()
        self.killed = threading.Event()
        self.block, self.waited, self.sent = block, False, []
        if block:
            self.stdout.readline = lambda size: self.killed.wait(2) and b""
        close = self.stdin.close
        def record_close():
            self.sent = [json.loads(line) for line in self.stdin.getvalue().splitlines()]
            close()
        self.stdin.close = record_close

    def kill(self):
        self.killed.set()

    def wait(self, timeout=None):
        self.waited = True
        if self.block and not self.killed.is_set():
            raise subprocess.TimeoutExpired("fake", timeout)


def source(child, **kwargs):
    popen = Mock(return_value=child)
    return usage.CodexPlanSource(exe_finder=lambda: "C:/fake/codex.exe", popen=popen, **kwargs), popen


@pytest.mark.parametrize("legacy", [False, True])
def test_chatgpt_protocol_and_cadence(legacy):
    rates = {**RATES, "rateLimits": RATES["rateLimitsByLimitId"]["codex"]} if legacy else RATES
    if legacy:
        rates.pop("rateLimitsByLimitId")
    child = Child(rates=rates)
    reader, popen = source(child)
    result = reader.refresh(NOW)
    assert result == {"status": "ok", "billing": "plan", "plan": {"status": "ok", "limits": [
        {"id": "primary", "label": "5h window", "used_pct": 21, "window_min": 300,
         "resets_at": "1970-01-01T00:00:00+00:00"},
        {"id": "weekly", "label": "Weekly", "used_pct": 47, "window_min": 10080,
         "resets_at": "1970-01-01T00:00:00+00:00"}], "reset_credits": 2}}
    assert reader.refresh(NOW + timedelta(seconds=299)) == result
    popen.assert_called_once_with(["C:/fake/codex.exe", "app-server", "--listen", "stdio://"],
        shell=False, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        creationflags=subprocess.CREATE_NO_WINDOW if usage.sys.platform == "win32" else 0)
    methods = [m["method"] for m in child.sent if "method" in m]
    assert methods == ["initialize", "initialized", "account/read", "account/rateLimits/read"]
    assert next(m for m in child.sent if m.get("method") == "account/read")["params"] == {"refreshToken": False}
    assert next(m for m in child.sent if m.get("id") == 90)["error"]["code"] == -32601
    assert child.stdin.closed and child.stdout.closed and child.waited


@pytest.mark.parametrize("account,status", [("apiKey", None), (None, "signed_out")])
def test_account_modes(account, status):
    child = Child(account=account)
    result = source(child)[0].refresh(NOW)
    assert result == ({"status": "ok", "billing": "payg"} if status is None else
                      {"status": "ok", "billing": "plan", "plan": {"status": status}})
    assert "account/rateLimits/read" not in [m.get("method") for m in child.sent]
    assert child.stdin.closed and child.waited


@pytest.mark.parametrize("bad", [b"garbage\n", b"[]\n", b'{"id":0,"error":{"code":1}}\n',
                                 b'{"id":0}\n', b"x" * 65537, b""],
                         ids=["json", "array", "rpc", "missing-result", "oversize", "eof"])
def test_failure_cleanup_and_cached_error(bad):
    child = Child(bad=bad)
    reader, popen = source(child)
    for seconds in (0, 60):
        with pytest.raises(RuntimeError):
            reader.refresh(NOW + timedelta(seconds=seconds))
    assert popen.call_count == 1
    assert child.stdin.closed and child.stdout.closed and child.waited


@pytest.mark.parametrize("account", ["apiKey", "chatgpt"])
def test_timeout_preserves_previous_billing_and_plan(account):
    from clawd_tank_daemon.usage_export import build_document
    child = Child(account=account)
    reader, popen = source(child, timeout_s=0.02)
    rs = {"codex": Mock(status="ok", cost_kind="estimated", snapshot=Mock(return_value=[]))}
    good = build_document(rs, NOW, plans={"codex": reader.refresh(NOW)})
    stuck = Child(block=True)
    popen.return_value = stuck
    with pytest.raises(RuntimeError):
        reader.refresh(NOW + timedelta(seconds=300))
    failed = build_document(rs, NOW, good, plans={"codex": None})
    assert failed["agents"]["codex"] == {**good["agents"]["codex"], "plan": {
        **good["agents"]["codex"].get("plan", {}), "status": "error"}}
    assert stuck.killed.is_set() and stuck.stdin.closed and stuck.waited
    assert usage.CodexPlanSource(exe_finder=lambda: None).refresh(NOW) == {
        "status": "ok", "billing": "plan", "plan": {"status": "not_installed"}}


def test_daemon_wires_codex_source():
    from clawd_tank_daemon.daemon import ClawdDaemon
    assert isinstance(ClawdDaemon(sim_only=True)._plan_sources["codex"].__self__, usage.CodexPlanSource)


def test_release_order_is_numeric(tmp_path):
    root = tmp_path / ".codex/packages/app-server-daemon/releases"
    for version in ("9", "10"):
        (root / version).mkdir(parents=True)
        (root / version / "codex.exe").touch()
    assert usage.find_codex_exe(env={}, home=tmp_path, platform="win32") == str(root / "10/codex.exe")


@pytest.mark.parametrize("rates", [{}, {"rateLimits": {"limitId": "other", "primary": {"usedPercent": 3}}}])
def test_no_codex_bucket(rates):
    child = Child(rates=rates)
    reader, _ = source(child)
    assert reader._timeout == 15
    assert reader.refresh(NOW)["plan"] == {"status": "no_data", "limits": [], "reset_credits": None}


def test_kill_after_shutdown_grace_and_spawn_failure():
    child = Child()
    child.wait = Mock(side_effect=[subprocess.TimeoutExpired("fake", 0.5), None])
    reader, popen = source(child)
    reader.refresh(NOW)
    assert child.killed.is_set() and child.wait.call_args_list[0].kwargs == {"timeout": 0.5}
    popen.side_effect = OSError("sensitive payload")
    with pytest.raises(RuntimeError, match="^Codex plan read failed$"):
        reader.refresh(NOW + timedelta(seconds=300))
