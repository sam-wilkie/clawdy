"""Check a desktop pet art set against the contract in docs/pet-art-bible.md.

Checks, without rendering anything (cheap to run after every generation):
- one file per state: <prefix>-<state>-v2.svg for every key of STATES in
  desktop/renderer/renderer.js, plus "alert";
- each file's viewBox equals the one the renderer uses for that state;
- every path coordinate is a whole art pixel.

Usage (from the repository root):
    python tools/pet_check.py desktop/renderer/assets/monster monster

Prints "OK <prefix>: N/N states" and exits 0, or prints one line per problem and
exits 1.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RENDERER = ROOT / "desktop" / "renderer" / "renderer.js"
FULL_VB = (-15, -25, 45)


def expected_states() -> dict[str, tuple[int, int, int]]:
    """state -> viewBox (x, y, size) as the renderer places it."""
    src = RENDERER.read_text(encoding="utf-8")
    block = src[src.index("const STATES = {"):]
    block = block[:block.index("\n};")]
    states = {}
    for name, vb in re.findall(r"^\s*(\w+):\s*(null|\{[^}]*\})", block, re.M):
        m = re.search(r"vb:\s*\[(-?\d+),\s*(-?\d+),\s*(\d+)\]", vb)
        states[name] = tuple(int(v) for v in m.groups()) if m else FULL_VB
    states.setdefault("alert", FULL_VB)
    return states


def check(folder: Path, prefix: str) -> list[str]:
    problems = []
    states = expected_states()
    for state, (x, y, size) in states.items():
        f = folder / f"{prefix}-{state}-v2.svg"
        if not f.exists():
            problems.append(f"missing: {f.name}")
            continue
        svg = f.read_text(encoding="utf-8")
        want = f"{x} {y} {size} {size}"
        m = re.search(r'viewBox="([^"]+)"', svg)
        got = m.group(1) if m else "none"
        if got != want:
            problems.append(f'{f.name}: viewBox "{got}", the renderer expects "{want}"')
        for d in re.findall(r' d="([^"]+)"', svg):
            bad = next((n for n in re.findall(r"-?\d+\.\d+", d) if float(n) != int(float(n))), None)
            if bad:
                problems.append(f"{f.name}: path coordinate {bad} is not a whole art pixel")
                break
    return problems


def main() -> int:
    if len(sys.argv) != 3:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        print("usage: python tools/pet_check.py <set folder> <file prefix>", file=sys.stderr)
        return 2
    folder, prefix = Path(sys.argv[1]), sys.argv[2]
    problems = check(folder, prefix)
    if problems:
        print("\n".join(problems))
        return 1
    n = len(expected_states())
    print(f"OK {prefix}: {n}/{n} states")
    return 0


if __name__ == "__main__":
    sys.exit(main())
