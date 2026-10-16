import { WINDOWS, acceptUsage, panelState } from './state.js';

const api = window.__TAURI__, body = document.getElementById('agents');
let data = null, selected = 'all', range = 'today', connectionError = false;
function element(tag, className, text, parent) {
  const node = document.createElement(tag);
  node.className = className; node.textContent = text; parent.append(node);
  return node;
}
const segments = WINDOWS.map(([id, name]) => {
  const button = element('button', '', name, document.getElementById('segments'));
  button.type = 'button';
  button.addEventListener('click', () => { range = id; render(); });
  return [id, button];
});
function render() {
  const state = panelState(data, range);
  for (const [id, button] of segments) button.setAttribute('aria-pressed', String(range === id));
  document.getElementById('range').textContent = `Pago por uso · ${WINDOWS.find(w => w[0] === range)[1]}`;
  document.getElementById('spend').textContent = data ? state.spend : '—';
  const fresh = document.getElementById('fresh');
  fresh.textContent = connectionError ? 'Falló la conexión de uso' : state.freshness;
  fresh.classList.toggle('stale', state.stale);
  body.replaceChildren();
  if (!data) { element('p', '', 'Sin datos de uso', body); return; }
  for (const row of state.agents.filter(a => selected === 'all' || a.id === selected)) {
    const article = element('article', 'agent-row', '', body);
    element('strong', '', row.name, article);
    element('p', row.agent.status === 'error' ? 'read-error' : '', row.detail, article);
  }
}
function select(agent) {
  selected = agent; range = 'today'; render(); body.scrollTop = 0;
  segments[0][1].focus();
}
async function connect() {
  let received = false, opened = false;
  await api.event.listen('panel-open', ({ payload }) => { opened = true; select(payload); });
  await api.event.listen('usage', ({ payload }) => { received = true; connectionError = false; data = acceptUsage(data, payload); render(); });
  const selection = await api.core.invoke('panel_selection');
  if (!opened) select(selection);
  const initial = await api.core.invoke('usage_snapshot');
  if (!received) { data = acceptUsage(data, initial); render(); }
}
const hide = () => api.core.invoke('hide_panel').catch(console.error);
document.getElementById('close').addEventListener('click', hide);
document.addEventListener('keydown', e => { if (e.key === 'Escape') hide(); });
render();
connect().catch(() => { connectionError = true; render(); });
setInterval(render, 5000);
