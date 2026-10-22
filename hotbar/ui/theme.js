/** Windows load their pages while setup() is still registering state; retry until it has. */
export async function invokeReady(command, args) {
  for (let attempt = 0; ; attempt++) {
    try { return await window.__TAURI__.core.invoke(command, args); }
    catch (error) {
      if (attempt >= 40 || !String(error).includes('not managed')) throw error;
      await new Promise(resolve => setTimeout(resolve, 100));
    }
  }
}
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
  const initial = await invokeReady('hotbar_state');
  if (!received) apply(initial);
}
