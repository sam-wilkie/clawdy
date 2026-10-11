// Run with: node --test test/   (no dependencies; node:test is built in)
const test = require("node:test");
const assert = require("node:assert");
const { mapAnim, CONDUCT_MS } = require("../renderer/anim-map.js");

test("without subagents the daemon name passes through (dizzy -> error)", () => {
  assert.strictEqual(mapAnim("building"), "building");
  assert.strictEqual(mapAnim("conducting", 0), "conducting");
  assert.strictEqual(mapAnim("idle", 0), "idle");
  assert.strictEqual(mapAnim("dizzy"), "error");
  assert.strictEqual(mapAnim(undefined), "idle");
});

test("main agent's own tool animation wins over subagents", () => {
  for (const a of ["typing", "building", "debugger", "wizard", "beacon", "sweeping",
                   "thinking", "alert", "confused", "hat_mishap"]) {
    assert.strictEqual(mapAnim(a, 3, Infinity), a, a);
  }
  assert.strictEqual(mapAnim("dizzy", 2), "error");
});

test("conducting is shown for the dispatch moment, then grooving", () => {
  assert.strictEqual(mapAnim("conducting", 1, 0), "conducting");
  assert.strictEqual(mapAnim("conducting", 1, CONDUCT_MS - 1), "conducting");
  assert.strictEqual(mapAnim("conducting", 1, CONDUCT_MS), "grooving");
  assert.strictEqual(mapAnim("conducting", 2), "grooving"); // unknown elapsed
});

test("idle with running subagents grooves", () => {
  assert.strictEqual(mapAnim("idle", 1), "grooving");
});

test("exhausted product shows no_credits over everything but an alert", () => {
  assert.strictEqual(mapAnim("low_battery", 0, Infinity, true), "no_credits");
  assert.strictEqual(mapAnim("idle", 2, Infinity, true), "no_credits"); // not grooving
  assert.strictEqual(mapAnim("dizzy", 0, Infinity, true), "no_credits");
  assert.strictEqual(mapAnim("alert", 0, Infinity, true), "alert");
});

test("without exhausted, low_battery passes through unchanged", () => {
  assert.strictEqual(mapAnim("low_battery", 0, Infinity, false), "low_battery");
  assert.strictEqual(mapAnim("low_battery"), "low_battery");
});
