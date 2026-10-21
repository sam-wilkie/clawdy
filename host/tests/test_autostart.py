"""Windows autostart command (HKCU Run key value)."""
import re
import subprocess
import sys

import pytest

pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="Windows Run key")

from clawd_tank_menubar import autostart  # noqa: E402


def test_dev_command_imports_the_package_from_any_cwd(tmp_path, monkeypatch):
    # Windows starts Run entries from System32, not from the checkout.
    monkeypatch.delattr(sys, "frozen", raising=False)
    command = autostart._expected_command()
    match = re.search(r' -c "(.*)"$', command)
    assert match, command
    code = match.group(1).replace("main()", "print('started')")
    result = subprocess.run([sys.executable, "-I", "-c", code], cwd=tmp_path,
                            capture_output=True, text=True)
    assert result.stdout.strip() == "started", result.stderr


def test_dev_command_uses_pythonw_when_available(monkeypatch):
    monkeypatch.delattr(sys, "frozen", raising=False)
    command = autostart._expected_command()
    assert command.startswith('"') and "-m clawd_tank_menubar" not in command


def test_frozen_command_is_the_installed_exe(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Apps\Clawdy\Clawdy.exe")
    assert autostart._expected_command() == '"C:\Apps\Clawdy\Clawdy.exe"'
