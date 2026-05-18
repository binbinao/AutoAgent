from __future__ import annotations

from collections.abc import Callable

from rich.console import Console

from autoagent.cli.display import execution_progress, render_plan_tree
from autoagent.config import AgentSettings
from autoagent.llm import LiteLLMRouter
from autoagent.memory import create_semantic_memory, record_run_history
from autoagent.models import AgentRun, NodeExecutionResult, NodeStatus, RunStatus
from autoagent.orchestrator import Orchestrator
from autoagent.report import ensure_run_report
from autoagent.run_state import RunProgress, RunSnapshot, clear_run_snapshot, save_run_snapshot
from autoagent.task_mode import TaskMode, parse_task_mode


def execute_approved_run(
    orchestrator: Orchestrator,
    agent_run: AgentRun,
    settings: AgentSettings,
    *,
    console: Console,
    snapshot: RunSnapshot | None = None,
    report_router: LiteLLMRouter | None = None,
    on_progress: Callable[[RunProgress], None] | None = None,
    task_mode: TaskMode | None = None,
) -> AgentRun:
    """Execute an approved run, persisting progress to *settings.state_path*."""
    progress = snapshot.progress.model_copy(deep=True) if snapshot else RunProgress()
    pid = snapshot.pid if snapshot else None
    detached = snapshot.detached if snapshot else False
    log_path = snapshot.log_path if snapshot else str(settings.log_path)

    def persist(run: AgentRun) -> None:
        save_run_snapshot(
            settings.state_path,
            RunSnapshot(
                run=run,
                progress=progress,
                pid=pid,
                detached=detached,
                log_path=log_path,
            ),
        )

    def on_node_finished(_plan: object, result: object) -> None:
        if not isinstance(result, NodeExecutionResult):
            return
        if result.tool_result.ok:
            progress.completed_nodes.append(result.node_id)
            progress.append_message(f"completed {result.node_id}")
        elif "skipped" in (result.tool_result.error or "").lower():
            progress.skipped_nodes.append(result.node_id)
            progress.append_message(f"skipped {result.node_id}")
        else:
            progress.failed_nodes.append(result.node_id)
            progress.append_message(f"failed {result.node_id}")
        persist(agent_run.with_update(status=RunStatus.RUNNING))
        if on_progress is not None:
            on_progress(progress)

    orchestrator.executor.on_node_finished = on_node_finished

    running = agent_run.with_update(status=RunStatus.RUNNING)
    persist(running)

    with execution_progress(console=console) as progress_bar:
        task_id = progress_bar.add_task("DAG execution", total=len(agent_run.plan.nodes))
        completed = orchestrator.execute(running, approved=True)
        progress_bar.update(task_id, completed=len(agent_run.plan.nodes))

    clear_run_snapshot(settings.state_path)

    lesson = None
    if completed.results:
        last = completed.results[-1].tool_result
        if last.ok and "answer" in last.output:
            lesson = str(last.output.get("answer", ""))[:500]

    mode = task_mode or parse_task_mode(settings.default_task_mode)
    report_path = ensure_run_report(
        goal=agent_run.goal,
        run_id=agent_run.id,
        results=completed.results,
        workspace=settings.workspace,
        router=report_router,
        report_synthesizer=orchestrator.executor.report_synthesizer,
        mode=mode,
    )

    record_run_history(
        settings.memory_path,
        workspace=settings.workspace,
        agent_run=agent_run,
        outcome=completed.status.value,
        results=completed.results,
        report_path=report_path,
    )
    if lesson:
        semantic = create_semantic_memory(settings)
        semantic.add(
            text=f"Goal: {agent_run.goal}\nOutcome: {completed.status.value}\nLesson: {lesson}",
            metadata={"goal": agent_run.goal[:200], "outcome": completed.status.value},
        )

    statuses = {
        r.node_id: NodeStatus.COMPLETED if r.tool_result.ok else NodeStatus.FAILED
        for r in completed.results
    }
    console.print(render_plan_tree(agent_run.plan, statuses=statuses))
    console.print(f"Status: {completed.status.value}")
    if report_path is not None:
        console.print(f"[green]Report:[/green] {report_path.resolve()}")
    return completed
