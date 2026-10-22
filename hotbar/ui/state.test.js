import test from 'node:test';
import assert from 'node:assert/strict';
import { AGENTS, agentOf, billingOf, ringOf, dockLabel, formatUsd } from './state.js';
import { collapsedDot, attentionList, attentionLabel } from './state.js';

test('collapsed dots share ring thresholds, absence and billing rules', () => {
  for (const [pct, expected] of [[0, 'dim'], [29.9, 'dim'], [30, 'brand'], [89.9, 'brand'], [90, 'alert'], [120, 'alert']])
    assert.equal(collapsedDot(plan(pct)), expected);
  assert.equal(collapsedDot(plan(20, 93)), 'alert');
  assert.equal(collapsedDot({ ...plan(99), billing: 'payg' }), 'brand');
  assert.equal(collapsedDot({ ...payg(), status: 'error' }), 'alert');
  assert.equal(collapsedDot({ ...plan(99), status: 'absent' }), 'track');
  assert.equal(collapsedDot({ billing: 'plan' }), 'brand');
  assert.equal(collapsedDot({ ...plan(99), plan: { status: 'error' } }), 'brand');
});
test('attention names and accessible tooltip use configured agent order', () => {
  const data = { agents: { claude: plan(93), codex: plan(90), opencode: { ...payg(), status: 'error' },
    kiro: { ...plan(99), status: 'absent' }, pi: { ...plan(99), billing: 'payg' } } };
  assert.deepEqual(attentionList(data), ['Claude', 'Codex', 'OpenCode']);
  assert.equal(attentionLabel(data), 'Atención: Claude, Codex, OpenCode');
  assert.equal(attentionLabel({ agents: { claude: plan(93), codex: plan(90) } }), 'Atención: Claude, Codex');
  assert.deepEqual(attentionList(null), []);
  assert.equal(attentionLabel(null), 'Sin alertas');
  assert.equal(attentionLabel({ agents: { claude: plan(89) } }), 'Sin alertas');
});
import { panelState, acceptUsage, costLabel, projectRows } from './state.js';
import * as cards from './state.js';

test('card limit names use Spanish ids, fallback labels and actual windows', () => {
  for (const [id, expected] of [['session', 'Sesión · 5 h'], ['primary', 'Ventana · 5 h'],
    ['weekly', 'Semana'], ['credits', 'Créditos del ciclo']]) {
    assert.equal(cards.limitName({ id }), expected);
  }
  assert.equal(cards.limitName({ id: 'primary', window_min: 120 }), 'Ventana · 2 h');
  assert.equal(cards.limitName({ id: 'weekly', window_min: 10080 }), 'Semana · 7 d');
  assert.equal(cards.limitName({ id: 'custom', label: 'Especial', window_min: 45 }), 'Especial · 45 min');
  assert.equal(cards.limitName({}), 'Límite');
});

test('reset labels use the timestamp and omit unavailable reset times', () => {
  const time = Date.parse('2026-10-16T12:00:00Z');
  assert.equal(cards.resetLabel('2026-10-16T14:14:00Z', time), 'Reinicio en 2 h 14 min');
  assert.equal(cards.resetLabel('2026-10-19T16:00:00Z', time), 'Reinicio en 3 d 4 h');
  assert.equal(cards.resetLabel('2026-10-16T12:38:00Z', time), 'Reinicio en 38 min');
  assert.equal(cards.resetLabel('2026-10-15T12:00:00Z', time), 'Reinicio en 0 min');
  for (const value of [null, undefined, 'invalid']) assert.equal(cards.resetLabel(value, time), '');
});

test('card billing, unavailable plans and numeric Codex reset credits', () => {
  assert.equal(cards.cardState('claude', plan(62)).chip, 'Plan');
  assert.equal(cards.cardState('pi', payg()).chip, 'Pago por uso');
  assert.equal(cards.cardState('codex', payg('estimated')).chip, 'API · estimado');
  for (const status of ['no_data', 'error', 'signed_out', 'not_installed']) {
    const card = cards.cardState('claude', { ...plan(62), plan: { status, limits: [{ used_pct: 62 }] } });
    assert.equal(card.note, 'Sin datos de límites');
    assert.deepEqual(card.limits, []);
    assert.equal(card.cost, '');
  }
  assert.equal(cards.cardState('claude', { billing: 'plan' }).note, 'Sin datos de límites');
  for (const value of [null, undefined, '2', NaN, Infinity]) {
    assert.equal(cards.cardState('codex', { ...plan(21), plan: { ...plan(21).plan, reset_credits: value } }).resets, '');
  }
  assert.equal(cards.cardState('codex', { ...plan(21), plan: { ...plan(21).plan, reset_credits: 0 } }).resets, '0 reinicios disponibles');
  assert.equal(cards.cardState('codex', { ...plan(21), plan: { ...plan(21).plan, reset_credits: 2 } }).resets, '2 reinicios disponibles');
});

test('Kiro credits use es-CO grouping and tokens use compact K/M/B units', () => {
  const agent = { ...plan(34), plan: { ...plan(34).plan, credits: { used: 340, limit: 1000 } } };
  assert.deepEqual(cards.cardState('kiro', agent).credits, ['340', '1.000', '660']);
  assert.deepEqual([0, 11500, 1430000, 1209000000].map(cards.formatTokens), ['0', '11.5 K', '1.4 M', '1.21 B']);
});

test('project share compares output tokens with the largest project in the selected range', () => {
  const agent = { projects: [{ today: { out: 10 }, '7d': { out: 80 } },
    { today: { out: 40 }, '7d': { out: 40 } }] };
  assert.equal(cards.projectShare(agent.projects[0], agent), .25);
  assert.equal(cards.projectShare(agent.projects[1], agent, '7d'), .5);
  assert.equal(cards.projectShare({ today: { out: 0 } }, { projects: [] }), 0);
});

const plan = (...values) => ({ status: 'ok', billing: 'plan', plan: {
  status: 'ok', limits: values.map((used_pct, i) => ({ id: i ? 'weekly' : 'session', used_pct })),
} });
const payg = (cost_kind = 'reported', cost = 1.5) => ({ status: 'ok', cost_kind,
  totals: { today: { cost }, '7d': { cost: 99 } } });

const now = Date.parse('2026-10-16T12:06:00Z');
const figures = (cost, out = 10) => ({ in: 20, out, cw: 0, cr: 0, cost, cost_partial: false });
const usage = () => ({ version: 1, currency: 'USD', generated_at: '2026-10-16T12:00:00Z', agents: {
  claude: { ...plan(62), cost_kind: 'estimated', totals: { today: figures(400) } }, codex: { status: 'absent' },
  opencode: { ...payg(), totals: { today: figures(1.5), '7d': figures(9) } },
  pi: { ...payg('estimated'), totals: { today: figures(2), '7d': figures(3) } },
} });

test('panel money is payg only, localized, estimated, partial or unpriced', () => {
  const data = usage(), state = panelState(data, undefined, now);
  assert.equal(state.window, 'today');
  assert.equal(costLabel(data.agents.claude), '');
  assert.equal(costLabel(data.agents.opencode), formatUsd(1.5));
  assert.equal(costLabel(data.agents.pi), `≈${formatUsd(2)} estimado`);
  assert.equal(state.spend, `≈${formatUsd(3.5)}`);
  assert.equal(panelState(data, '7d', now).spend, `≈${formatUsd(12)}`);
  data.agents.pi.totals.today = figures(null);
  assert.equal(costLabel(data.agents.pi), 'Sin precio');
  assert.match(panelState(data).agents.find(a => a.id === 'pi').detail, /10 tokens de salida/);
  data.agents.opencode.totals.today.cost_partial = true;
  assert.match(costLabel(data.agents.opencode), /parcial/);
  const rows = [{ name: 'small', today: figures(null, 1) }, { name: 'big', today: figures(2, 90) }];
  assert.deepEqual(projectRows({ projects: rows }).map(r => r.name), ['big', 'small']);
  assert.equal(rows[0].today.out, 1);
  assert.equal(projectRows({ projects: rows })[1].today.cost, null);
});

test('panel freshness, missing, absent and kept error totals', () => {
  const data = usage();
  assert.equal(panelState(data, 'today', now).stale, true);
  assert.equal(panelState(data, 'today', now, 600).stale, false);
  assert.equal(panelState(data, 'today', now - 60000).stale, false);
  assert.equal(panelState(data, 'today', now).freshness, 'Actualizado hace 6 min');
  assert.equal(panelState(null).freshness, 'Sin datos de uso');
  assert.equal(panelState(data).agents.find(a => a.id === 'kiro').detail, 'No instalado');
  data.agents.opencode.status = 'error';
  assert.match(panelState(data).agents.find(a => a.id === 'opencode').detail, /Falló la lectura.*1,50/);
});

test('invalid payloads retain last good data; null means a missing file', () => {
  const good = usage();
  assert.equal(acceptUsage(null, good), good);
  const bad = structuredClone(good); bad.agents.pi.totals.today.out = 'broken';
  for (const value of ['broken', {}, [], { ...good, version: 2 },
    { ...good, generated_at: 'bad date' }, { ...good, agents: {} }, bad]) {
    assert.equal(acceptUsage(good, value), good);
    assert.equal(acceptUsage(null, value), null);
  }
  assert.equal(acceptUsage(good, null), null);
});

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

test('project rows are named by the label the usage file writes', () => {
  assert.equal(cards.projectLabel({ key: String.raw`C:\work\clawdy`, label: 'clawdy' }), 'clawdy');
  assert.equal(cards.projectLabel({ key: '/home/me/work/api-service' }), 'api-service');
  assert.equal(cards.projectLabel({ key: 'C:\\work\\web-store\\' }), 'web-store');
  assert.equal(cards.projectLabel({}), 'Proyecto');
});

test('plan percentages are rounded the same way in the dock and the cards', () => {
  assert.equal(cards.formatPct(100 / 3), '33,33 %');
  assert.equal(cards.formatPct(34), '34 %');
  assert.match(dockLabel('kiro', { status: 'ok', billing: 'plan', plan: { status: 'ok',
    limits: [{ id: 'credits', used_pct: 100 / 3 }] } }), /33,33 %/);
});

test('pets map each agent to its relative idle asset', () => {
  for (const [id, pet] of [['claude', 'claude'], ['codex', 'codex'],
    ['kiro', 'monster'], ['opencode', 'monster'], ['pi', 'monster']]) {
    assert.equal(cards.petOf(id), `assets/pets/${pet}-idle.svg`);
  }
});


test('chevron points into its edge when expanded and away when collapsed', async () => {
  const { chevronRotation } = await import('./state.js');
  for (const [edge, angle] of [['right', 0], ['bottom', 90], ['left', 180], ['top', 270]]) {
    assert.equal(chevronRotation(edge, false), angle);
    assert.equal(chevronRotation(edge, true), (angle + 180) % 360);
  }
  assert.equal(chevronRotation(undefined, false), 0);
});

import { configView, DEFAULT_STALE_AFTER_S } from './state.js';
test('config view falls back to defaults and filters agents by id', () => {
  const all = AGENTS.map(a => a.id);
  for (const config of [null, undefined, {}, { stale_after_s: 0, agents: 'x' }]) {
    const view = configView(config);
    assert.equal(view.staleAfter, DEFAULT_STALE_AFTER_S);
    assert.deepEqual([...view.shown], all);
    assert.equal(view.error, null);
  }
  const view = configView({ stale_after_s: 60, agents: ['kiro', 'claude', 'nope'], error: 'invalid JSON' });
  assert.equal(view.staleAfter, 60);
  assert.deepEqual([...view.shown], ['claude', 'kiro']);
  assert.equal(view.error, 'invalid JSON');
});

import { cellText, cellTip, cellRunLabel } from './state.js';
test('custom cell text, tooltip and run status', () => {
  assert.equal(cellText('GitHub'), 'Git');
  assert.equal(cellText('  w '), 'w');
  assert.equal(cellText('\u{1F600}\u{1F600}\u{1F600}\u{1F600}'), '\u{1F600}\u{1F600}\u{1F600}');
  for (const empty of ['', '   ', null, undefined]) assert.equal(cellText(empty), '?');
  assert.equal(cellTip({ label: 'GH', error: null }), 'GH');
  assert.equal(cellTip({ label: 'X', error: 'unknown action prefix' }), 'X: unknown action prefix');
  assert.equal(cellRunLabel(null), 'Ejecutando…');
  assert.equal(cellRunLabel({ state: 'ok', truncated: false }), 'Listo');
  assert.equal(cellRunLabel({ state: 'ok', truncated: true }), 'Salida truncada (64 KiB)');
  assert.equal(cellRunLabel({ state: 'timeout' }), 'Tiempo agotado (10 s)');
  assert.equal(cellRunLabel({ state: 'error', exit: 3 }), 'Terminó con error (código 3)');
  assert.equal(cellRunLabel({ state: 'error', exit: null }), 'No se pudo ejecutar');
});

import { invokeReady } from './theme.js';
test('invokeReady retries only while the command state is not managed yet', async () => {
  let calls = 0;
  globalThis.window = { __TAURI__: { core: { invoke: async (command, args) => {
    calls++;
    if (command === 'late' && calls < 3) throw new Error('state not managed for field `store` on command `late`');
    if (command === 'broken') throw new Error('boom');
    return { command, args };
  } } } };
  assert.deepEqual(await invokeReady('late', { a: 1 }), { command: 'late', args: { a: 1 } });
  assert.equal(calls, 3);
  calls = 0;
  await assert.rejects(invokeReady('broken'), /boom/);
  assert.equal(calls, 1);
  delete globalThis.window;
});
