from __future__ import annotations

import signal
import subprocess
import sys
import time
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel

from autoagent.cli.display import make_react_step_printer, render_plan_tree
from autoagent.cli.run_flow import execute_approved_run
from autoagent.config import AgentSettings, user_config_path
from autoagent.dag.plan_mutator import ExtendNodesMutator
from autoagent.executor import DAGExecutor
from autoagent.llm import LiteLLMRouter, LLMPlanner
from autoagent.memory import EpisodicMemory, create_semantic_memory, record_task_with_semantic
from autoagent.models import AgentRun, NodeStatus, Plan, PlanNode, RunStatus
from autoagent.orchestrator import HeuristicPlanner, ManualApprover, Orchestrator
from autoagent.react import ReActAgent
from autoagent.run_state import (
    TERMINAL_RUN_STATUSES,
    RunSnapshot,
    load_run_snapshot,
    save_run_snapshot,
)
from autoagent.tools import (
    ApiRequestTool,
    BrowserSnapshotTool,
    EchoTool,
    FileListTool,
    FileReadTool,
    FileWriteTool,
    PythonSandboxTool,
    ToolRegistry,
    WebFetchTool,
    WebSearchTool,
)
from autoagent.utils.logging import configure_logging, new_trace_id

app = typer.Typer(help="AutoAgent — autonomous knowledge-work agent.")
console = Console()

_interrupt_state: dict[str, AgentRun | None] = {"run": None, "settings": None}


class RunInterruptedError(Exception):
    """Raised when the user interrupts execution with Ctrl+C."""


def build_registry(workspace: Path, settings: AgentSettings) -> ToolRegistry:
    return ToolRegistry.with_tools(
        [
            EchoTool(),
            FileReadTool(workspace),
            FileWriteTool(workspace),
            FileListTool(workspace),
            WebSearchTool(),
            WebFetchTool(),
            PythonSandboxTool(
                workspace,
                timeout_seconds=settings.python_timeout_seconds,
                use_docker=settings.use_docker_sandbox,
            ),
            ApiRequestTool(),
            BrowserSnapshotTool(),
        ]
    )


def build_orchestrator(
    settings: AgentSettings,
    *,
    use_llm_planner: bool = False,
    console: Console | None = None,
) -> Orchestrator:
    registry = build_registry(settings.workspace, settings)
    react_agent: ReActAgent | None = None
    planner: HeuristicPlanner | LLMPlanner

    if use_llm_planner:
        router = LiteLLMRouter(settings.default_model)
        semantic = create_semantic_memory(settings)
        planner = LLMPlanner(router, semantic=semantic)
        on_step = make_react_step_printer(console or Console()) if console else None
        react_agent = ReActAgent(
            router,
            registry,
            max_steps=settings.react_max_steps,
            max_context_tokens=settings.max_context_tokens,
        )
        executor = DAGExecutor(
            registry,
            react_agent=react_agent,
            on_react_step=on_step,
            plan_mutator=ExtendNodesMutator(),
        )
    else:
        planner = HeuristicPlanner()
        executor = DAGExecutor(registry, plan_mutator=ExtendNodesMutator())

    return Orchestrator(
        planner=planner,
        approver=ManualApprover(auto_approve=settings.auto_approve),
        executor=executor,
    )


def _display_plan(plan: Plan, statuses: dict[str, NodeStatus] | None = None) -> None:
    console.print(render_plan_tree(plan, statuses=statuses))


def _interactive_edit_plan(plan: Plan) -> Plan:
    new_nodes: list[PlanNode] = []
    for node in plan.nodes:
        text = typer.prompt(
            f"Description for node '{node.id}'",
            default=node.description,
        ).strip()
        desc = text or node.description
        new_nodes.append(node.model_copy(update={"description": desc}))
    return Plan(goal=plan.goal, nodes=new_nodes)


def _prompt_until_plan_resolved(plan: Plan) -> tuple[Plan, bool]:
    while True:
        choice = typer.prompt("Approve plan? [y/n/e]", default="y").strip().lower()
        if choice == "n":
            return plan, False
        if choice == "e":
            plan = _interactive_edit_plan(plan)
            _display_plan(plan)
            console.print("[dim]Plan updated — review again.[/dim]")
            continue
        if choice in ("y", ""):
            return plan, True
        console.print("[yellow]Please answer: y (approve), n (reject), or e (edit).[/yellow]")


def _resolve_settings(model: str | None = None) -> AgentSettings:
    settings = AgentSettings()
    if model:
        settings = settings.model_copy(update={"default_model": model})
    configure_logging(settings.log_level)
    return settings


def _handle_interrupt(signum: int, frame: object | None) -> None:
    del signum, frame
    run = _interrupt_state.get("run")
    settings = _interrupt_state.get("settings")
    if run is not None and settings is not None:
        interrupted = run.with_update(status=RunStatus.FAILED)
        save_run_snapshot(settings.state_path, RunSnapshot(run=interrupted))
        record_task_with_semantic(
            settings,
            goal=run.goal,
            plan_summary=run.plan.summary(),
            outcome="interrupted",
        )
        console.print(
            "\n[yellow]Interrupted — run state saved. "
            "Use `autoagent status` to inspect.[/yellow]"
        )
    raise RunInterruptedError()


@app.command(name="plan")
def plan_cmd(
    goal: str,
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model override."),
    llm: bool = typer.Option(False, "--llm", help="Use LLM planner (requires an API key)."),
) -> None:
    """Create a plan without executing it."""
    new_trace_id()
    settings = _resolve_settings(model)
    agent_run = build_orchestrator(settings, use_llm_planner=llm, console=console).plan(goal)
    _display_plan(agent_run.plan)
    console.print(f"Status: {agent_run.status.value}")


def _spawn_detached_run(
    goal: str,
    *,
    approve: bool,
    llm: bool,
    model: str | None,
    settings: AgentSettings,
) -> None:
    settings.log_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "-m", "autoagent.worker", "execute", goal]
    if approve:
        cmd.append("--approve")
    if llm:
        cmd.append("--llm")
    if model:
        cmd.extend(["--model", model])

    with settings.log_path.open("w", encoding="utf-8") as log_file:
        proc = subprocess.Popen(  # noqa: S603
            cmd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )

    placeholder = Plan(
        goal=goal,
        nodes=[
            PlanNode(
                id="pending",
                description="Background worker starting…",
                tool_name="echo",
                tool_args={"goal": goal},
            )
        ],
    )
    snapshot = RunSnapshot(
        run=AgentRun(goal=goal, plan=placeholder, status=RunStatus.RUNNING),
        pid=proc.pid,
        detached=True,
        log_path=str(settings.log_path),
    )
    save_run_snapshot(settings.state_path, snapshot)
    console.print(f"[green]Detached run started[/green] (pid={proc.pid})")
    console.print(f"Log: {settings.log_path}")
    console.print("Use [bold]autoagent status --watch[/bold] to follow progress.")


def _render_snapshot(snapshot: RunSnapshot) -> None:
    title = "Background run" if snapshot.detached else "Run state"
    console.print(Panel(snapshot.run.goal, title=title, border_style="yellow"))
    _display_plan(snapshot.run.plan)
    console.print(f"Status: {snapshot.run.status.value}")
    if snapshot.pid:
        console.print(f"PID: {snapshot.pid}")
    if snapshot.progress.messages:
        console.print("[dim]Recent events:[/dim]")
        for line in snapshot.progress.messages[-5:]:
            console.print(f"  • {line}")
    if snapshot.log_path:
        console.print(f"Log: {snapshot.log_path}")


@app.command()
def run(
    goal: str,
    approve: bool = typer.Option(
        False, "--approve", "-y", help="Approve plan automatically and execute."
    ),
    detach: bool = typer.Option(
        False, "--detach", "-d", help="Run in background; use autoagent status --watch."
    ),
    model: str | None = typer.Option(None, "--model", "-m", help="LLM model override."),
    llm: bool = typer.Option(False, "--llm", help="Use LLM planner (requires an API key)."),
) -> None:
    """Plan and optionally execute a goal."""
    new_trace_id()
    settings = _resolve_settings(model)

    if detach:
        if not approve:
            console.print("[yellow]Detached runs require --approve[/yellow]")
            raise typer.Exit(1)
        _spawn_detached_run(goal, approve=approve, llm=llm, model=model, settings=settings)
        return

    orchestrator = build_orchestrator(settings, use_llm_planner=llm, console=console)

    console.print(Panel(goal, title="[bold]Goal[/bold]", border_style="cyan"))
    console.print("[dim]Planning…[/dim]")
    agent_run = orchestrator.plan(goal)

    _display_plan(agent_run.plan)
    console.print(f"Status: {agent_run.status.value}")

    if agent_run.status is RunStatus.AWAITING_APPROVAL and not approve:
        current_plan, approved_plan = _prompt_until_plan_resolved(agent_run.plan)
        if not approved_plan:
            console.print("[red]Plan rejected.[/red]")
            raise typer.Exit(1)
        agent_run = agent_run.model_copy(update={"plan": current_plan})
        approve = True

    if approve or agent_run.status is RunStatus.APPROVED:
        _interrupt_state["run"] = agent_run
        _interrupt_state["settings"] = settings
        previous = signal.signal(signal.SIGINT, _handle_interrupt)
        try:
            console.print("[dim]Executing…[/dim]")
            execute_approved_run(
                orchestrator,
                agent_run,
                settings,
                console=console,
            )
        except RunInterruptedError:
            raise typer.Exit(130) from None
        finally:
            signal.signal(signal.SIGINT, previous)
            _interrupt_state["run"] = None
            _interrupt_state["settings"] = None


@app.command()
def status(
    watch: bool = typer.Option(False, "--watch", "-w", help="Refresh until run completes."),
    interval: float = typer.Option(1.0, "--interval", help="Refresh interval in seconds."),
) -> None:
    """Show saved or in-progress run state."""
    settings = _resolve_settings()

    while True:
        snapshot = load_run_snapshot(settings.state_path)
        if snapshot is None:
            console.print("[dim]No saved run state.[/dim]")
            return

        if watch:
            console.clear()
        _render_snapshot(snapshot)

        if not watch or snapshot.run.status in TERMINAL_RUN_STATUSES:
            break
        time.sleep(interval)


@app.command()
def history(
    limit: int = typer.Option(10, "--limit", "-n", help="Number of recent tasks to show."),
    offset: int = typer.Option(0, "--offset", help="Skip first N tasks (pagination)."),
) -> None:
    """Show recent task history."""
    settings = _resolve_settings()
    try:
        memory = EpisodicMemory(settings.memory_path)
        tasks = memory.list_tasks(limit=limit + offset)
        memory.close()
    except Exception:
        console.print("[yellow]No history available (memory store not initialised).[/yellow]")
        return

    page = tasks[offset : offset + limit] if offset else tasks[:limit]
    if not page:
        console.print("No tasks recorded yet.")
        return

    from rich.table import Table

    table = Table(title="Task History")
    table.add_column("ID", style="dim")
    table.add_column("Goal")
    table.add_column("Plan")
    table.add_column("Outcome")
    table.add_column("Date", style="dim")
    for task in page:
        table.add_row(
            task.id[:8],
            task.goal[:50],
            task.plan_summary[:30],
            task.outcome,
            task.created_at.strftime("%Y-%m-%d %H:%M"),
        )
    console.print(table)


@app.command(name="config")
def config_cmd(
    init: bool = typer.Option(False, "--init", help="Interactive setup wizard."),
) -> None:
    """Show or initialize configuration."""
    if init:
        _config_init_wizard()
        return

    settings = _resolve_settings()
    from rich.table import Table

    table = Table(title="AutoAgent Configuration")
    table.add_column("Setting", style="bold")
    table.add_column("Value")
    table.add_row("default_model", settings.default_model)
    table.add_row("workspace", str(settings.workspace))
    table.add_row("memory_path", str(settings.memory_path))
    table.add_row("chroma_path", str(settings.chroma_path))
    table.add_row("auto_approve", str(settings.auto_approve))
    table.add_row("python_timeout_seconds", str(settings.python_timeout_seconds))
    table.add_row("use_docker_sandbox", str(settings.use_docker_sandbox))
    table.add_row("log_level", settings.log_level)
    table.add_row("semantic_memory_backend", settings.semantic_memory_backend)
    table.add_row("user_config", str(user_config_path()))
    console.print(table)


def _config_init_wizard() -> None:
    path = user_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    model = typer.prompt("Default LLM model", default="gpt-4o-mini")
    workspace = typer.prompt("Workspace directory", default=str(Path.cwd()))
    backend = typer.prompt("Semantic memory backend (memory/chroma)", default="memory")
    auto = typer.confirm("Auto-approve plans?", default=False)
    docker = typer.confirm("Use Docker for python.run when available?", default=True)

    lines = [
        f'default_model = "{model}"',
        f'workspace = "{workspace}"',
        f'semantic_memory_backend = "{backend}"',
        f"auto_approve = {'true' if auto else 'false'}",
        f"use_docker_sandbox = {'true' if docker else 'false'}",
        "",
        "# Set API keys via environment, e.g. OPENAI_API_KEY or in .env",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    console.print(f"[green]Wrote {path}[/green]")
    console.print("[dim]Restart the shell or run commands to pick up changes.[/dim]")
