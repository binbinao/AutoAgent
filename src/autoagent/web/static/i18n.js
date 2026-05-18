const LOCALE_STORAGE_KEY = "autoagent.locale";
const DEFAULT_LOCALE = "en";

const MESSAGES = {
  en: {
    tagline: "Goal → DAG plan → Execute → Report",
    "config.loading": "Loading config…",
    "compose.title": "New task",
    "compose.desc": "Describe your goal, pick a mode, and start the agent",
    "goal.label": "Goal",
    "goal.placeholder":
      "e.g. Research a company and assess investment value; output a Markdown report",
    "mode.legend": "Task mode",
    "mode.aria": "Task mode",
    "mode.research.title": "Deep research",
    "mode.research.desc": "Multi-source search · Long report",
    "mode.quick.title": "Quick task",
    "mode.quick.desc": "Fast path · Short output",
    "toggle.llm": "LLM planning",
    "toggle.autoApprove": "Auto-approve & run",
    "btn.run": "Start run",
    "btn.approve": "Approve plan",
    "status.title": "Execution",
    "status.progress": "Progress",
    "status.logTitle": "Event log",
    "status.logEmpty": "Node completion events appear here while running",
    "run.notStarted": "Not started yet",
    "run.id": "Run {id}",
    "plan.title": "Plan DAG",
    "plan.desc": "Dependency graph · Live node status",
    "plan.waiting": "Waiting for plan…",
    "plan.noNodes": "No plan nodes",
    "dag.tooltip.status": "Status",
    "dag.tooltip.tool": "Tool",
    "dag.tooltip.deps": "Depends on",
    "dag.tooltip.description": "Description",
    "dag.tooltip.noDeps": "—",
    "report.title": "Research report",
    "report.desc": "Markdown preview",
    "report.empty": "Your report will appear here when the run completes",
    "report.selectAria": "Select report",
    "report.none": "No reports",
    "history.title": "Task history",
    "history.colGoal": "Goal",
    "history.colPlan": "Plan",
    "history.colOutcome": "Outcome",
    "history.colTime": "Time",
    "history.loading": "Loading…",
    "history.empty": "No history yet",
    "status.idle": "Idle",
    "status.running": "Running",
    "status.completed": "Completed",
    "status.failed": "Failed",
    "status.awaiting_approval": "Awaiting approval",
    "outcome.completed": "completed",
    "outcome.failed": "failed",
    "outcome.interrupted": "interrupted",
    "outcome.running": "running",
    "alert.goalRequired": "Please enter a goal",
    "alert.noRunToApprove": "No run is waiting for approval",
    "lang.en": "EN",
    "lang.zh": "中文",
    "lang.switchAria": "Interface language",
    "nav.aria": "Main navigation",
    "nav.workspace": "Tasks",
    "nav.config": "Configuration",
    "configPage.title": "Configuration",
    "configPage.desc":
      "Saved to ~/.autoagent/config.toml. Environment variables and .env still override after restart.",
    "configPage.path": "Config file: {path}",
    "configPage.inFile": "in file",
    "configPage.reset": "Reset",
    "configPage.save": "Save configuration",
    "configPage.loading": "Loading…",
    "configPage.saving": "Saving…",
    "configPage.saved": "Configuration saved.",
    "configPage.resetDone": "Form reset to last loaded values.",
    "configField.default_model": "Default model",
    "configField.default_model.desc": "LiteLLM model id (e.g. openai/gpt-4o-mini).",
    "configField.workspace": "Workspace",
    "configField.workspace.desc": "Root directory for file tools and reports.",
    "configField.default_task_mode": "Default task mode",
    "configField.default_task_mode.desc": "Default when starting runs without a mode.",
    "configField.auto_approve": "Auto-approve plans",
    "configField.auto_approve.desc": "Skip manual plan approval.",
    "configField.memory_path": "Memory database",
    "configField.memory_path.desc": "SQLite path for episodic task history.",
    "configField.chroma_path": "Chroma directory",
    "configField.chroma_path.desc": "ChromaDB storage when using chroma backend.",
    "configField.semantic_memory_backend": "Semantic memory",
    "configField.semantic_memory_backend.desc": "memory (in-process) or chroma.",
    "configField.python_timeout_seconds": "Python timeout (s)",
    "configField.python_timeout_seconds.desc": "Sandbox timeout for python.run.",
    "configField.use_docker_sandbox": "Docker sandbox",
    "configField.use_docker_sandbox.desc": "Run python.run in Docker when available.",
    "configField.log_level": "Log level",
    "configField.log_level.desc": "Application logging verbosity.",
    "configField.react_max_steps": "ReAct max steps (research)",
    "configField.react_max_steps.desc": "Max tool loop steps per node in research mode.",
    "configField.react_max_steps_quick": "ReAct max steps (quick)",
    "configField.react_max_steps_quick.desc": "Max tool loop steps per node in quick mode.",
    "configField.max_context_tokens": "Max context tokens",
    "configField.max_context_tokens.desc": "Token budget for assembled prompts.",
    "configField.state_path": "Run state file",
    "configField.state_path.desc": "Snapshot path for detached CLI runs.",
    "configField.log_path": "Run log file",
    "configField.log_path.desc": "Path for run execution logs.",
  },
  zh: {
    tagline: "目标 → 计划 DAG → 执行 → 报告",
    "config.loading": "加载配置…",
    "compose.title": "新建任务",
    "compose.desc": "描述目标，选择模式后启动 Agent",
    "goal.label": "目标",
    "goal.placeholder": "例如：研究某公司并评估投资价值，生成 Markdown 报告",
    "mode.legend": "任务类型",
    "mode.aria": "任务类型",
    "mode.research.title": "深度调研",
    "mode.research.desc": "多源搜索 · 长报告",
    "mode.quick.title": "轻量任务",
    "mode.quick.desc": "快速完成 · 简短输出",
    "toggle.llm": "LLM 规划",
    "toggle.autoApprove": "自动批准并执行",
    "btn.run": "开始运行",
    "btn.approve": "批准计划",
    "status.title": "执行状态",
    "status.progress": "进度",
    "status.logTitle": "事件日志",
    "status.logEmpty": "运行后将显示节点完成记录",
    "run.notStarted": "尚未开始",
    "run.id": "运行 {id}",
    "plan.title": "计划 DAG",
    "plan.desc": "依赖关系图 · 节点状态实时更新",
    "plan.waiting": "等待计划生成…",
    "plan.noNodes": "无计划节点",
    "dag.tooltip.status": "状态",
    "dag.tooltip.tool": "工具",
    "dag.tooltip.deps": "依赖",
    "dag.tooltip.description": "描述",
    "dag.tooltip.noDeps": "—",
    "report.title": "研究报告",
    "report.desc": "Markdown 渲染",
    "report.empty": "任务完成后，报告将显示在此处",
    "report.selectAria": "选择报告",
    "report.none": "无报告",
    "history.title": "历史任务",
    "history.colGoal": "目标",
    "history.colPlan": "计划",
    "history.colOutcome": "结果",
    "history.colTime": "时间",
    "history.loading": "加载中…",
    "history.empty": "暂无历史",
    "status.idle": "空闲",
    "status.running": "执行中",
    "status.completed": "已完成",
    "status.failed": "失败",
    "status.awaiting_approval": "待批准",
    "outcome.completed": "已完成",
    "outcome.failed": "失败",
    "outcome.interrupted": "已中断",
    "outcome.running": "运行中",
    "alert.goalRequired": "请输入目标",
    "alert.noRunToApprove": "没有待批准的运行",
    "lang.en": "EN",
    "lang.zh": "中文",
    "lang.switchAria": "界面语言",
    "nav.aria": "主导航",
    "nav.workspace": "任务",
    "nav.config": "配置",
    "configPage.title": "配置",
    "configPage.desc": "写入 ~/.autoagent/config.toml；重启后环境变量与 .env 仍可覆盖。",
    "configPage.path": "配置文件：{path}",
    "configPage.inFile": "已写入",
    "configPage.reset": "重置",
    "configPage.save": "保存配置",
    "configPage.loading": "加载中…",
    "configPage.saving": "保存中…",
    "configPage.saved": "配置已保存。",
    "configPage.resetDone": "已恢复为上次加载的值。",
    "configField.default_model": "默认模型",
    "configField.default_model.desc": "LiteLLM 模型 ID（如 openai/gpt-4o-mini）。",
    "configField.workspace": "工作目录",
    "configField.workspace.desc": "文件工具与报告的工作区根目录。",
    "configField.default_task_mode": "默认任务模式",
    "configField.default_task_mode.desc": "未指定模式时使用的默认值。",
    "configField.auto_approve": "自动批准计划",
    "configField.auto_approve.desc": "跳过手动批准计划步骤。",
    "configField.memory_path": "记忆数据库",
    "configField.memory_path.desc": "情景任务历史的 SQLite 路径。",
    "configField.chroma_path": "Chroma 目录",
    "configField.chroma_path.desc": "使用 chroma 后端时的数据目录。",
    "configField.semantic_memory_backend": "语义记忆后端",
    "configField.semantic_memory_backend.desc": "memory（进程内）或 chroma。",
    "configField.python_timeout_seconds": "Python 超时（秒）",
    "configField.python_timeout_seconds.desc": "python.run 沙箱超时。",
    "configField.use_docker_sandbox": "Docker 沙箱",
    "configField.use_docker_sandbox.desc": "可用时优先在 Docker 中运行 python.run。",
    "configField.log_level": "日志级别",
    "configField.log_level.desc": "应用日志详细程度。",
    "configField.react_max_steps": "ReAct 最大步数（调研）",
    "configField.react_max_steps.desc": "调研模式下每节点工具循环上限。",
    "configField.react_max_steps_quick": "ReAct 最大步数（轻量）",
    "configField.react_max_steps_quick.desc": "轻量模式下每节点工具循环上限。",
    "configField.max_context_tokens": "最大上下文 Token",
    "configField.max_context_tokens.desc": "组装提示时的 Token 预算。",
    "configField.state_path": "运行状态文件",
    "configField.state_path.desc": "后台 CLI 运行的快照路径。",
    "configField.log_path": "运行日志文件",
    "configField.log_path.desc": "执行过程日志路径。",
  },
};

let currentLocale = DEFAULT_LOCALE;

function t(key, vars = {}) {
  const bag = MESSAGES[currentLocale] || MESSAGES[DEFAULT_LOCALE];
  let text = bag[key] ?? MESSAGES[DEFAULT_LOCALE][key] ?? key;
  for (const [name, value] of Object.entries(vars)) {
    text = text.replaceAll(`{${name}}`, String(value));
  }
  return text;
}

function getLocale() {
  return currentLocale;
}

function setLocale(locale) {
  if (!MESSAGES[locale]) return;
  currentLocale = locale;
  localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  document.documentElement.lang = locale === "zh" ? "zh-CN" : "en";
  applyI18n();
  document.querySelectorAll("[data-lang-btn]").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.langBtn === locale);
  });
  if (typeof window.onLocaleChange === "function") {
    window.onLocaleChange();
  }
}

function initLocale() {
  const stored = localStorage.getItem(LOCALE_STORAGE_KEY);
  setLocale(stored && MESSAGES[stored] ? stored : DEFAULT_LOCALE);
}

function applyI18n() {
  document.querySelectorAll("[data-i18n]").forEach((el) => {
    el.textContent = t(el.getAttribute("data-i18n"));
  });
  document.querySelectorAll("[data-i18n-placeholder]").forEach((el) => {
    el.placeholder = t(el.getAttribute("data-i18n-placeholder"));
  });
  document.querySelectorAll("[data-i18n-aria]").forEach((el) => {
    el.setAttribute("aria-label", t(el.getAttribute("data-i18n-aria")));
  });
}

function translateOutcome(outcome) {
  const translated = t(`outcome.${outcome}`);
  return translated.startsWith("outcome.") ? outcome : translated;
}
