"""Brand monster for the Electron desktop pet: the default pet for any agent that has
no art set of its own (Claude keeps the crab, Codex keeps the cloud).

The monster reuses the Codex cloud engine (tools/codex_cloud_pixel.py) unchanged:
same pose functions, props, beats, fps and loops for every state, because both
characters fill the same 30 x 32 art-px body box. Only the character is swapped:

- body: a round ball, white on the left with a red crescent on the right;
- face: nine ring eyes (3 red, 6 white) as in assets/pet-samples/ai/
  monster-brand-cute-v1.png, pupils that look around, a smile with two baby fangs;
- hands: a white left mitten and a red right mitten.

Key poses per activity: assets/pet-samples/ai/monster-brand-activities-grid-v2.png.

Run from the repository root: ``python tools/monster_pixel.py``. It writes
desktop/renderer/assets/monster/monster-<state>-v2.svg and compare-v2.html; the
cloud's own output is not touched.

Dependency: tools/codex_cloud_pixel.py is kept local (gitignored, see NOTICE.md),
so this script only runs on a checkout that has it. The generated monster SVGs
are committed and self-contained.
"""

import math
from pathlib import Path

try:
    import codex_cloud_pixel as cc
except ModuleNotFoundError as exc:  # pragma: no cover - depends on the local checkout
    raise SystemExit("tools/codex_cloud_pixel.py is missing: it is kept local (gitignored, see NOTICE.md) "
                     "and the monster generator reuses its engine.") from exc

OUT = Path(__file__).resolve().parents[1] / "desktop" / "renderer" / "assets" / "monster"

# Palette: the cloud's ink outline and whites, plus the brand red.
OUTLINE, INK = cc.OUTLINE, cc.INK
WHITE, WHITE_L, WHITE_S = cc.BASE, cc.LIGHT, cc.SHADE
RED, RED_L, RED_S = "#E3202D", "#FF5C66", "#A8121E"
MOUTH, TONGUE = "#5A0F1E", "#F07A8A"
GOLD = "#FFC93C"
DIM_INK = "#4A5059"

# Whites -> recoloured whites already live in the cloud's variant palettes; add the reds.
cc.STORM.update({RED: "#9C4A52", RED_L: "#B5646B", RED_S: "#7A343C"})
cc.GREY.update({RED: "#D9737B", RED_L: "#E8959B", RED_S: "#B65660"})
cc.DIM.update({RED: "#B8858A", RED_L: "#CDA2A6", RED_S: "#9A6C71"})


# ---------------------------------------------------------------- body

CENTER = (15.0, 15.5)
RX, RY = 14.5, 14.0


def monster_mask(puff: int = 0, sx: float = 1.0, sy: float = 1.0) -> set[tuple[int, int]]:
    """Round body as art pixels; ``puff`` grows it by whole pixels, ``sx``/``sy``
    squash or stretch it around the middle of the ground row (same contract as
    the cloud mask, so every body variant of the engine works)."""
    cx, cy = CENTER
    rx, ry = RX + puff, RY + puff
    n = cc.SUPERSAMPLE

    def inside(x: float, y: float) -> bool:
        x, y = cx + (x - cx) / sx, cc.GROUND + (y - cc.GROUND) / sy
        return ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1.0

    px = set()
    for y in range(-3, 34):
        for x in range(-3, 34):
            hits = sum(inside(x + (i + .5) / n, y + (j + .5) / n) for i in range(n) for j in range(n))
            if 2 * hits >= n * n:
                px.add((x, y))
    return px


def monster_shade(mask: set[tuple[int, int]]) -> dict[str, set[tuple[int, int]]]:
    """Cloud shading (1 px outline, light top/left, shade bottom/right), then the
    pixels outside a white disc set up and to the left turn red: a crescent that is
    thick at the top right and thins out towards the bottom, like the logo."""
    colors = cc_shade_mask(mask)
    xs = [x for x, _ in mask]
    ys = [y for _, y in mask]
    x0, w = min(xs), max(xs) - min(xs) + 1
    y0, h = min(ys), max(ys) - min(ys) + 1
    wx, wy, wr = x0 + 0.33 * w, y0 + 0.60 * h, 0.45 * w

    def red(p):
        return math.hypot(p[0] + .5 - wx, p[1] + .5 - wy) > wr

    out = {OUTLINE: colors[OUTLINE]}
    for white, redc in ((WHITE_L, RED_L), (WHITE, RED), (WHITE_S, RED_S)):
        out[white] = {p for p in colors[white] if not red(p)}
        out[redc] = {p for p in colors[white] if red(p)}
    return out


cc_shade_mask = cc.shade_mask
cc.cloud_mask = monster_mask
cc.shade_mask = monster_shade


# ---------------------------------------------------------------- face

def paths(by_color: dict[str, set]) -> str:
    return "".join(f'<path fill="{c}" d="{cc.to_path(p)}"/>' for c, p in by_color.items() if p)


def art(rows: list[str], palette: dict[str, str], x0: int = 0, y0: int = 0) -> str:
    by_color: dict[str, set] = {}
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != ".":
                by_color.setdefault(palette[ch], set()).add((x0 + x, y0 + y))
    return paths(by_color)


# Nine 6 x 6 ring eyes in a hex cluster (top-left corners, body space). Neighbours
# share their outline column. Red eyes sit on the white side, white eyes reach into
# the red crescent, as in the reference.
EYES = [
    (12, 4, "w"), (12, 10, "w"), (12, 16, "w"),  # centre column
    (7, 7, "r"), (7, 13, "r"), (2, 10, "r"),     # left: the three red eyes
    (17, 7, "w"), (17, 13, "w"), (22, 10, "w"),  # right
]
# Each eye: a ring of colour (red or white) round a big pupil, on one dark blob that
# fills the gaps between the rings, as in the reference.
IRIS = [".II.", "IIII", "IIII", ".II."]
RING_FILL = {"w": WHITE, "r": RED}


def rings(dim: bool = False) -> str:
    blob = {(x + c, y + r) for x, y, _ in EYES for r in range(6) for c in range(6)}
    blob -= {(x, y) for x, y in blob
             if sum((x + dx, y + dy) in blob for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))) <= 2}
    out = {DIM_INK if dim else OUTLINE: blob}
    for x, y, kind in EYES:
        fill = RING_FILL[kind]
        fill = cc.DIM.get(fill, fill) if dim else fill
        out.setdefault(fill, set()).update(
            (x + 1 + c, y + 1 + r) for r, row in enumerate(IRIS) for c, ch in enumerate(row) if ch == "I")
    return paths(out)


def per_eye(rows: list[str], color: str = INK, dx: int = 1, dy: int = 1, shift=None, only=None) -> str:
    """The same 4 x 4 interior glyph inside every eye ('K' pixels). ``shift`` maps
    the eye index to an extra (x, y) offset (confused eyes look every which way)."""
    px = set()
    for i, (x, y, _) in enumerate(EYES):
        if only is not None and i not in only:
            continue
        sx, sy = shift(i) if shift else (0, 0)
        px |= {(x + dx + c + sx, y + dy + r + sy) for r, row in enumerate(rows) for c, ch in enumerate(row) if ch == "K"}
    return paths({color: px})


PUPIL = ["....", ".KK.", ".KK.", "...."]
GLINT = ["....", ".K..", "....", "...."]       # white catch-light on the pupil
PUPIL_S = ["....", ".K..", "....", "...."]      # startled: pin-prick pupils
LID = ["....", "....", "KKKK", "...."]           # closed
SLEEP = ["....", "K..K", ".KK.", "...."]         # relaxed closed, curved down
HAPPY = ["....", ".KK.", "K..K", "...."]         # ^ arcs
HALF = ["KKKK", "....", ".KK.", "...."]          # heavy lid line over a low pupil
X = ["K..K", ".KK.", ".KK.", "K..K"]
SWIRL_A = ["KKK.", "...K", "K.KK", "KK.."]
SWIRL_B = cc.rot90(SWIRL_A)
STAR = [".KK.", "KKKK", "KKKK", ".KK."]

MP = {"K": INK, "M": MOUTH, "W": WHITE_L, "T": TONGUE}
MOUTH_X, MOUTH_Y = 10, 23
SMILE = ["K........K", ".KWMMMMWK.", "..KKKKKK.."]          # rest: smile with two baby fangs
GRIN = ["KKKKKKKKKK", ".KWMMMMWK.", "..KMTTMK..", "...KKKK..."]
SMALL = ["..K....K..", "...KKKK..."]
SMIRK = ["........K.", "..KKKKKK..."]
O_MOUTH = ["...KKKK...", "..KMMMMK..", "...KKKK..."]
WAVY = ["..K.K.K.K.", "...K.K.K.."]
CAT = ["...K.K.K..", "....K.K..."]
YAWN = {
    1: ["...KKKK...", "..KMMMMK..", "...KKKK..."],
    2: ["...KKKK...", "..KMMMMK..", "..KMTTMK..", "...KKKK..."],
    3: ["..KKKKKK..", ".KMMMMMMK.", ".KMMMMMMK.", ".KMTTTTMK.", "..KKKKKK.."],
}
TYPE = [  # focused: the tongue pokes out while typing, sliding along
    ["..KKKKKK.."],
    ["..KKKKKK..", "...TT....."],
    ["..KKKKKK..", ".....TT..."],
    ["..KKKKKK..", ".......TT."],
]


def mouth(rows: list[str], dy: int = 0) -> str:
    return art(rows, MP, MOUTH_X, MOUTH_Y + dy)


BLUSH = (f'<path fill="{cc.BLUSH}" d="M2 20h4v2h-4zM23 20h4v2h-4z"/>'
         f'<path fill="{cc.BLUSH_MID}" d="M3 20h2v1h-2zM24 20h2v1h-2z"/>')


COOL_LIDS = {2, 6, 7, 8}
COOL_OPEN = set(range(len(EYES))) - COOL_LIDS


def confused_shift(i: int) -> tuple[int, int]:
    return ((-1, -1), (1, 0), (0, 1), (1, -1), (-1, 1), (0, -1), (-1, 0), (1, 1), (0, 0))[i]


def face_defs() -> dict[str, str]:
    """Faces under the cloud's ids, so every pose of the engine picks them up. The
    rings are their own layer ("eye-rings"): faces draw only the pupils or lids."""
    return {
        "eye-rings-dim": rings(dim=True),
        "face-o": per_eye(PUPIL_S) + mouth(O_MOUTH),
        "face-sleep": per_eye(SLEEP) + mouth(SMALL),
        "face-dizzy-a": per_eye(SWIRL_A) + mouth(WAVY),
        "face-dizzy-b": per_eye(SWIRL_B) + mouth(WAVY),
        "face-x": per_eye(X) + mouth(WAVY),
        "face-star": per_eye(STAR, GOLD) + per_eye(PUPIL) + per_eye(GLINT, WHITE_L) + mouth(GRIN),
        "face-oO": per_eye(PUPIL, shift=confused_shift) + per_eye(GLINT, WHITE_L, shift=confused_shift) + mouth(WAVY),
        "face-wink": per_eye(HAPPY) + mouth(CAT),
        "eyes-line": per_eye(LID),
        "mouth-u": mouth(SMALL),
        "mouth-smirk": mouth(SMIRK),
        "eyes-half": per_eye(HALF),
        **{f"type-{k}": mouth(rows) for k, rows in enumerate(TYPE)},
        # cool: relaxed half-lids on the right-hand eyes, a lopsided smile
        "face-cool": (per_eye(PUPIL, only=COOL_OPEN) + per_eye(GLINT, WHITE_L, only=COOL_OPEN)
                      + per_eye(HALF, only=COOL_LIDS) + mouth(SMIRK)),
    }


# ---------------------------------------------------------------- hands

MITTEN = [".OOO.", "OLLBO", "OLBBO", "OBBSO", ".OOO."]
HAND_W = art(MITTEN, {"O": OUTLINE, "L": WHITE_L, "B": WHITE, "S": WHITE_S})
HAND_R = art(MITTEN, {"O": OUTLINE, "L": RED_L, "B": RED, "S": RED_S})


def hand_layers(*names: str) -> list:
    return [(n, cc.use("hand-r" if n == "hr" else "hand")) for n in names]


# ---------------------------------------------------------------- shared defs

def defs() -> str:
    """Same ids as the cloud's defs(), with the monster's art."""
    body = lambda *a: cc.layer(monster_shade(monster_mask(*a)))
    return f'''    <g id="shadow">
      <path fill="#000000" fill-opacity="0.3" d="M5 30h20v1h-20z"/>
      <path fill="#000000" fill-opacity="0.15" d="M8 31h14v1h-14z"/>
    </g>
    <g id="shadow-sm">
      <path fill="#000000" fill-opacity="0.3" d="M7 30h16v1h-16z"/>
      <path fill="#000000" fill-opacity="0.15" d="M10 31h10v1h-10z"/>
    </g>
    <!-- round body: white left, red crescent right, 1 px outline, light top/left -->
    <g id="cloud">
{body(0)}
    </g>
    <g id="cloud-puff">
{body(1)}
    </g>
    <g id="cloud-squash">
{body(0, 1.08, 0.88)}
    </g>
    <g id="cloud-stretch">
{body(0, 0.93, 1.07)}
    </g>
    <g id="eye-rings">{rings()}</g>
    <g id="face-happy">{per_eye(HAPPY)}{mouth(GRIN)}</g>
    <g id="blush">{BLUSH}</g>
    <g id="face-caret">{per_eye(HAPPY)}{mouth(SMILE)}</g>
    <g id="eyes-open">{per_eye(PUPIL)}{per_eye(GLINT, WHITE_L)}</g>
    <g id="eyes-shut">{per_eye(LID)}</g>
    <g id="cursor">{mouth(SMILE)}</g>
    <g id="mouth-yawn-1">{mouth(YAWN[1])}</g>
    <g id="mouth-yawn-2">{mouth(YAWN[2])}</g>
    <g id="mouth-yawn-3">{mouth(YAWN[3], -1)}</g>
    <g id="mini-puff">{cc.sprite([".OO.", "OLBO", "OBBO", ".OO."], {"O": OUTLINE, "L": RED_L, "B": RED})}</g>
    <g id="hand">{HAND_W}</g>
    <g id="hand-r">{HAND_R}</g>'''


# Every face sits on the rings, except the dimmed x_x which brings its own.
RINGED = {k: (["eye-rings"] if k != "x-dim" else ["eye-rings-dim"]) for k in cc.FACES}
for key, parts in cc.FACES.items():
    cc.FACES[key] = [*(p for p in parts if p == "blush"), *RINGED[key], *(p for p in parts if p != "blush")]
cc.FACES["cool"] = ["eye-rings", "face-cool"]
cc.FACE_IDS[:0] = ["eye-rings", "eye-rings-dim"]
cc.FACE_IDS.append("face-cool")
cc.FACE_LAYERS[:0] = [("f-eye-rings", cc.use("eye-rings")), ("f-eye-rings-dim", cc.use("eye-rings-dim"))]
cc.FACE_LAYERS.append(("f-face-cool", cc.use("face-cool")))


class Pose(cc.Pose):
    """The cloud blinks its ">_" cursor; the monster's cursor is its mouth, so it
    always stays on."""

    def face(self, name, x, y, look=(0, 0), cursor=True):
        super().face(name, x, y, look, True)


cc.Pose = Pose
cc.hand_layers = hand_layers
cc.defs = defs
cc.face_defs = face_defs
cc.LIB = cc.kit()
cc.LIB["face-x-dim"] = cc.LIB["face-x"].replace(INK, DIM_INK)

# The idle scene keeps the cloud's tracks; the rings ride the face so they squash
# with the hops, and the cursor (now the mouth) never blinks.
cc.IDLE_SCENE = cc.IDLE_SCENE.replace('<g class="face-sq">', '<g class="face-sq"><use href="#eye-rings"/>')


def write_state(name: str, fps: int, frames: int, beats: str, layers: list, pose,
                viewbox: str = "-15 -25 45 45", wrap: str = 'transform="scale(.5)"', hold_s: float = 0.75) -> str:
    timeline, rows, ids = cc.animate(frames, fps, layers, pose, hold_s)
    extra = "\n".join(f'    <g id="{i}">{cc.LIB[i]}</g>' for i in sorted(ids) if i in cc.LIB)
    loop_s = f"{frames / fps:g}"
    comment = (f"Monster v2 {name}: {loop_s} s loop, poses at {fps} fps ({frames} frames), same beats as the "
               f"Codex cloud v2 {name}; appearance swaps step-end, motion interpolated. {beats}")
    scene = f"  <g {wrap}>\n{rows}\n  </g>\n"
    svg = cc.svg_doc(comment, loop_s, timeline, scene, extra, viewbox)
    (OUT / f"monster-{name}-v2.svg").write_text(svg, encoding="utf-8")
    return name


cc.write_state = write_state


cc_idle_timeline = cc.idle_timeline


def idle_timeline() -> dict:
    """The cloud's idle blinks its cursor; the monster's mouth only gives way to the yawn."""
    tl = cc_idle_timeline()
    yawning = [any(tl[f"yawn-{k}"][0][f] for k in (1, 2, 3)) for f in range(cc.FRAMES)]
    tl["cursor"] = ([not y for y in yawning], tl["cursor"][1])
    return tl


cc.idle_timeline = idle_timeline


def render_idle() -> str:
    return cc.render_idle().replace("Codex cloud v2 idle", "Monster v2 idle (Codex cloud v2 beats)")


def render_waiting_reply() -> str:
    svg = cc.render_waiting_reply().replace("Codex cloud v2 waiting_reply", "Monster v2 waiting_reply")
    svg = svg.replace('<use href="#cloud"/><use href="#blush"/>', '<use href="#cloud"/><use href="#blush"/><use href="#eye-rings"/>')
    return svg.replace('<g transform="translate(26 19)"><use href="#hand"/>', '<g transform="translate(26 19)"><use href="#hand-r"/>')


# ---------------------------------------------------------------- own beats
# Two activities differ from the cloud, following the key poses of grid v2:
# CONSTRUYENDO stacks code blocks (no hammer) and COOL is a thumbs-up (no glasses).

BLOCK_COLORS = {"blue": ("#1F4E9C", "#3D7BE0", "#8FB8FF"), "green": ("#1E6B34", "#3CB45A", "#8FE3A2"),
                "gold": ("#8A5A06", "#F2B630", "#FFE08A")}
BLOCK = ["LLLLLLLL", "LBBBBBBS", "LBBBBBBS", "LBBBBBBS", "SSSSSSSS"]
BRACKET = ["........", "..K..K..", ".K....K.", "..K..K..", "........"]  # < > on the gold block


def block(color: str, code: bool = False) -> str:
    o, b, l = BLOCK_COLORS[color]
    rows = BLOCK
    if code:
        rows = ["".join("K" if k == "K" else c for c, k in zip(r, br)) for r, br in zip(BLOCK, BRACKET)]
    return cc.outlined(rows, {"L": l, "B": b, "S": o, "K": "#14161D"}, outline=OUTLINE)


THUMB = ["..OO...", ".OLBO..", ".OLBO..", "OOLBOOO", "OLLBBBO", "OLBBBSO", "OBBBBSO", ".OOOOO."]
THUMB_UP = cc.sprite(THUMB, {"O": OUTLINE, "L": RED_L, "B": RED, "S": RED_S})

cc.LIB.update({"block-blue": block("blue"), "block-green": block("green"), "block-gold": block("gold", True),
               "thumb-up": THUMB_UP})


def render_building() -> str:
    fps, n = 8, 24
    # The red mitten lifts the gold { } block over the stack, sets it down (squash,
    # sparks), lets go, then picks it up again for the next loop.
    carry = [(25, 16), (26, 12), (28, 8), (30, 4), (31, 2), (32, 1), (32, 1), (32, 3), (32, 5), (32, 7),
             (32, 8), (32, 9)]
    lift = [(32, 9), (32, 7), (31, 5), (30, 8), (28, 12), (26, 15)]

    def pose(f):
        Pose_ = cc.Pose
        if f < 12:
            p = Pose_().body("n", 0, 0, "focus-0" if f % 4 < 2 else "focus-1", look=(1, -1))
            hand, held = carry[f], True
        elif f < 18:
            landed = f in (12, 13)
            p = Pose_().body("sq" if f == 12 else "n", 0, 0, "happy" if landed else "rest", look=(1, 0))
            hand, held = (26, 19), False
            if f == 12:
                p["burst"] = (31, 4)
            if f == 13:
                p["burst-2"] = (30, 2)
        else:
            p = Pose_().body("n", 0, 0, "rest", look=(1, -1))
            hand, held = lift[f - 18], True
        p["hl"] = at(cc.L_REST, 0, -1 if (f // 6) % 2 else 0)
        p["hr"] = hand
        p["blk-1"] = (32, 24)
        p["blk-2"] = (32, 17)
        p["blk-3"] = (hand[0] + 1, hand[1] - 6) if held else (32, 10)
        return p

    at = cc.at
    layers = (cc.SHADOW_LAYERS + [("blk-1", cc.use("block-blue")), ("blk-2", cc.use("block-green"))] +
              cc.BODY_LAYERS + cc.FACE_LAYERS + [("blk-3", cc.use("block-gold"))] + hand_layers("hl", "hr") +
              [("burst", cc.use("burst")), ("burst-2", cc.use("burst-2"))])
    return write_state("building", fps, n, "Grid v2 CONSTRUYENDO: the red mitten lifts a gold { } block over a "
                       "blue and green stack, sets it down with a squash and sparks, and picks it up again.",
                       layers, pose)


def render_cool() -> str:
    fps, n = 6, 30

    def pose(f):
        on = 6 <= f < 26
        dy = -1 if on and (f // 6) % 2 and f > 8 else 0
        p = cc.Pose().body("sq" if f == 6 else "n", 0, dy, "cool" if on else "rest", look=(0, -1) if f < 6 else (0, 0))
        p["hl"] = cc.at(cc.L_REST, 0, dy)
        if on:
            p["thumb"] = (26, 11 + dy - (1 if f in (7, 8) else 0))
        else:
            p["hr"] = cc.R_REST
        if f in (10, 11, 18, 19):
            p["spk-a"] = (30, 2)
        if f in (14, 15, 22, 23):
            p["spk-b"] = (-4, 4)
        return p

    layers = (cc.SHADOW_LAYERS + cc.BODY_LAYERS + cc.FACE_LAYERS + hand_layers("hl", "hr") +
              [("thumb", cc.use("thumb-up")), ("spk-a", cc.use("sparkle")), ("spk-b", cc.use("sparkle-s"))])
    return write_state("cool", fps, n, "Grid v2 COOL: no glasses; half-lidded eyes on the right, a lopsided "
                       "smile and a red thumbs-up that bounces while two sparkles twinkle.", layers, pose, hold_s=1.5)


OWN = {"building": render_building, "cool": render_cool}
STATE_RENDERERS = [OWN.get(r.__name__.removeprefix("render_"), r) for r in cc.STATE_RENDERERS]


def compare_page(states: list[str]) -> str:
    rows = "\n".join(
        f'<tr><th>{s}</th><td><img src="../codex/cloud-{s}-v2.svg" alt=""></td>'
        f'<td><img src="monster-{s}-v2.svg" alt=""></td></tr>' for s in states)
    return f'''<!doctype html><meta charset="utf-8"><title>Monster v2 gallery</title>
<style>body{{margin:0;padding:24px;background:#1b1f2b;color:#cfd8f0;font:13px system-ui}}
table{{border-collapse:separate;border-spacing:12px}}th{{text-align:right;font-weight:600;padding-right:8px}}
td{{background:#2a3042;border-radius:12px;padding:8px}}img{{width:220px;height:220px;image-rendering:pixelated;display:block}}
thead th{{text-align:center}}</style>
<table><thead><tr><th>state</th><th>Codex v2</th><th>Monster v2</th></tr></thead>
{rows}
</table>
'''


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "monster-idle-v2.svg").write_text(render_idle(), encoding="utf-8")
    (OUT / "monster-waiting_reply-v2.svg").write_text(render_waiting_reply(), encoding="utf-8")
    names = ["idle", "waiting_reply"] + [r() for r in STATE_RENDERERS]
    (OUT / "compare-v2.html").write_text(compare_page(names), encoding="utf-8")
    print(f"wrote {len(names)} monster states and compare-v2.html to {OUT}")


if __name__ == "__main__":
    main()
