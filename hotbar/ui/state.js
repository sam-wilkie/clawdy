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
