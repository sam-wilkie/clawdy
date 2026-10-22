// renderer.js — one product's crab (Phase 3). Each window renders a single AI
// product (window.pet.agent) and shows an "xN" badge when that product has more
// than one active session.
//
// Click-through model (unchanged from the single-window spike):
//   - main.js starts the window with setIgnoreMouseEvents(true, {forward:true}),
//     so the whole window passes clicks through BUT the renderer still gets
//     mousemove events.
//   - When the pointer is over #crab-hit, we ask main to STOP ignoring mouse
//     events so clicks/drag land on the crab; on leave we go back to click-through.
//   - Drag moves THIS window via window.pet.moveWindow.

const crab = document.getElementById("crab");
const hit = document.getElementById("crab-hit");
const badge = document.getElementById("crab-badge");
const label = document.getElementById("crab-label");

// Human-readable product name for the always-visible identity label. Set once:
// each window renders a single product for its whole lifetime.
const AGENT_LABELS = { claude: "Claude", codex: "Codex", kiro: "Kiro", opencode: "OpenCode", antigravity: "Antigravity", pi: "Pi" };
const AGENT = (window.pet && window.pet.agent) || "claude";
if (label) label.textContent = AGENT_LABELS[AGENT] || AGENT;
crab.dataset.agent = AGENT;

let overBody = false;
let dragging = false;
let permQueue = [];            // pending approvals, oldest first
let lastX = 0, lastY = 0;
let pressX = 0, pressY = 0;
let movedDuringPress = false;

// A pending approval keeps the buttons clickable even when the pointer leaves
// the pet's body. All paths use the same rule so hover cannot disable a prompt.
function syncMouseInteractivity() {
  window.pet.setInteractive(dragging || overBody || permQueue.length > 0);
}

// --- Shake-to-dizzy detection ------------------------------------------------
// A "shake" is a fast back-and-forth drag: several horizontal direction
// reversals, each above a speed threshold, within a short window. A normal slow
// drag never triggers it. On a shake we play the dizzy oneshot (defined below).
const SHAKE_MIN_SPEED = 6;      // px per mousemove to count as a fast move
const SHAKE_REVERSALS = 3;      // direction flips needed to be a shake
const SHAKE_WINDOW_MS = 1000;   // flips must happen within this window
let shakeDir = 0;               // last horizontal direction (-1/0/+1)
let shakeFlips = [];            // timestamps of recent qualifying reversals

/** Is a window-space point inside the crab's hit rectangle? */
function pointInHit(clientX, clientY) {
  const r = hit.getBoundingClientRect();
  return clientX >= r.left && clientX <= r.right && clientY >= r.top && clientY <= r.bottom;
}

window.addEventListener("mousemove", (e) => {
  if (dragging) {
    const dx = e.screenX - lastX;
    const dy = e.screenY - lastY;
    if (Math.hypot(e.screenX - pressX, e.screenY - pressY) > 5) movedDuringPress = true;
    lastX = e.screenX;
    lastY = e.screenY;
    if (dx !== 0 || dy !== 0) window.pet.moveWindow(dx, dy);
    detectShake(dx);
    return;
  }
  const inside = pointInHit(e.clientX, e.clientY);
  if (inside !== overBody) {
    overBody = inside;
    syncMouseInteractivity();
  }
});

hit.addEventListener("mousedown", (e) => {
  if (e.button !== 0) return;
  dragging = true;
  lastX = e.screenX;
  lastY = e.screenY;
  pressX = e.screenX;
  pressY = e.screenY;
  movedDuringPress = false;
  crab.dataset.held = "true";
  e.preventDefault();
});

window.addEventListener("mouseup", () => {
  if (!dragging) return;
  dragging = false;
  crab.dataset.held = "false";
  if (!movedDuringPress) window.pet.openPanel();
  shakeDir = 0;
  shakeFlips = [];
  syncMouseInteractivity();
});

/** Count fast horizontal direction reversals; on enough of them within the
 *  window, make the crab dizzy. Called on every drag mousemove with the frame's
 *  horizontal delta. */
function detectShake(dx) {
  if (Math.abs(dx) < SHAKE_MIN_SPEED) return;
  const dir = dx > 0 ? 1 : -1;
  if (shakeDir !== 0 && dir !== shakeDir) {
    const now = Date.now();
    shakeFlips.push(now);
    shakeFlips = shakeFlips.filter((t) => now - t <= SHAKE_WINDOW_MS);
    if (shakeFlips.length >= SHAKE_REVERSALS) {
      shakeFlips = [];
      playOneshot("dizzy");
    }
  }
  shakeDir = dir;
}

// --- Per-state animations ----------------------------------------------------
// Overlay <img> shows the animated SVG for each state; idle uses the inline SVG.
let img = document.getElementById("crab-anim");
const STATES = {
  idle:         null,
  dizzy:        { src: "assets/clawd-dizzy-v2.svg",              vb: [-15, -25, 45] },
  happy:        { src: "assets/clawd-happy-v2.svg",             vb: [-12, -15, 40] },
  sleeping:     { src: "assets/clawd-sleeping-v2.svg",          vb: [-10, -20, 40] },
  wake:         { src: "assets/clawd-wake-v2.svg",              vb: [-15, -25, 45] },
  thinking:     { src: "assets/clawd-working-thinking-v2.svg",  vb: [-15, -25, 45] },
  typing:       { src: "assets/clawd-working-typing-v2.svg",    vb: [-15, -25, 45] },
  building:     { src: "assets/clawd-working-building-v2.svg",  vb: [-15, -25, 45] },
  notification: { src: "assets/clawd-notification-v2.svg",      vb: [-15, -25, 45] },
  confused:     { src: "assets/clawd-working-confused-v2.svg",  vb: [-15, -25, 45] },
  debugger:     { src: "assets/clawd-working-debugger-v2.svg",  vb: [-15, -25, 45] },
  conducting:   { src: "assets/clawd-working-conducting-v2.svg", vb: [-15, -25, 45] },
  beacon:       { src: "assets/clawd-working-beacon-v2.svg",    vb: [-15, -25, 45] },
  sweeping:     { src: "assets/clawd-working-sweeping-v2.svg",  vb: [-15, -25, 45] },
  hat_mishap:   { src: "assets/clawd-hat-mishap-v2.svg",        vb: [-15, -25, 45] },
  low_battery:  { src: "assets/clawd-idle-low-battery-v2.svg",  vb: [-15, -25, 45] },
  no_credits:   { src: "assets/clawd-no-credits-v2.svg",        vb: [-15, -25, 45] },
  waiting_reply:{ src: "assets/clawd-waiting-reply-v2.svg",     vb: [-15, -25, 45] },
  wizard:       { src: "assets/clawd-wizard-v2.svg",            vb: [-15, -25, 45] },
  juggling:     { src: "assets/clawd-juggling-v2.svg",          vb: [-15, -25, 45] },
  grooving:     { src: "assets/clawd-grooving-v2.svg",          vb: [-15, -25, 45] },
  walking:      { src: "assets/clawd-walking-v2.svg",           vb: [-15, -25, 45] },
  going_away:   { src: "assets/clawd-going-away-v2.svg",        vb: [-15, -25, 45] },
  disconnected: { src: "assets/clawd-disconnected-v2.svg",      vb: [-15, -25, 45] },
  mini_clawd:   { src: "assets/clawd-mini-clawd-v2.svg",        vb: [-15, -25, 45] },
  cool:         { src: "assets/clawd-cool-v2.svg",              vb: [-15, -25, 45] },
  error:        { src: "assets/clawd-error-v2.svg",             vb: [-15, -25, 45] },
  idea:         { src: "assets/clawd-idea-v2.svg",              vb: [-15, -25, 45] },
};

// Codex has its own pixel-art cloud (the Codex logo with a ">_" face), drawn
// with the Clawd v2 art rules by tools/codex_cloud_pixel.py. The state names
// still come from the daemon, so only the art selection changes in a Codex
// window: every state uses assets/codex/cloud-<state>-v2.svg with the same vb
// as the matching Clawd entry (each file's viewBox equals that vb), so the art
// lines up exactly like Clawd's. Idle has no Clawd file (Clawd idles on the
// inline SVG), so its cloud uses the full 45-unit box.
// Codex also has its own "alert" (urgent: needs permission or input), distinct
// from "notification" (gentle: a message arrived). resolveState() finds it
// before the ALIAS fallback, which Clawd still uses (alert -> notification).
const FULL_VB = [-15, -25, 45];
const CODEX_STATES = Object.fromEntries(
  [...Object.keys(STATES), "alert"].map((state) => [
    state,
    { src: `assets/codex/cloud-${state}-v2.svg`, vb: (STATES[state] && STATES[state].vb) || FULL_VB },
  ]),
);
// The brand monster (tools/monster_pixel.py) is the default pet: every agent with
// no art set of its own (kiro, opencode, antigravity, pi, unknown) uses
// assets/monster/monster-<state>-v2.svg, with the same states and vb as Codex.
const MONSTER_STATES = Object.fromEntries(
  Object.keys(CODEX_STATES).map((state) => [
    state,
    { src: `assets/monster/monster-${state}-v2.svg`, vb: CODEX_STATES[state].vb },
  ]),
);
const ART = AGENT === "claude" ? "crab" : AGENT === "codex" ? "cloud" : "monster";
crab.dataset.art = ART;
// The default monster is a character of its own, Mochi (docs/mochi.md): it says
// its name in the tooltip, while the label keeps naming the agent it works for.
if (ART === "monster") hit.title = "Mochi · Clic para ver actividad · Arrastra para mover";
const ART_STATES = { crab: STATES, cloud: CODEX_STATES, monster: MONSTER_STATES }[ART];

const ALIAS = {
  working_1: "typing", working_2: "typing", working_3: "typing",
  alert: "notification",
};

function resolveState(name) {
  if (!name) return "idle";
  if (ART_STATES[name] !== undefined) return name;
  if (ALIAS[name] && ART_STATES[ALIAS[name]] !== undefined) return ALIAS[name];
  return "idle";
}

// Badge and name label are positioned from the art box (vb), not the window, so they
// stay attached to the sprite when its box is scaled. Full box (vb -15,-25,45) gives the
// original positions: label just below the box, badge at the top-right corner.
function placeOverlays(vb) {
  const left = (15 + vb[0]) / 45 * 100;
  const top = (25 + vb[1]) / 45 * 100;
  const size = vb[2] / 45 * 100;
  if (badge) {
    badge.style.top = (top + size * 0.24) + "%";
    badge.style.right = (100 - (left + size * 0.8)) + "%";
  }
  // Anchored to the window bottom: it must not move with the art box of each state.
  if (label) { label.style.top = "auto"; label.style.bottom = "2%"; }
}

function renderState(name) {
  const key = resolveState(name);
  crab.dataset.state = key;
  const s = ART_STATES[key];
  if (!s) { img.hidden = true; img.removeAttribute("src"); return; }

  const fresh = document.createElement("img");
  fresh.id = "crab-anim";
  fresh.className = "crab-layer";
  fresh.alt = "";
  fresh.style.width = (s.vb[2] / 45 * 100) + "%";
  fresh.style.height = (s.vb[2] / 45 * 100) + "%";
  fresh.style.left = ((15 + s.vb[0]) / 45 * 100) + "%";
  fresh.style.top = ((25 + s.vb[1]) / 45 * 100) + "%";
  placeOverlays(s.vb);
  fresh.onerror = () => console.error("[pet] FAILED to load:", s.src);
  fresh.src = s.src;
  img.replaceWith(fresh);
  img = fresh;
}

// Warm the cache so swaps don't flash.
Object.keys(ART_STATES).forEach((k) => {
  if (ART_STATES[k]) { const im = new Image(); im.src = ART_STATES[k].src; }
});

// --- xN badge ----------------------------------------------------------------
function renderBadge(count) {
  if (!badge) return;
  if (count > 1) {
    badge.textContent = "x" + count;
    badge.hidden = false;
  } else {
    badge.hidden = true;
  }
}

// --- Pet-side state controller ------------------------------------------------
// Derives the extra web-only states from the daemon's product anim, same as the
// single-window spike did, but driven by this window's product-state updates.
const ONESHOT_MS = { walking: 1500, going_away: 3200, idea: 1500, cool: 5000, happy: 2000, dizzy: 2000 };
const RESTING = new Set(["idle", "sleeping", "low_battery", "no_credits", "waiting_reply", "happy", "alert", "notification"]);

let linked = false;      // daemon connected to the bridge
let base = "idle";       // latest state from the daemon, after mapping
let shown = null;        // what is on screen right now
let oneshot = null;      // { name, timer } while a oneshot plays
let seenFirst = false;   // first product-state received (for walking oneshot)
let leaving = false;     // going_away is playing; main closes the window after it

// Codex rests at the end of a turn instead of raising its prompt bubble: a
// "your turn" that needs no action reads better as a quiet idle cloud.
const CALM_OVERRIDES = AGENT === "codex" ? { waiting_reply: "idle" } : {};

function show(name) {
  if (name === shown) return;
  shown = name;
  renderState(name);
}

function refresh() {
  if (leaving) return;
  if (!linked) { show("disconnected"); return; }
  if (oneshot) return;
  show(base);
}

function playOneshot(name) {
  if (oneshot) clearTimeout(oneshot.timer);
  oneshot = { name, timer: setTimeout(() => { oneshot = null; refresh(); }, ONESHOT_MS[name] || 1500) };
  if (linked) show(name);
}

// 'conducting' tracking: the daemon keeps reporting it for as long as the Agent
// tool is the main agent's last tool, so the pet times it itself (see
// AnimMap.mapAnim) and settles into 'grooving' once subagents are working.
let conductSince = null;   // Date.now() when the daemon started reporting it
let conductTimer = null;   // re-evaluates the mapping when CONDUCT_MS elapses
let lastProduct = null;    // latest product-state, for the timer re-evaluation

function handleProductState(state) {
  // A state update means main cancelled the leave (the product came back).
  leaving = false;
  linked = !!state.linked;
  renderBadge(Number(state.count) || 1);
  lastProduct = state;

  if (!linked) { refresh(); return; }

  // Track how long the daemon has been saying 'conducting'.
  if (state.anim === "conducting") {
    if (conductSince === null) conductSince = Date.now();
  } else {
    conductSince = null;
  }
  clearTimeout(conductTimer);
  conductTimer = null;
  const bg = Number(state.bg) || 0;
  const conductMs = conductSince === null ? Infinity : Date.now() - conductSince;
  if (state.anim === "conducting" && bg > 0 && conductMs < AnimMap.CONDUCT_MS) {
    conductTimer = setTimeout(() => handleProductState(lastProduct), AnimMap.CONDUCT_MS - conductMs + 20);
  }

  const mapped = AnimMap.mapAnim(state.anim, bg, conductMs, !!state.exhausted);
  const next = CALM_OVERRIDES[mapped] || mapped;
  const prev = base;

  // First time we see this product's window: play the walking entrance.
  if (!seenFirst) {
    seenFirst = true;
    base = next;
    playOneshot("walking");
    return;
  }

  base = (next === "happy" || next === "cool") ? prev : next;

  if (next === "happy" || next === "cool") { playOneshot(next); return; }
  if (next === "thinking" && RESTING.has(prev) && !oneshot) { playOneshot("idea"); return; }
  refresh();
}

window.pet.onProductState(handleProductState);

window.pet.onLeave(() => {
  if (oneshot) { clearTimeout(oneshot.timer); oneshot = null; }
  leaving = true;
  renderBadge(1);
  shown = "going_away";
  renderState("going_away");
});

// --- Permission bubble -------------------------------------------------------
// A FIFO of pending requests (the daemon can have several); we show the first.
// Clicking Allow/Deny replies to the daemon and advances to the next, mirroring
// the SDL2 simulator's bubble. While a bubble is up the whole window must be
// interactive (not click-through) so the buttons are clickable.
const permCard = document.getElementById("perm-card");
const permProject = document.getElementById("perm-project");
const permTool = document.getElementById("perm-tool");
const permCount = document.getElementById("perm-count");
const permSummary = document.getElementById("perm-summary");
const permAllow = document.getElementById("perm-allow");
const permDeny = document.getElementById("perm-deny");

// Guard against an accidental click landing on a bubble that just appeared.
const PERM_CLICK_GUARD_MS = 350;
let permShownAt = 0;

function renderPermission() {
  if (permQueue.length === 0) {
    if (!permCard.hidden) window.pet.setExpanded(false);
    permCard.hidden = true;
    syncMouseInteractivity();
    return;
  }
  const r = permQueue[0];
  permProject.textContent = r.project || "";
  permTool.textContent = r.tool || "";
  permSummary.textContent = r.summary || r.tool || "";
  permCount.textContent = permQueue.length > 1 ? "+" + (permQueue.length - 1) : "";
  if (permCard.hidden) {
    window.pet.setExpanded(true); // room above the crab so the bubble doesn't cover it
    permCard.hidden = false;
    permShownAt = Date.now();
  }
  syncMouseInteractivity();
}

function answerPermission(decision) {
  if (permQueue.length === 0) return;
  if (Date.now() - permShownAt < PERM_CLICK_GUARD_MS) return; // ignore stray clicks
  const r = permQueue.shift();
  window.pet.sendPermissionDecision({
    event: "permission_decision", id: r.id, nonce: r.nonce, decision,
  });
  permShownAt = Date.now(); // re-arm the guard for the next queued request
  renderPermission();
}

permAllow.addEventListener("click", () => answerPermission("allow"));
permDeny.addEventListener("click", () => answerPermission("deny"));

window.pet.onPermissionRequest((req) => {
  if (!req || !req.id) return;
  if (permQueue.some((p) => p.id === req.id)) return; // de-dup
  permQueue.push(req);
  renderPermission();
});

window.pet.onPermissionClear((msg) => {
  if (!msg) return;
  const before = permQueue.length;
  permQueue = permQueue.filter((p) => p.id !== msg.id);
  if (permQueue.length !== before) renderPermission();
});

// Ask main for our initial state, then render.
window.pet.requestState();
refresh(); // "disconnected" until the first linked product-state arrives
