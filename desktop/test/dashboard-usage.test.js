const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

function dashboard() {
  const elements = new Map();
  let resetCalls = 0;
  let closeCalls = 0;
  const element = (id) => {
    if (!elements.has(id)) elements.set(id, {
      textContent: "", hidden: false, attributes: {}, style: {}, dataset: {}, listeners: {},
      getAttribute(key) { return this.attributes[key]; },
      setAttribute(key, value) { this.attributes[key] = value; },
      removeAttribute(key) { delete this.attributes[key]; },
      querySelector() { return element(`${id}/span`); },
      addEventListener(name, callback) { this.listeners[name] = callback; },
      focus() {}, append() {}, replaceChildren() {},
      click() { if (!this.disabled) return this.listeners.click?.(); },
    });
    return elements.get(id);
  };
  const context = vm.createContext({ document: { getElementById: element, createElement: () => element(`created/${elements.size}`),
    addEventListener() {}, querySelector: () => ({ getBoundingClientRect: () => ({ height: 500 }) }) }, requestAnimationFrame: (callback) => callback(),
    window: { clawdyPanel: { onSnapshot() {}, resizeToContent() {}, close() { closeCalls++; },
      async resetCodexUsage() { resetCalls++; return { status: "reset" }; } } } });
  vm.runInContext(fs.readFileSync(path.join(__dirname, "../renderer/dashboard.js"), "utf8"), context);
  return { element, get resetCalls() { return resetCalls; }, get closeCalls() { return closeCalls; },
    snapshot(value) { context.inputSnapshot = value; vm.runInContext("render(inputSnapshot)", context); },
    usage(value, agent) {
    context.inputUsage = value;
    context.inputAgent = agent;
    vm.runInContext("renderUsage(inputUsage, inputAgent)", context);
  } };
}

test("switching from Claude to Codex replaces values, captions and reset times", () => {
  const ui = dashboard();
  ui.usage({ session_pct: 73, weekly_pct: 42, reset_s: 3600 }, "claude");
  assert.equal(ui.element("session-value").textContent, "73%");
  ui.usage({ status: "ready", session_pct: 0, weekly_pct: 10, reset_s: 60,
    weekly_reset_s: 172800, session_window_minutes: 300, weekly_window_minutes: 10080 }, "codex");
  assert.equal(ui.element("session-value").textContent, "0%");
  assert.equal(ui.element("weekly-value").textContent, "10%");
  assert.equal(ui.element("session-label").textContent, "Ventana · 5 h");
  assert.equal(ui.element("weekly-label").textContent, "Semana");
  assert.equal(ui.element("weekly-reset-label").textContent, "Reinicio en 2 d 0 h");
  assert.match(ui.element("usage-note").textContent, /cuenta de Codex/);
  assert.equal(ui.element("session-usage-row").hidden, false);
});

test('spending periods replace cost and retain their choice per agent, with unknown cost distinct from zero', () => {
  const ui = dashboard();
  const periods = { all: { cost: 12.5, input_tokens: 1000 }, day: { cost: 0, input_tokens: 12 }, month: { cost: null } };
  ui.snapshot({ agent: 'opencode', usage: { status: 'ready', source: 'opencode_db', periods } });
  assert.equal(ui.element('spending').hidden, false);
  assert.equal(ui.element('session-usage-row').hidden, true);
  assert.match(ui.element('spend-value').textContent, /12,50/);
  ui.element('period-day').click();
  assert.match(ui.element('spend-value').textContent, /0,00/);
  assert.equal(ui.element('period-day').attributes['aria-pressed'], 'true');
  ui.snapshot({ agent: 'antigravity', usage: { status: 'ready', source: 'antigravity_db', periods: { all: { cost: null } } } });
  assert.equal(ui.element('spend-value').textContent, 'No disponible');
  assert.equal(ui.element('period-all').attributes['aria-pressed'], 'true');
  ui.snapshot({ agent: 'opencode', usage: { status: 'ready', source: 'opencode_db', periods } });
  assert.equal(ui.element('period-day').attributes['aria-pressed'], 'true');
  ui.snapshot({ agent: 'codex', usage: { status: 'ready', session_pct: 10 } });
  assert.equal(ui.element('spending').hidden, true);
});

test("reset requires the confirmation button, and cancel never calls the account action", async () => {
  const ui = dashboard();
  ui.snapshot({ agent: "codex", usage: { status: "ready", session_pct: 80, reset_credits: 2 } });
  ui.element("request-reset-button").click();
  assert.equal(ui.element("reset-confirm").hidden, false);
  assert.equal(ui.resetCalls, 0);
  ui.element("cancel-reset-button").click();
  assert.equal(ui.element("reset-confirm").hidden, true);
  assert.equal(ui.resetCalls, 0);
  ui.element("request-reset-button").click();
  await ui.element("confirm-reset-button").click();
  assert.equal(ui.resetCalls, 1);
  assert.equal(ui.element("reset-message").textContent, "Reinicio aplicado.");
});

test("no-credit and unknown-credit accounts cannot confirm a reset; Claude hides the controls", () => {
  const ui = dashboard();
  for (const count of [0, null]) {
    ui.snapshot({ agent: "codex", usage: { status: "ready", session_pct: 80, reset_credits: count } });
    assert.equal(ui.element("request-reset-button").disabled, true);
    ui.element("request-reset-button").click();
    assert.equal(ui.element("reset-confirm").hidden, true);
    assert.equal(ui.resetCalls, 0);
  }
  ui.snapshot({ agent: "claude", usage: { session_pct: 80 } });
  assert.equal(ui.element("reset-controls").hidden, true);
  assert.match(ui.element("agent-avatar").getAttribute("src"), /svgView/);
});

test("missing secondary limits are hidden and Codex's actual duration is shown", () => {
  const ui = dashboard();
  ui.usage({ session_pct: 25, session_window_minutes: 15 }, "codex");
  assert.equal(ui.element("session-label").textContent, "Ventana · 15 min");
  assert.equal(ui.element("weekly-usage-row").hidden, true);
});

test("a failed Codex read clears Claude meters and explains the failure", () => {
  const ui = dashboard();
  ui.usage({ session_pct: 73, weekly_pct: 42, reset_s: 3600 }, "claude");
  ui.usage({ status: "signed_out" }, "codex");
  assert.equal(ui.element("session-usage-row").hidden, true);
  assert.equal(ui.element("weekly-usage-row").hidden, true);
  assert.equal(ui.element("reset-label").textContent, "");
  assert.match(ui.element("usage-note").textContent, /Inicia sesión en Codex/);
});
