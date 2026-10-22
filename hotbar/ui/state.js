export const AGENTS = Object.freeze([
  { id: 'claude', name: 'Claude' }, { id: 'codex', name: 'Codex' },
  { id: 'opencode', name: 'OpenCode' }, { id: 'kiro', name: 'Kiro' },
  { id: 'pi', name: 'Gentle Shell' },
].map(Object.freeze));
export const agentOf = (data, id) => data?.agents?.[id] ?? { status: 'absent' };
export const billingOf = (agent) => agent?.billing === 'plan' ? 'plan' : 'payg';
const usd = new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'USD' });
const number = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 2 });
export const formatUsd = (value) => usd.format(value);
export const WINDOWS = [['today', 'Hoy'], ['7d', '7 días'], ['30d', '30 días'], ['month', 'Mes']];
export function costLabel(agent, window = 'today') {
  if (billingOf(agent) === 'plan') return '';
  const row = agent?.totals?.[window];
  if (!Number.isFinite(row?.cost) || agent.cost_kind === 'none') return 'Sin precio';
  return `${agent.cost_kind === 'estimated' ? '≈' : ''}${formatUsd(row.cost)}${
    agent.cost_kind === 'estimated' ? ' estimado' : ''}${row.cost_partial ? ' parcial' : ''}`;
}
export const projectRows = (agent, window = 'today') => [...(agent?.projects ?? [])]
  .sort((a, b) => (b[window]?.out ?? 0) - (a[window]?.out ?? 0));

export function acceptUsage(previous, payload) {
  if (payload === null) return null;
  const figures = row => row && ['in', 'out', 'cw', 'cr'].every(k => Number.isInteger(row[k]) && row[k] >= 0)
    && typeof row.cost_partial === 'boolean' && (row.cost === null || (Number.isFinite(row.cost) && row.cost >= 0));
  const entry = a => a && (a.status === 'absent' || (['ok', 'error'].includes(a.status)
    && ['reported', 'estimated', 'none'].includes(a.cost_kind)
    && (a.totals === undefined || (a.totals && typeof a.totals === 'object' && !Array.isArray(a.totals)
      && Object.values(a.totals).every(figures)))));
  return payload?.version === 1 && payload.currency === 'USD' && typeof payload.generated_at === 'string'
    && Number.isFinite(Date.parse(payload.generated_at)) && payload.agents
    && ['claude', 'codex', 'opencode', 'pi'].every(id => entry(payload.agents[id]))
    ? payload : previous;
}

export function panelState(data, window = 'today', now = Date.now(), stale_after_s = 300) {
  const age = Math.max(0, Math.floor((now - Date.parse(data?.generated_at)) / 1000));
  const agents = AGENTS.map(({ id, name }) => {
    const agent = agentOf(data, id);
    const detail = agent.status === 'absent' ? 'No instalado' : [
      agent.status === 'error' ? 'Falló la lectura' : '',
      billingOf(agent) === 'plan' ? 'Plan' : costLabel(agent, window),
      Number.isFinite(agent.totals?.[window]?.out) ? `${number.format(agent.totals[window].out)} tokens de salida` : '',
    ].filter(Boolean).join(' · ');
    return { id, name, agent, detail };
  });
  const paid = agents.map(a => a.agent).filter(a => a.status !== 'absent' && billingOf(a) === 'payg');
  const spend = paid.reduce((sum, a) => sum + (a.cost_kind !== 'none' ? a.totals?.[window]?.cost ?? 0 : 0), 0);
  return { window, agents, stale: age > stale_after_s,
    spend: `${paid.some(a => a.cost_kind === 'estimated') ? '≈' : ''}${formatUsd(spend)}`,
    freshness: !data ? 'Sin datos de uso' : `Actualizado hace ${age < 60 ? `${age} s` : `${Math.floor(age / 60)} min`}` };
}
const limitNames = { session: 'Sesión · 5 h', primary: 'Ventana · 5 h', weekly: 'Semana', credits: 'Créditos del ciclo' };

export function ringOf(agent) {
  const plan = agent?.plan;
  if (agent?.status === 'absent' || billingOf(agent) !== 'plan' || plan?.status !== 'ok'
    || !Array.isArray(plan.limits) || !plan.limits.length
    || !plan.limits.every((limit) => Number.isFinite(limit?.used_pct) && limit.used_pct >= 0)) return null;
  const pct = Math.max(...plan.limits.map((limit) => limit.used_pct));
  return { pct, high: pct >= 90 };
}

export function dockLabel(id, agent) {
  const name = AGENTS.find((a) => a.id === id)?.name ?? id;
  if (!agent || agent.status === 'absent') return `${name}: No instalado`;
  let detail;
  if (billingOf(agent) === 'plan') {
    detail = ringOf(agent) ? agent.plan.limits.map((limit) =>
      `${limitNames[limit.id] ?? limit.label ?? 'Límite'} ${number.format(limit.used_pct)} %`).join(', ')
      : 'Sin datos de límites';
  } else {
    const today = agent.totals?.today;
    const estimated = agent.cost_kind === 'estimated';
    detail = `hoy ${Number.isFinite(today?.cost) && agent.cost_kind !== 'none'
      ? `${estimated ? '≈' : ''}${formatUsd(today.cost)} ${estimated ? 'estimado' : 'reportado'}` : 'Sin precio'}`;
    if (today?.cost_partial) detail += ' parcial';
  }
  return `${name}: ${detail}${agent.status === 'error' ? ', falló la lectura' : ''}`;
}
