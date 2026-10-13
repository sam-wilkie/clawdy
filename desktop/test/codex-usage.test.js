const test = require("node:test");
const assert = require("node:assert/strict");
const { spawn } = require("node:child_process");
const { readCodexUsage, normalizeRateLimits, consumeCodexReset } = require("../codex-usage");

const NOW = 1700000000000;
const limits = { primary: { usedPercent: 0, windowDurationMins: 300, resetsAt: NOW / 1000 + 100 },
  secondary: { usedPercent: 48, windowDurationMins: 10080, resetsAt: NOW / 1000 + 200000 } };

test("Codex bucket wins over a different legacy bucket, with zero usage and both reset times", () => {
  const usage = normalizeRateLimits({ rateLimits: { limitId: "reviews", ...limits },
    rateLimitsByLimitId: { codex: limits } }, NOW);
  assert.equal(usage.status, "ready");
  assert.equal(usage.session_pct, 0);
  assert.equal(usage.weekly_pct, 48);
  assert.equal(usage.reset_s, 100);
  assert.equal(usage.weekly_reset_s, 200000);
  assert.equal(usage.session_window_minutes, 300);
});

test("legacy Codex response preserves actual window duration and missing secondary", () => {
  const usage = normalizeRateLimits({ rateLimits: { primary: {
    usedPercent: 25, windowDurationMins: 15, resetsAt: NOW / 1000 - 1 }, secondary: null } }, NOW);
  assert.equal(usage.session_window_minutes, 15);
  assert.equal(usage.reset_s, 0);
  assert.equal(usage.weekly_pct, null);
});

test("unrelated buckets and invalid usage never become Codex percentages", () => {
  assert.equal(normalizeRateLimits({ rateLimits: { limitId: "reviews", ...limits } }).status, "no_limits");
  assert.equal(normalizeRateLimits({ rateLimitsByLimitId: { reviews: limits } }).status, "no_limits");
  assert.equal(normalizeRateLimits({ rateLimits: { primary: { usedPercent: null } } }).status, "no_limits");
});

// Exercise actual stdio framing and subprocess cleanup with a small local RPC
// server. No user authentication or network is involved in these tests.
function server(options = {}) {
  let child;
  let closed;
  const script = `
    const readline = require('node:readline');
    const options = ${JSON.stringify(options)};
    let initialized = false;
    let acknowledged = false;
    let consumed = false;
    function reply(id, result) { process.stdout.write(JSON.stringify({id,result}) + '\\n'); }
    const lines = readline.createInterface({input:process.stdin});
    lines.on('line', line => {
      const message = JSON.parse(line);
      if (options.hang) return;
      if (message.method === 'initialize') {
        initialized = true;
        // A notification can arrive before a response; it has no request id.
        process.stdout.write(JSON.stringify({method:'account/updated',params:{}}) + '\\n');
        return reply(message.id, {});
      }
      if (message.method === 'initialized') { acknowledged = true; return; }
      if (!initialized || !acknowledged) process.exit(9);
      if (message.method === 'account/read') {
        return reply(message.id, {account:options.signedOut ? null : {type:options.apiKey ? 'apiKey' : 'chatgpt'}});
      }
      if (message.method === 'account/rateLimits/read') {
        if (options.unsupported || (consumed && options.refreshFails)) {
          process.stdout.write(JSON.stringify({id:message.id,error:{code:-32601}}) + '\\n');
          return;
        }
        return reply(message.id, {rateLimits:{limitId:'codex',primary:{usedPercent:consumed ? 0 : 31,windowDurationMins:300,resetsAt:2000000000}},
          rateLimitResetCredits:options.availableCredits === undefined ? null : {availableCount:options.availableCredits - (consumed ? 1 : 0),credits:null}});
      }
      if (message.method === 'account/rateLimitResetCredit/consume') {
        if (!options.availableCredits || message.params.idempotencyKey !== 'stable-request-key') process.exit(7);
        consumed = true;
        return reply(message.id, {outcome:options.outcome || 'reset'});
      }
      process.exit(8);
    });
    lines.on('close', () => process.exit(0));
  `;
  return {
    spawnProcess(executable, args, spawnOptions) {
      assert.deepEqual(args, ["app-server", "--listen", "stdio://"]);
      assert.equal(spawnOptions.windowsHide, true);
      child = spawn(process.execPath, ["-e", script], spawnOptions);
      closed = new Promise((resolve) => child.once("close", (code) => resolve(code)));
      return child;
    },
    async waitClosed() { assert.equal(await closed, 0); },
  };
}

test("RPC handshake reads only account and limits, then closes its helper", async () => {
  const rpc = server();
  const usage = await readCodexUsage({ executable: "codex", spawnProcess: rpc.spawnProcess });
  assert.equal(usage.status, "ready");
  assert.equal(usage.session_pct, 31);
  assert.equal(usage.weekly_pct, null);
  await rpc.waitClosed();
});

test("earned-reset count is authoritative even when details are omitted", () => {
  assert.equal(normalizeRateLimits({ rateLimits: limits, rateLimitResetCredits: { availableCount: 2, credits: [] } }).reset_credits, 2);
  assert.equal(normalizeRateLimits({ rateLimits: limits, rateLimitResetCredits: null }).reset_credits, null);
});

test("a confirmed reset carries the same request key and refreshes limits from the server", async () => {
  const rpc = server({ availableCredits: 2 });
  const result = await consumeCodexReset({ idempotencyKey: "stable-request-key", executable: "codex", spawnProcess: rpc.spawnProcess });
  assert.equal(result.status, "reset");
  assert.equal(result.usage.session_pct, 0);
  assert.equal(result.usage.reset_credits, 1);
  await rpc.waitClosed();
});

test("no available credit blocks consumption before sending the action", async () => {
  const rpc = server({ availableCredits: 0 });
  const result = await consumeCodexReset({ idempotencyKey: "stable-request-key", executable: "codex", spawnProcess: rpc.spawnProcess });
  assert.equal(result.status, "noCredit");
  await rpc.waitClosed();
});

test("a confirmed successful reset stays successful if the follow-up query fails", async () => {
  const rpc = server({ availableCredits: 2, refreshFails: true });
  const result = await consumeCodexReset({ idempotencyKey: "stable-request-key", executable: "codex", spawnProcess: rpc.spawnProcess });
  assert.equal(result.status, "reset");
  assert.equal(result.usage.status, "unavailable");
  await rpc.waitClosed();
});

for (const [options, status] of [[{ signedOut: true }, "signed_out"], [{ apiKey: true }, "api_key"],
  [{ unsupported: true }, "unsupported"], [{ hang: true }, "unavailable"]]) {
  test(`RPC reports ${status} and cleans up`, async () => {
    const rpc = server(options);
    const usage = await readCodexUsage({ executable: "codex", spawnProcess: rpc.spawnProcess, timeoutMs: 600 });
    assert.equal(usage.status, status);
    assert.equal(usage.session_pct, null);
    await rpc.waitClosed();
  });
}

test("closing the panel cancels a pending query and terminates its helper", async () => {
  const rpc = server({ hang: true });
  const controller = new AbortController();
  const result = readCodexUsage({ executable: "codex", spawnProcess: rpc.spawnProcess, signal: controller.signal });
  controller.abort();
  assert.equal((await result).status, "cancelled");
  await rpc.waitClosed();
});
