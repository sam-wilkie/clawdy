"""Tests for tools/pet_check.py (desktop pet set contract).

Run from the repo root:
    python -m unittest tools.tests.test_pet_check -v
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MONSTER = ROOT / "desktop" / "renderer" / "assets" / "monster"


def run(*args):
    return subprocess.run([sys.executable, str(ROOT / "tools" / "pet_check.py"), *args],
                          capture_output=True, text=True, cwd=ROOT)


class PetCheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.set = self.tmp / "monster"
        shutil.copytree(MONSTER, self.set)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_the_monster_set_passes(self):
        r = run(str(self.set), "monster")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(r.stdout.strip(), "OK monster: 29/29 states")
        self.assertEqual(r.stderr, "")

    def test_a_missing_state_fails_and_names_it(self):
        (self.set / "monster-wizard-v2.svg").unlink()
        r = run(str(self.set), "monster")
        self.assertEqual(r.returncode, 1)
        self.assertIn("missing: monster-wizard-v2.svg", r.stdout)

    def test_a_wrong_viewbox_fails_and_names_both(self):
        f = self.set / "monster-happy-v2.svg"
        f.write_text(f.read_text(encoding="utf-8").replace('viewBox="-12 -15 40 40"', 'viewBox="-15 -25 45 45"', 1),
                     encoding="utf-8")
        r = run(str(self.set), "monster")
        self.assertEqual(r.returncode, 1)
        self.assertIn('monster-happy-v2.svg: viewBox "-15 -25 45 45", the renderer expects "-12 -15 40 40"',
                      r.stdout)

    def test_fractional_art_pixels_fail(self):
        f = self.set / "monster-idle-v2.svg"
        f.write_text(f.read_text(encoding="utf-8").replace("<defs>", '<defs><path d="M1.5 2h1v1h-1z"/>', 1),
                     encoding="utf-8")
        r = run(str(self.set), "monster")
        self.assertEqual(r.returncode, 1)
        self.assertIn("monster-idle-v2.svg: path coordinate 1.5 is not a whole art pixel", r.stdout)


if __name__ == "__main__":
    unittest.main()
