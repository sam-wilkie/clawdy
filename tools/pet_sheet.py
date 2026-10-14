"""Contact sheet of pet animation frames: one row per SVG, N evenly spaced frames.

One PNG instead of many screenshots is the cheap way to review an animation (for a
person or an agent). Frames are sampled by pausing every CSS animation at the same
time, so the sheet shows exactly what the pet window plays.

Usage (from the repository root):
    python tools/pet_sheet.py out.png desktop/renderer/assets/monster/monster-cool-v2.svg [more.svg ...]
        [--frames 8] [--size 200]

Needs Playwright with Chromium and Pillow (the same as tools/svg2frames.py).
"""

import argparse
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw
from playwright.sync_api import sync_playwright

BACKGROUND = "#c8d2e1"


def sheet(files: list[Path], frames: int, size: int) -> Image.Image:
    rows = []
    with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": size, "height": size})
        shot = Path(tmp) / "frame.png"
        for f in files:
            page.goto(f.resolve().as_uri())
            dur = page.evaluate("Math.max(0, ...document.getAnimations()"
                                ".map(a => a.effect.getComputedTiming().duration || 0))") or 1000
            row = []
            for k in range(frames):
                t = dur * k / frames
                page.evaluate(f"""() => {{ const e = document.documentElement;
                    e.setAttribute('width', '{size}'); e.setAttribute('height', '{size}');
                    e.style.background = '{BACKGROUND}';
                    document.getAnimations().forEach(a => {{ a.pause(); a.currentTime = {t}; }}); }}""")
                page.screenshot(path=str(shot))
                row.append(Image.open(shot).convert("RGB"))
            rows.append((f.stem, row))
        browser.close()
    out = Image.new("RGB", (size * frames, (size + 14) * len(rows)), (240, 240, 240))
    draw = ImageDraw.Draw(out)
    for i, (name, row) in enumerate(rows):
        for j, im in enumerate(row):
            out.paste(im, (j * size, i * (size + 14) + 14))
        draw.text((4, i * (size + 14)), name, fill=(0, 0, 0))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("out", type=Path)
    ap.add_argument("svgs", type=Path, nargs="+")
    ap.add_argument("--frames", type=int, default=8)
    ap.add_argument("--size", type=int, default=200)
    a = ap.parse_args()
    sheet(a.svgs, a.frames, a.size).save(a.out)
    print(a.out)


if __name__ == "__main__":
    main()
