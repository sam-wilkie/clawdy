"""Brand monster for the Electron desktop pet: the default pet for any agent that has
no art set of its own (Claude keeps the crab, Codex keeps the cloud).

Design (approved mockup "C3, option 2", odd/tasks/monster-default-pet.md):

- body: a round ball, white on the left with a soft cherry crescent on the right,
  tonal outlines (plum on the white side, dark red on the red side) like the crab's
  brown outline, light from the top left, no stray tip pixels;
- eyes: three big 7 x 8 ring eyes in one touching arched row (one red ring, two
  light rings) sitting just above the mouth, with a 2 x 2 catch-light that follows
  the gaze; closed eyes are drawn spread apart, one soft curve each;
- a small smile with two baby fangs, blush, and floating mittens (white left, red
  right) that the poses use as hands.

Motion: tools/codex_cloud_pixel.py is the engine (Pose, animate, props, timing);
both characters fill the same 30 x 32 art-px body box. Most states keep the cloud's
beats; error, low_battery, happy, beacon, debugger, waiting_reply, alert and
disconnected follow the Claude crab's beats instead, and building/cool follow the
grid v2 key poses (code blocks, thumbs-up).

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
use, at, Smooth = cc.use, cc.at, cc.Smooth

# ---------------------------------------------------------------- palette

W_O, W_L, W_B, W_S = "#5E4B5A", "#FFFFFF", "#F6F1F0", "#D9CDD2"   # white side: plum outline
R_O, R_L, R_B, R_S = "#7C1E2B", "#F2848D", "#DE4553", "#B32F40"   # red side: dark red outline
EYE_INK, EYE_HI = "#2A1A22", "#FFFFFF"
RING_RED, RING_LIGHT = R_B, "#B9AAB2"
MOUTH_INK, MOUTH, TONGUE = "#5A2433", "#5A0F1E", "#F07A8A"
BLUSH = "#F2A0AE"
GOLD = "#FFC93C"
DIM_INK = "#6E6470"

# Recoloured body variants of the engine (storm, grey, dim) keyed on our colours.
cc.STORM.update({W_B: "#8A8191", W_L: "#A79FAD", W_S: "#6C6372", R_B: "#9C4A52", R_L: "#B5646B", R_S: "#7A343C"})
cc.GREY.update({W_B: "#E2DCDD", W_L: "#F0ECEC", W_S: "#BDB2B7", R_B: "#D9737B", R_L: "#E8959B", R_S: "#B65660"})
cc.DIM.update({W_B: "#CFC8CB", W_L: "#DDD8DA", W_S: "#ADA3A8", R_B: "#B8858A", R_L: "#CDA2A6", R_S: "#9A6C71",
               W_O: DIM_INK, R_O: DIM_INK})


# ---------------------------------------------------------------- body

CENTER = (15.0, 15.5)
RX, RY = 14.5, 14.0


def monster_mask(puff: int = 0, sx: float = 1.0, sy: float = 1.0) -> set[tuple[int, int]]:
    """Round body as art pixels (same contract as the cloud mask: ``puff`` grows it,
    ``sx``/``sy`` squash or stretch it around the ground row)."""
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
    # Drop lone tip pixels (one 4-neighbour or fewer) so the silhouette stays round.
    while nubs := {(x, y) for x, y in px
                   if sum((x + dx, y + dy) in px for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))) <= 1}:
        px -= nubs
    return px


def monster_shade(mask: set[tuple[int, int]]) -> dict[str, set[tuple[int, int]]]:
    """Cloud shading, then every pixel outside a white disc set to the lower left
    turns red (a crescent, thick at the top right), outline included: tonal."""
    base = cc_shade_mask(mask)
    xs = [x for x, _ in mask]
    ys = [y for _, y in mask]
    x0, w = min(xs), max(xs) - min(xs) + 1
    y0, h = min(ys), max(ys) - min(ys) + 1
    wx, wy, wr = x0 + 0.33 * w, y0 + 0.60 * h, 0.45 * w

    def red(p):
        return math.hypot(p[0] + .5 - wx, p[1] + .5 - wy) > wr

    roles = {cc.OUTLINE: (W_O, R_O), cc.LIGHT: (W_L, R_L), cc.BASE: (W_B, R_B), cc.SHADE: (W_S, R_S)}
    out: dict[str, set] = {}
    for c, px in base.items():
        white, redc = roles[c]
        out.setdefault(white, set()).update(p for p in px if not red(p))
        out.setdefault(redc, set()).update(p for p in px if red(p))
    return out


cc_shade_mask = cc.shade_mask
cc.cloud_mask = monster_mask
cc.shade_mask = monster_shade


# ---------------------------------------------------------------- drawing helpers

def paths(by_color: dict[str, set]) -> str:
    return "".join(f'<path fill="{c}" d="{cc.to_path(p)}"/>' for c, p in by_color.items() if p)


def art(rows: list[str], palette: dict[str, str], x0: int = 0, y0: int = 0) -> str:
    by_color: dict[str, set] = {}
    for y, row in enumerate(rows):
        for x, ch in enumerate(row):
            if ch != ".":
                by_color.setdefault(palette[ch], set()).add((x0 + x, y0 + y))
    return paths(by_color)


# ---------------------------------------------------------------- eyes

# Arched row: the centre eye sits 2 px higher; neighbours share one ring column.
EYES = [(5, 14, "r"), (17, 14, "w"), (11, 12, "w")]   # the centre eye is drawn last
RING = [".RRRRR.", "RKKKKKR", "RKKKKKR", "RKKKKKR", "RKKKKKR", "RKKKKKR", "RKKKKKR", ".RRRRR."]
# Closed eyes are spread apart (a tight cluster of closed lids reads oddly).
SPREAD = [(3, 17), (18, 17), (11, 15)]


def rings(dim: bool = False) -> str:
    out = ""
    for x, y, kind in EYES:
        ring = RING_RED if kind == "r" else RING_LIGHT
        pal = {"R": cc.DIM.get(ring, "#A99EA4") if dim else ring, "K": DIM_INK if dim else EYE_INK}
        out += art(RING, pal, x, y)
    return out


def per_eye(rows: list[str], palette: dict[str, str], only=None) -> str:
    """A glyph drawn inside every open eye; (0, 0) is the eye's top-left interior
    pixel (the interior is 5 x 6)."""
    return "".join(art(rows, palette, x + 1, y + 1) for i, (x, y, _) in enumerate(EYES)
                   if only is None or i in only)


def spread(rows: list[str], color: str = EYE_INK) -> str:
    return "".join(art(rows, {"K": color}, x, y) for x, y in SPREAD)


IP = {"H": EYE_HI, "W": EYE_HI, "K": EYE_INK, "Y": GOLD, "S": W_S, "D": DIM_INK}
HILITE = ["....", ".HH.", ".HH.", "....", "...H"]          # catch-light, moves with the gaze
STARTLED = ["WWWWW", "WWWWW", "WWKWW", "WKKKW", "WWKWW", "WWWWW"]
X_EYE = ["WWWWW", "KWWWK", "WKWKW", "WWKWW", "WKWKW", "KWWWK"]
SWIRL_A = ["KKKKK", "WWWWK", "KKKWK", "KWKWK", "KWWWK", "KKKKK"]
SWIRL_B = [r[::-1] for r in SWIRL_A[::-1]]
STAR = ["..Y..", ".YYY.", "YYYYY", ".YYY.", "..Y..", "....."]
HALF = ["SSSSS", "SSSSS", "KKKKK", ".....", ".HH..", "....."]   # heavy lid over a low gaze
CLOSED = ["K.....K", ".KKKKK."]                                  # relaxed, curving down
ARC = [".KKKKK.", "K.....K"]                                     # ^ happy


# ---------------------------------------------------------------- mouth and cheeks

MP = {"K": MOUTH_INK, "M": MOUTH, "W": EYE_HI, "T": TONGUE}
MOUTH_X, MOUTH_Y = 10, 23
SMILE = [".K......K.", "..KKKKKK..", "...W..W..."]                 # rest: smile with two baby fangs
GRIN = ["..KKKKKK..", "..KWMMWK..", "...KTTK...", "....KK...."]
SMALL = ["...KKKK..."]
SMIRK = [".......K..", "...KKKK..."]
O_MOUTH = ["....KK....", "...KMMK...", "....KK...."]
WAVY = ["..K.K.K...", "...K.K.K.."]
CAT = ["...K.K.K..", "....K.K..."]
YAWN = {
    1: ["....KK....", "...KMMK...", "....KK...."],
    2: ["...KKKK...", "..KMMMMK..", "..KMTTMK..", "...KKKK..."],
    3: ["..KKKKKK..", ".KMMMMMMK.", ".KMMMMMMK.", ".KMTTTTMK.", "..KKKKKK.."],
}
TYPE = [  # focused: the tongue pokes out while typing, sliding along
    ["...KKKK..."],
    ["...KKKK...", "...T......"],
    ["...KKKK...", ".....T...."],
    ["...KKKK...", "......T..."],
]


def mouth(rows: list[str], dy: int = 0) -> str:
    return art(rows, MP, MOUTH_X, MOUTH_Y + dy)


BLUSH_SVG = art(["BBB", "BBB"], {"B": BLUSH}, 1, 21) + art(["BBB", "BBB"], {"B": BLUSH}, 26, 21)
COOL_LIDS = {1}  # the right eye half-shut for "cool"


def face_defs() -> dict[str, str]:
    """Every face part the engine's FACES table names. Open-eyed faces sit on the
    rings (their own layer); closed-eyed faces draw spread lids without rings."""
    return {
        "eye-rings-dim": rings(dim=True),
        "face-o": per_eye(STARTLED, IP) + mouth(O_MOUTH),
        "face-sleep": spread(CLOSED) + mouth(SMALL),
        "face-dizzy-a": per_eye(SWIRL_A, IP) + mouth(WAVY),
        "face-dizzy-b": per_eye(SWIRL_B, IP) + mouth(WAVY),
        "face-x": per_eye(X_EYE, IP) + mouth(WAVY),
        "face-star": per_eye(STAR, IP) + mouth(GRIN),
        "face-oO": per_eye(STARTLED, IP, only={0}) + per_eye(HILITE, IP, only={1, 2}) + mouth(WAVY),
        "face-wink": spread(ARC) + mouth(CAT),
        "eyes-line": spread(CLOSED),
        "mouth-u": mouth(SMALL),
        "mouth-smirk": mouth(SMIRK),
        "lid-half": per_eye(HALF, IP),
        "face-cool": per_eye(HILITE, IP, only={0, 2}) + per_eye(HALF, IP, only=COOL_LIDS) + mouth(SMIRK),
        **{f"type-{k}": mouth(rows) for k, rows in enumerate(TYPE)},
    }


# Faces: blush first, then the rings (open eyes only), then the parts.
OPEN = ["eye-rings"]
FACES = {
    "rest": OPEN + ["eyes-open", "cursor"], "shut": ["eyes-shut", "cursor"],
    "happy": ["blush", "face-happy"], "rest-blush": ["blush"] + OPEN + ["eyes-open", "cursor"],
    "caret": ["face-caret"], "caret-blush": ["blush", "face-caret"],
    "o": OPEN + ["face-o"], "sleep": ["face-sleep"],
    "dizzy-a": OPEN + ["face-dizzy-a"], "dizzy-b": OPEN + ["face-dizzy-b"],
    "x": OPEN + ["face-x"], "x-dim": ["eye-rings-dim", "face-x-dim"], "star": OPEN + ["face-star"],
    "oO": OPEN + ["face-oO"], "wink": ["blush", "face-wink"], "line": ["eyes-line", "mouth-u"],
    "smirk": OPEN + ["eyes-open", "mouth-smirk"], "half": OPEN + ["lid-half", "cursor"],
    "cool": OPEN + ["face-cool"],
    **{f"focus-{k}": OPEN + ["eyes-open", f"type-{k}"] for k in range(4)},
}
FACE_IDS = ["eye-rings", "eye-rings-dim", "eyes-open", "eyes-shut", "cursor", "face-happy", "blush", "face-caret",
            "face-o", "face-sleep", "face-dizzy-a", "face-dizzy-b", "face-x", "face-x-dim", "face-star", "face-oO",
            "face-wink", "eyes-line", "mouth-u", "mouth-smirk", "lid-half", "face-cool",
            "type-0", "type-1", "type-2", "type-3"]
cc.FACES.clear()
cc.FACES.update(FACES)
cc.FACE_IDS[:] = FACE_IDS
cc.FACE_LAYERS[:] = [(f"f-{i}", use(i)) for i in FACE_IDS]


class Pose(cc.Pose):
    """The cloud blinks its ">_" cursor; the monster's cursor is its mouth, so it
    always stays on."""

    def face(self, name, x, y, look=(0, 0), cursor=True):
        super().face(name, x, y, look, True)


cc.Pose = Pose


# ---------------------------------------------------------------- hands

# 8 x 7 mitten with a thumb lobe and a crease, so the hands read as hands. The red
# (right) mitten has its thumb on the left, towards the body; the white one is its
# mirror. Drawn 2 px left and 1 px up of the engine's 5 x 5 hand spot so it stays
# centred on it.
MITTEN = ["..OOOOO.",
          ".OLLLBBO",
          "OOLBBBBO",
          "OLOBBBSO",
          "OLBBBBSO",
          ".OBBBSSO",
          "..OOOOO."]
MITTEN_W = [r[::-1] for r in MITTEN]
W_PAL = {"O": W_O, "L": W_L, "B": W_B, "S": W_S}
R_PAL = {"O": R_O, "L": R_L, "B": R_B, "S": R_S}
HAND_W = art(MITTEN_W, W_PAL, -2, -1)
HAND_R = art(MITTEN, R_PAL, -2, -1)


def mitten_at(cx: float, cy: float, side: str) -> str:
    """A mitten centred on (cx, cy), for the crab-skinned states."""
    rows, pal = (MITTEN_W, W_PAL) if side == "w" else (MITTEN, R_PAL)
    return art(rows, pal, round(cx - 4), round(cy - 3.5))


def hand_layers(*names: str) -> list:
    return [(n, use("hand-r" if n == "hr" else "hand")) for n in names]


cc.hand_layers = hand_layers
L_REST, R_REST = cc.L_REST, cc.R_REST


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
    <!-- round body: white left, cherry crescent right, tonal 1 px outline, light top/left -->
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
    <g id="face-happy">{spread(ARC)}{mouth(GRIN)}</g>
    <g id="blush">{BLUSH_SVG}</g>
    <g id="face-caret">{spread(ARC)}{mouth(SMILE)}</g>
    <g id="eyes-open">{per_eye(HILITE, IP)}</g>
    <g id="eyes-shut">{spread(CLOSED)}</g>
    <g id="cursor">{mouth(SMILE)}</g>
    <g id="mouth-yawn-1">{mouth(YAWN[1])}</g>
    <g id="mouth-yawn-2">{mouth(YAWN[2])}</g>
    <g id="mouth-yawn-3">{mouth(YAWN[3], -1)}</g>
    <g id="mini-puff">{cc.sprite([".OO.", "OLBO", "OBBO", ".OO."], {"O": R_O, "L": R_L, "B": R_B})}</g>
    <g id="hand">{HAND_W}</g>
    <g id="hand-r">{HAND_R}</g>'''


cc.defs = defs


# ---------------------------------------------------------------- own props

def outlined(rows, palette, outline, diag=True):
    return cc.outlined(rows, palette, outline, diag=diag)


BLOCK_COLORS = {"blue": ("#1F4E9C", "#3D7BE0", "#8FB8FF"), "green": ("#1E6B34", "#3CB45A", "#8FE3A2"),
                "gold": ("#8A5A06", "#F2B630", "#FFE08A")}
BLOCK = ["LLLLLLLL", "LBBBBBBS", "LBBBBBBS", "LBBBBBBS", "SSSSSSSS"]
BRACKET = ["........", "..K..K..", ".K....K.", "..K..K..", "........"]  # < > on the gold block


def block(color: str, code: bool = False) -> str:
    o, b, l = BLOCK_COLORS[color]
    rows = BLOCK
    if code:
        rows = ["".join("K" if k == "K" else c for c, k in zip(r, br)) for r, br in zip(BLOCK, BRACKET)]
    return outlined(rows, {"L": l, "B": b, "S": o, "K": EYE_INK}, W_O)


def own_props() -> dict[str, str]:
    p = {"block-blue": block("blue"), "block-green": block("green"), "block-gold": block("gold", True)}
    p["thumb-up"] = cc.sprite(["..OO...", ".OLBO..", ".OLBO..", "OOLBOOO", "OLLBBBO", "OLBBBSO", "OBBBBSO",
                               ".OOOOO."], {"O": R_O, "L": R_L, "B": R_B, "S": R_S})
    # error: blinking pixel ERROR label and grey smoke puffs
    font = {"E": ["KKK", "K..", "KK.", "K..", "KKK"], "R": ["KK.", "K.K", "KK.", "K.K", "K.K"],
            "O": [".K.", "K.K", "K.K", "K.K", ".K."]}
    word = ["".join(font[c][r] + "." for c in "ERROR")[:-1] for r in range(5)]
    p["error-label"] = outlined([r.replace("K", "R") for r in word], {"R": "#FF4B4B"}, "#3A0E12")
    p["smoke"] = outlined([".GG.", "GGGG", ".GG."], {"G": "#A9A3AE"}, "#6E6470", diag=False)
    p["smoke-s"] = outlined(["GG", "GG"], {"G": "#BDB7C1"}, "#6E6470", diag=False)
    # beacon: cyan (( )) arcs, one per radius, shrinking to dotted at the edge
    for i, r0 in enumerate((5, 8, 11)):
        inner, outer = set(), set()
        for y in range(-14, 15):
            for x in range(-14, 15):
                r = math.hypot(x + .5, y + .5)
                ang = abs(math.degrees(math.atan2(y + .5, abs(x + .5))))
                if r0 <= r < r0 + 2 and ang <= 42 and (i < 2 or (x + y) % 2 == 0):
                    (inner if r < r0 + 1 else outer).add((x, y))
        p[f"wave-{i}"] = f'<path fill="#BDEFFF" d="{cc.to_path(inner)}"/><path fill="#40C4FF" d="{cc.to_path(outer)}"/>'
    p["tip-on"] = cc.sprite([".OOO.", "OWYYO", "OYYYO", "OYYYO", ".OOO."], {"O": "#2F353C", "W": "#FFFFFF", "Y": "#FFE36B"})
    # debugger: magnifier held from below, the lens over the right eye
    p["glass"] = cc.sprite([".OOOOOO...", "OCLLCCO...", "OLLCCCO...", "OCCCCCO...", "OCCCCCO...",
                            "OCCCCCO...", ".OOOOOOd..", ".......dW.", "........dW", ".........d"],
                           {"O": "#2F353C", "C": "#BDEFFF", "L": "#FFFFFF", "d": "#5C3922", "W": "#93603E"})
    # waiting_reply: a small speech bubble, its "!" blinks
    p["say-bubble"] = cc.sprite([".OOOOOOOOO.", "OWWWWWWWWWO", "OWWWWWWWWWO", "OWWWWWWWWWO", "OWWWWWWWWWO",
                                 "OWWWWWWWWWO", "OWWWWWWWWWO", "OWWWWWWWWWO", ".OOOOOWWOO.", "......OWO..",
                                 ".......O..."], {"O": EYE_INK, "W": "#FFFFFF"})
    p["say-bang"] = cc.sprite(["RR", "RR", "RR", "..", "RR"], {"R": "#E25A35"})
    # disconnected: Bluetooth badge and its pulsing halo
    bt = [".BBBBBBBBB.", "BBBBBWBBBBB", "BBBBBWWBBBB", "BBWBBWBWBBB", "BBBWBWWBBBB", "BBBBWWBBBBB",
          "BBBWBWWBBBB", "BBWBBWBWBBB", "BBBBBWWBBBB", "BBBBBWBBBBB", ".BBBBBBBBB."]
    p["bt-badge"] = outlined(bt, {"B": "#2F6FE0", "W": "#FFFFFF"}, "#15306B")
    for i, r0 in enumerate((9, 11)):
        ring = {(x, y) for y in range(-14, 15) for x in range(-14, 15) if r0 <= math.hypot(x + .5, y + .5) < r0 + 1}
        p[f"bt-halo-{i}"] = f'<path fill="#8FB8FF" fill-opacity="{0.8 - 0.35 * i}" d="{cc.to_path(ring)}"/>'
    return p


# ---------------------------------------------------------------- welding props (building)

STEEL_O, STEEL_D, STEEL, STEEL_L = "#2F353C", "#6B737D", "#A9B2BC", "#DCE2E8"
HOT, HOT_L, WARM = "#FF7A1A", "#FFE36B", "#C2551E"
BEAM_H = 20


def welding_props() -> dict[str, str]:
    flange = ["OOOOOOOOO", "OLLLLLLSO", "OOOOLSOOO"]
    web = ["...OLSO.."]
    beam = flange + web * (BEAM_H - 6) + flange[::-1]
    p = {"beam": cc.sprite(beam, {"O": STEEL_O, "L": STEEL_L, "S": STEEL_D})}
    p["torch"] = cc.sprite(["...OOO....",
                            "OOOODDOOO.",
                            "ORRODDLLLO",
                            "OOOODDOOO.",
                            "...OOO...."], {"O": STEEL_O, "R": R_B, "D": STEEL_D, "L": "#C98A3A"})
    p["flame"] = cc.sprite(["W.", "WY", "W."], {"W": "#FFFFFF", "Y": HOT_L})
    p["spark-a"] = cc.sprite(["Y...Y..", ".Y.Y...", "..W..YY", ".Y.Y...", "Y...Y.."], {"Y": HOT_L, "W": "#FFFFFF"})
    p["spark-b"] = cc.sprite(["..Y....", "Y.Y.Y..", ".YWY...", "Y.Y.YY.", "..Y...Y"], {"Y": HOT, "W": HOT_L})
    for k, c in enumerate((HOT_L, HOT, WARM)):
        p[f"seam-{k}"] = f'<path fill="{c}" d="M0 0h1v1h-1z"/>'
    p["smoke-w"] = cc.outlined([".G.", "GGG"], {"G": "#C9C4CC"}, "#8A848E", diag=False)
    return p


def kit() -> dict[str, str]:
    """The cloud's kit() with our bodies (no dotted dim outline: tonal outlines are
    two colours) plus our faces and props."""
    lib = {}
    for key, (did, args) in cc.BODIES.items():
        if args is not None:
            puff, sx, sy, pal = args
            lib[did] = cc.body_variant(monster_mask(puff, sx, sy), pal)
    lib.update(face_defs())
    lib.update(cc.props())
    lib["face-x-dim"] = lib["face-x"].replace(EYE_INK, DIM_INK)
    lib.update(own_props())
    lib.update(welding_props())
    return lib


cc.LIB = kit()
LIB = cc.LIB


# ---------------------------------------------------------------- idle

# Rings ride the face: shown with the open eyes, hidden with the shut ones and the
# kawaii face; the cursor (now the mouth) only gives way to the yawn.
cc.IDLE_SCENE = cc.IDLE_SCENE.replace('<g class="ey-look">', '<g class="ey-open"><use href="#eye-rings"/></g>\n      <g class="ey-look">')
cc_idle_timeline = cc.idle_timeline


def idle_timeline() -> dict:
    tl = cc_idle_timeline()
    yawning = [any(tl[f"yawn-{k}"][0][f] for k in (1, 2, 3)) for f in range(cc.FRAMES)]
    tl["cursor"] = ([not y for y in yawning], tl["cursor"][1])
    return tl


cc.idle_timeline = idle_timeline


def render_idle() -> str:
    return cc.render_idle().replace("Codex cloud v2 idle", "Monster v2 idle (Codex cloud v2 beats)")


# ---------------------------------------------------------------- writer

def write_state(name: str, fps: int, frames: int, beats: str, layers: list, pose,
                viewbox: str = "-15 -25 45 45", wrap: str = 'transform="scale(.5)"', hold_s: float = 0.75) -> str:
    timeline, rows, ids = cc.animate(frames, fps, layers, pose, hold_s)
    extra = "\n".join(f'    <g id="{i}">{LIB[i]}</g>' for i in sorted(ids) if i in LIB)
    loop_s = f"{frames / fps:g}"
    comment = (f"Monster v2 {name}: {loop_s} s loop, poses at {fps} fps ({frames} frames); appearance swaps "
               f"step-end, motion interpolated. {beats}")
    scene = f"  <g {wrap}>\n{rows}\n  </g>\n"
    svg = cc.svg_doc(comment, loop_s, timeline, scene, extra, viewbox)
    (OUT / f"monster-{name}-v2.svg").write_text(svg, encoding="utf-8")
    return name


cc.write_state = write_state

BASE = cc.SHADOW_LAYERS + cc.BODY_LAYERS + cc.FACE_LAYERS


def L(*names: str) -> list:
    """Prop layers: "key=lib-id" or just "lib-id"."""
    return [(n.split("=")[0], use(n.split("=")[-1])) for n in names]


# ================================================================ crab-beat states
# Each follows the beats, fps and loop of the Claude crab's file of the same state.


def render_error() -> str:
    """clawd-error-v2: collapsed flat, X eyes, three little stars orbit above the
    head, hands limp on the floor, a slow defeated breath, grey smoke rises and a
    red ERROR label blinks above. 2.4 s."""
    fps, n = 10, 24

    def pose(f):
        exhale = (f // 12) % 2
        p = Pose().body("dfl" if exhale else "dfl2", 0, 0, "x")
        p["hl"] = (-3, 25)
        p["hr"] = (28, 25)
        for k in range(3):  # stars on a flat ellipse, 120 degrees apart
            a = 2 * math.pi * (f / n + k / 3)
            p[f"star{k}"] = (round(13 + 11 * math.cos(a)), round(2 + 2 * math.sin(a)))
        for k, (x0, off) in enumerate(((10, 0), (18, 8), (13, 16))):
            age = (f - off) % n
            if age < 10:
                p[f"smoke{k}" if age < 5 else f"smokes{k}"] = (x0 + age // 3, -1 - age)
        if (f // 4) % 2 == 0:
            p["label"] = (2, -16)
        return p

    layers = (BASE + hand_layers("hl", "hr") + L("star0=sparkle-s", "star1=sparkle-s", "star2=sparkle-s") +
              [(f"smoke{k}", use("smoke")) for k in range(3)] +
              [(f"smokes{k}", use("smoke-s")) for k in range(3)] + L("label=error-label"))
    return write_state("error", fps, n, "Crab beats: collapsed flat with X eyes, three stars orbit above, mittens "
                       "limp on the floor, slow breath, grey smoke rises, a red ERROR label blinks.", layers, pose)


def render_happy() -> str:
    """clawd-happy-v2: two hops with squash, flapping hands, happy eyes,
    twinkling sparkles. 2 s at 10 fps."""
    fps, n = 10, 20
    hop = [("sq", 0), ("st", -2), ("n", -4), ("n", -5), ("n", -4), ("n", -2), ("sq", 0), ("n", 0), ("n", 0), ("n", 0)]
    spots = [((-8, 2), "sparkle"), ((31, -1), "sparkle-s"), ((33, 14), "sparkle"), ((-9, 17), "sparkle-s")]

    def pose(f):
        v, dy = hop[f % 10]
        p = Pose().body(v, 0, dy, "caret-blush", shadow=False)
        p["sh" if dy == 0 else "sh-s"] = (0, 0)
        air = hop[(f - 1) % 10][1] < 0
        flap = -2 if (f // 2) % 2 else 0
        p["hl"] = (-4, 9 + flap + dy) if air else at(L_REST, 0, -1)
        p["hr"] = (29, 9 + flap + dy) if air else at(R_REST, 0, -1)
        for k, (xy, _) in enumerate(spots):
            if (f + 5 * k) % 10 < 4:
                p[f"spk{k}"] = xy
        return p

    layers = BASE + hand_layers("hl", "hr") + [(f"spk{k}", use(s)) for k, (_, s) in enumerate(spots)]
    return write_state("happy", fps, n, "Crab beats: ^ ^ eyes with blush, two hops with squash and stretch, "
                       "mittens flap while airborne, sparkles twinkle around.", layers, pose, viewbox="-12 -15 40 40")


def render_waiting_reply() -> str:
    """clawd-waiting-reply-v2: turn finished, waiting for the next prompt. Wide eyes
    toward the viewer, blush and smile, the left mitten waves, a bubble hops with a
    blinking "!". 2 s at 8 fps."""
    fps, n = 8, 16
    wave = [(-3, 8), (-5, 7), (-3, 8), (-5, 9)]

    def pose(f):
        p = Pose().body("n", 0, 0, "rest-blush")
        p["hl"] = wave[(f // 2) % 4]
        p["hr"] = R_REST
        hop = -1 if f % 8 in (0, 1) else 0
        p["bubble"] = (22, -12 + hop)
        if (f // 4) % 2 == 0:
            p["bang"] = (26, -10 + hop)
        return p

    layers = BASE + hand_layers("hl", "hr") + L("bubble=say-bubble", "bang=say-bang")
    return write_state("waiting_reply", fps, n, "Crab beats: wide eyes toward you, blush and smile, the white "
                       "mitten waves, a bubble hops with a blinking !.", layers, pose)


def render_alert() -> str:
    """clawd-notification-v2 (the crab's alert): startled recoil with a look right
    and a red "!" popping up, a squash, six stretch-and-land jumps with the mittens
    flapping up and out, then recover. 4 s at 10 fps."""
    fps, n = 10, 40
    jump = [("st", -2), ("n", -4), ("n", -2), ("sq", 0)]

    def beat(f):
        if f < 6:
            return "n", -1 if f < 3 else 0, 0, "o"
        if f < 8:
            return "sq", 0, 0, "o"
        if f < 32:
            v, dy = jump[(f - 8) % 4]
            return v, 0, dy, "rest"
        return "n", 0, 0, "rest"

    def pose(f):
        v, dx, dy, face = beat(f)
        p = Pose().body(v, dx, dy, face, look=(1, 0) if f < 8 else (0, 0), shadow=False)
        p["sh" if dy == 0 else "sh-s"] = (0, 0)
        air = beat(f - 1)[2] < 0
        p["hl"] = (-5, 6 + dy) if air else at(L_REST, dx, 0)
        p["hr"] = (30, 6 + dy) if air else at(R_REST, dx, 0)
        if 2 <= f < 34:
            p["bang"] = (30, -12 + (-2 if f in (2, 3) else 0))
        return p

    layers = BASE + hand_layers("hl", "hr") + L("bang")
    return write_state("alert", fps, n, "Crab beats: startled recoil looking right with a red ! popping up, "
                       "squash, six stretch-and-land jumps with mittens flapping up and out, recover.", layers, pose)


def render_cool() -> str:
    fps, n = 6, 30

    def pose(f):
        on = 6 <= f < 26
        dy = -1 if on and (f // 6) % 2 and f > 8 else 0
        p = Pose().body("sq" if f == 6 else "n", 0, dy, "cool" if on else "rest", look=(0, -1) if f < 6 else (0, 0))
        p["hl"] = at(L_REST, 0, dy)
        if on:
            p["thumb"] = (26, 11 + dy - (1 if f in (7, 8) else 0))
        else:
            p["hr"] = R_REST
        if f in (10, 11, 18, 19):
            p["spk-a"] = (30, 2)
        if f in (14, 15, 22, 23):
            p["spk-b"] = (-4, 4)
        return p

    layers = BASE + hand_layers("hl", "hr") + L("thumb=thumb-up", "spk-a=sparkle", "spk-b=sparkle-s")
    return write_state("cool", fps, n, "Grid v2 COOL: no glasses; the right eye half-lidded, a lopsided smile "
                       "and a red thumbs-up that bounces while two sparkles twinkle.", layers, pose, hold_s=1.5)



# ================================================================ crab-skinned states
# These states are the Claude crab's own animation files with the crab swapped for
# the monster: same scene, same CSS timing, same props. Legs are emptied, the torso
# becomes the monster body (with its mouth), pincers become mittens centred where the
# pincers were, the eye groups become monster eyes, and props that sit on the crab's
# head move up to the monster's head (the crab's top is y 12, the monster's y 2).

import re

CRAB = Path(__file__).resolve().parents[1] / "desktop" / "renderer" / "assets"
HEAD_UP = -10


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


def shifted(rows: list[str], dx: int, dy: int) -> list[str]:
    w, h = len(rows[0]), len(rows)
    grid = [["."] * w for _ in range(h)]
    for y, r in enumerate(rows):
        for x, c in enumerate(r):
            if c != "." and 0 <= x + dx < w and 0 <= y + dy < h:
                grid[y + dy][x + dx] = c
    return ["".join(r) for r in grid]


HILITE5 = [".....", ".HH..", ".HH..", ".....", "...H.", "....."]
OPEN_EYES = rings() + per_eye(HILITE5, IP)
CRAB_EYES = {
    "eyes-open": OPEN_EYES, "eyes-focus": OPEN_EYES,
    "eyes-ur": rings() + per_eye(shifted(HILITE5, 1, -1), IP),
    "eyes-wide": rings() + per_eye(STARTLED, IP),
    "eyes-shut": spread(CLOSED), "eyes-shut-hi": spread(CLOSED),
    "eyes-squint": rings() + per_eye(HALF, IP),
    "eye-l-squint": rings() + per_eye(HALF, IP, only={0}) + per_eye(HILITE5, IP, only={1, 2}),
}


def torso(name: str) -> str:
    """Monster body for a crab torso def: the squashed 24x13 torso squashes, the
    leaning 22x14-lpA... torsos lean by A/4 px, everything else is the plain body."""
    if name == "torso-24x13":
        return cc.layer(monster_shade(monster_mask(0, 1.08, 0.88))) + mouth(SMALL, 2)
    m = re.match(r"torso-\d+x\d+-lp(\d+)", name)
    dx = round(int(m.group(1)) / 4) if m else 0
    body = cc.layer(monster_shade(monster_mask(0))) + mouth(SMILE)
    return f'<g transform="translate({dx} 0)">{body}</g>' if dx else body


def crab_skin(state: str, src: str, shifts: dict, edit=None) -> str:
    svg = (CRAB / src).read_text(encoding="utf-8")
    for gid, a, b in sorted(def_groups(svg), key=lambda g: -g[1]):
        content = svg[a:b]
        if gid.startswith("leg"):
            new = ""
        elif gid.startswith("torso"):
            new = torso(gid)
        elif gid.startswith("arm-"):
            x0, y0, x1, y1 = bbox(content)
            new = mitten_at((x0 + x1) / 2, (y0 + y1) / 2, "w" if gid.startswith("arm-l") else "r")
        elif gid in CRAB_EYES:
            new = CRAB_EYES[gid]
        else:
            dxy = next((v for k, v in shifts.items() if gid == k or (k.endswith("*") and gid.startswith(k[:-1]))), None)
            if dxy is None:
                continue
            new = f'<g transform="translate({dxy[0]} {dxy[1]})">{content}</g>'
        svg = svg[:a] + new + svg[b:]
    if edit:
        svg = edit(svg)
    svg = re.sub(r"<!--.*?-->", "", svg, count=1, flags=re.S)
    svg = svg.replace("<defs>", f"<!-- Monster v2 {state}: the Claude crab's {src} (same scene and timing) "
                      "with the monster's body, eyes and mittens. -->\n  <defs>", 1)
    (OUT / f"monster-{state}-v2.svg").write_text(svg, encoding="utf-8")
    return state


def crab_beacon() -> str:
    return crab_skin("beacon", "clawd-working-beacon-v2.svg",
                     {"antenna": (0, HEAD_UP), "tip*": (0, HEAD_UP)},
                     lambda s: re.sub(r'<g class="w(\d+)">', rf'<g transform="translate(0 {HEAD_UP})" class="w\1">', s))


def crab_debugger() -> str:
    # the lens moves from the crab's right eye (y 15) onto the monster's (y 17.5)
    return crab_skin("debugger", "clawd-working-debugger-v2.svg", {"lens": (-1, 3), "handle": (-1, 3)})


def crab_thinking() -> str:
    return crab_skin("thinking", "clawd-working-thinking-v2.svg", {"think-*": (0, HEAD_UP)})


def crab_disconnected() -> str:
    return crab_skin("disconnected", "clawd-disconnected-v2.svg", {"qmark": (0, HEAD_UP), "bang": (0, HEAD_UP)})


def crab_low_battery() -> str:
    return crab_skin("low_battery", "clawd-idle-low-battery-v2.svg", {"battery*": (0, -6)})


def crab_sweeping() -> str:
    return crab_skin("sweeping", "clawd-working-sweeping-v2.svg", {})


# The wizard hat is as wide as the crab's flat head; on the round monster its brim
# sits higher, where the head is about as wide as the brim.
HAT_UP = -6


def crab_wizard() -> str:
    return crab_skin("wizard", "clawd-wizard-v2.svg", {"hat": (0, HAT_UP)})


def crab_hat_mishap() -> str:
    return crab_skin("hat_mishap", "clawd-hat-mishap-v2.svg", {"hat-*": (0, HAT_UP), "spk-*": (0, HAT_UP)})


# ================================================================ building: welding
# Not the crab's hammer nor the cloud's bricks: the monster welds a steel I-beam. The
# red mitten runs a torch down the beam, sparks spray from the tip, the glowing seam
# cools from orange to brown behind it, a puff of smoke, eyes squint in focus.

def render_building() -> str:
    fps, n = 8, 24
    seam_len = 12
    bx, by = 33, 29 - BEAM_H  # the beam stands on the ground at the right

    def pose(f):
        welding = f < seam_len
        shake = (f % 2) if welding else 0
        p = Pose().body("n", 0, 0, "half" if welding else "rest", look=(1, 0))
        p["hl"] = at(L_REST, 0, -1 if (f // 6) % 2 else 0)
        tip_y = by + 4 + min(f, seam_len - 1)  # the torch follows the seam down
        p["hr"] = (24 + shake, tip_y - 1)
        p["torch"] = (26 + shake, tip_y - 2)
        if welding:
            p["flame"] = (36, tip_y - 1)
            p["spk/a" if f % 2 == 0 else "spk/b"] = (37, tip_y - 3)
        for k in range(min(f + 1, seam_len)):  # hot at the torch, cooling behind it
            age = (f - k) if welding else 99
            heat = 0 if age < 2 else 1 if age < 5 else 2 if age < 9 else None
            if heat is not None:
                p[f"seam{k}/{heat}"] = (bx + 4, by + 4 + k)
        if 14 <= f < 22:
            p["smoke"] = (35 + (f - 14) // 3, by + 2 - (f - 14))
        p["beam"] = (bx, by)
        return p

    seam = [(f"seam{k}/{h}", use(f"seam-{h}")) for k in range(seam_len) for h in range(3)]
    layers = (cc.SHADOW_LAYERS + L("beam") + seam + cc.BODY_LAYERS + cc.FACE_LAYERS + L("torch") +
              hand_layers("hl", "hr") + L("flame", "spk/a=spark-a", "spk/b=spark-b", "smoke=smoke-w"))
    return write_state("building", fps, n, "Welding: the red mitten runs a torch down a steel I-beam, sparks "
                       "spray, the seam glows and cools from orange to brown, a puff of smoke, eyes squint.",
                       layers, pose)

OWN = {r.__name__.removeprefix("render_"): r for r in (
    render_error, render_happy, render_alert, render_building, render_cool)}
OWN.update({f.__name__.removeprefix("crab_"): f for f in (
    crab_beacon, crab_debugger, crab_thinking, crab_disconnected, crab_low_battery, crab_sweeping,
    crab_wizard, crab_hat_mishap)})
STATE_RENDERERS = [render_waiting_reply] + [OWN.get(r.__name__.removeprefix("render_"), r)
                                            for r in cc.STATE_RENDERERS]


def compare_page(states: list[str]) -> str:
    # Claude idles on the inline SVG of index.html; its file twin is clawd-idle-living-v2.svg.
    clawd = lambda s: f'<img src="../{cc.CLAWD_V2[s]}" alt="">' if s in cc.CLAWD_V2 else ""
    rows = "\n".join(
        f'<tr><th>{s}</th><td>{clawd(s)}</td><td><img src="../codex/cloud-{s}-v2.svg" alt=""></td>'
        f'<td><img src="monster-{s}-v2.svg" alt=""></td></tr>' for s in states)
    return f'''<!doctype html><meta charset="utf-8"><title>Monster v2 gallery</title>
<style>body{{margin:0;padding:24px;background:#1b1f2b;color:#cfd8f0;font:13px system-ui}}
table{{border-collapse:separate;border-spacing:12px}}th{{text-align:right;font-weight:600;padding-right:8px}}
td{{background:#2a3042;border-radius:12px;padding:8px}}img{{width:220px;height:220px;image-rendering:pixelated;display:block}}
thead th{{text-align:center}}</style>
<table><thead><tr><th>state</th><th>Claude v2</th><th>Codex v2</th><th>Monster v2</th></tr></thead>
{rows}
</table>
'''


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "monster-idle-v2.svg").write_text(render_idle(), encoding="utf-8")
    names = ["idle"] + [r() for r in STATE_RENDERERS]
    (OUT / "compare-v2.html").write_text(compare_page(names), encoding="utf-8")
    print(f"wrote {len(names)} monster states and compare-v2.html to {OUT}")


if __name__ == "__main__":
    main()
