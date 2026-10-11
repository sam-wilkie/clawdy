// tools/preview.js — render an animated SVG to a frame strip PNG.
// Usage: node tools/preview.js <svg> <outDir> <name> [count=8] [intervalMs=200]
// Produces <outDir>/<name>_strip.png (frames left to right, in time order).
const { execFileSync } = require("child_process");
const fs = require("fs");
const path = require("path");

const [svg, outDir, name, count = "8", interval = "200"] = process.argv.slice(2);
if (!svg || !outDir || !name) {
  console.error("usage: node tools/preview.js <svg> <outDir> <name> [count] [intervalMs]");
  process.exit(1);
}
fs.mkdirSync(outDir, { recursive: true });
const prefix = path.join(outDir, name);
const electron = require("electron"); // path to the electron binary
execFileSync(electron, [path.join(__dirname, "render-frames.js"), svg, prefix, count, interval], { stdio: "inherit" });
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", `${prefix}_%02d.png`,
  "-vf", `tile=${count}x1`, "-frames:v", "1", `${prefix}_strip.png`], { stdio: "inherit" });
for (let i = 0; i < Number(count); i++) fs.rmSync(`${prefix}_${String(i).padStart(2, "0")}.png`, { force: true });
console.log("strip:", `${prefix}_strip.png`);
