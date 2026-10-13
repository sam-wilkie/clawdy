// Account quotas and user-confirmed earned resets through Codex's own
// authenticated app-server. Each helper ends after its account operations.
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const readline = require("node:readline");
const { spawn } = require("node:child_process");

function emptyUsage(status = "loading") {
  return { status, session_pct: null, weekly_pct: null, reset_s: null };
}

function isFile(file) {
  try { return fs.statSync(file).isFile(); } catch { return false; }
}

function directories(root) {
  try {
    return fs.readdirSync(root, { withFileTypes: true })
      .filter((entry) => entry.isDirectory())
      .sort((a, b) => b.name.localeCompare(a.name, undefined, { numeric: true }))
      .map((entry) => path.join(root, entry.name));
  } catch { return []; }
}

function findCodexExecutable({ env = process.env, home = os.homedir(), platform = process.platform } = {}) {
  if (env.CLAWDY_CODEX_BIN) return isFile(env.CLAWDY_CODEX_BIN) ? env.CLAWDY_CODEX_BIN : null;
  const binary = platform === "win32" ? "codex.exe" : "codex";
  const paths = (env.PATH || env.Path || "").split(platform === "win32" ? ";" : ":");
  const candidates = paths.filter(Boolean).map((dir) => path.join(dir, binary));

  // The desktop app can be installed without putting Codex CLI on PATH.
  const codexHome = env.CODEX_HOME || path.join(home, ".codex");
  for (const dir of directories(path.join(codexHome, "packages", "app-server-daemon", "releases"))) {
    candidates.push(path.join(dir, "bin", binary), path.join(dir, binary));
  }
  if (platform === "win32") {
    for (const dir of directories(path.join(env.LOCALAPPDATA || path.join(home, "AppData", "Local"), "OpenAI", "Codex", "bin"))) {
      candidates.push(path.join(dir, binary));
    }
    // npm's .cmd shim requires a shell. Use the native binary shipped in the
    // package instead, including both the older vendor and newer package layout.
    const npmRoots = [env.APPDATA && path.join(env.APPDATA, "npm"), ...paths.filter(Boolean)];
    for (const root of npmRoots.filter(Boolean)) {
      const pkg = path.join(root, "node_modules", "@openai", "codex");
      const packages = [pkg, ...directories(path.join(pkg, "node_modules", "@openai"))];
      for (const nativePkg of packages) {
        for (const target of directories(path.join(nativePkg, "vendor"))) {
          candidates.push(path.join(target, "codex", binary));
        }
      }
    }
  } else {
    candidates.push(path.join(home, ".local", "bin", binary), "/opt/homebrew/bin/codex", "/usr/local/bin/codex");
    if (platform === "darwin") candidates.push("/Applications/Codex.app/Contents/Resources/codex");
  }
  return candidates.find(isFile) || null;
}

function number(value) {
  return typeof value === "number" && Number.isFinite(value) && value >= 0 ? value : null;
}

function normalizeRateLimits(result, now = Date.now()) {
  const rawCredits = result && result.rateLimitResetCredits && result.rateLimitResetCredits.availableCount;
  const resetCredits = Number.isInteger(rawCredits) && rawCredits >= 0 ? rawCredits : null;
  const buckets = result && result.rateLimitsByLimitId;
  const legacy = result && result.rateLimits;
  const limits = buckets && buckets.codex ||
    (legacy && (!legacy.limitId || legacy.limitId === "codex") ? legacy : null);
  if (!limits) return { ...emptyUsage("no_limits"), reset_credits: resetCredits };
  const primary = limits.primary || {};
  const secondary = limits.secondary || {};
  const session = number(primary.usedPercent);
  const weekly = number(secondary.usedPercent);
  if (session === null && weekly === null) return { ...emptyUsage("no_limits"), reset_credits: resetCredits };
  const remaining = (value) => number(value) === null ? null : Math.max(0, Math.ceil(value - now / 1000));
  return {
    status: "ready",
    session_pct: session,
    weekly_pct: weekly,
    session_window_minutes: number(primary.windowDurationMins),
    weekly_window_minutes: number(secondary.windowDurationMins),
    reset_s: remaining(primary.resetsAt),
    weekly_reset_s: remaining(secondary.resetsAt),
    updated_at: now,
    reset_credits: resetCredits,
  };
}

async function withCodexAccount(operation, { executable = findCodexExecutable(), signal, timeoutMs = 15000, spawnProcess = spawn } = {}) {
  if (signal && signal.aborted) return emptyUsage("cancelled");
  if (!executable) return emptyUsage("not_installed");
  let child;
  let lines;
  let timer;
  let failure;
  let nextId = 0;
  const pending = new Map();
  const fail = (error) => {
    failure = error;
    for (const { reject } of pending.values()) reject(error);
    pending.clear();
  };
  const abort = () => fail({ usageStatus: "cancelled" });
  const send = (message) => child.stdin.write(`${JSON.stringify(message)}\n`);
  const request = (method, params) => new Promise((resolve, reject) => {
    if (failure) return reject(failure);
    const id = nextId++;
    pending.set(id, { resolve, reject });
    send({ id, method, ...(params === undefined ? {} : { params }) });
  });
  try {
    child = spawnProcess(executable, ["app-server", "--listen", "stdio://"], {
      windowsHide: true,
      stdio: ["pipe", "pipe", "ignore"],
    });
    child.on("error", (error) => fail({ usageStatus: error.code === "ENOENT" ? "not_installed" : "unavailable" }));
    child.on("close", () => fail({ usageStatus: "unavailable" }));
    child.stdin.on("error", () => fail({ usageStatus: "unavailable" }));
    lines = readline.createInterface({ input: child.stdout });
    lines.on("line", (line) => {
      let message;
      try { message = JSON.parse(line); } catch { return; }
      if (!message || typeof message !== "object") return;
      // This client cannot fulfill server requests (e.g. external token refresh).
      if (message.method && message.id !== undefined) {
        send({ id: message.id, error: { code: -32601, message: "Unsupported client request" } });
        return;
      }
      const waiting = pending.get(message.id);
      if (!waiting) return;
      pending.delete(message.id);
      if (message.error) {
        waiting.reject({ usageStatus: message.error.code === -32601 ? "unsupported" : "unavailable" });
      } else {
        waiting.resolve(message.result);
      }
    });
    timer = setTimeout(() => fail({ usageStatus: "unavailable" }), timeoutMs);
    if (signal) signal.addEventListener("abort", abort, { once: true });
    await request("initialize", { clientInfo: { name: "clawdy_desktop", title: "Clawdy", version: "0.0.1" } });
    send({ method: "initialized", params: {} });
    const account = await request("account/read", { refreshToken: false });
    if (!account || !account.account) return emptyUsage("signed_out");
    if (account.account.type === "apiKey") return emptyUsage("api_key");
    return await operation(request);
  } catch (error) {
    return emptyUsage(error.usageStatus || "unavailable");
  } finally {
    clearTimeout(timer);
    if (signal) signal.removeEventListener("abort", abort);
    if (lines) lines.close();
    if (child) {
      child.stdin.end();
      // EOF normally stops app-server. Bound shutdown so closing the panel
      // never leaves a quota helper running in the background.
      const stopTimer = setTimeout(() => child.kill(), 500);
      stopTimer.unref();
      child.once("close", () => clearTimeout(stopTimer));
    }
  }
}

function readCodexUsage(options) {
  return withCodexAccount(async (request) => normalizeRateLimits(await request("account/rateLimits/read")), options);
}

function consumeCodexReset({ idempotencyKey, ...options } = {}) {
  if (typeof idempotencyKey !== "string" || !idempotencyKey.trim()) {
    return Promise.resolve({ status: "invalid_request" });
  }
  return withCodexAccount(async (request) => {
    const usage = normalizeRateLimits(await request("account/rateLimits/read"));
    // Re-check eligibility before consuming; the panel's count may be stale.
    if (!(usage.reset_credits > 0)) return { status: "noCredit", usage };
    const result = await request("account/rateLimitResetCredit/consume", { idempotencyKey });
    const status = result && result.outcome;
    if (!["reset", "alreadyRedeemed", "nothingToReset", "noCredit"].includes(status)) {
      return { status: "unavailable" };
    }
    // Preserve the confirmed outcome if refreshing the percentages fails.
    try {
      return { status, usage: normalizeRateLimits(await request("account/rateLimits/read")) };
    } catch {
      return { status, usage: emptyUsage("unavailable") };
    }
  }, options);
}

module.exports = { emptyUsage, findCodexExecutable, normalizeRateLimits, readCodexUsage, consumeCodexReset };
