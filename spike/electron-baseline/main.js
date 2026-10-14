// Same scene as the Tauri spike: 320x320 transparent frameless always-on-top window,
// selective click-through. Electron has setIgnoreMouseEvents(.., {forward:true}), no polling.
const { app, BrowserWindow, ipcMain } = require("electron");
app.whenReady().then(() => {
  const win = new BrowserWindow({ width: 320, height: 320, transparent: true, frame: false, alwaysOnTop: true,
    resizable: false, skipTaskbar: true, hasShadow: false, title: "pet-electron",
    webPreferences: { nodeIntegration: true, contextIsolation: false } });
  win.loadFile("index.html");
  ipcMain.on("ignore", (_e, v) => win.setIgnoreMouseEvents(v, { forward: true }));
});
