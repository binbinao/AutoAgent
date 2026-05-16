## Learned User Preferences

- 默认使用中文进行交流与回复。
- 常以仓库根目录的 `plan.md`（产品/技术总纲）为路线：按章节对照差距、检查当前项目状态并继续执行后续开发步骤。
- 在长周期开发中可能要求「yolo 模式」，希望在整体完成前减少反复确认、加快自主推进；实现与收尾仍应满足项目自带的验证门槛。
- 在宣称任务完成或健康状态前，倾向先用仓库内可重复的验证命令（例如 `.venv/bin/pytest` 满足 `pyproject.toml` 的覆盖率门槛，并可辅以 `ruff check src/autoagent tests`）作为依据。
- 推进开发时常要求启用 Superpowers 技能（如 executing-plans、verification-before-completion）与 `plan.md` 路线配合。
- 其余与工作流相关的偏好将随持续对话补充。

## Learned Workspace Facts

- 本仓库为 AutoAgent：面向生产的自主 Agent 框架，将目标拆解为 DAG 计划，节点内以 ReAct 循环执行；详细能力以 `README.md` 为准。
- Python 版本约束为 3.11（见 `pyproject.toml`）；可安装包名为 `autoagent`，源码位于 `src/autoagent/`，CLI 命令为 `autoagent`。
- 依赖管理使用 `uv`（`uv sync`，开发工具为 `uv sync --extra dev`）；可选功能通过 extras 安装，例如 `browser`（Playwright）与 `vector`（ChromaDB）。
- 测试位于 `tests/`，`pytest` 在配置中启用了对 `autoagent` 的覆盖率统计并设置了最低覆盖率阈值。
