const sessionList = document.getElementById("session-list");
const emptyState = document.getElementById("empty-state");
const connection = document.getElementById("connection");
const connectionLabel = document.getElementById("connection-label");
const sessionCount = document.getElementById("session-count");
const usageNote = document.getElementById("usage-note");
let latestSnapshot = null;
let resetConfirming = false;
const spendingPeriods = new Map();

const AGENT_NAMES = { claude: "Claude", codex: "Codex", kiro: "Kiro", opencode: "OpenCode", antigravity: "Antigravity" };
const STATE_NAMES = {
  working: "Trabajando", thinking: "Pensando", waiting: "Esperando respuesta",
  alert: "Necesita atención", idle: "En pausa", sleeping: "En pausa",
  registered: "Iniciando", confused: "Con dificultad", low_battery: "Uso elevado",
  out_of_credits: "Límite de uso", error: "Error",
};

function make(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function safePercent(value) {
  if (value === null || value === undefined || value === "") return null;
  const number = Number(value);
  return Number.isFinite(number) && number >= 0 ? Math.min(100, number) : null;
}

function setMeter(id, value) {
  const meter = document.getElementById(id);
  const percent = safePercent(value);
  if (percent === null) {
    meter.removeAttribute("aria-valuenow");
    meter.setAttribute("aria-valuetext", "Sin datos");
  } else {
    meter.setAttribute("aria-valuenow", String(percent));
    meter.removeAttribute("aria-valuetext");
  }
  meter.querySelector("span").style.width = `${percent === null ? 0 : percent}%`;
  document.getElementById(id === "session-meter" ? "session-value" : "weekly-value").textContent =
    percent === null ? "—" : `${Math.round(percent)}%`;
  return percent !== null;
}

function formatReset(seconds) {
  if (seconds === null || seconds === undefined || seconds === "") return "";
  const value = Number(seconds);
  if (!Number.isFinite(value) || value < 0) return "";
  const hours = Math.floor(value / 3600);
  const days = Math.floor(hours / 24);
  const minutes = Math.floor((value % 3600) / 60);
  if (days) return `Reinicio en ${days} d ${hours % 24} h`;
  return `Reinicio en ${hours ? `${hours} h ` : ""}${minutes} min`;
}

function windowLabel(minutes, fallback) {
  const value = Number(minutes);
  if (!Number.isFinite(value) || value <= 0) return fallback;
  if (value === 10080) return "Semana";
  if (value % 1440 === 0) return `Ventana · ${value / 1440} d`;
  if (value % 60 === 0) return `Ventana · ${value / 60} h`;
  return `Ventana · ${value} min`;
}

function renderUsage(usage = {}, agent = "claude") {
  const hasSpending = renderSpending(usage, agent);
  const hasSession = setMeter("session-meter", usage.session_pct);
  const hasWeekly = setMeter("weekly-meter", usage.weekly_pct);
  const primaryLabel = agent === "codex"
    ? windowLabel(usage.session_window_minutes, "Límite principal") : agent === "kiro" ? "Créditos del ciclo" : "Sesión · 5 h";
  const secondaryLabel = agent === "codex"
    ? windowLabel(usage.weekly_window_minutes, "Límite adicional") : "Semana";
  document.getElementById("session-label").textContent = primaryLabel;
  document.getElementById("weekly-label").textContent = secondaryLabel;
  document.getElementById("session-meter").setAttribute("aria-label", `Uso de ${primaryLabel} de ${AGENT_NAMES[agent] || agent}`);
  document.getElementById("weekly-meter").setAttribute("aria-label", `Uso de ${secondaryLabel} de ${AGENT_NAMES[agent] || agent}`);
  document.getElementById("session-usage-row").hidden = !hasSession;
  document.getElementById("weekly-usage-row").hidden = !hasWeekly;
  document.getElementById("reset-label").textContent = hasSession ? formatReset(usage.reset_s) : "";
  document.getElementById("weekly-reset-label").textContent = hasWeekly ? formatReset(usage.weekly_reset_s) : "";
  const metrics = document.getElementById("usage-metrics");
  metrics.replaceChildren();
  const entries = !hasSpending && Array.isArray(usage.metrics) ? usage.metrics : [];
  for (const metric of entries) {
    if (typeof metric.value !== "number" || !Number.isFinite(metric.value) || metric.value < 0) continue;
    const format = metric.format === "usd" ? { style: "currency", currency: "USD", currencyDisplay: "code" }
      : { maximumFractionDigits: 2 };
    metrics.append(make("dt", "", metric.label), make("dd", "", new Intl.NumberFormat("es-CO", format).format(metric.value)));
  }
  metrics.hidden = entries.length === 0;
  if (usage.source === "kiro_cache") {
    const updated = usage.updated_at ? new Intl.DateTimeFormat("es-CO", {
      day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit",
    }).format(new Date(usage.updated_at)) : "sin fecha";
    usageNote.textContent = `Caché de Kiro IDE · actualizado ${updated}.`;
    return;
  }
  if (usage.source === "opencode_db") {
    usageNote.textContent = "Historial local de OpenCode · actualización cada minuto.";
    return;
  }
  if (usage.source === "antigravity_db") {
    const clients = Array.isArray(usage.clients) && usage.clients.length ? ` ${usage.clients.join(" + ")}` : "";
    usageNote.textContent = `Historial local de Antigravity${clients} · actualización cada minuto.`;
    return;
  }
  if (hasSession || hasWeekly) {
    usageNote.textContent = agent === "codex"
      ? "Uso de tu cuenta de Codex · actualización cada minuto."
      : `Porcentajes del uso de ${AGENT_NAMES[agent] || agent} disponibles en este equipo.`;
  } else if (agent === "codex") {
    const notes = {
      loading: "Consultando los límites de tu cuenta de Codex…",
      not_installed: "Clawdy no encuentra Codex. Instala Codex CLI o abre la aplicación de Codex.",
      signed_out: "Inicia sesión en Codex para ver los límites de tu cuenta.",
      api_key: "La sesión usa una clave API. Los límites del plan ChatGPT requieren iniciar sesión con ChatGPT.",
      unsupported: "Actualiza Codex para consultar sus límites de uso.",
      no_limits: "Codex no devolvió límites de uso para esta cuenta.",
      unavailable: "No se pudo consultar el uso de Codex. Clawdy volverá a intentarlo en un minuto.",
    };
    usageNote.textContent = notes[usage.status] || notes.unavailable;
  } else {
    usageNote.textContent = usage.status === "loading" ? `Leyendo el uso de ${AGENT_NAMES[agent] || agent}…`
      : agent === "kiro" ? "Abre la vista de uso de Kiro IDE para actualizar su caché de créditos."
      : agent === "opencode" ? usage.status === "not_installed" ? "Clawdy no encuentra OpenCode instalado."
      : "No se pudieron consultar las estadísticas locales de OpenCode."
      : agent === "antigravity" ? usage.status === "no_history"
      ? "Abre una conversación de Antigravity para registrar su consumo aquí."
      : "No se pudo leer el consumo local de Antigravity. Clawdy volverá a intentarlo en un minuto."
      : agent === "claude" ? "Abre una sesión de Claude para actualizar su línea de estado de uso."
      : "Clawdy aún no recibe métricas de uso para este agente.";
  }
}

function renderSpending(usage, agent) {
  const panel = document.getElementById("spending");
  const available = usage.status === "ready" && usage.periods && ["opencode", "antigravity"].includes(agent);
  panel.hidden = !available;
  if (!available) return false;
  const period = spendingPeriods.get(agent) || "all";
  for (const name of ["day", "month", "all"]) {
    document.getElementById(`period-${name}`).setAttribute("aria-pressed", String(name === period));
  }
  const row = usage.periods[period];
  const cost = row && typeof row.cost === "number" && Number.isFinite(row.cost) && row.cost >= 0 ? row.cost
    : agent === "opencode" && row?.messages === 0 ? 0 : null;
  const amount = document.getElementById("spend-value");
  amount.dataset.available = String(cost !== null);
  amount.textContent = cost === null ? "No disponible" : new Intl.NumberFormat("es-CO", {
    style: "currency", currency: "USD", currencyDisplay: "code", minimumFractionDigits: 2, maximumFractionDigits: 4,
  }).format(cost);
  const metrics = document.getElementById("spend-metrics");
  metrics.replaceChildren();
  for (const [key, label] of [["input_tokens", "Tokens de entrada"], ["output_tokens", "Tokens de salida"],
    ["cache_read_tokens", "Tokens leídos de caché"], ["thinking_tokens", "De salida, razonamiento"],
    ["messages", agent === "antigravity" ? "Llamadas registradas" : "Respuestas registradas"]]) {
    const value = row?.[key];
    if (typeof value === "number" && Number.isSafeInteger(value) && value >= 0) {
      metrics.append(make("dt", "", label), make("dd", "", new Intl.NumberFormat("es-CO").format(value)));
    }
  }
  const incompleteCost = row && row.cost_messages < row.messages;
  document.getElementById("spend-note").textContent = agent === "antigravity"
    ? "Antigravity registra tokens, pero no publica un costo monetario en este historial."
    : incompleteCost ? "Costo parcial: algunas respuestas no incluyen precio. No equivale a tu factura del proveedor."
    : "Costo informado por OpenCode. Puede diferir de tu factura del proveedor.";
  if (usage.partial) document.getElementById("spend-note").textContent += " Algunas conversaciones no se pudieron leer.";
  return true;
}

function resizePanel() {
  requestAnimationFrame(() => window.clawdyPanel.resizeToContent(Math.ceil(document.querySelector(".panel").getBoundingClientRect().height)));
}

function renderReset(usage = {}, agent, reset = { status: "idle" }) {
  const controls = document.getElementById("reset-controls");
  controls.hidden = agent !== "codex" || (usage.status !== "ready" && usage.reset_credits === undefined && reset.status === "idle");
  const credits = Number.isInteger(usage.reset_credits) && usage.reset_credits >= 0 ? usage.reset_credits : null;
  const busy = reset.status === "busy";
  const allowed = credits !== null && credits > 0 && !busy;
  const requestButton = document.getElementById("request-reset-button");
  requestButton.disabled = !allowed;
  requestButton.textContent = busy ? "Reiniciando…" : "Reiniciar uso";
  document.getElementById("reset-credit-count").textContent = credits === null
    ? "Codex no informa reinicios disponibles."
    : credits === 0 ? "No hay reinicios disponibles."
    : `${credits} ${credits === 1 ? "reinicio disponible" : "reinicios disponibles"}`;
  if (!allowed || agent !== "codex") resetConfirming = false;
  document.getElementById("reset-confirm").hidden = !resetConfirming;
  document.getElementById("confirm-reset-button").disabled = !allowed;
  const messages = {
    busy: "Aplicando el reinicio a tu cuenta…",
    reset: "Reinicio aplicado.",
    alreadyRedeemed: "Este reinicio ya se había aplicado.",
    nothingToReset: "Codex no encontró límites elegibles para reiniciar.",
    noCredit: "Tu cuenta ya no tiene reinicios disponibles.",
    unsupported: "Esta versión de Codex no permite reiniciar el uso. Actualiza Codex.",
    unavailable: "No se pudo confirmar el reinicio. Puedes reintentarlo; se comprobará la misma solicitud.",
    signed_out: "Inicia sesión en Codex antes de reiniciar el uso.",
    api_key: "Inicia sesión con ChatGPT para usar un reinicio.",
  };
  const message = document.getElementById("reset-message");
  message.textContent = messages[reset.status] || "";
  message.hidden = !message.textContent;
}

function displayState(raw) {
  if (["working_1", "working_2", "working_3", "typing", "building", "debugger", "conducting"].includes(raw)) {
    return { key: "working", label: "Trabajando" };
  }
  const key = raw === "permission" ? "waiting" : (raw || "idle");
  return { key, label: STATE_NAMES[key] || "Activo" };
}

function renderSessions(sessions = [], products = []) {
  const rows = Array.isArray(sessions) ? sessions : [];
  sessionCount.textContent = String(rows.length);
  sessionList.replaceChildren();
  emptyState.hidden = rows.length !== 0;

  for (const session of rows) {
    const state = displayState(session.state);
    const item = make("article", "session-item");
    item.dataset.state = state.key;
    item.append(make("span", "session-state-dot"));

    const info = make("div", "session-info");
    info.append(make("div", "session-project", session.project || "Proyecto sin nombre"));
    const meta = make("div", "session-meta");
    meta.append(make("span", "agent-name", AGENT_NAMES[session.agent] || session.agent || "Agente"));
    if (session.tool) meta.append(make("span", "", session.tool));
    if (Number(session.subagents) > 0) meta.append(make("span", "", `${session.subagents} subagentes`));
    info.append(meta);
    item.append(info, make("span", "state-label", state.label));
    sessionList.append(item);
  }

  // Older daemons do not send per-session detail. Keep their useful product
  // summary visible instead of showing a misleading empty state.
  if (rows.length === 0 && Array.isArray(products) && products.length) {
    emptyState.hidden = true;
    sessionCount.textContent = String(products.reduce((sum, product) => sum + (Number(product.count) || 0), 0));
    for (const product of products) {
      const state = displayState(product.anim);
      const item = make("article", "session-item");
      item.dataset.state = state.key;
      item.append(make("span", "session-state-dot"));
      const info = make("div", "session-info");
      info.append(make("div", "session-project", AGENT_NAMES[product.agent] || product.agent || "Agente"));
      info.append(make("div", "session-meta", `${Number(product.count) || 1} sesiones`));
      item.append(info, make("span", "state-label", state.label));
      sessionList.append(item);
    }
  }
}

function render(snapshot) {
  if (!snapshot) return;
  if (latestSnapshot && latestSnapshot.agent !== snapshot.agent) resetConfirming = false;
  latestSnapshot = snapshot;
  const agentName = AGENT_NAMES[snapshot.agent] || snapshot.agent || "Agente";
  const avatar = document.getElementById("agent-avatar");
  const agentArt = snapshot.agent === "codex"
    ? "assets/codex/cloud-idle-v2.svg#svgView(viewBox(-1,-3,18,21))"
    : snapshot.agent === "kiro" ? "assets/providers/kiro.png"
    : snapshot.agent === "opencode" ? "assets/providers/opencode.png"
    : "assets/clawd-idle-living-v2.svg#svgView(viewBox(-1,-3,18,21))";
  if (avatar.getAttribute("src") !== agentArt) {
    avatar.setAttribute("src", agentArt);
    avatar.alt = `Mascota de ${agentName}`;
  }
  document.getElementById("panel-title").textContent = `Actividad de ${agentName}`;
  document.getElementById("usage-title").textContent = `Uso de ${agentName}`;
  document.getElementById("sessions-title").textContent = `Sesiones de ${agentName}`;
  document.getElementById("empty-title").textContent = `No hay sesiones abiertas de ${agentName}.`;
  document.getElementById("empty-copy").textContent = `Abre ${agentName} para ver su actividad aquí.`;
  connection.dataset.online = snapshot.linked ? "true" : "false";
  connectionLabel.textContent = snapshot.linked ? "En línea" : "Sin conexión";
  renderUsage(snapshot.usage, snapshot.agent);
  renderReset(snapshot.usage, snapshot.agent, snapshot.reset);
  renderSessions(snapshot.sessions, snapshot.products);
  resizePanel();
}

window.clawdyPanel.onSnapshot(render);
for (const period of ["day", "month", "all"]) {
  document.getElementById(`period-${period}`).addEventListener("click", () => {
    if (!latestSnapshot) return;
    spendingPeriods.set(latestSnapshot.agent, period);
    renderUsage(latestSnapshot.usage, latestSnapshot.agent);
    resizePanel();
  });
}
document.getElementById("request-reset-button").addEventListener("click", () => {
  if (!latestSnapshot || document.getElementById("request-reset-button").disabled) return;
  resetConfirming = true;
  renderReset(latestSnapshot.usage, latestSnapshot.agent, latestSnapshot.reset);
  document.getElementById("confirm-reset-button").focus();
  resizePanel();
});
document.getElementById("cancel-reset-button").addEventListener("click", () => {
  resetConfirming = false;
  if (latestSnapshot) renderReset(latestSnapshot.usage, latestSnapshot.agent, latestSnapshot.reset);
  document.getElementById("request-reset-button").focus();
  resizePanel();
});
document.getElementById("confirm-reset-button").addEventListener("click", async () => {
  if (!latestSnapshot || !resetConfirming || document.getElementById("confirm-reset-button").disabled) return;
  resetConfirming = false;
  renderReset(latestSnapshot.usage, latestSnapshot.agent, { status: "busy" });
  resizePanel();
  let result;
  try { result = await window.clawdyPanel.resetCodexUsage(); }
  catch { result = { status: "unavailable" }; }
  if (latestSnapshot) renderReset(latestSnapshot.usage, latestSnapshot.agent, result);
  resizePanel();
});
document.addEventListener("keydown", (event) => {
  if (event.key !== "Escape") return;
  if (resetConfirming) document.getElementById("cancel-reset-button").click();
  else window.clawdyPanel.close();
});
