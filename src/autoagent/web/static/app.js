const TERMINAL = new Set(["completed", "failed"]);
const ACTIVE = new Set(["running", "approved", "created"]);
const RUN_STORAGE_KEY = "autoagent.activeRunId";

const STATUS_LABELS = {
  idle: "空闲",
  running: "执行中",
  completed: "已完成",
  failed: "失败",
  awaiting_approval: "待批准",
};

const $ = (id) => document.getElementById(id);

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
  badge.textContent = STATUS_LABELS[shown] || shown;
  badge.className = `status-badge status-${shown}`;
}

function renderPlan(plan, nodeStatuses = {}) {
  const list = $("plan-list");
  if (!plan?.nodes?.length) {
    list.innerHTML = '<li class="timeline-empty">无计划节点</li>';
    list.classList.add("muted");
    return;
  }
  list.classList.remove("muted");
  list.innerHTML = plan.nodes
    .map((node, index) => {
      const st = nodeStatuses[node.id] || "pending";
      const tool = node.tool_name || "ReAct";
      return `<li class="timeline-item status-${st}">
        <div class="timeline-marker">${index + 1}</div>
        <div class="timeline-body">
          <div><span class="node-id">${escapeHtml(node.id)}</span>
          <span class="node-tool">${escapeHtml(tool)}</span></div>
          <p class="node-desc">${escapeHtml(node.description)}</p>
        </div>
      </li>`;
    })
    .join("");
}

function renderProgress(run) {
  $("run-meta").textContent = `Run ${run.id.slice(0, 8)}`;
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

async function loadConfig() {
  const cfg = await api("/api/config");
  const mode = cfg.default_task_mode || "research";
  syncTaskModeRadios(mode);
  $("config-pill").textContent = `${cfg.default_model} · ${mode}`;
}

async function loadHistory() {
  const rows = await api("/api/history?limit=15");
  const body = $("history-body");
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="4" class="muted">暂无历史</td></tr>';
    return;
  }
  body.innerHTML = rows
    .map(
      (r) => `<tr>
        <td>${escapeHtml(r.goal.slice(0, 60))}${r.goal.length > 60 ? "…" : ""}</td>
        <td>${escapeHtml(r.plan_summary.slice(0, 40))}…</td>
        <td class="status-${escapeHtml(r.outcome)}">${escapeHtml(r.outcome)}</td>
        <td>${escapeHtml(r.created_at.slice(0, 16).replace("T", " "))}</td>
      </tr>`
    )
    .join("");
}

async function loadReports(selectName) {
  const reports = await api("/api/reports");
  const sel = $("report-select");
  sel.innerHTML = reports.length
    ? reports.map((r) => `<option value="${escapeHtml(r.name)}">${escapeHtml(r.name)}</option>`).join("")
    : '<option value="">无报告</option>';

  const name = selectName || reports[0]?.name;
  if (!name) return;
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

let pollTimer = null;
let currentRunId = null;

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
  $("plan-list").classList.remove("muted");
  startPoll(active.id);
  return true;
}

async function startRun() {
  syncTaskModeSelect();
  const goal = $("goal").value.trim();
  if (!goal) return alert("请输入目标");

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
  if (!currentRunId) return alert("没有待批准的运行");
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

document.querySelectorAll('input[name="task-mode-radio"]').forEach((el) => {
  el.addEventListener("change", syncTaskModeSelect);
});

$("run-btn").addEventListener("click", startRun);
$("approve-btn").addEventListener("click", approveRun);
$("report-select").addEventListener("change", (e) => loadReports(e.target.value));

async function bootstrap() {
  try {
    await loadConfig();
    const resumed = await resumeActiveRun();
    await loadHistory();
    if (!resumed) await loadReports();
    if (!resumed) setStatusBadge("idle");
  } catch (e) {
    console.error(e);
  }
}

bootstrap();
