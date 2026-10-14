"""Re-skin a Claude crab (Clawd v2) animation file with another character.

The crab's SVG files keep every part in <defs> (torso, legs, pincers, eye groups,
props) and animate them from the scene with CSS. ``skin`` rewrites the content of
those <defs> groups through a handler and leaves the scene and the timing alone, so
the new character plays the crab's exact animation. Used by tools/monster_pixel.py
and by the local tools/codex_cloud_pixel.py.
"""

import re
from pathlib import Path

CRAB = Path(__file__).resolve().parents[1] / "desktop" / "renderer" / "assets"


def def_groups(svg: str) -> list[tuple[str, int, int]]:
    """(id, start of content, end of content) for every <g id=...>."""
    out = []
    for m in re.finditer(r'<g id="([^"]+)"[^>]*>', svg):
        depth, j = 1, m.end()
        while depth:
            a, b = svg.find("<g", j), svg.find("</g>", j)
            if a != -1 and a < b:
                depth, j = depth + 1, a + 2
            else:
                depth, j = depth - 1, b + 4
        out.append((m.group(1), m.end(), j - 4))
    return out


def bbox(svg: str) -> tuple[float, float, float, float]:
    """Bounding box of the run-length paths (M x y h w v h h -w z) in ``svg``."""
    xs, ys = [], []
    for d in re.findall(r' d="([^"]+)"', svg):
        x = y = 0.0
        for cmd, args in re.findall(r"([MmHhVvZz])([^MmHhVvZz]*)", d):
            nums = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", args)]
            if cmd == "M":
                x, y = nums[0], nums[1]
            elif cmd == "h":
                x += nums[0]
            elif cmd == "v":
                y += nums[0]
            elif cmd == "H":
                x = nums[0]
            elif cmd == "V":
                y = nums[0]
            if cmd not in "Zz":
                xs.append(x)
                ys.append(y)
    return min(xs), min(ys), max(xs), max(ys)


def raster(svg: str) -> dict[tuple[int, int], str]:
    """Pixels of a run-length path group (each subpath is one axis-aligned rect)."""
    px = {}
    for fill, d in re.findall(r'fill="(#[0-9A-Fa-f]{6})" d="([^"]+)"', svg):
        for sp in re.findall(r"M[^Mz]*z?", d):
            x0, y0, x1, y1 = bbox(f' d="{sp}"')
            for y in range(int(y0), int(y1)):
                for x in range(int(x0), int(x1)):
                    px[(x, y)] = fill
    return px


def skin(src: str, out: Path, handler, edit=None, comment: str = "") -> None:
    """Write ``out``: the crab file ``src`` with each <defs> group's content replaced
    by ``handler(id, content)`` (None keeps it), then ``edit`` on the whole text, and
    its first comment replaced by ``comment``."""
    svg = (CRAB / src).read_text(encoding="utf-8")
    for gid, a, b in sorted(def_groups(svg), key=lambda g: -g[1]):
        new = handler(gid, svg[a:b])
        if new is not None:
            svg = svg[:a] + new + svg[b:]
    if edit:
        svg = edit(svg)
    svg = re.sub(r"<!--.*?-->", "", svg, count=1, flags=re.S)
    svg = svg.replace("<defs>", f"<!-- {comment} -->\n  <defs>", 1)
    out.write_text(svg, encoding="utf-8")
