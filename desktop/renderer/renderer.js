// renderer.js — click-through boundary + drag for the Clawdy desktop pet (spike).
//
// Click-through model (Electron transparent window):
//   - main.js starts the window with setIgnoreMouseEvents(true, {forward:true}),
//     so the whole window passes clicks through BUT the renderer still receives
//     mousemove events (that's what forward:true buys us).
//   - When the pointer is over the crab body (#crab-hit), we ask main to STOP
//     ignoring mouse events, so clicks/drag land on the crab.
//   - When it leaves, we go back to click-through.

const crab = document.getElementById("crab");
const hit = document.getElementById("crab-hit");

let overBody = false;
let dragging = false;
let lastX = 0, lastY = 0;

/** Is a window-space point inside the crab's hit rectangle? */
function pointInHit(clientX, clientY) {
  const r = hit.getBoundingClientRect();
  return clientX >= r.left && clientX <= r.right && clientY >= r.top && clientY <= r.bottom;
}

// Track the pointer across the whole (forwarded) window to toggle interactivity.
window.addEventListener("mousemove", (e) => {
  if (dragging) {
    // While dragging, move the window by the pointer delta (screen-space).
    const dx = e.screenX - lastX;
    const dy = e.screenY - lastY;
    lastX = e.screenX;
    lastY = e.screenY;
    if (dx !== 0 || dy !== 0) window.pet.moveWindow(dx, dy);
    return;
  }
  const inside = pointInHit(e.clientX, e.clientY);
  if (inside !== overBody) {
    overBody = inside;
    window.pet.setInteractive(inside);
  }
});

// Start a drag on left press over the body.
hit.addEventListener("mousedown", (e) => {
  if (e.button !== 0) return;
  dragging = true;
  lastX = e.screenX;
  lastY = e.screenY;
  crab.dataset.held = "true";
  e.preventDefault();
});

window.addEventListener("mouseup", () => {
  if (!dragging) return;
  dragging = false;
  crab.dataset.held = "false";
  // After releasing, if the pointer is no longer over the body, go click-through.
  if (!overBody) window.pet.setInteractive(false);
});

// --- Per-state animations ----------------------------------------------------
// Overlay <img> shows the animated SVG for each state; idle uses the inline SVG.
// Ported from website/js/crab.js. vb = [x, y, size] of the SVG viewBox; idle box
// is [-15,-25,45], so the overlay is sized/offset relative to that.
let img = document.getElementById("crab-anim");
const STATES = {
  idle:         null,
  // viewBox read from each SVG: most are [-15,-25,45]; happy/sleeping differ.
  dizzy:        { src: "assets/clawd-dizzy-v2.svg",              vb: [-15, -25, 45] },
  happy:        { src: "assets/clawd-happy-v2.svg",             vb: [-12, -15, 40] },
  sleeping:     { src: "assets/clawd-sleeping-v2.svg",          vb: [-10, -20, 40] },
  wake:         { src: "assets/clawd-wake-v2.svg",              vb: [-15, -25, 45] },
  thinking:     { src: "assets/clawd-working-thinking-v2.svg",  vb: [-15, -25, 45] },
  typing:       { src: "assets/clawd-working-typing-v2.svg",    vb: [-15, -25, 45] },
  building:     { src: "assets/clawd-working-building-v2.svg",  vb: [-15, -25, 45] },
  notification: { src: "assets/clawd-notification-v2.svg",      vb: [-15, -25, 45] },
  // Previously aliased to generic sprites — now each has its own v2 art.
  confused:     { src: "assets/clawd-working-confused-v2.svg",  vb: [-15, -25, 45] },
  debugger:     { src: "assets/clawd-working-debugger-v2.svg",  vb: [-15, -25, 45] },
  conducting:   { src: "assets/clawd-working-conducting-v2.svg", vb: [-15, -25, 45] },
  beacon:       { src: "assets/clawd-working-beacon-v2.svg",    vb: [-15, -25, 45] },
  sweeping:     { src: "assets/clawd-working-sweeping-v2.svg",  vb: [-15, -25, 45] },
  hat_mishap:   { src: "assets/clawd-hat-mishap-v2.svg",        vb: [-15, -25, 45] },
  low_battery:  { src: "assets/clawd-idle-low-battery-v2.svg",  vb: [-15, -25, 45] },
  waiting_reply:{ src: "assets/clawd-waiting-reply-v2.svg",     vb: [-15, -25, 45] },
  // Web-motion v2 art (smooth, website + desktop only; not the ESP32).
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

// Daemon state names → our sprite keys. set_status sends working_1..3 and the
// legacy "alert"; set_sessions sends the raw anim name (which now mostly has
// its own SVG above). Only the names WITHOUT dedicated art are aliased.
const ALIAS = {
  working_1: "typing", working_2: "typing", working_3: "typing",
  alert: "notification",
};

function resolveState(name) {
  if (!name) return "idle";
  if (STATES[name] !== undefined) return name;
  if (ALIAS[name] && STATES[ALIAS[name]] !== undefined) return ALIAS[name];
  return "idle";
}

function renderState(name) {
  const key = resolveState(name);
  crab.dataset.state = key;
  const s = STATES[key];
  if (!s) { img.hidden = true; img.removeAttribute("src"); return; } // idle: inline SVG only

  // Replace the <img> node entirely. Swapping only .src does NOT reliably
  // restart a CSS-animated SVG's timeline in Chromium (it can keep showing the
  // previous frame), which looked like "the old animation stays until a working
  // one appears". A fresh element guarantees a clean load + animation from 0.
  const fresh = document.createElement("img");
  fresh.id = "crab-anim";
  fresh.className = "crab-layer";
  fresh.alt = "";
  fresh.style.width = (s.vb[2] / 45 * 100) + "%";
  fresh.style.height = (s.vb[2] / 45 * 100) + "%";
  fresh.style.left = ((15 + s.vb[0]) / 45 * 100) + "%";
  fresh.style.top = ((25 + s.vb[1]) / 45 * 100) + "%";
  fresh.onerror = () => console.error("[pet] FAILED to load:", s.src);
  fresh.src = s.src; // clean path, no query string (file:// safe)
  img.replaceWith(fresh);
  img = fresh;
}

// Warm the cache so swaps don't flash.
Object.keys(STATES).forEach((k) => {
  if (STATES[k]) { const im = new Image(); im.src = STATES[k].src; }
});

// --- Pet-side state controller ------------------------------------------------
// The daemon (shared with the ESP32) is NOT changed. The pet derives the extra
// web-only states from what it already receives:
//   conducting + 1 subagent  -> grooving      conducting + 2+ -> juggling
//   dizzy (API error)        -> error
//   new session id           -> walking  (oneshot, then the real state)
//   session id gone          -> going_away (oneshot)
//   idle-ish -> thinking     -> idea (oneshot), then thinking
//   cool (all tests passed, sent by the daemon) -> cool oneshot
//   no daemon connection     -> disconnected
const ONESHOT_MS = { walking: 1500, going_away: 3200, idea: 1500, cool: 5000, happy: 2000 };
const RESTING = new Set(["idle", "sleeping", "low_battery", "waiting_reply", "happy", "alert", "notification"]);

let linked = false;      // daemon connected to the bridge
let base = "idle";       // latest state from the daemon, after mapping
let shown = null;        // what is on screen right now
let oneshot = null;      // { name, timer } while a oneshot plays
let knownIds = null;     // session ids from the last set_sessions (null = none yet)

function show(name) {
  if (name === shown) return;
  shown = name;
  renderState(name);
}

function refresh() {
  if (!linked) { show("disconnected"); return; }
  if (oneshot) return;   // the oneshot owns the screen until it ends
  show(base);
}

function playOneshot(name) {
  if (oneshot) clearTimeout(oneshot.timer);
  oneshot = { name, timer: setTimeout(() => { oneshot = null; refresh(); }, ONESHOT_MS[name] || 1500) };
  if (linked) show(name);
}

/** Map the daemon's animation name to the pet's art, using the subagent count. */
function mapAnim(name, subagents) {
  if (name === "conducting") return subagents >= 2 ? "juggling" : "grooving";
  if (name === "dizzy") return "error";
  return name || "idle";
}

function handleState(next, ids) {
  const prev = base;

  // Session arrivals and departures (set_sessions only).
  if (ids) {
    const now = new Set(ids);
    if (knownIds) {
      const arrived = ids.some((id) => !knownIds.has(id));
      const left = [...knownIds].some((id) => !now.has(id));
      if (left && !arrived) playOneshot("going_away");
      else if (arrived) playOneshot("walking");
    }
    knownIds = now;
  } else if (next === "sleeping" && knownIds && knownIds.size) {
    // Last session ended: the daemon falls back to set_status sleeping.
    knownIds = new Set();
    playOneshot("going_away");
  }

  base = (next === "happy" || next === "cool") ? prev : next;   // oneshots, not resting states

  if (next === "happy" || next === "cool") {
    // "cool" = all tests passed (to be sent by the daemon); "happy" = turn finished.
    playOneshot(next);
    return;
  }
  if (next === "thinking" && RESTING.has(prev) && !oneshot) {
    playOneshot("idea");   // new prompt: the bulb lights up, then it thinks
    return;
  }
  refresh();
}

window.pet.onDaemonCommand((cmd) => {
  if (!cmd || !cmd.action) return;
  if (cmd.action === "set_status") {
    handleState(mapAnim(cmd.status, 0), null);
  } else if (cmd.action === "set_sessions") {
    const anims = Array.isArray(cmd.anims) ? cmd.anims : [];
    const ids = Array.isArray(cmd.ids) ? cmd.ids.map(String) : null;
    handleState(mapAnim(anims[0], Number(cmd.subagents) || 0), ids);
  } else if (cmd.action.startsWith("permission")) {
    console.log("[pet] permission cmd:", cmd);
  }
});

window.pet.onDaemonLink((connected) => {
  linked = connected;
  if (!connected) { knownIds = null; if (oneshot) { clearTimeout(oneshot.timer); oneshot = null; } }
  refresh();
});

refresh(); // start as "disconnected" until the daemon connects
