import { AGENTS, agentOf, billingOf, ringOf, dockLabel } from './state.js';

const dock = document.getElementById('dock'), cells = new Map();
dock.addEventListener('panel-request', ({ detail }) => {
  window.__TAURI__.core.invoke('open_panel', { agent: detail.agent }).catch(console.error);
});
const STALE_AFTER_S = 300; // Configuration arrives in PR 10.
let documentData = null, connectionError = false;
function element(tag, className, parent) {
  const node = document.createElement(tag);
  node.className = className;
  parent.append(node);
  return node;
}
function label(button, value) { button.setAttribute('aria-label', value); button.title = value; }
function svg(tag, attrs, parent) {
  const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
  for (const [key, value] of Object.entries(attrs)) node.setAttribute(key, value);
  parent.append(node);
  return node;
}
function button(text, icon, agent) {
  const node = element('button', 'dbtn', dock);
  node.type = 'button';
  label(node, text);
  if (icon) {
    const image = svg('svg', { viewBox: '0 0 24 24', 'aria-hidden': 'true' }, node);
    svg('path', { d: icon, fill: 'none', stroke: 'currentColor', 'stroke-width': 2,
      'stroke-linecap': 'round', 'stroke-linejoin': 'round' }, image);
  }
  if (agent) {
    node.dataset.agent = agent;
    node.addEventListener('click', () => dock.dispatchEvent(new CustomEvent('panel-request', {
      detail: { agent }, bubbles: true,
    })));
  }
  return node;
}
button('Contraer hotbar', 'M9 6l6 6-6 6');
element('hr', '', dock);
for (const { id } of AGENTS) {
  const node = button(dockLabel(id), null, id);
  const wrap = element('span', `ringwrap agent-${id}`, node);
  wrap.setAttribute('aria-hidden', 'true');
  const ring = svg('svg', { class: 'ring', viewBox: '0 0 36 36' }, wrap);
  svg('circle', { class: 'bg', cx: 18, cy: 18, r: 15 }, ring);
  const fill = svg('circle', { class: 'fg', cx: 18, cy: 18, r: 15, pathLength: 100 }, ring);
  element('span', 'logo', wrap);
  const badge = element('span', 'badge', node);
  badge.setAttribute('aria-hidden', 'true');
  cells.set(id, { node, ring, fill, badge });
}
element('hr', '', dock);
const all = button('Todos los agentes', 'M4 19V9M10 19V5M16 19v-7M22 19H2', 'all');
const staleBadge = element('span', 'badge stale', all);
staleBadge.setAttribute('aria-hidden', 'true');
button('Ajustes', 'M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8M15 12a3 3 0 1 1-6 0 3 3 0 1 1 6 0');

function render(data) {
  documentData = data;
  for (const [id, { node, ring, fill, badge }] of cells) {
    const agent = agentOf(data, id), value = ringOf(agent);
    label(node, dockLabel(id, agent));
    node.classList.toggle('absent', agent.status === 'absent');
    ring.classList.toggle('hi', value?.high === true);
    ring.classList.toggle('hidden', !value);
    fill.style.setProperty('stroke-dashoffset', String(100 - Math.min(100, value?.pct ?? 0)));
    badge.className = `badge ${agent.status === 'error' ? 'err' : 'usd'}`;
    badge.textContent = agent.status === 'error' ? '' : '$';
    badge.hidden = agent.status === 'absent' || (agent.status !== 'error' && billingOf(agent) === 'plan');
  }
  const age = (Date.now() - Date.parse(data?.generated_at)) / 1000;
  staleBadge.hidden = !(age > STALE_AFTER_S);
  label(all, `Todos los agentes${connectionError ? ': Falló la conexión de uso' : !data ? ': Sin datos de uso'
    : age > STALE_AFTER_S ? `: Actualizado hace ${Math.floor(age / 60)} min` : ''}`);
}
async function connect() {
  let received = false;
  // A later event proves the link works, even if the initial snapshot call failed.
  await window.__TAURI__.event.listen('usage', ({ payload }) => { received = true; connectionError = false; render(payload); });
  const initial = await window.__TAURI__.core.invoke('usage_snapshot');
  if (!received) render(initial);
}
render(null);
connect().catch(() => { connectionError = true; render(documentData); });
setInterval(() => render(documentData), 5000);
