const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("clawdyPanel", {
  onSnapshot: (callback) => ipcRenderer.on("panel-snapshot", (_event, snapshot) => callback(snapshot)),
  resizeToContent: (height) => ipcRenderer.send("resize-panel-to-content", height),
  resetCodexUsage: () => ipcRenderer.invoke("reset-codex-usage"),
  close: () => window.close(),
});
