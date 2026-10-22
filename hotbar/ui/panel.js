import { WINDOWS, acceptUsage, panelState, cardState, limitName, resetLabel,
  formatTokens, projectRows, projectShare, costLabel, projectLabel, formatPct, petOf, cellRunLabel } from './state.js';
import { connectState } from './theme.js';

const api = window.__TAURI__, body = document.getElementById('agents');
let data = null, selected = 'all', range = 'today', connectionError = false, cellRun = null;
const expanded = new Set();
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
function metrics(parent, labels, values) {
  const grid = element('div', `grid${labels.length}`, '', parent);
  labels.forEach((label, i) => {
    const metric = element('div', 'metric', '', grid);
    element('span', '', label, metric); element('b', '', values[i], metric);
  });
}
function fill(parent, className, ratio) {
  const track = element('span', className, '', parent);
  track.setAttribute('aria-hidden', 'true');
  element('i', '', '', track).style.setProperty('transform', `scaleX(${Math.max(0, Math.min(1, ratio))})`);
}
function card(row, state, parent) {
  const { id, name, agent } = row, model = cardState(id, agent, range);
  const article = element('article', `agent agent-${id}`, '', parent);
  const head = element('div', 'ahead', '', article);
  const pet = element('span', 'pet', '', head);
  const image = element('img', '', '', pet);
  image.alt = ''; image.src = petOf(id);
  const who = element('span', 'who', '', head), title = element('span', 'aname-row', '', who);
  const logo = element(id === 'pi' ? 'img' : 'span', 'orig', '', title);
  logo.setAttribute('aria-hidden', 'true');
  if (id === 'pi') { logo.src = 'assets/agents/gentle-shell.png'; logo.alt = ''; }
  element('span', 'aname', name, title);
  element('span', 'chip', model.chip, element('span', 'chips', '', who));
  if (agent.status === 'absent') { element('p', 'note', 'No instalado', article); return; }
  if (!model.isPlan) element('span', 'acost', model.cost, head);
  if (model.note) element('p', 'note', model.note, article);
  if (model.limits.length) {
    const limits = element('div', 'limits', '', article);
    for (const limit of model.limits) {
      const high = limit.used_pct >= 90 ? ' hi' : '', line = element('div', `limit${high}`, '', limits);
      element('span', 'lname', limitName(limit), line);
      element('span', 'lpct', formatPct(limit.used_pct), line);
      fill(line, `bar${high}`, limit.used_pct / 100);
      const reset = resetLabel(limit.resets_at);
      if (reset) element('span', 'reset', reset, line);
    }
  }
  if (model.resets) element('p', 'note', model.resets, article);
  if (id === 'kiro') {
    if (model.credits) metrics(article, ['Usados', 'Del plan', 'Restantes'], model.credits);
    element('p', 'note', 'Caché de Kiro IDE. Kiro no registra tokens por proyecto.', article);
  } else if (agent.totals?.[range]) {
    element('span', 'sublbl', `Tokens · ${WINDOWS.find(w => w[0] === range)[1].toLowerCase()}`, article);
    metrics(article, ['Entrada', 'Salida', 'Caché leída', 'Caché escrita'],
      ['in', 'out', 'cr', 'cw'].map(k => formatTokens(agent.totals[range][k])));
    if (id === 'codex' && !model.isPlan && agent.cost_kind === 'estimated')
      element('p', 'note', 'Sesión con API key: se estima el costo con precios públicos.', article);
    const projects = projectRows(agent, range), list = element('div', 'projects', '', article);
    for (const project of projects.slice(0, expanded.has(id) ? projects.length : 3)) {
      const line = element('div', 'proj', '', list);
      const name = projectLabel(project), label = element('span', 'pname', name, line);
      label.title = project.key ?? name;
      element('span', 'ptok', `${formatTokens(project[range]?.out)} tok`, line);
      if (!model.isPlan) element('span', 'pcost', costLabel({ ...agent, totals: { [range]: project[range] } }, range), line);
      fill(line, 'share', projectShare(project, agent, range));
    }
    if (!projects.length) element('p', 'note', 'Sin uso en este rango.', article);
    if (projects.length > 3) {
      const more = element('button', 'more', expanded.has(id) ? 'Ver menos' : `Ver los ${projects.length} proyectos`, article);
      more.type = 'button'; more.setAttribute('aria-expanded', String(expanded.has(id)));
      more.addEventListener('click', () => {
        const scroll = body.scrollTop;
        expanded.has(id) ? expanded.delete(id) : expanded.add(id); render();
        body.scrollTop = scroll; body.querySelector(`.agent-${id} .more`).focus({ preventScroll: true });
      });
    }
  }
  if (agent.status === 'error' || agent.plan?.status === 'error')
    element('p', 'note err', 'Falló la lectura. Se muestran los últimos datos buenos.', article);
  if (state.stale) element('p', 'note', `${state.freshness}. Los datos pueden estar desactualizados.`, article);
}
function renderCell(next) {
  const box = element('section', 'cellrun', '', next);
  element('h2', '', cellRun.label, box);
  element('p', `note${cellRun.run?.state && cellRun.run.state !== 'ok' ? ' err' : ''}`, cellRunLabel(cellRun.run), box);
  if (cellRun.run?.text) element('pre', '', cellRun.run.text, box);
}
function render() {
  const isCell = selected.startsWith('cell:') && cellRun;
  document.querySelector('.panel').classList.toggle('cell-view', Boolean(isCell));
  if (isCell) {
    const next = document.createElement('div');
    renderCell(next);
    if (next.innerHTML !== body.innerHTML) body.replaceChildren(...next.childNodes);
    return;
  }
  const state = panelState(data, range);
  for (const [id, button] of segments) button.setAttribute('aria-pressed', String(range === id));
  document.getElementById('range').textContent = `Pago por uso · ${WINDOWS.find(w => w[0] === range)[1]}`;
  document.getElementById('spend').textContent = data ? state.spend : '—';
  const fresh = document.getElementById('fresh');
  fresh.textContent = connectionError ? 'Falló la conexión de uso' : state.freshness;
  fresh.classList.toggle('stale', state.stale);
  const next = document.createElement('div');
  if (!data) element('p', '', 'Sin datos de uso', next);
  else for (const row of state.agents.filter(a => selected === 'all' || a.id === selected)) card(row, state, next);
  // Replacing identical cards would restart the pets' SVG animations every 5 s.
  if (next.innerHTML !== body.innerHTML) body.replaceChildren(...next.childNodes);
}
async function labelCell(id) {
  const cell = (await api.core.invoke('hotbar_config')).cells.find(c => c.id === id);
  if (cell && cellRun?.id === id) { cellRun.label = cell.label; render(); }
}
function select(agent) {
  cellRun = agent.startsWith('cell:') ? { id: agent.slice(5), label: agent.slice(5), run: null } : null;
  if (cellRun) labelCell(cellRun.id).catch(console.error);
  selected = agent; range = 'today'; render(); body.scrollTop = 0;
  segments[0][1].focus();
}
async function connect() {
  let received = false, opened = false;
  await api.event.listen('panel-open', ({ payload }) => { opened = true; select(payload); });
  await api.event.listen('cell-output', ({ payload }) => {
    if (cellRun?.id === payload.id) { cellRun.run = payload.run; render(); }
  });
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
connectState().catch(console.error);
