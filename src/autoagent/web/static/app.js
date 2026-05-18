const TERMINAL = new Set(["completed", "failed"]);
const ACTIVE = new Set(["running", "approved", "created"]);
const RUN_STORAGE_KEY = "autoagent.activeRunId";

const $ = (id) => document.getElementById(id);

let pollTimer = null;
let currentRunId = null;
let lastRenderedRun = null;

async function api(path, options = {}) {
  const res = await fetch(path, {
    cache: "no-store",
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

function syncTaskModeSelect() {
  const selected = document.querySelector('input[name="task-mode-radio"]:checked');
  if (selected && $("task-mode")) $("task-mode").value = selected.value;
}

function syncTaskModeRadios(mode) {
  const radio = document.querySelector(`input[name="task-mode-radio"][value="${mode}"]`);
  if (radio) radio.checked = true;
  if ($("task-mode")) $("task-mode").value = mode;
}

function setRunning(running) {
  $("run-btn").disabled = running;
  $("goal").disabled = running;
  document.body.classList.toggle("is-running", running);
}

function displayStatus(status) {
  if (status === "approved" || status === "created") return "running";
  return status;
}

function setStatusBadge(status) {
  const badge = $("status-badge");
  if (!badge) return;
  const shown = status === "idle" ? "idle" : displayStatus(status);
  const label = t(`status.${shown}`);
  badge.textContent = label !== `status.${shown}` ? label : shown;
  badge.className = `status-badge status-${shown}`;
}

function showIdleRunMeta() {
  $("run-meta").textContent = t("run.notStarted");
  $("run-meta").classList.add("muted");
  setStatusBadge("idle");
}

function renderPlan(plan, nodeStatuses = {}) {
  const graph = $("plan-graph");
  if (!graph) return;
  if (!plan?.nodes?.length) {
    graph.classList.add("muted");
    graph.innerHTML = `<p class="plan-graph-empty">${escapeHtml(t("plan.noNodes"))}</p>`;
    return;
  }
  renderPlanGraph(graph, plan, nodeStatuses);
}

function renderProgress(run) {
  lastRenderedRun = run;
  $("run-meta").textContent = t("run.id", { id: run.id.slice(0, 8) });
  $("run-meta").classList.remove("muted");
  setStatusBadge(run.status);

  const total = run.plan?.nodes?.length || 1;
  const done = Object.keys(run.node_statuses || {}).length;
  let pct = run.status === "completed" ? 100 : Math.min(95, Math.round((done / total) * 100));
  if (ACTIVE.has(run.status) && done === 0) pct = Math.max(pct, 8);

  $("progress-bar").style.width = `${pct}%`;
  const pctEl = $("progress-pct");
  if (pctEl) pctEl.textContent = `${pct}%`;
  const wrap = document.querySelector(".progress-wrap");
  if (wrap) wrap.setAttribute("aria-valuenow", String(pct));

  const log = $("progress-log");
  log.innerHTML = (run.progress || []).map((m) => `<li>${escapeHtml(m)}</li>`).join("");
  if (run.plan) renderPlan(run.plan, run.node_statuses || {});
}

function persistActiveRunId(runId) {
  if (runId) sessionStorage.setItem(RUN_STORAGE_KEY, runId);
  else sessionStorage.removeItem(RUN_STORAGE_KEY);
}

function isActiveRun(run) {
  return ACTIVE.has(run.status);
}

function updateConfigPill(cfg) {
  const effective = cfg.effective || cfg;
  const mode = effective.default_task_mode || "research";
  syncTaskModeRadios(mode);
  $("config-pill").textContent = `${effective.default_model} · ${mode}`;
  $("config-pill").removeAttribute("data-i18n");
}

async function loadConfig() {
  const cfg = await api("/api/config");
  updateConfigPill(cfg);
  return cfg;
}

function formatHistoryTime(iso) {
  return iso.slice(0, 16).replace("T", " ");
}

function historyStatusClass(outcome) {
  if (outcome === "completed") return "history-pill history-pill-success";
  if (outcome === "failed") return "history-pill history-pill-danger";
  return "history-pill";
}

function renderHistoryChild(child) {
  return `<li class="history-step" role="treeitem">
    <span class="history-step-rail" aria-hidden="true"></span>
    <div class="history-step-body">
      <p class="history-step-title" title="${escapeHtml(child.goal)}">${escapeHtml(child.goal)}</p>
      <div class="history-step-meta">
        <span class="history-step-tool">${escapeHtml(child.plan_summary)}</span>
        <span class="${historyStatusClass(child.outcome)}">${escapeHtml(translateOutcome(child.outcome))}</span>
      </div>
    </div>
  </li>`;
}

function renderHistoryReportBar(reports) {
  if (!reports.length) {
    return `<div class="history-report-bar history-report-bar-empty">
      <span class="history-report-hint">${escapeHtml(t("history.noReportsHint"))}</span>
    </div>`;
  }
  const options = reports
    .map((r) => `<option value="${escapeHtml(r.name)}">${escapeHtml(r.name)}</option>`)
    .join("");
  return `<div class="history-report-bar">
    <label class="history-report-label">${escapeHtml(t("history.reportLabel"))}</label>
    <select class="history-report-select" aria-label="${escapeHtml(t("history.reportSelect"))}">${options}</select>
    <button type="button" class="btn btn-primary btn-sm history-download">${escapeHtml(t("history.download"))}</button>
  </div>`;
}

function renderHistoryRoot(item, expanded) {
  const reports = item.reports || [];
  const children = (item.children || []).map(renderHistoryChild).join("");
  const hasChildren = children.length > 0;
  const childCount = (item.children || []).length;
  return `<article class="history-session" role="treeitem" aria-expanded="${expanded ? "true" : "false"}">
    <header class="history-session-header">
      ${hasChildren ? `<button type="button" class="history-toggle" aria-label="${escapeHtml(t("history.toggle"))}" data-expanded="${expanded ? "true" : "false"}">${expanded ? "▾" : "▸"}</button>` : '<span class="history-toggle-spacer" aria-hidden="true"></span>'}
      <div class="history-session-main">
        <h3 class="history-session-goal" title="${escapeHtml(item.goal)}">${escapeHtml(item.goal)}</h3>
        <div class="history-session-meta">
          <span class="${historyStatusClass(item.outcome)}">${escapeHtml(translateOutcome(item.outcome))}</span>
          <time class="history-time">${escapeHtml(formatHistoryTime(item.created_at))}</time>
          ${hasChildren ? `<span class="history-step-count">${escapeHtml(t("history.stepCount", { count: childCount }))}</span>` : ""}
        </div>
      </div>
      ${renderHistoryReportBar(reports)}
    </header>
    ${hasChildren ? `<ul class="history-steps" role="group"${expanded ? "" : " hidden"}>${children}</ul>` : ""}
  </article>`;
}

async function loadHistory() {
  const { items } = await api("/api/history/tree?limit=15");
  const container = $("history-tree");
  if (!items.length) {
    container.innerHTML = `<p class="muted">${escapeHtml(t("history.empty"))}</p>`;
    return;
  }
  container.innerHTML = items.map((item, index) => renderHistoryRoot(item, index === 0)).join("");

  container.querySelectorAll(".history-toggle").forEach((btn) => {
    btn.addEventListener("click", () => {
      const session = btn.closest(".history-session");
      const group = session?.querySelector(".history-steps");
      const expanded = btn.getAttribute("data-expanded") !== "true";
      btn.setAttribute("data-expanded", expanded ? "true" : "false");
      btn.textContent = expanded ? "▾" : "▸";
      session?.setAttribute("aria-expanded", expanded ? "true" : "false");
      if (group) group.hidden = !expanded;
    });
  });

  container.querySelectorAll(".history-download").forEach((btn) => {
    btn.addEventListener("click", () => {
      const bar = btn.closest(".history-report-bar");
      const sel = bar?.querySelector(".history-report-select");
      const name = sel?.value;
      if (!name) return;
      window.location.href = `/api/reports/${encodeURIComponent(name)}/download`;
    });
  });
}


async function loadReports(selectName) {
  const reports = await api("/api/reports");
  const sel = $("report-select");
  sel.innerHTML = reports.length
    ? reports.map((r) => `<option value="${escapeHtml(r.name)}">${escapeHtml(r.name)}</option>`).join("")
    : `<option value="">${escapeHtml(t("report.none"))}</option>`;

  const name = selectName || reports[0]?.name;
  if (!name) {
    const view = $("report-view");
    view.classList.add("muted");
    view.innerHTML = `<div class="empty-state"><p>${escapeHtml(t("report.empty"))}</p></div>`;
    return;
  }
  sel.value = name;
  const doc = await api(`/api/reports/${encodeURIComponent(name)}`);
  const view = $("report-view");
  view.classList.remove("muted");
  view.innerHTML = marked.parse(doc.content);
}

function escapeHtml(s) {
  return String(s)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function stopPoll() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

async function pollRunOnce(runId) {
  const run = await api(`/api/runs/${runId}`);
  renderProgress(run);

  if (run.status === "awaiting_approval") {
    $("approve-btn").classList.remove("hidden");
    setRunning(false);
    persistActiveRunId(run.id);
    stopPoll();
    return;
  }

  if (TERMINAL.has(run.status)) {
    setRunning(false);
    persistActiveRunId(null);
    stopPoll();
    if (run.report_name) await loadReports(run.report_name);
    await loadHistory();
    if (run.error) {
      $("run-meta").textContent += ` · ${run.error}`;
      setStatusBadge("failed");
    }
  }
}

function startPoll(runId) {
  stopPoll();
  persistActiveRunId(runId);
  pollRunOnce(runId).catch(console.error);
  pollTimer = setInterval(() => pollRunOnce(runId).catch(console.error), 1200);
}

async function resumeActiveRun() {
  const storedId = sessionStorage.getItem(RUN_STORAGE_KEY);
  let runs = [];
  try {
    runs = await api("/api/runs?limit=15");
  } catch (e) {
    console.error(e);
    return false;
  }

  let active = storedId ? runs.find((r) => r.id === storedId && isActiveRun(r)) : null;
  if (!active) active = runs.find((r) => isActiveRun(r));
  if (!active) {
    persistActiveRunId(null);
    return false;
  }

  currentRunId = active.id;
  renderProgress(active);
  $("approve-btn").classList.add("hidden");
  setRunning(true);
  $("plan-graph")?.classList.remove("muted");
  startPoll(active.id);
  return true;
}

async function startRun() {
  syncTaskModeSelect();
  const goal = $("goal").value.trim();
  if (!goal) return alert(t("alert.goalRequired"));

  setRunning(true);
  setStatusBadge("running");
  $("approve-btn").classList.add("hidden");
  $("progress-log").innerHTML = "";
  $("progress-bar").style.width = "4%";
  if ($("progress-pct")) $("progress-pct").textContent = "4%";

  try {
    const run = await api("/api/runs", {
      method: "POST",
      body: JSON.stringify({
        goal,
        llm: $("use-llm").checked,
        approve: $("auto-approve").checked,
        task_mode: $("task-mode").value,
        locale: getLocale(),
      }),
    });
    currentRunId = run.id;
    renderProgress(run);
    if (isActiveRun(run)) {
      startPoll(run.id);
    } else if (run.status === "awaiting_approval") {
      persistActiveRunId(run.id);
      $("approve-btn").classList.remove("hidden");
      setRunning(false);
      setStatusBadge("awaiting_approval");
    } else {
      persistActiveRunId(null);
      setRunning(false);
      if (run.report_name) await loadReports(run.report_name);
    }
  } catch (e) {
    setRunning(false);
    setStatusBadge("failed");
    alert(e.message);
  }
}

async function approveRun() {
  if (!currentRunId) return alert(t("alert.noRunToApprove"));
  setRunning(true);
  setStatusBadge("running");
  $("approve-btn").classList.add("hidden");
  try {
    const updated = await api(`/api/runs/${currentRunId}/approve`, { method: "POST" });
    renderProgress(updated);
    startPoll(currentRunId);
  } catch (e) {
    setRunning(false);
    setStatusBadge("failed");
    alert(e.message);
  }
}

window.onLocaleChange = () => {
  applyI18n();
  const nav = document.querySelector(".main-tabs");
  if (nav) nav.setAttribute("aria-label", t("nav.aria"));
  const group = document.querySelector(".lang-switch");
  if (group) group.setAttribute("aria-label", t("lang.switchAria"));
  if (cachedConfig) renderConfigForm(cachedConfig);
  if (lastRenderedRun) {
    renderProgress(lastRenderedRun);
  } else {
    showIdleRunMeta();
    const graph = $("plan-graph");
    if (graph && !lastRenderedRun) {
      graph.classList.add("muted");
      graph.innerHTML = `<p class="plan-graph-empty">${escapeHtml(t("plan.waiting"))}</p>`;
    }
  }
  loadHistory().catch(console.error);
  const view = $("report-view");
  if (view?.classList.contains("muted")) {
    view.innerHTML = `<div class="empty-state"><p>${escapeHtml(t("report.empty"))}</p></div>`;
  }
};

function bindLangSwitch() {
  document.querySelectorAll("[data-lang-btn]").forEach((btn) => {
    btn.addEventListener("click", () => setLocale(btn.dataset.langBtn));
  });
}

document.querySelectorAll('input[name="task-mode-radio"]').forEach((el) => {
  el.addEventListener("change", syncTaskModeSelect);
});

$("run-btn").addEventListener("click", startRun);
$("approve-btn").addEventListener("click", approveRun);
$("report-select").addEventListener("change", (e) => loadReports(e.target.value));

let cachedConfig = null;
let configDirty = false;

function configFieldLabel(key) {
  const label = t(`configField.${key}`);
  return label.startsWith("configField.") ? key : label;
}

function switchMainTab(tab) {
  const isConfig = tab === "config";
  $("tab-workspace").classList.toggle("is-active", !isConfig);
  $("tab-config").classList.toggle("is-active", isConfig);
  $("tab-workspace").setAttribute("aria-selected", String(!isConfig));
  $("tab-config").setAttribute("aria-selected", String(isConfig));
  $("view-workspace").classList.toggle("hidden", isConfig);
  $("view-config").classList.toggle("hidden", !isConfig);
  $("view-workspace").hidden = isConfig;
  $("view-config").hidden = !isConfig;
  if (isConfig && !cachedConfig) loadConfigPage().catch(console.error);
}

function renderConfigForm(cfg) {
  cachedConfig = cfg;
  const form = $("config-form");
  const pathEl = $("config-path");
  if (pathEl) {
    pathEl.textContent = t("configPage.path", { path: cfg.user_config_path });
  }

  form.innerHTML = cfg.fields
    .map((field) => {
      const key = field.key;
      const value = cfg.effective[key];
      const inFile = Object.hasOwn(cfg.user_file, key);
      const envHint = field.env ? `<span class="config-env">${escapeHtml(field.env)}</span>` : "";
      const fileBadge = inFile
        ? `<span class="config-badge">${escapeHtml(t("configPage.inFile"))}</span>`
        : "";

      let control = "";
      if (field.type === "bool") {
        control = `<label class="toggle config-toggle">
          <input type="checkbox" name="${escapeHtml(key)}" ${value ? "checked" : ""} />
          <span class="toggle-track"></span>
          <span class="toggle-label">${value ? "true" : "false"}</span>
        </label>`;
      } else if (field.type === "select") {
        const options = (field.options || [])
          .map(
            (opt) =>
              `<option value="${escapeHtml(opt)}" ${opt === value ? "selected" : ""}>${escapeHtml(opt)}</option>`
          )
          .join("");
        control = `<select class="select" name="${escapeHtml(key)}" id="cfg-${escapeHtml(key)}">${options}</select>`;
      } else {
        const inputType = field.type === "int" ? "number" : "text";
        const extra = field.type === "int" ? ' min="1" step="1"' : "";
        control = `<input class="select config-input" type="${inputType}" name="${escapeHtml(key)}" id="cfg-${escapeHtml(key)}" value="${escapeHtml(String(value ?? ""))}"${extra} />`;
      }

      const descKey = `configField.${key}.desc`;
      const desc = t(descKey);
      const descHtml =
        desc !== descKey ? `<p class="config-field-desc">${escapeHtml(desc)}</p>` : `<p class="config-field-desc">${escapeHtml(field.description || "")}</p>`;

      return `<div class="config-field" data-config-key="${escapeHtml(key)}">
        <div class="config-field-head">
          <label class="field-label" for="cfg-${escapeHtml(key)}">${escapeHtml(configFieldLabel(key))}</label>
          ${fileBadge}${envHint}
        </div>
        ${control}
        ${descHtml}
      </div>`;
    })
    .join("");

  form.querySelectorAll("input, select").forEach((el) => {
    el.addEventListener("change", () => {
      configDirty = true;
      setConfigStatus("");
      if (el.type === "checkbox") {
        const label = el.closest(".toggle")?.querySelector(".toggle-label");
        if (label) label.textContent = el.checked ? "true" : "false";
      }
    });
  });
  configDirty = false;
}

function collectConfigForm() {
  const payload = {};
  $("config-form").querySelectorAll("[name]").forEach((el) => {
    const key = el.name;
    if (el.type === "checkbox") {
      payload[key] = el.checked;
    } else if (el.type === "number") {
      payload[key] = Number(el.value);
    } else {
      payload[key] = el.value;
    }
  });
  return payload;
}

function setConfigStatus(message, isError = false) {
  const el = $("config-status");
  if (!el) return;
  el.textContent = message;
  el.classList.toggle("config-status-error", isError);
  el.classList.toggle("muted", !message);
}

async function loadConfigPage() {
  setConfigStatus(t("configPage.loading"));
  const cfg = await api("/api/config");
  renderConfigForm(cfg);
  updateConfigPill(cfg);
  setConfigStatus("");
}

async function saveConfig() {
  const btn = $("config-save-btn");
  btn.disabled = true;
  setConfigStatus(t("configPage.saving"));
  try {
    const cfg = await api("/api/config", {
      method: "PUT",
      body: JSON.stringify(collectConfigForm()),
    });
    renderConfigForm(cfg);
    updateConfigPill(cfg);
    configDirty = false;
    setConfigStatus(t("configPage.saved"));
  } catch (e) {
    setConfigStatus(e.message, true);
  } finally {
    btn.disabled = false;
  }
}

function bindMainTabs() {
  $("tab-workspace").addEventListener("click", () => switchMainTab("workspace"));
  $("tab-config").addEventListener("click", () => switchMainTab("config"));
  $("config-save-btn").addEventListener("click", () => saveConfig());
  $("config-reset-btn").addEventListener("click", () => {
    if (cachedConfig) renderConfigForm(cachedConfig);
    configDirty = false;
    setConfigStatus(t("configPage.resetDone"));
  });
}

async function bootstrap() {
  initLocale();
  bindLangSwitch();
  bindMainTabs();
  showIdleRunMeta();
  try {
    const cfg = await loadConfig();
    cachedConfig = cfg;
    const resumed = await resumeActiveRun();
    await loadHistory();
    if (!resumed) await loadReports();
  } catch (e) {
    console.error(e);
  }
}

bootstrap();
