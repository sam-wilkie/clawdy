const agents = { claude: 'Claude', codex: 'Codex', opencode: 'OpenCode', pi: 'Pi' };
const cells = new Map();
const STALE_AFTER_S = 300; // hotbar.json stale_after_s arrives with config.rs (PR 10).
let documentData = null;
for (const [id, label] of Object.entries(agents)) {
  const cell = document.createElement('section');
  const name = document.createElement('h2');
  const tokens = document.createElement('div');
  const cost = document.createElement('div');
  name.textContent = label;
  tokens.className = 'tokens';
  cost.className = 'cost';
  cell.append(name, tokens, cost);
  document.querySelector('main').append(cell);
  cells.set(id, { cell, tokens, cost });
}

function render(data) {
  documentData = data;
  for (const [id, { cell, tokens, cost }] of cells) {
    const agent = data?.agents?.[id];
    const today = agent?.totals?.today;
    cell.classList.toggle('error', agent?.status === 'error');
    tokens.textContent = agent?.status === 'absent' ? 'not installed'
      : today ? `${Number(today.out).toLocaleString('en-US')} output tokens` : 'No usage data';
    let price = '';
    if (today && agent.status !== 'absent') {
      price = today.cost == null || agent.cost_kind === 'none' ? 'no price data'
        : `${agent.cost_kind === 'estimated' ? '~' : ''}$${today.cost.toFixed(2)}${agent.cost_kind === 'estimated' ? ' (API-equiv.)' : ''}`;
      if (today.cost_partial) price += ' (partial)';
    }
    cost.textContent = [price, agent?.status === 'error' ? 'Error' : ''].filter(Boolean).join(' · ');
  }
  const age = Math.max(0, Math.floor((Date.now() - Date.parse(data?.generated_at)) / 1000));
  const stale = age > STALE_AFTER_S;
  const freshness = document.getElementById('freshness');
  freshness.classList.toggle('stale', stale);
  freshness.textContent = !data ? 'No usage data' : !Number.isFinite(age) ? 'Unknown update time'
    : stale ? `Stale · ${Math.floor(age / 60)} min old` : 'Usage up to date';
}

async function connect() {
  let received = false;
  await window.__TAURI__.event.listen('usage', ({ payload }) => {
    received = true;
    render(payload);
  });
  const initial = await window.__TAURI__.core.invoke('usage_snapshot');
  if (!received) render(initial);
}
render(null);
connect().catch(() => { document.getElementById('freshness').textContent = 'Usage connection error'; });
setInterval(() => render(documentData), 5000);
