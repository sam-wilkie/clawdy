const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { emptyUsage } = require('./codex-usage');
let sqlite;
const cache = new Map();

// Antigravity's steps.metadata protobuf: timestamp=1, token usage=9.
// Read metadata only, never message text, prompts, credentials or tool payloads.
function fields(bytes) {
  const result = new Map();
  let offset = 0;
  function varint() {
    let value = 0n;
    for (let shift = 0n; shift < 70n && offset < bytes.length; shift += 7n) {
      const byte = bytes[offset++];
      value |= BigInt(byte & 127) << shift;
      if (!(byte & 128)) {
        if (value > BigInt(Number.MAX_SAFE_INTEGER)) throw new Error('Oversized protobuf integer');
        return Number(value);
      }
    }
    throw new Error('Truncated protobuf');
  }
  while (offset < bytes.length) {
    const tag = varint();
    const number = Math.floor(tag / 8), wire = tag % 8;
    if (!number) throw new Error('Invalid protobuf tag');
    let value;
    if (wire === 0) value = varint();
    else if (wire === 2) {
      const length = varint();
      if (offset + length > bytes.length) throw new Error('Truncated protobuf field');
      value = bytes.subarray(offset, offset + length);
      offset += length;
    } else if (wire === 1 || wire === 5) {
      offset += wire === 1 ? 8 : 4;
      if (offset > bytes.length) throw new Error('Truncated protobuf fixed field');
      continue;
    } else throw new Error('Unsupported protobuf wire type');
    result.set(number, value);
  }
  return result;
}

function decodeUsage(bytes) {
  const metadata = fields(bytes);
  if (!(metadata.get(9) instanceof Uint8Array)) return null;
  const usage = fields(metadata.get(9));
  const input = usage.get(2) ?? 0, output = usage.get(3) ?? 0;
  const thinking = usage.get(9) ?? 0, cacheRead = usage.get(5) ?? 0;
  if (![input, output, thinking, cacheRead].every(v => Number.isSafeInteger(v) && v >= 0)
      || thinking > output || (usage.has(10) && thinking + usage.get(10) !== output)) return null;
  if (!input && !output && !cacheRead) return null;
  let timestamp = null;
  if (metadata.get(1) instanceof Uint8Array) {
    const seconds = fields(metadata.get(1)).get(1);
    if (Number.isSafeInteger(seconds) && seconds > 0) timestamp = seconds * 1000;
  }
  return { input_tokens: input, output_tokens: output, thinking_tokens: thinking,
    cache_read_tokens: cacheRead, timestamp };
}

function periodStarts(now) {
  const date = new Date(now);
  return { day: new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime(),
    month: new Date(date.getFullYear(), date.getMonth(), 1).getTime() };
}

function aggregate(records, now) {
  const starts = periodStarts(now);
  const periods = {};
  for (const period of ['day', 'month', 'all']) {
    const rows = records.filter(row => period === 'all' || row.timestamp >= starts[period]);
    periods[period] = { cost: null, messages: rows.length, input_tokens: 0,
      output_tokens: 0, cache_read_tokens: 0, thinking_tokens: 0 };
    for (const row of rows) {
      for (const key of ['input_tokens', 'output_tokens', 'cache_read_tokens', 'thinking_tokens']) periods[period][key] += row[key];
    }
  }
  return periods;
}

async function readAntigravityUsage({ home = os.homedir(), signal, now = Date.now() } = {}) {
  const records = [];
  let found = 0, failed = 0, readable = 0;
  const clients = new Set();
  const seen = new Set();
  for (const product of ['antigravity-cli', 'antigravity-ide']) {
    const dir = path.join(home, '.gemini', product, 'conversations');
    let files;
    try { files = await fs.readdir(dir); } catch { continue; }
    for (const name of files.filter(name => name.endsWith('.db'))) {
      if (signal?.aborted) return emptyUsage('cancelled');
      found++;
      const file = path.join(dir, name);
      seen.add(file);
      let db;
      try {
        const stat = await fs.stat(file);
        if (stat.size > 64 * 1024 * 1024) throw new Error('Database too large');
        const signature = `${stat.mtimeMs}:${stat.size}`;
        let entry = cache.get(file);
        if (!entry || entry.signature !== signature) {
          sqlite ||= require('sql.js')({ locateFile: () => require.resolve('sql.js/dist/sql-wasm.wasm') });
          const SQL = await sqlite;
          db = new SQL.Database(await fs.readFile(file));
          const rows = db.exec('SELECT metadata FROM steps WHERE metadata IS NOT NULL');
          const decoded = [];
          let malformed = 0;
          for (const [bytes] of rows[0]?.values || []) {
            try { const row = decodeUsage(bytes); if (row) decoded.push(row); }
            catch { malformed++; }
          }
          entry = { signature, rows: decoded, malformed };
          cache.set(file, entry);
        }
        readable++;
        failed += entry.malformed;
        if (entry.rows.length) clients.add(product === 'antigravity-cli' ? 'CLI' : 'IDE');
        records.push(...entry.rows);
      } catch { failed++; }
      finally { db?.close(); }
    }
  }
  for (const file of cache.keys()) if (!seen.has(file)) cache.delete(file);
  if (!found) return emptyUsage('no_history');
  if (!readable || !records.length) return emptyUsage('unavailable');
  return { ...emptyUsage('ready'), source: 'antigravity_db', updated_at: now,
    periods: aggregate(records, now), partial: failed > 0, scope: 'local_conversations', clients: [...clients] };
}

module.exports = { readAntigravityUsage, decodeUsage, periodStarts, aggregate };
