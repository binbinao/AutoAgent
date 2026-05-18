## Learned User Preferences

- 默认使用中文进行交流与回复。
- 常以仓库根目录的 `plan.md`（产品/技术总纲）为路线：按章节对照差距、检查当前项目状态并继续执行后续开发步骤。
- 在长周期开发中可能要求「yolo 模式」，希望在整体完成前减少反复确认、加快自主推进；实现与收尾仍应满足项目自带的验证门槛。
- 在宣称任务完成或健康状态前，倾向先用仓库内可重复的验证命令（例如 `.venv/bin/pytest` 满足 `pyproject.toml` 的覆盖率门槛，并可辅以 `ruff check src/autoagent tests`）作为依据。
- 全量推进 `plan.md` 时倾向严格走 Superpowers 流程（writing-plans → executing-plans → TDD → verification-before-completion），并与路线图配合直至可体验。
- 实际跑通 Agent 时常用 `autoagent run` 或 `plan` 加 `--llm`；非交互验证或自动化时可配合 `--approve`。
- 会明确要求将变更提交或推送到 GitHub；本地 `.env` 与 `.autoagent-test/` 等运行时数据不应纳入版本库。

## Learned Workspace Facts

- 本仓库为 AutoAgent：面向生产的自主 Agent 框架，将目标拆解为 DAG 计划，节点内以 ReAct 循环执行；详细能力以 `README.md` 为准。
- 远程仓库为 https://github.com/binbinao/AutoAgent（`main` 推送目标）。
- Python 版本约束为 3.11（见 `pyproject.toml`）；可安装包名为 `autoagent`，源码位于 `src/autoagent/`，CLI 命令为 `autoagent`。
- 依赖管理使用 `uv`（`uv sync`，开发工具为 `uv sync --extra dev`）；可选功能通过 extras 安装，例如 `browser`（Playwright）与 `vector`（ChromaDB）。
- DAG 调度与动态扩图在 `src/autoagent/dag/`（`scheduler.py`、`plan_mutator.py`）；`Plan.add_node` 与工具输出中的 `extend_nodes` 支持执行中扩图。
- CLI 入口在 `src/autoagent/cli/`（`app.py`、`run_flow.py`、`display.py`）；后台运行为 `run --detach` 与 `status --watch`，状态持久化见 `run_state.py` 与 `worker.py`（`RunSnapshot`）。
- Superpowers 实现计划文档存放在 `docs/superpowers/plans/`。
- 测试位于 `tests/`，`pytest` 在配置中启用了对 `autoagent` 的覆盖率统计并设置了最低覆盖率阈值。
- `.gitignore` 排除 `.venv/`、`.env`、`.autoagent/`、`.autoagent-test/`、`data/`、`uv.lock` 等运行时与本地环境文件。
- 使用 OpenAI 兼容网关（`OPENAI_API_BASE`）时，`AUTOAGENT_DEFAULT_MODEL` 须为 LiteLLM 的 `openai/<网关模型 ID>`（勿写裸模型名）；`llm.py` 会从项目根 `.env` 加载环境变量，避免 `.env` 内重复定义 `AUTOAGENT_DEFAULT_MODEL` 互相覆盖。
- 运行时数据：默认 `~/.autoagent/`（`memory.db`、`run.log`、`config.toml`）；`scripts/user_smoke_test.sh` 写入仓库 `.autoagent-test/`；亦可通过 `AUTOAGENT_MEMORY_PATH` 等指向仓库内 `.autoagent/`。任务历史用 `autoagent history`，原始库可用 `sqlite3` 查 `tasks` 表。
