import { AGENTS, agentOf, billingOf, ringOf, dockLabel, collapsedDot, attentionLabel, chevronRotation, configView } from './state.js';
import { connectState } from './theme.js';

const dock = document.getElementById('dock'), cells = new Map();
dock.addEventListener('panel-request', ({ detail }) => {
  window.__TAURI__.core.invoke('open_panel', { agent: detail.agent }).catch(console.error);
});
let documentData = null, connectionError = false, config = configView(null);
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
const chevron = button('Contraer hotbar', 'M9 6l6 6-6 6');
chevron.classList.add('chevron');
chevron.addEventListener('click', () => window.__TAURI__.core.invoke('toggle_collapsed').catch(console.error));
const dots = element('span', 'dots', dock), dotCells = new Map();
dots.setAttribute('aria-hidden', 'true');
for (const { id } of AGENTS) dotCells.set(id, element('i', `dot agent-${id}`, dots));
connectState(state => {
  dock.classList.toggle('collapsed', state.collapsed);
  chevron.firstElementChild.style.transform = `rotate(${chevronRotation(state.edge, state.collapsed)}deg)`;
  chevron.setAttribute('aria-expanded', String(!state.collapsed));
  label(chevron, state.collapsed ? 'Expandir hotbar' : 'Contraer hotbar');
  render(documentData);
}).catch(console.error);
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
const gear = button('Ajustes', 'M12 3v2.5M12 18.5V21M3 12h2.5M18.5 12H21M5.6 5.6l1.8 1.8M16.6 16.6l1.8 1.8M5.6 18.4l1.8-1.8M16.6 7.4l1.8-1.8M15 12a3 3 0 1 1-6 0 3 3 0 1 1 6 0');

const configBadge = element('span', 'badge err', gear);
configBadge.setAttribute('aria-hidden', 'true');
const showMenu = () => window.__TAURI__.core.invoke('show_menu').catch(console.error);
gear.addEventListener('click', showMenu);
document.addEventListener('contextmenu', event => { event.preventDefault(); showMenu(); });
dock.addEventListener('pointerdown', event => {
  if (event.button === 0 && !event.target.closest('button'))
    window.__TAURI__.window.getCurrentWindow().startDragging().catch(console.error);
});
function render(data) {
  documentData = data;
  if (dock.classList.contains('collapsed')) label(dock, attentionLabel(data));
  else { dock.removeAttribute('title'); dock.setAttribute('aria-label', 'Agentes de Clawdy'); }
  for (const [id, dot] of dotCells) dot.hidden = !config.shown.has(id);
  for (const [id, dot] of dotCells) dot.className = `dot agent-${id} ${collapsedDot(agentOf(data, id))}`;
  for (const [id, { node, ring, fill, badge }] of cells) {
    node.hidden = !config.shown.has(id);
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
  staleBadge.hidden = !(age > config.staleAfter);
  label(all, `Todos los agentes${connectionError ? ': Falló la conexión de uso' : !data ? ': Sin datos de uso'
    : age > config.staleAfter ? `: Actualizado hace ${Math.floor(age / 60)} min` : ''}`);
}
function applyConfig(value) {
  config = configView(value);
  configBadge.hidden = !config.error;
  label(gear, config.error ? `Ajustes: configuración con errores (${config.error})` : 'Ajustes');
  render(documentData);
}
async function connect() {
  let received = false;
  // A later event proves the link works, even if the initial snapshot call failed.
  await window.__TAURI__.event.listen('usage', ({ payload }) => { received = true; connectionError = false; render(payload); });
  await window.__TAURI__.event.listen('config-reload', ({ payload }) => applyConfig(payload));
  applyConfig(await window.__TAURI__.core.invoke('hotbar_config'));
  const initial = await window.__TAURI__.core.invoke('usage_snapshot');
  if (!received) render(initial);
}
render(null);
connect().catch(() => { connectionError = true; render(documentData); });
setInterval(() => render(documentData), 5000);
