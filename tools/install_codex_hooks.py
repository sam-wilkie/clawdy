"""Install Margarita Tank's user-level Codex hooks; optionally test the live bridge.

Run with host/.venv/Scripts/python.exe tools/install_codex_hooks.py --smoke-test.
Review the installed hooks in Codex before using them in a new session.
"""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "host"))
from clawd_tank_menubar import hooks


def smoke_test():
    """Verify a real hook reaches the running daemon, then remove the test session."""
    sid = "margarita-smoke-" + uuid.uuid4().hex
    state_path = hooks.CLAWD_DIR / "sessions.json"

    def send(event):
        result = subprocess.run(
            [sys.executable, str(hooks.NOTIFY_SCRIPT_PATH), "codex"],
            input=json.dumps({"hook_event_name": event, "session_id": sid,
                              "cwd": str(Path.cwd())}),
            text=True, capture_output=True, timeout=10,
        )
        result.check_returncode()

    def wait_for(present):
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                sessions = json.loads(state_path.read_text(encoding="utf-8"))["sessions"]
                if ("codex:" + sid in sessions) == present:
                    return
            except (OSError, ValueError, KeyError):
                pass
            time.sleep(0.1)
        raise RuntimeError("Live daemon did not confirm the Codex test session")

    try:
        send("SessionStart")
        wait_for(True)
        print("PASS: Codex hook reached the running daemon.")
    finally:
        send("SessionEnd")
        wait_for(False)
    print("PASS: temporary test session removed.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke-test", action="store_true")
    args = parser.parse_args()
    if hooks._load_codex_hooks() is None:
        raise SystemExit("Existing hooks.json is invalid; left untouched.")
    # Keep the first pre-install copy, including the shared Claude/Kiro bridge.
    for path in (hooks.CODEX_HOOKS_PATH, hooks.NOTIFY_SCRIPT_PATH):
        backup = path.with_name(path.name + ".before-codex.bak")
        if path.exists() and not backup.exists():
            shutil.copy2(path, backup)
    hooks.install_notify_script()
    if not hooks.install_codex_hooks():
        raise SystemExit("Codex hook installation failed.")
    print("Installed:", hooks.CODEX_HOOKS_PATH)
    print("Command:", hooks.CODEX_HOOK_COMMAND)
    if args.smoke_test:
        smoke_test()
    print()
    print("ACTION REQUIRED: Codex will NOT run these hooks until you approve them.")
    print("  1. Open /hooks in Codex and approve every hook marked 'Review'.")
    print("  2. Send a message; the Codex crab should appear.")
    print("Changing hooks.json (re-running this script, updating the app) requires approving again.")


if __name__ == "__main__":
    main()
