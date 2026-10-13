const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { EventEmitter } = require("node:events");
const { emptyUsage } = require("../codex-usage");

const usage = { status: "ready", session_pct: 80, weekly_pct: 50, reset_credits: 3 };
const flush = () => new Promise(setImmediate);

async function mainProcess(consume = async () => ({ status: "reset", usage })) {
  const handles = new Map();
  const intervals = new Set();
  const created = [];
  const calls = [];
  let nextKey = 0;
  const ipcMain = new EventEmitter();
  ipcMain.handle = (name, callback) => handles.set(name, callback);
  class Window extends EventEmitter {
    constructor(options) {
      super(); this.destroyed = false; created.push(this);
      this.options = options;
      this.webContents = { send() {}, id: created.length };
    }
    isDestroyed() { return this.destroyed; }
    loadFile() { return Promise.resolve(); }
    show() {} focus() {}
    setMenu(menu) { this.menu = menu; }
    setTitle(title) { this.title = title; }
    setIcon(icon) { this.icon = icon; }
    getSize() { return [this.options.width, this.options.height]; }
    setPosition(x, y) { this.position = [x, y]; }
    setBounds(bounds) { this.options = { ...this.options, ...bounds }; }
    setAppDetails(details) { this.appDetails = details; }
    close() { this.destroyed = true; this.emit("closed"); }
  }
  const app = new EventEmitter();
  app.whenReady = () => Promise.resolve();
  const context = vm.createContext({
    __dirname: path.resolve(__dirname, ".."), process: { env: {}, platform: "win32" }, AbortController,
    setTimeout, clearTimeout,
    setInterval(callback) { const timer = { callback }; intervals.add(timer); return timer; },
    clearInterval(timer) { intervals.delete(timer); },
    require(name) {
      if (name === "electron") return { app, BrowserWindow: Window, ipcMain, screen: {} };
      if (name === "./daemon-bridge") return { SIM_DEFAULT_PORT: 19872, startBridge: () => ({ close() {} }) };
      if (name === "./codex-usage") return { emptyUsage, readCodexUsage: async () => usage,
        consumeCodexReset: (options) => { calls.push(options.idempotencyKey); return consume(options); } };
      if (name === "./agent-usage") return { readAgentUsage: async (agent) => ({ ...usage, source: agent }) };
      if (name === "./session-labels") return require("../session-labels");
      if (name === "node:crypto") return { randomUUID: () => `reset-key-${++nextKey}` };
      return require(name);
    },
  });
  vm.runInContext(fs.readFileSync(path.resolve(__dirname, "../main.js"), "utf8"), context);
  await flush();
  ipcMain.emit("open-panel", {}, "codex");
  const panel = created[0];
  panel.emit("ready-to-show");
  await flush();
  return { panel, calls, intervals,
    async openAgent(agent) { ipcMain.emit("open-panel", {}, agent); await flush(); },
    reset: (sender = panel.webContents) => handles.get("reset-codex-usage")({ sender }),
    snapshot: () => vm.runInContext("panelSnapshot()", context),
  };
}

test("blur closes the activity panel and stops quota polling", async () => {
  const main = await mainProcess();
  assert.equal(main.intervals.size, 1);
  main.panel.emit("blur");
  assert.equal(main.panel.isDestroyed(), true);
  assert.equal(main.intervals.size, 0);
});

test("the popup has no Windows frame or menu, and switching agent updates its icon and usage", async () => {
  const main = await mainProcess();
  assert.equal(main.panel.options.frame, false);
  assert.equal(main.panel.options.minimizable, false);
  assert.equal(main.panel.menu, null);
  for (const agent of ["claude", "kiro", "opencode"]) {
    await main.openAgent(agent);
    assert.equal(main.snapshot().agent, agent);
    assert.equal(main.snapshot().usage.source, agent);
    assert.match(main.panel.icon, new RegExp(`${agent}\\.png$`));
    assert.equal(main.panel.appDetails.appId, `Clawdy.Activity.${agent}`);
    assert.equal(main.intervals.size, 1);
  }
  main.panel.close();
});

test("only the activity panel can reset quotas, and concurrent clicks consume once", async () => {
  let finish;
  const main = await mainProcess(() => new Promise((resolve) => { finish = resolve; }));
  assert.equal((await main.reset({})).status, "invalid_request");
  assert.equal(main.calls.length, 0);
  const first = main.reset();
  assert.equal((await main.reset()).status, "busy");
  assert.equal(main.calls.length, 1);
  finish({ status: "reset", usage: { ...usage, reset_credits: 2, session_pct: 0 } });
  assert.equal((await first).status, "reset");
  assert.equal(main.snapshot().usage.session_pct, 0);
  assert.equal(main.intervals.size, 1);
  main.panel.close();
});

test("uncertain responses reuse the action key instead of spending a second reset", async () => {
  let attempts = 0;
  const main = await mainProcess(async () => ({ status: ++attempts === 1 ? "unavailable" : "reset", usage }));
  assert.equal((await main.reset()).status, "unavailable");
  await flush();
  assert.equal((await main.reset()).status, "reset");
  assert.equal(main.calls[0], main.calls[1]);
  assert.equal(main.intervals.size, 1);
  main.panel.close();
});

test("closing during a confirmed reset still records its outcome and leaves polling stopped", async () => {
  let finish;
  const main = await mainProcess(() => new Promise((resolve) => { finish = resolve; }));
  const action = main.reset();
  main.panel.emit("blur");
  finish({ status: "reset", usage: { ...usage, reset_credits: 2 } });
  assert.equal((await action).status, "reset");
  assert.equal(main.intervals.size, 0);
  assert.equal(main.snapshot().reset.status, "reset");
});
