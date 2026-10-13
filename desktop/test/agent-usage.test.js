const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");
const { normalizeClaude, normalizeKiro, normalizeOpenCode, readKiroUsage, readOpenCodeUsage } = require("../agent-usage");

test("Claude zero usage stays known and both reset times are normalized", () => {
  const usage = normalizeClaude({ rate_limits: { five_hour: { used_percentage: 0, resets_at: 1700000060 },
    seven_day: { used_percentage: 30, resets_at: 1700010000 } } }, 1700000000000, 1700000000000);
  assert.equal(usage.session_pct, 0);
  assert.equal(usage.weekly_pct, 30);
  assert.equal(usage.reset_s, 60);
  assert.equal(usage.weekly_reset_s, 10000);
});

const cache = { timestamp: 1700000000000, usageBreakdowns: [{ type: "CREDIT", currentUsage: 2000, usageLimit: 2000,
  resetDate: "2026-11-01T00:00:00.000Z" }] };

test("Kiro credits are monthly-plan usage with their actual cache timestamp", () => {
  const usage = normalizeKiro(cache);
  assert.equal(usage.session_pct, 100);
  assert.equal(usage.weekly_pct, null);
  assert.equal(usage.quota_used, 2000);
  assert.equal(usage.updated_at, cache.timestamp);
  assert.equal(normalizeKiro({ usageBreakdowns: [{ type: "CREDIT", usageLimit: 0 }] }).status, "no_cache");
});

test("Kiro cache query reads only the extension state and ignores secret-storage rows", async () => {
  const SQL = await require("sql.js")({ locateFile: () => require.resolve("sql.js/dist/sql-wasm.wasm") });
  const db = new SQL.Database();
  const temp = await fs.mkdtemp(path.join(os.tmpdir(), "clawdy-usage-"));
  try {
    db.run("CREATE TABLE ItemTable (key TEXT PRIMARY KEY, value TEXT)");
    db.run("INSERT INTO ItemTable VALUES (?, ?)", ["kiro.kiroAgent", JSON.stringify({ "kiro.resourceNotifications.usageState": cache })]);
    db.run("INSERT INTO ItemTable VALUES (?, ?)", ["secret://kiro", "not-valid-json"]);
    const file = path.join(temp, "state.vscdb");
    await fs.writeFile(file, db.export());
    const usage = await readKiroUsage({ env: { CLAWDY_KIRO_STATE_DB: file } });
    assert.equal(usage.status, "ready");
    assert.equal(usage.quota_limit, 2000);
  } finally {
    db.close();
    assert.equal(path.dirname(path.resolve(temp)), path.resolve(os.tmpdir()));
    assert.ok(path.basename(temp).startsWith("clawdy-usage-"));
    await fs.rm(temp, { recursive: true, force: true });
  }
});

test("OpenCode queries aggregates only, uses no external plugins, and preserves exact token counts", async () => {
  const usage = await readOpenCodeUsage({ executable: "opencode", runFile: async (_executable, args, options) => {
    assert.equal(args[0], "--pure");
    assert.equal(args[1], "db");
    assert.match(args[2], /SUM\(json_extract/);
    assert.doesNotMatch(args[2], /SELECT\s+\*/i);
    assert.equal(options.windowsHide, true);
    return { stdout: JSON.stringify([{ input_tokens: 1234567, output_tokens: 4567, cache_read_tokens: 10000, cost: 4.72 }]) };
  } });
  assert.equal(usage.source, "opencode_db");
  assert.equal(usage.metrics[0].value, 1234567);
  assert.equal(usage.metrics[3].format, "usd");
  assert.equal(usage.session_pct, null);
  assert.equal(normalizeOpenCode({ input_tokens: null }).status, "unavailable");
});
