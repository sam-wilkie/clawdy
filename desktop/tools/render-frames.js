// tools/render-frames.js — capture frames of an animated SVG to PNG (offscreen Electron).
// Usage: pnpm exec electron tools/render-frames.js <svg> <outPrefix> [count=8] [intervalMs=200]
// Writes <outPrefix>_00.png ... and a horizontal strip <outPrefix>_strip.png.
const { app, BrowserWindow, nativeImage } = require("electron");
const fs = require("fs");
const path = require("path");
const { pathToFileURL } = require("url");

const [svgArg, outPrefix, countArg, intervalArg] = process.argv.slice(2).filter((a) => !a.startsWith("--"));
const COUNT = parseInt(countArg || "8", 10);
const INTERVAL = parseInt(intervalArg || "200", 10);
const SIZE = parseInt(process.env.SIZE || "200", 10);

app.disableHardwareAcceleration();
app.whenReady().then(async () => {
  const win = new BrowserWindow({
    width: SIZE, height: SIZE, show: false,
    webPreferences: { offscreen: true },
  });
  const svgAbs = path.resolve(svgArg);
  const htmlFile = path.join(path.dirname(svgAbs), `.__render_${process.pid}.html`);
  // ZOOM=1: render the SVG at 3x and center the crab (art box sits at ~50%,79% of the viewBox).
  const zoom = process.env.ZOOM === "1";
  const imgPx = zoom ? SIZE * 3 : SIZE;
  const offL = zoom ? SIZE / 2 - imgPx * 0.5 : 0;
  const offT = zoom ? SIZE / 2 - imgPx * 0.76 : 0;
  fs.writeFileSync(htmlFile, `<html><body style="margin:0;background:#f4ead8;overflow:hidden">
    <img src="${path.basename(svgAbs)}" style="position:absolute;left:${offL}px;top:${offT}px;width:${imgPx}px;height:${imgPx}px;image-rendering:pixelated"></body></html>`);
  await win.loadFile(htmlFile);
  await new Promise((r) => setTimeout(r, 300));
  fs.unlinkSync(htmlFile);

  const frames = [];
  for (let i = 0; i < COUNT; i++) {
    const img = await win.webContents.capturePage();
    const file = `${outPrefix}_${String(i).padStart(2, "0")}.png`;
    fs.writeFileSync(file, img.toPNG());
    frames.push(img.toBitmap());
    await new Promise((r) => setTimeout(r, INTERVAL));
  }
  console.log(`wrote ${COUNT} frames to ${outPrefix}_*.png`);
  app.quit();
});
