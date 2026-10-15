"""The Windows build ships as Clawdy.exe (S6) and the release assets are named Clawdy.
Helper exes keep their names because installed hooks point at them."""

from pathlib import Path

HOST = Path(__file__).resolve().parents[1]
SPEC = (HOST / "windows" / "margarita_tank.spec").read_text(encoding="utf-8")
ISS = (HOST / "windows" / "installer.iss").read_text(encoding="utf-8")
RELEASE = (HOST.parent / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


def test_spec_builds_the_clawdy_tray_exe_and_folder():
    assert 'APP_NAME = "Clawdy"' in SPEC


def test_installer_installs_and_launches_clawdy_exe():
    assert '#define AppName "Clawdy"' in ISS
    assert '#define AppExeName "Clawdy.exe"' in ISS
    assert '#define BuildDir "..\\dist\\Clawdy"' in ISS


def test_helper_exe_names_are_unchanged_because_hooks_point_at_them():
    assert 'NOTIFY_NAME = "margarita-notify"' in SPEC
    assert 'STATUSLINE_NAME = "margarita-statusline"' in SPEC


def test_installer_is_named_clawdy_setup():
    assert 'OutputBaseFilename=Clawdy-Setup' in ISS


def test_release_publishes_clawdy_assets():
    assert "assets/Clawdy.dmg" in RELEASE
    assert "assets/Clawdy-Setup.exe" in RELEASE
    assert "Margarita-Tank" not in RELEASE


def test_release_checks_the_clawdy_build_folder():
    assert "working-directory: host/dist/Clawdy" in RELEASE
    assert "for f in Clawdy.exe " in RELEASE
    assert "MargaritaTank" not in RELEASE
