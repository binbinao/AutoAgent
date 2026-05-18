const TERMINAL = new Set(["completed", "failed"]);

const $ = (id) => document.getElementById(id);

async function api(path, options = {}) {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json", ...options.headers },
    ...options,
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return res.json();
}

function setRunning(running) {
  $("run-btn").disabled = running;
  $("goal").disabled = running;
}

function renderPlan(plan, nodeStatuses = {}) {
  const list = $("plan-list");
  if (!plan?.nodes?.length) {
    list.innerHTML = "<li>无计划节点</li>";
    list.classList.add("muted");
    return;
  }
  list.classList.remove("muted");
  list.innerHTML = plan.nodes
    .map((node) => {
      const st = nodeStatuses[node.id];
      const cls = st === "completed" ? "done" : st === "failed" ? "failed" : "";
      const tool = node.tool_name ? ` (${node.tool_name})` : " (ReAct)";
      return `<li class="${cls}"><strong>${node.id}</strong>${tool}: ${node.description}</li>`;
    })
    .join("");
}

function renderProgress(run) {
  $("run-meta").textContent = `状态: ${run.status} · ID: ${run.id.slice(0, 8)}`;
  $("run-meta").classList.remove("muted");

  const total = run.plan?.nodes?.length || 1;
  const done = Object.keys(run.node_statuses || {}).length;
  const pct = run.status === "completed" ? 100 : Math.min(95, Math.round((done / total) * 100));
  $("progress-bar").style.width = `${pct}%`;

  const log = $("progress-log");
  log.innerHTML = (run.progress || []).map((m) => `<li>${m}</li>`).join("");

  if (run.plan) renderPlan(run.plan, run.node_statuses || {});
}

async function loadConfig() {
  const cfg = await api("/api/config");
  const mode = cfg.default_task_mode || "research";
  $("task-mode").value = mode;
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
        <td class="status-${r.outcome}">${r.outcome}</td>
        <td>${r.created_at.slice(0, 16).replace("T", " ")}</td>
      </tr>`
    )
    .join("");
}

async function loadReports(selectName) {
  const reports = await api("/api/reports");
  const sel = $("report-select");
  sel.innerHTML = reports.length
    ? reports.map((r) => `<option value="${r.name}">${r.name}</option>`).join("")
    : '<option value="">无报告</option>';

  const name = selectName || reports[0]?.name;
  if (!name) return;
  sel.value = name;
  const doc = await api(`/api/reports/${encodeURIComponent(name)}`);
  $("report-view").classList.remove("muted");
  $("report-view").innerHTML = marked.parse(doc.content);
}

function escapeHtml(s) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

let pollTimer = null;
let currentRunId = null;

function stopPoll() {
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = null;
}

function startPoll(runId) {
  stopPoll();
  pollTimer = setInterval(async () => {
    try {
      const run = await api(`/api/runs/${runId}`);
      renderProgress(run);

      if (run.status === "awaiting_approval") {
        $("approve-btn").classList.remove("hidden");
        setRunning(false);
        stopPoll();
        return;
      }

      if (TERMINAL.has(run.status)) {
        setRunning(false);
        stopPoll();
        if (run.report_name) await loadReports(run.report_name);
        await loadHistory();
        if (run.error) $("run-meta").textContent += ` · 错误: ${run.error}`;
      }
    } catch (e) {
      console.error(e);
    }
  }, 1200);
}

async function startRun() {
  const goal = $("goal").value.trim();
  if (!goal) return alert("请输入目标");

  setRunning(true);
  $("approve-btn").classList.add("hidden");
  $("progress-log").innerHTML = "";
  $("progress-bar").style.width = "4%";

  const body = {
    goal,
    llm: $("use-llm").checked,
    approve: $("auto-approve").checked,
    task_mode: $("task-mode").value,
  };

  try {
    const run = await api("/api/runs", { method: "POST", body: JSON.stringify(body) });
    currentRunId = run.id;
    renderProgress(run);
    if (!TERMINAL.has(run.status) && run.status !== "awaiting_approval") {
      startPoll(run.id);
    } else if (run.status === "awaiting_approval") {
      $("approve-btn").classList.remove("hidden");
      setRunning(false);
    } else {
      setRunning(false);
      if (run.report_name) await loadReports(run.report_name);
    }
  } catch (e) {
    setRunning(false);
    alert(e.message);
  }
}

async function approveRun() {
  if (!currentRunId) return alert("没有待批准的运行");

  setRunning(true);
  $("approve-btn").classList.add("hidden");
  try {
    const updated = await api(`/api/runs/${currentRunId}/approve`, { method: "POST" });
    renderProgress(updated);
    startPoll(currentRunId);
  } catch (e) {
    setRunning(false);
    alert(e.message);
  }
}

$("run-btn").addEventListener("click", startRun);
$("approve-btn").addEventListener("click", approveRun);
$("report-select").addEventListener("change", (e) => loadReports(e.target.value));

loadConfig().catch(console.error);
loadHistory().catch(console.error);
loadReports().catch(console.error);
