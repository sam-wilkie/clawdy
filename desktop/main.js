// main.js — Clawdy desktop pet (Phase 3: one window per AI product).
//
// The daemon sends set_sessions with a per-product aggregation array:
//   products: [{agent:"claude", count:3, anim:"building", bg:2}, {agent:"kiro", ...}]
// (bg = subagents currently running, omitted when 0; sendProduct forwards the
// whole entry, so the renderer maps it to 'grooving' — see renderer/anim-map.js)
// We render ONE transparent, always-on-top, draggable window per product, each
// showing that product's crab and an "xN" badge when it has more than one
// session. Windows are laid out from the bottom-right corner, stacked leftward.
//
// Each window:
//   - transparent, frameless, always-on-top, no taskbar entry, never focusable
//   - click-through everywhere EXCEPT the crab body (forwarded per-window)
//   - draggable independently (renderer drives move-window on its own window)
//
// The daemon-bridge (sim-compatible TCP server) stays in the main process; main
// routes each product's state to its window. A legacy set_status (no products)
// maps to a single "claude" crab so older daemons still work.

const { app, BrowserWindow, ipcMain, screen } = require("electron");
const path = require("path");
const { startBridge, SIM_DEFAULT_PORT } = require("./daemon-bridge");

/** Window lifecycle logging, on only with CLAWDY_DEBUG=1 (quiet in production). */
const debugLog = process.env.CLAWDY_DEBUG === "1"
  ? (...a) => console.log("[main]", ...a)
  : () => {};

/** Logical size of each pet window (CSS pixels). */
const WIN_W = 320;
const WIN_H = 320;
/** Gap between stacked product windows (px), and inset from screen edges. */
const WIN_GAP = 8;
const EDGE_INSET = 24;
/** Fixed left-to-right display order so the layout is stable as products
 *  come and go. Products not listed fall after these, in arrival order. */
const AGENT_ORDER = ["claude", "codex", "kiro"];

/** agent -> { win: BrowserWindow, product: {agent,count,anim}, moved: boolean } */
const windows = new Map();
let bridge = null;
let linked = false;

/** Sort product agents into a stable left-to-right order. */
function orderedAgents(agents) {
  return [...agents].sort((a, b) => {
    const ia = AGENT_ORDER.indexOf(a);
    const ib = AGENT_ORDER.indexOf(b);
    return (ia === -1 ? 99 : ia) - (ib === -1 ? 99 : ib);
  });
}

/** Default position for the slot-th window (0 = rightmost), bottom-right. */
function slotPosition(slot) {
  const { workArea } = screen.getPrimaryDisplay();
  const x = workArea.x + workArea.width - WIN_W - EDGE_INSET - slot * (WIN_W + WIN_GAP);
  const y = workArea.y + workArea.height - WIN_H - EDGE_INSET;
  return { x, y };
}

function createWindow(agent, slot) {
  const { x, y } = slotPosition(slot);
  const win = new BrowserWindow({
    width: WIN_W,
    height: WIN_H,
    x,
    y,
    frame: false,
    transparent: true,
    resizable: false,
    movable: true,
    skipTaskbar: true,
    alwaysOnTop: true,
    hasShadow: false,
    focusable: false, // never steal keyboard focus from the user's terminal
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
      // The window learns which product it is from this query arg; the preload
      // reads it and hands it to the renderer. Avoids an extra IPC round-trip
      // before the first paint.
      additionalArguments: [`--clawdy-agent=${agent}`],
    },
  });

  win.setAlwaysOnTop(true, "screen-saver");
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
  win.setIgnoreMouseEvents(true, { forward: true });
  win.loadFile(path.join(__dirname, "renderer", "index.html"));

  if (process.env.CLAWDY_DEBUG === "1") {
    win.webContents.openDevTools({ mode: "detach" });
  }
  return win;
}

/** Push a product's current state to its window's renderer. */
function sendProduct(entry) {
  const { win, product } = entry;
  if (win && !win.isDestroyed() && win.webContents) {
    win.webContents.send("product-state", { ...product, linked });
  }
}

/**
 * Reconcile the live windows with the daemon's product list: create windows for
 * new products, destroy windows for products that vanished, update the rest, and
 * reposition any window the user has not dragged.
 */
function handleProducts(products) {
  const wanted = new Map(products.map((p) => [p.agent, p]));

  // Remove windows whose product is gone.
  for (const [agent, entry] of [...windows]) {
    if (!wanted.has(agent)) {
      if (entry.win && !entry.win.isDestroyed()) entry.win.destroy();
      windows.delete(agent);
      debugLog(`window destroyed: ${agent}`);
    }
  }

  // Create or update windows for wanted products.
  for (const [agent, product] of wanted) {
    let entry = windows.get(agent);
    if (!entry) {
      entry = { win: createWindow(agent, windows.size), product, moved: false };
      windows.set(agent, entry);
      debugLog(`window created: ${agent} (count=${product.count}, anim=${product.anim})`);
    } else {
      entry.product = product;
      sendProduct(entry);
      debugLog(`window updated: ${agent} (count=${product.count}, anim=${product.anim})`);
    }
  }

  debugLog(`live windows: ${[...windows.keys()].join(", ") || "(none)"}`);
  layoutWindows();
}

/** Place every window that the user has NOT dragged at its slot position, in a
 *  stable left-to-right order. Dragged windows keep the user's position. */
function layoutWindows() {
  const agents = orderedAgents([...windows.keys()]);
  agents.forEach((agent, slot) => {
    const entry = windows.get(agent);
    if (!entry || !entry.win || entry.win.isDestroyed()) return;
    if (entry.moved) return; // respect a user-dragged window
    const { x, y } = slotPosition(slot);
    entry.win.setPosition(x, y);
  });
}

/** Fall back to a single "claude" crab for a legacy set_status (no products). */
function handleStatus(status) {
  handleProducts([{ agent: "claude", count: 1, anim: status }]);
}

function closeAllWindows() {
  for (const [, entry] of windows) {
    if (entry.win && !entry.win.isDestroyed()) entry.win.destroy();
  }
  windows.clear();
}

// --- Permission bubble routing -----------------------------------------------
// The daemon sends permission_request {id,nonce,agent,project,tool,summary} and
// waits for a permission_decision {id,nonce,decision} reply (see daemon.py
// _wait_for_permission). We show the bubble over the requesting product's crab
// window and relay the user's Allow/Deny back through the bridge. permission_clear
// {id} takes a bubble down (answered elsewhere, timed out, cancelled).

/** id -> agent, so a later permission_clear can reach the right window. */
const permissionAgents = new Map();

/** The window that should host a permission for `agent`: that product's window
 *  if present, else any live window, else none. */
function permissionTargetWindow(agent) {
  let entry = windows.get(agent);
  if (!entry) entry = windows.values().next().value;
  return entry && entry.win && !entry.win.isDestroyed() ? entry.win : null;
}

function handlePermissionRequest(cmd) {
  const agent = cmd.agent || "claude";
  permissionAgents.set(cmd.id, agent);
  const win = permissionTargetWindow(agent);
  if (win) win.webContents.send("permission-request", cmd);
}

function handlePermissionClear(id) {
  const agent = permissionAgents.get(id);
  permissionAgents.delete(id);
  // Tell whichever window might be showing it to remove it. Broadcast to the
  // agent's window; if we don't know it, tell them all (cheap, idempotent).
  const targets = [];
  if (agent && windows.get(agent)) targets.push(windows.get(agent));
  else for (const entry of windows.values()) targets.push(entry);
  for (const entry of targets) {
    if (entry.win && !entry.win.isDestroyed()) {
      entry.win.webContents.send("permission-clear", { id });
    }
  }
}

// --- IPC from the per-window renderers ---------------------------------------

/** The window's renderer is loaded and wants its current product state. */
ipcMain.on("ready-for-state", (evt) => {
  for (const entry of windows.values()) {
    if (entry.win && !entry.win.isDestroyed() &&
        entry.win.webContents.id === evt.sender.id) {
      sendProduct(entry);
      return;
    }
  }
});

/** Toggle click-through for the window that sent this (pointer over its crab). */
ipcMain.on("set-interactive", (evt, interactive) => {
  const win = BrowserWindow.fromWebContents(evt.sender);
  if (!win || win.isDestroyed()) return;
  if (interactive) win.setIgnoreMouseEvents(false);
  else win.setIgnoreMouseEvents(true, { forward: true });
});

/** Drag: move the sender's own window by a pointer delta, and mark it moved so
 *  layoutWindows() stops repositioning it. */
ipcMain.on("move-window", (evt, dx, dy) => {
  const win = BrowserWindow.fromWebContents(evt.sender);
  if (!win || win.isDestroyed()) return;
  const [x, y] = win.getPosition();
  win.setPosition(Math.round(x + dx), Math.round(y + dy));
  for (const entry of windows.values()) {
    if (entry.win === win) entry.moved = true;
  }
});

/** A renderer sends a permission decision back to the daemon. */
ipcMain.on("permission-decision", (_evt, decision) => {
  if (bridge) bridge.sendEvent(decision);
});

// --- Daemon bridge ------------------------------------------------------------

app.whenReady().then(() => {
  bridge = startBridge((cmd) => {
    // Daemon messages are keyed by either "action" (set_sessions/set_status) or
    // "event" (permission_request/permission_clear). Accept both.
    if (!cmd || (!cmd.action && !cmd.event)) return;
    if (cmd.action === "set_sessions") {
      if (Array.isArray(cmd.products) && cmd.products.length) {
        handleProducts(cmd.products);
      } else {
        // A daemon without Phase 2 products[]: collapse the slots to one claude
        // crab using the first anim, so the pet still shows something.
        const anims = Array.isArray(cmd.anims) ? cmd.anims : [];
        handleStatus(anims[0] || "idle");
      }
    } else if (cmd.action === "set_status") {
      if (cmd.status === "sleeping") closeAllWindows();
      else handleStatus(cmd.status);
    } else if (cmd.action === "permission_request") {
      handlePermissionRequest(cmd);
    } else if (cmd.action === "permission_clear") {
      handlePermissionClear(cmd.id);
    }
  }, Number(process.env.CLAWDY_PORT) || SIM_DEFAULT_PORT, (connected) => {
    linked = connected;
    // Tell every live window about the link state.
    for (const entry of windows.values()) sendProduct(entry);
    // On disconnect, keep the windows (they show "disconnected"); on connect,
    // the next set_sessions reconciles them.
  });
});

app.on("window-all-closed", () => {
  // No active sessions means no pet windows. Keep the bridge alive so the next
  // session can create its window without restarting the desktop process.
});

app.on("before-quit", () => {
  if (bridge) bridge.close();
});
