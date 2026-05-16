# AutoAgent 产品与技术计划

本文档汇总产品定位、技术选型、架构方案、实现要点、目录规划、关键接口示例与 CLI 设计。

---

## 1. 产品概述

**AutoAgent** 是面向通用知识工作任务、可自主执行的生产级 Agent 框架。用户给定目标后，Agent 将目标拆解为执行计划（DAG），经人类审核批准后再执行；每个节点内部以 ReAct 循环自主推进。**远期目标**：在可控前提下演进为完全自主执行。

---

## 2. 核心特性

| 维度 | 说明 |
|------|------|
| **多模型大脑** | 通过 litellm 统一接口支持 OpenAI / Claude / 本地模型（Ollama、vLLM），可按任务类型配置推荐模型 |
| **DAG + ReAct 混合编排** | 规划阶段生成 DAG；执行中允许 Agent 动态调整图；节点内 ReAct 循环 |
| **规划与执行分离** | 先产出执行计划，人类审核后再执行；架构预留自动审批扩展点 |
| **分层记忆** | 工作记忆（当前步骤）、情景记忆（历史任务摘要）、语义记忆（向量知识库） |
| **工具集** | 网页搜索与抓取、文件读写、Python 沙箱、浏览器自动化（Playwright）、API 调用 |
| **CLI 优先** | 命令行为核心交互；架构预留 Web UI |
| **生产级** | 错误处理、日志、配置管理、可观测性 |

---

## 3. 技术栈

| 类别 | 选型 |
|------|------|
| 语言 | Python 3.11 |
| 包管理 | uv + `pyproject.toml` |
| LLM 抽象 | litellm |
| 数据校验 | Pydantic v2 |
| CLI | Typer + Rich |
| 运行时 | asyncio |
| 向量存储 | ChromaDB（语义记忆，轻量嵌入式） |
| 结构化存储 | SQLite（情景记忆、任务状态） |
| 浏览器 | Playwright |
| HTTP | httpx（异步） |
| 代码沙箱 | Docker 隔离执行 |
| 日志 | loguru |
| 测试 | pytest + pytest-asyncio |

---

## 4. 架构与实现方案

### 4.1 数据流

1. **用户输入目标** → CLI 接收  
2. **Planner 生成 DAG** → 调用 LLM 拆解任务；节点 = 子任务，边 = 依赖  
3. **Approver 展示计划** → CLI 展示 DAG；用户审批 / 修改 / 拒绝  
4. **Executor 按 DAG 执行** → 拓扑排序；无依赖节点并行，有依赖串行  
5. **节点内 ReAct** → Thought → Action → Observation，循环至完成  
6. **记忆贯穿** → 工作记忆实时更新；关键信息入情景记忆；知识沉淀至语义记忆  
7. **输出** → CLI 展示；同时写入情景记忆  

### 4.2 DAG 数据结构

- 每个节点：**任务描述**、**依赖列表**、**状态**（`pending` / `running` / `completed` / `failed`）、**分配模型**、**重试策略**。  
- DAG 支持**动态扩展**：执行中可新增节点或修改依赖。  

### 4.3 记忆系统

| 类型 | 职责与实现要点 |
|------|----------------|
| **工作记忆** | 每轮 ReAct 的消息历史 + 当前步骤上下文；滑动窗口控制 token |
| **情景记忆** | SQLite；每任务记录目标、DAG 摘要、关键决策、结果、经验教训 |
| **语义记忆** | ChromaDB；从情景记忆提炼的知识片段；相似检索为新任务提供参考 |

### 4.4 审批机制

- **当前**：CLI 展示 DAG，`y`（批准）/ `n`（拒绝）/ `e`（编辑节点）交互审批。  
- **预留**：`Approver` 抽象接口；未来可接置信度评估、规则引擎自动审批。  

### 4.5 关键设计决策

- **litellm 而非 LangChain**：避免框架绑架；litellm 专注模型调用，核心逻辑自研可控。  
- **ChromaDB 而非 Pinecone / Weaviate**：嵌入式、零外部依赖；后续可换远程向量库。  
- **DAG 节点内 ReAct**：全局结构化（DAG）与局部灵活性（ReAct）兼顾。  
- **Docker 沙箱**：代码执行必须在隔离容器中，安全优先。  

---

## 5. 实现注意事项

- **Token**：工作记忆滑动窗口 + 摘要压缩；ReAct 设最大步数防死循环。  
- **错误恢复**：节点失败可配置重试；失败节点不阻塞无依赖的其他节点。  
- **配置分层**：默认 → `~/.autoagent/` → 环境变量 → CLI 参数（后者覆盖前者）。  
- **日志**：loguru 结构化日志；`trace_id` 贯穿链路；避免泄露敏感信息。  
- **异步**：执行引擎全异步；无依赖节点并行。  
- **沙箱**：Docker 隔离；限制网络与文件系统；设置超时。  

---

## 6. 项目目录结构

```
AutoAgent/
├── pyproject.toml                    # [NEW] 项目配置、依赖声明、uv 管理
├── .python-version                   # [NEW] Python 3.11 版本锁定
├── README.md                         # [NEW] 项目文档
├── .env.example                      # [NEW] 环境变量示例（API keys 等）
├── .gitignore                        # [NEW] Git 忽略配置
│
├── src/
│   └── autoagent/
│       ├── __init__.py               # [NEW] 包初始化，版本号
│       ├── main.py                   # [NEW] CLI 入口，typer app，启动编排器
│       │
│       ├── core/                     # 核心引擎
│       │   ├── __init__.py
│       │   ├── orchestrator.py       # [NEW] 编排：Planner → Approver → Executor
│       │   ├── planner.py            # [NEW] 规划：目标 → DAG
│       │   ├── executor.py           # [NEW] 执行：按 DAG 拓扑调度节点
│       │   ├── approver.py           # [NEW] 审批：展示计划；预留自动审批接口
│       │   └── config.py             # [NEW] 全局配置，Pydantic Settings，分层覆盖
│       │
│       ├── agent/
│       │   ├── __init__.py
│       │   ├── react.py              # [NEW] ReAct：Thought → Action → Observation
│       │   ├── llm_router.py         # [NEW] LLM 路由：litellm、模型选择与降级
│       │   └── tool_registry.py      # [NEW] 工具注册、发现与调用
│       │
│       ├── dag/
│       │   ├── __init__.py
│       │   ├── graph.py              # [NEW] DAG：节点/边、拓扑排序、动态扩展
│       │   └── scheduler.py          # [NEW] 调度：并行就绪节点、状态管理
│       │
│       ├── memory/
│       │   ├── __init__.py
│       │   ├── working.py            # [NEW] 工作记忆、滑动窗口
│       │   ├── episodic.py           # [NEW] 情景记忆、SQLite
│       │   └── semantic.py           # [NEW] 语义记忆、ChromaDB
│       │
│       ├── tools/
│       │   ├── __init__.py
│       │   ├── base.py               # [NEW] Tool 基类接口
│       │   ├── web_search.py         # [NEW] 搜索与抓取
│       │   ├── file_ops.py           # [NEW] 文件读写
│       │   ├── python_sandbox.py     # [NEW] Python 沙箱，Docker
│       │   ├── browser.py            # [NEW] Playwright 浏览器自动化
│       │   └── api_caller.py         # [NEW] httpx 异步 API 调用
│       │
│       ├── cli/
│       │   ├── __init__.py
│       │   ├── app.py                # [NEW] Typer 应用、命令注册
│       │   ├── display.py            # [NEW] Rich：DAG 可视化、进度
│       │   └── commands/
│       │       ├── __init__.py
│       │       ├── run.py            # [NEW] autoagent run "任务描述"
│       │       ├── history.py        # [NEW] autoagent history
│       │       └── config.py         # [NEW] autoagent config
│       │
│       └── utils/
│           ├── __init__.py
│           ├── logging.py            # [NEW] loguru、trace_id
│           └── tokens.py             # [NEW] Token 与上下文窗口
│
├── tests/
│   ├── __init__.py
│   ├── conftest.py                   # [NEW] pytest fixtures
│   ├── test_dag.py
│   ├── test_react.py
│   ├── test_planner.py
│   ├── test_executor.py
│   ├── test_memory.py
│   └── test_tools.py
│
└── data/
    ├── autoagent.db                  # [NEW] SQLite（运行时）
    └── chroma/                       # [NEW] ChromaDB 数据（运行时）
```

---

## 7. 关键代码结构（示例）

### 7.1 Tool 基类接口

```python
from abc import ABC, abstractmethod
from pydantic import BaseModel

class ToolResult(BaseModel):
    success: bool
    output: str
    error: str | None = None

class BaseTool(ABC):
    name: str
    description: str

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult: ...
```

### 7.2 DAG 节点与图结构

```python
from pydantic import BaseModel
from enum import Enum

class NodeStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"

class DAGNode(BaseModel):
    id: str
    description: str
    dependencies: list[str] = []
    status: NodeStatus = NodeStatus.PENDING
    model: str | None = None
    max_retries: int = 2
    result: str | None = None

class DAGGraph(BaseModel):
    goal: str
    nodes: list[DAGNode]

    def topological_order(self) -> list[DAGNode]: ...
    def ready_nodes(self) -> list[DAGNode]: ...
    def add_node(self, node: DAGNode) -> None: ...
```

### 7.3 记忆系统抽象

```python
from abc import ABC, abstractmethod

class BaseMemory(ABC):
    @abstractmethod
    async def store(self, content: str, metadata: dict | None = None) -> str: ...

    @abstractmethod
    async def retrieve(self, query: str, top_k: int = 5) -> list[str]: ...

    @abstractmethod
    async def clear(self) -> None: ...
```

---

## 8. CLI 与设计规范

### 8.1 设计风格

采用现代终端美学，以 **Rich** 为核心，呈现专业、可读的 CLI。

### 8.2 布局设计

**主命令 `autoagent run`**

- 顶部状态栏：当前目标 + 执行状态（Rich Panel，渐变边框）  
- DAG 区：Rich Tree 展示依赖；颜色区分状态（灰=待执行，蓝=执行中，绿=完成，红=失败）  
- ReAct 实时区：Thought（斜体）、Action（加粗）、Observation（常规）；三色区分  
- 审批区：计划展示后高亮关键节点，等待 `y` / `n` / `e`（编辑）  
- 底部：Rich Progress 整体进度  

**`autoagent history`**

- 表格：目标、状态、耗时、模型；支持分页  

**`autoagent config`**

- 交互式向导：API Key、默认模型、记忆路径等  

### 8.3 交互设计

- DAG 审批：`y`（批准）、`n`（拒绝）、`e`（编辑节点）  
- 执行中 **Ctrl+C**：优雅中断并保存状态  
- 长任务：支持后台运行与重连查看进度  

---

## 9. Agent Extensions（Skills）

开发阶段可挂载的 Cursor / Agent 技能参考：

| Skill | 用途 |
|-------|------|
| `python-patterns` | Pythonic 与 PEP 8，保证代码风格 |
| `python-testing` | pytest、TDD，目标 80%+ 覆盖率 |
| `security-review` | API Key 与敏感信息、沙箱隔离审查 |
| `agent-browser` | 浏览器自动化实现参考 |
