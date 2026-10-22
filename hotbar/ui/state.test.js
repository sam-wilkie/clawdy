import test from 'node:test';
import assert from 'node:assert/strict';
import { AGENTS, agentOf, billingOf, ringOf, dockLabel, formatUsd } from './state.js';

const plan = (...values) => ({ status: 'ok', billing: 'plan', plan: {
  status: 'ok', limits: values.map((used_pct, i) => ({ id: i ? 'weekly' : 'session', used_pct })),
} });
const payg = (cost_kind = 'reported', cost = 1.5) => ({ status: 'ok', cost_kind,
  totals: { today: { cost }, '7d': { cost: 99 } } });

test('agent order and display names preserve file ids', () => {
  assert.deepEqual(AGENTS.map(({ id, name }) => [id, name]), [
    ['claude', 'Claude'], ['codex', 'Codex'], ['opencode', 'OpenCode'],
    ['kiro', 'Kiro'], ['pi', 'Gentle Shell'],
  ]);
  assert.deepEqual(agentOf({ agents: { claude: plan(62) } }, 'kiro'), { status: 'absent' });
  assert.equal(agentOf(null, 'pi').status, 'absent');
});

test('billing defaults to payg for old files and missing entries', () => {
  assert.equal(billingOf(plan(62)), 'plan');
  for (const agent of [payg(), { billing: 'payg' }, undefined]) assert.equal(billingOf(agent), 'payg');
});

test('rings use the highest percentage and cherry starts at 90', () => {
  assert.deepEqual(ringOf(plan(21, 47)), { pct: 47, high: false });
  assert.deepEqual(ringOf(plan(93, 71)), { pct: 93, high: true });
  assert.deepEqual(ringOf(plan(90)), { pct: 90, high: true });
  assert.deepEqual(ringOf(plan(0)), { pct: 0, high: false });
  assert.deepEqual(ringOf(plan(120)), { pct: 120, high: true });
});

test('missing, unavailable, malformed and payg plans have no ring', () => {
  for (const status of ['no_data', 'signed_out', 'not_installed', 'error']) {
    assert.equal(ringOf({ ...plan(62), plan: { ...plan(62).plan, status } }), null);
  }
  for (const limits of [null, {}, [], [null], [{ used_pct: '62' }], [{ used_pct: NaN }],
    [{ used_pct: Infinity }], [{ used_pct: -1 }], [{ used_pct: 62 }, {}]]) {
    assert.equal(ringOf({ ...plan(62), plan: { status: 'ok', limits } }), null);
  }
  for (const agent of [undefined, {}, { billing: 'plan' }, { ...plan(62), billing: 'payg' },
    { ...plan(62), status: 'absent' }]) assert.equal(ringOf(agent), null);
});

test('plan labels list every limit in Spanish and never show money', () => {
  assert.equal(dockLabel('claude', { ...plan(62, 38), ...payg() }), 'Claude: Sesión · 5 h 62 %, Semana 38 %');
  assert.equal(dockLabel('codex', { ...plan(21), plan: { status: 'ok', limits: [
    { id: 'primary', used_pct: 21 }, { id: 'custom', label: 'Límite especial', used_pct: 4 },
  ] } }), 'Codex: Ventana · 5 h 21 %, Límite especial 4 %');
  assert.equal(dockLabel('kiro', { ...plan(34), plan: { status: 'ok', limits: [
    { id: 'credits', used_pct: 34 },
  ] } }), 'Kiro: Créditos del ciclo 34 %');
  assert.equal(dockLabel('claude', { billing: 'plan' }), 'Claude: Sin datos de límites');
});

test('payg labels use today, es-CO USD, estimated and read-error wording', () => {
  assert.equal(formatUsd(1234.5), new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'USD' }).format(1234.5));
  assert.equal(dockLabel('pi', payg()), `Gentle Shell: hoy ${formatUsd(1.5)} reportado`);
  assert.equal(dockLabel('codex', payg('estimated', 2)), `Codex: hoy ≈${formatUsd(2)} estimado`);
  assert.equal(dockLabel('opencode', { ...payg(), status: 'error' }), `OpenCode: hoy ${formatUsd(1.5)} reportado, falló la lectura`);
  assert.equal(dockLabel('pi', payg('reported', null)), 'Gentle Shell: hoy Sin precio');
  assert.equal(dockLabel('kiro'), 'Kiro: No instalado');
  assert.match(dockLabel('pi', { ...payg(), totals: { today: { cost: 1, cost_partial: true } } }), /parcial/);
});
