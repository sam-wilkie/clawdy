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

function rendererArt(agent) {
  const noop = () => {};
  const pet = new Proxy({ agent }, { get: (t, k) => (k in t ? t[k] : noop) });
  const els = new Map();
  const element = (id) => (els.has(id) ? els.get(id) : els.set(id, stubElement()).get(id));
  const context = vm.createContext({
    document: { getElementById: element, createElement: stubElement }, window: { pet, addEventListener: noop },
    setTimeout, clearTimeout, setInterval: noop, requestAnimationFrame: noop, Image: class {},
  });
  vm.runInContext(read("renderer/renderer.js"), context);
  return { art: element("crab").dataset.art, idle: vm.runInContext("ART_STATES.idle && ART_STATES.idle.src", context),
    typing: vm.runInContext("ART_STATES.typing.src", context) };
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

test("agents without their own art get the monster pet; claude and codex keep theirs", () => {
  assert.deepEqual(rendererArt("claude"), { art: "crab", idle: null, typing: "assets/clawd-working-typing-v2.svg" });
  assert.deepEqual(rendererArt("codex"),
    { art: "cloud", idle: "assets/codex/cloud-idle-v2.svg", typing: "assets/codex/cloud-typing-v2.svg" });
  for (const agent of ["kiro", "opencode", "antigravity", "mystery"]) {
    assert.deepEqual(rendererArt(agent),
      { art: "monster", idle: "assets/monster/monster-idle-v2.svg", typing: "assets/monster/monster-typing-v2.svg" }, agent);
  }
});

test("every monster art file the renderer can request exists", () => {
  for (const agent of ["kiro"]) {
    const noop = () => {};
    const pet = new Proxy({ agent }, { get: (t, k) => (k in t ? t[k] : noop) });
    const context = vm.createContext({
      document: { getElementById: () => stubElement(), createElement: stubElement }, window: { pet, addEventListener: noop },
      setTimeout, clearTimeout, setInterval: noop, requestAnimationFrame: noop, Image: class {},
    });
    vm.runInContext(read("renderer/renderer.js"), context);
    const srcs = JSON.parse(vm.runInContext("JSON.stringify(Object.values(ART_STATES).filter(Boolean).map((s) => s.src))", context));
    for (const src of srcs) assert.ok(fs.existsSync(path.resolve(__dirname, "..", "renderer", src)), src);
  }
});

test("the default monster pet introduces itself as Vinnie in its tooltip; crab and cloud keep theirs", () => {
  const tooltip = (agent) => {
    const els = new Map();
    const element = (id) => (els.has(id) ? els.get(id) : els.set(id, stubElement()).get(id));
    const noop = () => {};
    const pet = new Proxy({ agent }, { get: (t, k) => (k in t ? t[k] : noop) });
    const context = vm.createContext({
      document: { getElementById: element, createElement: stubElement }, window: { pet, addEventListener: noop },
      setTimeout, clearTimeout, setInterval: noop, requestAnimationFrame: noop, Image: class {},
    });
    vm.runInContext(read("renderer/renderer.js"), context);
    const title = element("crab-hit").title; // the stub answers unset keys with a function
    return { title: typeof title === "string" ? title : undefined, label: element("crab-label").textContent };
  };
  for (const agent of ["kiro", "opencode", "antigravity"]) {
    assert.equal(tooltip(agent).title, "Vinnie · Clic para ver actividad · Arrastra para mover", agent);
  }
  assert.equal(tooltip("kiro").label, "Kiro");
  assert.equal(tooltip("claude").title, undefined);
  assert.equal(tooltip("codex").title, undefined);
});

test("Vinnie is drawn at 80 % and only Vinnie: the crab and the cloud keep full size", () => {
  const css = read("renderer/style.css");
  assert.match(css, /#crab\[data-art="monster"\] #crab-art \{ scale: 0\.8; \}/);
  assert.equal((css.match(/scale:/g) || []).length, 1);
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

test("badge and name label are placed from the art box, not the window (so they follow the scaled sprite)", () => {
  const src = read("renderer/renderer.js");
  assert.match(src, /function placeOverlays\(/);
  assert.match(src, /badge\.style\.top = /);
  assert.match(src, /label\.style\.top = /);
  assert.match(src, /placeOverlays\(s\.vb\)/);
});

test("name label is anchored to the window bottom, not to the art box, so it never clips and does not jump between states", () => {
  const src = read("renderer/renderer.js");
  assert.match(src, /label\.style\.bottom = /);
  assert.doesNotMatch(src, /label\.style\.top = \(top/);
});
