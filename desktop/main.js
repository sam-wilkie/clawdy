// main.js — Clawdy desktop pet (Electron spike).
//
// Goal of this spike: prove the window shell works, independently of the firmware/SDL2 path.
//   - transparent, frameless, always-on-top window
//   - click-through everywhere EXCEPT the crab's body (forwarded via setIgnoreMouseEvents)
//   - draggable crab (handled in the renderer via -webkit-app-region or manual move)
//   - no taskbar entry, no focus steal
//
// It does NOT talk to the daemon yet. That bridge comes after the shell is approved.

const { app, BrowserWindow, ipcMain, screen } = require("electron");
const path = require("path");
const { startBridge, SIM_DEFAULT_PORT } = require("./daemon-bridge");

/** Logical size of the pet window (CSS pixels). The crab art is centered inside. */
const WIN_W = 320;
const WIN_H = 320;

let win = null;
let bridge = null;

function createWindow() {
  const { workArea } = screen.getPrimaryDisplay();
  // Start near the bottom-right corner, a bit inset from the edges.
  const x = workArea.x + workArea.width - WIN_W - 24;
  const y = workArea.y + workArea.height - WIN_H - 24;

  win = new BrowserWindow({
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
    // The window must never steal keyboard focus from the user's terminal.
    focusable: false,
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      nodeIntegration: false,
    },
  });

  // Keep it above full-screen apps too (best effort per-OS).
  win.setAlwaysOnTop(true, "screen-saver");
  win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });

  // Start fully click-through; the renderer re-enables the crab's hit area by
  // asking us to stop ignoring mouse events while the pointer is over the body.
  win.setIgnoreMouseEvents(true, { forward: true });

  win.loadFile(path.join(__dirname, "renderer", "index.html"));

  // Diagnostics: run with CLAWDY_DEBUG=1 to open DevTools (detached) and see
  // the renderer console, e.g. "[pet] FAILED to load: ..." for broken sprites.
  if (process.env.CLAWDY_DEBUG === "1") {
    win.webContents.openDevTools({ mode: "detach" });
  }
}

// Renderer tells us when the pointer enters/leaves the crab's interactive area.
// forward:true lets us still receive move events to detect re-entry.
ipcMain.on("set-interactive", (_evt, interactive) => {
  if (!win) return;
  if (interactive) {
    win.setIgnoreMouseEvents(false);
  } else {
    win.setIgnoreMouseEvents(true, { forward: true });
  }
});

// Renderer drives window moves during a drag (frameless + custom hit area).
ipcMain.on("move-window", (_evt, dx, dy) => {
  if (!win) return;
  const [x, y] = win.getPosition();
  win.setPosition(Math.round(x + dx), Math.round(y + dy));
});

app.whenReady().then(() => {
  createWindow();

  // Start the sim-compatible TCP server so the existing daemon connects here.
  bridge = startBridge((cmd) => {
    // Forward every daemon command to the renderer, which maps action→animation.
    if (win && !win.isDestroyed()) {
      win.webContents.send("daemon-command", cmd);
    }
  }, Number(process.env.CLAWDY_PORT) || SIM_DEFAULT_PORT, (connected) => {
    if (win && !win.isDestroyed()) win.webContents.send("daemon-link", connected);
  });
});

// Renderer sends a permission decision (allow/deny) back to the daemon.
ipcMain.on("permission-decision", (_evt, decision) => {
  if (bridge) bridge.sendEvent(decision);
});

// Self-test (development only): CLAWDY_SELFTEST=<dir> runs the fake-daemon
// scenario against this pet, captures the window every 500 ms into <dir> and
// quits after ~20 s. Lets the state controller be checked without a human.
if (process.env.CLAWDY_SELFTEST) {
  app.whenReady().then(() => {
    const fs = require("fs");
    const { spawn } = require("child_process");
    const dir = process.env.CLAWDY_SELFTEST;
    fs.mkdirSync(dir, { recursive: true });
    setTimeout(() => {
      spawn("node", [path.join(__dirname, "fake-daemon.js"), "scenario"], { stdio: "inherit" });
    }, 800);
    let n = 0;
    const tick = setInterval(async () => {
      if (!win || win.isDestroyed()) return;
      const img = await win.webContents.capturePage();
      fs.writeFileSync(path.join(dir, `f_${String(n++).padStart(2, "0")}.png`), img.toPNG());
    }, 500);
    setTimeout(() => { clearInterval(tick); app.quit(); }, 25500);
  });
}

app.on("window-all-closed", () => {
  if (bridge) bridge.close();
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
