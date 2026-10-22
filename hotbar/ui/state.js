export const AGENTS = Object.freeze([
  { id: 'claude', name: 'Claude' }, { id: 'codex', name: 'Codex' },
  { id: 'opencode', name: 'OpenCode' }, { id: 'kiro', name: 'Kiro' },
  { id: 'pi', name: 'Gentle Shell' },
].map(Object.freeze));
export const DEFAULT_STALE_AFTER_S = 300;
/** What the bar reads from hotbar.json; anything missing or malformed falls back to the defaults. */
export function configView(config) {
  const stale = config?.stale_after_s;
  const listed = Array.isArray(config?.agents) ? config.agents : null;
  return {
    staleAfter: Number.isFinite(stale) && stale > 0 ? stale : DEFAULT_STALE_AFTER_S,
    shown: new Set(AGENTS.map(a => a.id).filter(id => !listed || listed.includes(id))),
    error: config?.error ?? null,
  };
}
export function petOf(id) {
  return `assets/pets/${id === 'claude' || id === 'codex' ? id : 'monster'}-idle.svg`;
}
export const agentOf = (data, id) => data?.agents?.[id] ?? { status: 'absent' };
export const billingOf = (agent) => agent?.billing === 'plan' ? 'plan' : 'payg';
export function collapsedDot(agent) {
  if (agent?.status === 'absent') return 'track';
  const ring = ringOf(agent);
  if (agent?.status === 'error' || ring?.high) return 'alert';
  return ring && ring.pct < 30 ? 'dim' : 'brand';
}
export const attentionList = data => AGENTS.filter(({ id }) => collapsedDot(agentOf(data, id)) === 'alert')
  .map(({ name }) => name);
export function attentionLabel(data) {
  const names = attentionList(data);
  return names.length ? `Atención: ${names.join(', ')}` : 'Sin alertas';
}
const usd = new Intl.NumberFormat('es-CO', { style: 'currency', currency: 'USD' });
const number = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 2 });
export const formatPct = (value) => `${number.format(value)} %`;
export const formatUsd = (value) => usd.format(value);
export const WINDOWS = [['today', 'Hoy'], ['7d', '7 días'], ['30d', '30 días'], ['month', 'Mes']];
export function costLabel(agent, window = 'today') {
  if (billingOf(agent) === 'plan') return '';
  const row = agent?.totals?.[window];
  if (!Number.isFinite(row?.cost) || agent.cost_kind === 'none') return 'Sin precio';
  return `${agent.cost_kind === 'estimated' ? '≈' : ''}${formatUsd(row.cost)}${
    agent.cost_kind === 'estimated' ? ' estimado' : ''}${row.cost_partial ? ' parcial' : ''}`;
}
// The usage file names projects with `label`; fall back to the last segment of the path key.
export const projectLabel = (project) => project?.label
  || String(project?.key ?? '').split(/[\\/]+/).filter(Boolean).pop() || 'Proyecto';
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

export function limitName(limit) {
  const name = limitNames[limit.id] ?? limit.label ?? 'Límite';
  const minutes = limit.window_min;
  if (!Number.isFinite(minutes) || minutes <= 0) return name;
  const duration = minutes % 1440 === 0 ? `${minutes / 1440} d`
    : minutes % 60 === 0 ? `${minutes / 60} h` : `${minutes} min`;
  return `${name.replace(' · 5 h', '')} · ${duration}`;
}
export function resetLabel(timestamp, now = Date.now()) {
  if (!timestamp || !Number.isFinite(Date.parse(timestamp))) return '';
  const minutes = Math.max(0, Math.ceil((Date.parse(timestamp) - now) / 60000));
  const hours = Math.floor(minutes / 60), days = Math.floor(hours / 24);
  return `Reinicio en ${days ? `${days} d ${hours % 24} h`
    : hours ? `${hours} h ${minutes % 60} min` : `${minutes} min`}`;
}
export const formatTokens = (value = 0) => value >= 1e9 ? `${(value / 1e9).toFixed(2)} B`
  : value >= 1e6 ? `${(value / 1e6).toFixed(1)} M`
    : value >= 1e3 ? `${(value / 1e3).toFixed(1)} K` : String(Math.round(value));
export function projectShare(project, agent, window = 'today') {
  const max = Math.max(0, ...(agent.projects ?? []).map(p => p[window]?.out ?? 0));
  return max ? Math.max(0, Math.min(1, (project[window]?.out ?? 0) / max)) : 0;
}
export function cardState(id, agent, window = 'today') {
  const isPlan = billingOf(agent) === 'plan', valid = isPlan && agent.plan?.status === 'ok';
  const limits = ringOf(agent) ? agent.plan.limits : [];
  const credits = valid ? agent.plan.credits : null;
  return { isPlan, chip: isPlan ? 'Plan' : agent.cost_kind === 'estimated' ? 'API · estimado' : 'Pago por uso',
    cost: costLabel(agent, window), limits,
    note: isPlan && !valid ? 'Sin datos de límites' : '',
    credits: credits && Number.isFinite(credits.used) && Number.isFinite(credits.limit)
      ? [credits.used, credits.limit, Math.max(0, credits.limit - credits.used)].map(v => number.format(v)) : null,
    resets: id === 'codex' && valid && Number.isFinite(agent.plan.reset_credits)
      ? `${number.format(agent.plan.reset_credits)} reinicios disponibles` : '' };
}

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
      `${limitNames[limit.id] ?? limit.label ?? 'Límite'} ${formatPct(limit.used_pct)}`).join(', ')
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

export function chevronRotation(edge = 'right', collapsed = false) {
  return (({ right: 0, bottom: 90, left: 180, top: 270 }[edge] ?? 0) + (collapsed ? 180 : 0)) % 360;
}
