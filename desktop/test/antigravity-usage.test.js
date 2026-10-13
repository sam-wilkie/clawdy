const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { decodeUsage, aggregate, periodStarts, readAntigravityUsage } = require('../antigravity-usage');

function varint(number) {
  const bytes = [];
  do { bytes.push((number % 128) | (number > 127 ? 128 : 0)); number = Math.floor(number / 128); } while (number);
  return bytes;
}
const integer = (field, value) => [...varint(field * 8), ...varint(value)];
const message = (field, bytes) => [...varint(field * 8 + 2), ...varint(bytes.length), ...bytes];
function metadata(timestamp, input = 1200, output = 100) {
  return Uint8Array.from([...message(1, integer(1, Math.floor(timestamp / 1000))),
    ...message(9, [...integer(2, input), ...integer(3, output), ...integer(5, 500), ...integer(9, 60), ...integer(10, output - 60)])]);
}

test('Antigravity metadata preserves exact totals and does not add reasoning twice', () => {
  const row = decodeUsage(metadata(1791800000000));
  assert.equal(row.input_tokens, 1200);
  assert.equal(row.output_tokens, 100);
  assert.equal(row.thinking_tokens, 60);
  assert.equal(row.cache_read_tokens, 500);
  assert.equal(decodeUsage(Uint8Array.from(integer(4, 12))), null);
  assert.throws(() => decodeUsage(Uint8Array.from([74, 10, 1])));
  assert.equal(decodeUsage(Uint8Array.from(message(9, [...integer(3, 10), ...integer(9, 11)]))), null);
});

test('local day/month boundaries include midnight and keep older history only in accumulated totals', () => {
  const now = new Date(2026, 9, 12, 15).getTime();
  const starts = periodStarts(now);
  const periods = aggregate([decodeUsage(metadata(starts.day)), decodeUsage(metadata(starts.day - 1000)),
    decodeUsage(metadata(starts.month - 1000))], now);
  assert.equal(periods.day.messages, 1);
  assert.equal(periods.month.messages, 2);
  assert.equal(periods.all.messages, 3);
  assert.equal(periods.all.cost, null);
});

test('reader aggregates metadata only, refreshes changed databases, and isolates broken conversations', async () => {
  const home = await fs.mkdtemp(path.join(os.tmpdir(), 'clawdy-agy-'));
  const dir = path.join(home, '.gemini/antigravity-cli/conversations');
  const SQL = await require('sql.js')();
  const now = Date.now();
  await fs.mkdir(dir, { recursive: true });
  const db = new SQL.Database();
  try {
    db.run('CREATE TABLE steps (metadata BLOB, step_payload TEXT)');
    db.run('INSERT INTO steps VALUES (?, ?)', [metadata(now), 'Private conversation must never leave the database']);
    const file = path.join(dir, 'session.db');
    await fs.writeFile(file, db.export());
    await fs.writeFile(path.join(dir, 'broken.db'), 'not sqlite');
    const first = await readAntigravityUsage({ home, now });
    assert.equal(first.periods.all.input_tokens, 1200);
    assert.equal(first.partial, true);
    assert.deepEqual(first.clients, ['CLI']);
    assert.doesNotMatch(JSON.stringify(first), /Private conversation/);
    db.run('INSERT INTO steps VALUES (?, ?)', [metadata(now, 2000), 'another message']);
    await fs.writeFile(file, db.export());
    await fs.utimes(file, new Date(), new Date(now + 2000));
    assert.equal((await readAntigravityUsage({ home, now })).periods.all.input_tokens, 3200);
    assert.equal((await readAntigravityUsage({ home, signal: { aborted: true } })).status, 'cancelled');
  } finally {
    db.close();
    await fs.rm(home, { recursive: true, force: true });
  }
});
