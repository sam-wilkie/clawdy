const fs = require("node:fs/promises");
const syncFs = require("node:fs");
const path = require("node:path");
const os = require("node:os");
const { execFile } = require("node:child_process");
const { promisify } = require("node:util");
const { emptyUsage } = require("./codex-usage");
const { readAntigravityUsage, periodStarts } = require("./antigravity-usage");
const runFile = promisify(execFile);
let sqlite;

function numeric(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

function normalizeClaude(data, updatedAt, now = Date.now()) {
  const limits = data?.rate_limits || {};
  const primary = limits.five_hour || {};
  const secondary = limits.seven_day || {};
  const session = numeric(primary.used_percentage);
  const weekly = numeric(secondary.used_percentage);
  if (session === null && weekly === null) return emptyUsage("no_limits");
  const remaining = (epoch) => numeric(epoch) === null ? null : Math.max(0, Math.ceil(epoch - now / 1000));
  return { status: "ready", source: "claude_statusline", session_pct: session, weekly_pct: weekly,
    reset_s: remaining(primary.resets_at), weekly_reset_s: remaining(secondary.resets_at), updated_at: updatedAt };
}

function normalizeKiro(cache, now = Date.now()) {
  const credits = cache?.usageBreakdowns?.find((item) => item.type === "CREDIT");
  const used = numeric(credits?.currentUsage);
  const limit = numeric(credits?.usageLimit);
  if (used === null || limit === null || limit <= 0) return emptyUsage("no_cache");
  const reset = typeof credits.resetDate === "string" ? Date.parse(credits.resetDate) : NaN;
  return { status: "ready", source: "kiro_cache", session_pct: used / limit * 100, weekly_pct: null,
    reset_s: Number.isFinite(reset) ? Math.max(0, Math.ceil((reset - now) / 1000)) : null,
    updated_at: numeric(cache.timestamp), quota_used: used, quota_limit: limit,
    metrics: [{ label: "Créditos usados", value: used }, { label: "Créditos del plan", value: limit },
      { label: "Créditos restantes del plan", value: Math.max(0, limit - used) }] };
}

async function kiroStatePaths(home, env, platform) {
  if (env.CLAWDY_KIRO_STATE_DB) return [env.CLAWDY_KIRO_STATE_DB];
  const base = platform === "win32" ? path.join(env.APPDATA || path.join(home, "AppData/Roaming"), "Kiro")
    : platform === "darwin" ? path.join(home, "Library/Application Support/Kiro")
    : path.join(env.XDG_CONFIG_HOME || path.join(home, ".config"), "Kiro");
  const user = path.join(base, "User");
  const files = [path.join(user, "globalStorage/state.vscdb")];
  try {
    for (const dir of await fs.readdir(path.join(user, "profiles"), { withFileTypes: true })) {
      if (dir.isDirectory()) files.push(path.join(user, "profiles", dir.name, "globalStorage/state.vscdb"));
    }
  } catch { /* The default profile does not need a profiles directory. */ }
  return files;
}

async function readKiroUsage({ home = os.homedir(), env = process.env, platform = process.platform, signal } = {}) {
  let latest = null;
  for (const file of await kiroStatePaths(home, env, platform)) {
    if (signal?.aborted) return emptyUsage("cancelled");
    let db;
    try {
      const stat = await fs.stat(file);
      if (stat.size > 64 * 1024 * 1024) continue;
      sqlite ||= require("sql.js")({ locateFile: () => require.resolve("sql.js/dist/sql-wasm.wasm") });
      const SQL = await sqlite;
      db = new SQL.Database(await fs.readFile(file));
      // Query only the extension's global state, excluding secret-storage rows.
      const rows = db.exec("SELECT value FROM ItemTable WHERE key IN ('kiro.kiroAgent', 'kiro.kiroagent')");
      for (const [raw] of rows[0]?.values || []) {
        const state = JSON.parse(typeof raw === "string" ? raw : Buffer.from(raw).toString("utf8"));
        const usage = normalizeKiro(state["kiro.resourceNotifications.usageState"]);
        if (usage.status === "ready" && (!latest || usage.updated_at > latest.updated_at)) latest = usage;
      }
    } catch { /* An absent or busy cache should not interrupt the desktop. */ }
    finally { if (db) db.close(); }
  }
  return latest || emptyUsage("no_cache");
}

function findOpenCode({ home = os.homedir(), env = process.env, platform = process.platform } = {}) {
  const binary = platform === "win32" ? "opencode.exe" : "opencode";
  const candidates = env.CLAWDY_OPENCODE_BIN ? [env.CLAWDY_OPENCODE_BIN] : [
    ...(env.PATH || env.Path || "").split(platform === "win32" ? ";" : ":").filter(Boolean).map((dir) => path.join(dir, binary)),
    path.join(home, ".opencode/bin", binary), path.join(home, ".local/bin", binary),
    path.join(env.APPDATA || path.join(home, "AppData/Roaming"), "npm/node_modules/opencode-ai/bin", binary),
  ];
  return candidates.find((file) => { try { return syncFs.statSync(file).isFile(); } catch { return false; } });
}

function normalizeOpenCode(row, now = Date.now()) {
  if (!row || numeric(row.input_tokens) === null || numeric(row.output_tokens) === null) return emptyUsage("unavailable");
  const metrics = [{ label: "Tokens de entrada", value: row.input_tokens }, { label: "Tokens de salida", value: row.output_tokens }];
  if (numeric(row.cache_read_tokens) !== null) metrics.push({ label: "Tokens leídos de caché", value: row.cache_read_tokens });
  if (numeric(row.cost) !== null) metrics.push({ label: "Coste estimado", value: row.cost, format: "usd" });
  const periods = row.periods || { all: row };
  return { ...emptyUsage("ready"), source: "opencode_db", updated_at: now, metrics, periods };
}

async function readOpenCodeUsage(options = {}) {
  const executable = options.executable || findOpenCode(options);
  if (!executable) return emptyUsage("not_installed");
  // Let OpenCode query its own database; the result contains aggregates only.
  const now = options.now ?? Date.now();
  const starts = periodStarts(now);
  const query = `SELECT COALESCE(SUM(json_extract(data,'$.tokens.input')),0) AS input_tokens,
    COALESCE(SUM(json_extract(data,'$.tokens.output')),0) AS output_tokens,
    COALESCE(SUM(json_extract(data,'$.tokens.cache.read')),0) AS cache_read_tokens,
    SUM(json_extract(data,'$.cost')) AS cost,
    COUNT(*) AS messages,
    COUNT(json_extract(data,'$.cost')) AS cost_messages,
    'all' AS period FROM message WHERE json_extract(data,'$.role')='assistant'`;
  const periodQuery = ['day', 'month'].map(period => query.replace("'all' AS period", `'${period}' AS period`)
    + ` AND time_created>=${Math.floor(starts[period])}`).join(' UNION ALL ');
  try {
    const { stdout } = await (options.runFile || runFile)(executable, ["--pure", "db", `${query} UNION ALL ${periodQuery}`, "--format", "json"], {
      windowsHide: true, timeout: 30000, maxBuffer: 1024 * 1024, encoding: "utf8", signal: options.signal,
    });
    const rows = JSON.parse(stdout);
    const all = rows.find(row => row.period === 'all') || rows[0];
    if (!all) return emptyUsage('unavailable');
    return normalizeOpenCode({ ...all, periods: Object.fromEntries(rows.map(row => [row.period || 'all', row])) }, now);
  } catch (error) {
    return emptyUsage(error.name === "AbortError" ? "cancelled" : "unavailable");
  }
}

async function readAgentUsage(agent, options = {}) {
  if (agent === "kiro") return readKiroUsage(options);
  if (agent === "opencode") return readOpenCodeUsage(options);
  if (agent === "antigravity") return readAntigravityUsage(options);
  if (agent === "claude") {
    const file = path.join(options.home || os.homedir(), ".clawd-tank/statusline-cache.json");
    try {
      return normalizeClaude(JSON.parse(await fs.readFile(file, "utf8")), (await fs.stat(file)).mtimeMs);
    } catch { return emptyUsage("no_cache"); }
  }
  return emptyUsage("no_limits");
}

module.exports = { readAgentUsage, readKiroUsage, readOpenCodeUsage, normalizeClaude, normalizeKiro, normalizeOpenCode };
