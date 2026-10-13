// Build Windows/taskbar PNGs from the repo's pixel SVGs and official favicon.
const { app, BrowserWindow, nativeImage } = require("electron");
const fs = require("node:fs");
const path = require("node:path");
const { pathToFileURL } = require("node:url");
const assets = path.resolve(__dirname, "../renderer/assets");
app.setPath("userData", path.resolve(__dirname, "../../terminal-ab-test/icon-user-data"));
app.whenReady().then(async () => {
  const win = new BrowserWindow({ width: 256, height: 256, show: false, transparent: true,
    webPreferences: { offscreen: true, backgroundThrottling: false, contextIsolation: true } });
  await win.loadFile(path.join(__dirname, "icon-template.html"));
  for (const [agent, file] of [["claude", "clawd-idle-living-v2.svg"], ["codex", "codex/cloud-idle-v2.svg"],
    ["kiro", "providers/kiro-mark.png"], ["opencode", "providers/opencode-mark.ico"]]) {
    const uri = pathToFileURL(path.join(assets, file)).href + (file.endsWith(".svg") ? "#svgView(viewBox(-1,-3,18,21))" : "");
    await win.webContents.executeJavaScript(`new Promise((resolve, reject) => {
      const img = document.getElementById('icon'); img.onload = () => resolve(true); img.onerror = () => reject(new Error('Icon could not load'));
      img.src = ${JSON.stringify(uri)};
    })`);
    await new Promise((resolve) => setTimeout(resolve, 150));
    fs.writeFileSync(path.join(assets, "providers", `${agent}.png`), (await win.webContents.capturePage()).toPNG());
  }
  for (const agent of ["claude", "codex", "kiro", "opencode"]) {
    const file = path.join(assets, "providers", `${agent}.png`);
    if (nativeImage.createFromPath(file).isEmpty()) throw new Error(`Invalid ${agent} icon`);
    // Windows supports PNG-compressed ICOs. All generated PNGs are 256 × 256.
    const png = fs.readFileSync(file);
    const header = Buffer.alloc(22);
    header.writeUInt16LE(1, 2); header.writeUInt16LE(1, 4);
    header.writeUInt16LE(1, 10); header.writeUInt16LE(32, 12);
    header.writeUInt32LE(png.length, 14); header.writeUInt32LE(22, 18);
    fs.writeFileSync(path.join(assets, "providers", `${agent}.ico`), Buffer.concat([header, png]));
  }
  win.destroy();
  app.quit();
}).catch((error) => { console.error(error); app.exit(1); });
