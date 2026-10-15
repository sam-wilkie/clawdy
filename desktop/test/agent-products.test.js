const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { EventEmitter } = require("node:events");

const read = (rel) => fs.readFileSync(path.resolve(__dirname, "..", rel), "utf8");

function mainContext() {
  const app = new EventEmitter();
  app.whenReady = () => new Promise(() => {});
  const context = vm.createContext({
    __dirname: path.resolve(__dirname, ".."), process: { env: {} }, setTimeout, clearTimeout,
    setInterval() {}, clearInterval() {}, AbortController,
    require(name) {
      if (name === "electron") return { app, BrowserWindow: class {}, ipcMain: Object.assign(new EventEmitter(), { handle() {} }), screen: {} };
      if (name === "./daemon-bridge") return { SIM_DEFAULT_PORT: 19872, startBridge: () => ({ close() {} }) };
      if (name.startsWith("./")) return require(path.resolve(__dirname, "..", name));
      return require(name);
    },
  });
  vm.runInContext(read("main.js"), context);
  return context;
}

function stubElement() {
  const noop = () => {};
  return new Proxy({ textContent: "", style: {}, dataset: {}, classList: { add: noop, remove: noop, toggle: noop } },
    { get: (t, k) => (k in t ? t[k] : noop), set: (t, k, v) => ((t[k] = v), true) });
}

function rendererLabel(agent) {
  const els = new Map();
  const element = (id) => (els.has(id) ? els.get(id) : els.set(id, stubElement()).get(id));
  const noop = () => {};
  const pet = new Proxy({ agent }, { get: (t, k) => (k in t ? t[k] : noop) });
  const context = vm.createContext({
    document: { getElementById: element, createElement: stubElement }, window: { pet, addEventListener: noop },
    setTimeout, clearTimeout, setInterval: noop, requestAnimationFrame: noop, Image: class {},
  });
  vm.runInContext(read("renderer/renderer.js"), context);
  return element("crab-label").textContent;
}

test("product order places opencode and antigravity after kiro", () => {
  const ctx = mainContext();
  const sorted = vm.runInContext(
    'orderedAgents(["antigravity","opencode","kiro","codex","claude"])', ctx);
  assert.deepEqual([...sorted], ["claude", "codex", "kiro", "opencode", "antigravity"]);
});

test("unknown products sort last and do not throw", () => {
  const ctx = mainContext();
  const sorted = vm.runInContext('orderedAgents(["mystery","antigravity","claude"])', ctx);
  assert.deepEqual([...sorted], ["claude", "antigravity", "mystery"]);
});

test("pet window label shows display names for new products", () => {
  assert.equal(rendererLabel("antigravity"), "Antigravity");
  assert.equal(rendererLabel("opencode"), "OpenCode");
  assert.equal(rendererLabel("mystery"), "mystery");
});

test("dashboard names include new products", () => {
  const ctx = vm.createContext({ document: { getElementById: stubElement, createElement: stubElement,
    addEventListener() {}, querySelector: () => ({ scrollHeight: 1 }) }, requestAnimationFrame() {},
    window: { clawdyPanel: new Proxy({}, { get: () => () => {} }) } });
  vm.runInContext(read("renderer/dashboard.js"), ctx);
  assert.equal(vm.runInContext("AGENT_NAMES.antigravity", ctx), "Antigravity");
  assert.equal(vm.runInContext("AGENT_NAMES.opencode", ctx), "OpenCode");
});

test("product order and names include pi (gentle-shell) after antigravity", () => {
  const ctx = mainContext();
  const sorted = vm.runInContext('orderedAgents(["pi","antigravity","claude"])', ctx);
  assert.deepEqual([...sorted], ["claude", "antigravity", "pi"]);
  assert.equal(vm.runInContext("AGENT_NAMES.pi", ctx), "Pi");
});

test("pet window is 200x200 CSS px (user chose ~62% of the old 320)", () => {
  const main = read("main.js");
  assert.match(main, /const WIN_W = 200;/);
  assert.match(main, /const WIN_H = 200;/);
});

test("the default monster art is wired for non-Claude, non-Codex products (Pi)", () => {
  const src = read("renderer/renderer.js");
  assert.match(src, /const MONSTER_STATES = /);
  assert.match(src, /monster: MONSTER_STATES/);
});

test("monster sprite is drawn smaller than the window box so it matches Clawd's visual size (option 1)", () => {
  const src = read("renderer/renderer.js");
  assert.match(src, /const MONSTER_SCALE = 0\.8;/);
  assert.match(src, /function shrinkVb\(/);
  assert.match(src, /vb: shrinkVb\(CODEX_STATES\[state\]\.vb, MONSTER_SCALE\)/);
});

test("badge and name label are placed from the art box, not the window (so they follow the scaled sprite)", () => {
  const src = read("renderer/renderer.js");
  assert.match(src, /function placeOverlays\(/);
  assert.match(src, /badge\.style\.top = /);
  assert.match(src, /label\.style\.top = /);
  assert.match(src, /placeOverlays\(s\.vb\)/);
});
