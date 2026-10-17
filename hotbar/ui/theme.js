export async function connectState(onState = () => {}) {
  const api = window.__TAURI__;
  let received = false;
  const apply = state => {
    if (state.theme) document.documentElement.dataset.theme = state.theme;
    else delete document.documentElement.dataset.theme;
    document.documentElement.dataset.edge = state.edge ?? 'right';
    onState(state);
  };
  await api.event.listen('hotbar-state', ({ payload }) => { received = true; apply(payload); });
  const initial = await api.core.invoke('hotbar_state');
  if (!received) apply(initial);
}
