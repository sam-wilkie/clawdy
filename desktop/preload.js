// preload.js — minimal, safe bridge between a per-product renderer and main.
const { contextBridge, ipcRenderer } = require("electron");

// Which AI product this window represents, passed by main.js as a launch arg
// (--clawdy-agent=claude|codex|kiro|opencode|antigravity). Defaults to "claude" if absent.
function readAgent() {
  const arg = process.argv.find((a) => a.startsWith("--clawdy-agent="));
  return arg ? arg.slice("--clawdy-agent=".length) : "claude";
}

contextBridge.exposeInMainWorld("pet", {
  // The product this window renders (fixed for the window's lifetime).
  agent: readAgent(),
  // Enable/disable click-through for THIS window. interactive=true => the
  // window captures the mouse (pointer over the crab); false => pass through.
  setInteractive: (interactive) => ipcRenderer.send("set-interactive", !!interactive),
  // Move THIS frameless window by a delta (used while dragging the crab).
  moveWindow: (dx, dy) => ipcRenderer.send("move-window", dx, dy),
  // Ask main for this window's current product state (called once on load).
  requestState: () => ipcRenderer.send("ready-for-state"),
  // Receive this product's state: { agent, count, anim, linked }.
  onProductState: (cb) => ipcRenderer.on("product-state", (_e, state) => cb(state)),
  // This product's sessions are gone: play the exit before main closes the window.
  onLeave: (cb) => ipcRenderer.on("product-leave", () => cb()),
  // A permission prompt to show over this crab: { id, nonce, agent, project, tool, summary }.
  onPermissionRequest: (cb) => ipcRenderer.on("permission-request", (_e, req) => cb(req)),
  // Take down a permission bubble (answered elsewhere / timed out): { id }.
  onPermissionClear: (cb) => ipcRenderer.on("permission-clear", (_e, msg) => cb(msg)),
  // Send a permission allow/deny decision back to the daemon. Pass the full
  // {event:"permission_decision", id, nonce, decision} object.
  sendPermissionDecision: (decision) => ipcRenderer.send("permission-decision", decision),
  // Grow THIS window upward while a permission bubble is up (true), or shrink it back.
  setExpanded: (expanded) => ipcRenderer.send("set-expanded", !!expanded),
  openPanel: () => ipcRenderer.send("open-panel", readAgent()),
});
