"""T5: the Pi extension source resolves in source and frozen builds, and ships in the spec."""

from pathlib import Path

import clawd_tank_menubar.hooks as hooks

HOST = Path(__file__).resolve().parents[1]


def test_source_run_resolves_to_host_pi_extension():
    p = hooks.resolve_pi_extension_source(False, "python", None, HOST / "clawd_tank_menubar" / "hooks.py")
    assert p == HOST / "pi-extension" / "clawd-tank.js"


def test_frozen_run_resolves_next_to_the_exe(tmp_path):
    exe = tmp_path / "Clawdy.exe"
    p = hooks.resolve_pi_extension_source(True, str(exe), None, "ignored")
    assert p == tmp_path / "pi-extension" / "clawd-tank.js"


def test_spec_ships_the_pi_extension():
    spec = (HOST / "windows" / "margarita_tank.spec").read_text(encoding="utf-8")
    assert '"pi-extension"' in spec and "clawd-tank.js" in spec
