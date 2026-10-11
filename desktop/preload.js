// preload.js — minimal, safe bridge between the renderer and the main process.
const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("pet", {
  // Enable/disable click-through. interactive=true => the window captures the
  // mouse (pointer is over the crab); false => clicks pass through to apps below.
  setInteractive: (interactive) => ipcRenderer.send("set-interactive", !!interactive),
  // Move the frameless window by a delta (used while dragging the crab).
  moveWindow: (dx, dy) => ipcRenderer.send("move-window", dx, dy),
  // Receive daemon commands (set_sessions / set_status / permission_* / ...).
  onDaemonCommand: (cb) => ipcRenderer.on("daemon-command", (_e, cmd) => cb(cmd)),
  // true when the daemon connects to the pet, false when it drops.
  onDaemonLink: (cb) => ipcRenderer.on("daemon-link", (_e, connected) => cb(!!connected)),
  // Send a permission allow/deny decision back to the daemon.
  sendPermissionDecision: (decision) => ipcRenderer.send("permission-decision", decision),
});
