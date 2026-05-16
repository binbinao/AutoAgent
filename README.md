# AutoAgent

生产级自主 Agent 框架，将用户目标拆解为可执行的 DAG 计划，经人类审批后执行；每个节点内部以 ReAct 循环（Thought → Action → Observation）自主推进。

## 功能特性

| 特性 | 说明 |
|------|------|
| **DAG 规划** | LLM 将目标拆解为有依赖关系的任务图，无依赖节点可并行 |
| **ReAct 执行** | 每个节点可以通过 ReAct 循环自主选择工具、观察结果、继续推进 |
| **规划与执行分离** | 先产出计划，人类审批（`y/n`）后再执行；支持 `auto_approve` 无人值守模式 |
| **分层记忆** | 工作记忆（滑动窗口）、SQLite 情景记忆、可选 ChromaDB 语义记忆 |
| **完整工具集** | 网页搜索、抓取、文件读写、Python 沙箱、Playwright 浏览器、API 调用 |
| **多模型支持** | 通过 litellm 统一接口支持 OpenAI、Claude、Ollama 等 |
| **Rich CLI** | 美观的 DAG 可视化、进度展示、任务历史 |
| **失败重试** | 每个节点支持可配置重试次数（默认 2 次） |

## 快速开始

```bash
# 安装依赖
uv sync --extra dev

# 复制环境变量示例，填入 API Key
cp .env.example .env

# 运行一个任务（需要 LLM API Key）
autoagent run "研究 AI Agent 的最新设计模式" --llm

# 先规划，手动确认后执行
autoagent run "写一个 Python CSV 分析脚本" --llm --model gpt-4o

# 查看历史任务
autoagent history

# 查看当前配置
autoagent config
```

## 安装

```bash
# 仅核心功能
uv sync

# 含开发工具（pytest、ruff、mypy）
uv sync --extra dev

# 含 Playwright 浏览器自动化
uv sync --extra browser
playwright install chromium

# 含 ChromaDB 语义记忆
uv sync --extra vector
```

## CLI 命令

### `autoagent run <goal>`

将目标规划为 DAG 并执行。

```
选项:
  --approve / -y     自动审批，无需交互确认
  --llm              使用 LLM 规划器（需要 API Key）
  --model / -m TEXT  指定 LLM 模型，覆盖默认配置
```

示例：

```bash
autoagent run "查询 Python 3.13 的新特性并写成报告" --llm --approve
autoagent run "分析当前目录的所有 .py 文件" --llm --model gpt-4o
```

### `autoagent plan <goal>`

只规划，不执行，用于预览任务拆解结果。

```bash
autoagent plan "构建一个 REST API 服务" --llm
```

### `autoagent history`

显示最近执行过的任务记录（支持分页）。

```bash
autoagent history --limit 20 --offset 10
```

### `autoagent config`

显示当前配置（来源：默认值 → `~/.autoagent/config.toml` → `.env` → 环境变量）。

```bash
autoagent config --init   # 交互式向导，写入 ~/.autoagent/config.toml
```

### `autoagent status`

查看因 Ctrl+C 中断而保存的运行状态（`~/.autoagent/run_state.json`）。

## 配置

所有配置项均可通过环境变量覆盖（前缀 `AUTOAGENT_`）：

| 环境变量 | 默认值 | 说明 |
|---|---|---|
| `AUTOAGENT_DEFAULT_MODEL` | `gpt-4o-mini` | 默认 LLM 模型 |
| `AUTOAGENT_AUTO_APPROVE` | `false` | 是否自动审批计划 |
| `AUTOAGENT_WORKSPACE` | 当前目录 | 工作目录（文件工具的沙箱根） |
| `AUTOAGENT_MEMORY_PATH` | `~/.autoagent/memory.db` | SQLite 情景记忆路径 |
| `AUTOAGENT_CHROMA_PATH` | `~/.autoagent/chroma` | ChromaDB 数据目录 |
| `AUTOAGENT_PYTHON_TIMEOUT_SECONDS` | `10` | Python 沙箱超时秒数 |
| `AUTOAGENT_USE_DOCKER_SANDBOX` | `true` | 优先用 Docker 运行 `python.run` |
| `AUTOAGENT_LOG_LEVEL` | `WARNING` | 日志级别 |
| `AUTOAGENT_SEMANTIC_MEMORY_BACKEND` | `memory` | 语义记忆后端：`memory` 或 `chroma` |

## 架构

```
用户输入目标
    │
    ▼
Planner (LLMPlanner / HeuristicPlanner)
    │  生成 DAG（节点 = 子任务，边 = 依赖）
    ▼
Approver  ─── y/n/auto ───►  拒绝或继续
    │
    ▼
DAGExecutor
    │  拓扑排序，按依赖顺序执行每个节点
    ▼
 每个节点
  ├── tool_name 明确 → ToolRegistry.run(tool, args)  [失败自动重试]
  └── tool_name=None → ReActAgent.run(description)   [内部 Thought→Action→Observation 循环]
    │
    ▼
EpisodicMemory  ←  记录目标、计划摘要、执行结果
```

## 开发

```bash
# 运行测试（含覆盖率报告）
.venv/bin/pytest

# 代码风格检查
.venv/bin/ruff check .

# 类型检查
.venv/bin/mypy src

# 安全扫描
.venv/bin/bandit -r src
```

## 项目结构

```
src/autoagent/
├── cli/              Typer 命令、Rich 展示、审批交互
├── dag/              并行调度（ready 节点批次）
├── config.py         分层配置（~/.autoagent/config.toml）
├── orchestrator.py   编排：Planner → Approver → Executor
├── executor.py       异步并行 DAG 执行、失败隔离
├── react.py          ReAct + 工作记忆 + token 窗口
├── llm.py            LLM 路由与语义增强规划
├── memory.py         工作 / 情景 / 语义记忆
├── run_state.py      中断状态持久化
├── models.py         核心数据模型（Pydantic v2）
├── tools/            工具集（含 Docker python 沙箱）
└── utils/            日志（loguru）、token 工具
```
