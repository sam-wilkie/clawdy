"""Mochi presentation sheet for the README and the brand: key poses with captions.

Each pose is a frame of Mochi's real animation file (paused at a chosen time), so
the sheet always matches what the pet plays. Output: assets/readme/mochi-sheet.png.

Run from the repository root: ``python tools/mochi_sheet.py`` (Playwright + Pillow).
"""

import tempfile
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
SET = ROOT / "desktop" / "renderer" / "assets" / "monster"
OUT = ROOT / "assets" / "readme" / "mochi-sheet.png"

# (state, time in ms, caption): one pose per trait of the character sheet
POSES = [
    ("idle", 3000, "hola"), ("thinking", 1500, "pensando"), ("building", 600, "soldando"),
    ("wizard", 1200, "buscando"), ("happy", 300, "listo"), ("cool", 3500, "cool"),
    ("sleeping", 1000, "durmiendo"), ("error", 200, "error"),
]
CELL, COLS, PAD, TITLE_H = 220, 4, 16, 96
BG, CARD, INK, SUB = (27, 31, 43), (42, 48, 66), (246, 241, 240), (190, 182, 196)


def font(size: int, bold: bool = False):
    for name in (("seguisb.ttf", "segoeuib.ttf", "DejaVuSans-Bold.ttf") if bold else ("segoeui.ttf", "DejaVuSans.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def frame(page, svg: Path, t: int, shot: Path) -> Image.Image:
    page.goto(svg.resolve().as_uri())
    page.evaluate(f"""() => {{ const e = document.documentElement;
        e.setAttribute('width', '{CELL}'); e.setAttribute('height', '{CELL}');
        document.getAnimations().forEach(a => {{ a.pause(); a.currentTime = {t}; }}); }}""")
    page.screenshot(path=str(shot), omit_background=True)
    return Image.open(shot).convert("RGBA")


def main() -> None:
    rows = (len(POSES) + COLS - 1) // COLS
    w = COLS * CELL + (COLS + 1) * PAD
    h = TITLE_H + rows * (CELL + 34) + (rows + 1) * PAD
    sheet = Image.new("RGBA", (w, h), BG + (255,))
    d = ImageDraw.Draw(sheet)
    d.text((PAD + 4, 18), "Mochi", font=font(44, True), fill=INK)
    d.text((PAD + 170, 34), "la mascota por defecto de Clawdy · tres ojos, cero apuro", font=font(20), fill=SUB)
    with sync_playwright() as p, tempfile.TemporaryDirectory() as tmp:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": CELL, "height": CELL})
        for i, (state, t, caption) in enumerate(POSES):
            x = PAD + (i % COLS) * (CELL + PAD)
            y = TITLE_H + PAD + (i // COLS) * (CELL + 34 + PAD)
            d.rounded_rectangle((x, y, x + CELL, y + CELL + 34), 14, fill=CARD)
            im = frame(page, SET / f"monster-{state}-v2.svg", t, Path(tmp) / "f.png")
            sheet.alpha_composite(im, (x, y))
            tw = d.textlength(caption, font=font(18, True))
            d.text((x + (CELL - tw) / 2, y + CELL + 4), caption, font=font(18, True), fill=INK)
        browser.close()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sheet.convert("RGB").save(OUT)
    print(OUT)


if __name__ == "__main__":
    main()
