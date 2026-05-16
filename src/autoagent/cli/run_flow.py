from __future__ import annotations

from rich.console import Console

from autoagent.cli.display import execution_progress, render_plan_tree
from autoagent.config import AgentSettings
from autoagent.memory import record_task_with_semantic
from autoagent.models import AgentRun, NodeExecutionResult, NodeStatus, RunStatus
from autoagent.orchestrator import Orchestrator
from autoagent.run_state import RunProgress, RunSnapshot, clear_run_snapshot, save_run_snapshot


def execute_approved_run(
    orchestrator: Orchestrator,
    agent_run: AgentRun,
    settings: AgentSettings,
    *,
    console: Console,
    snapshot: RunSnapshot | None = None,
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

    record_task_with_semantic(
        settings,
        goal=agent_run.goal,
        plan_summary=agent_run.plan.summary(),
        outcome=completed.status.value,
        lesson=lesson,
    )

    statuses = {
        r.node_id: NodeStatus.COMPLETED if r.tool_result.ok else NodeStatus.FAILED
        for r in completed.results
    }
    console.print(render_plan_tree(agent_run.plan, statuses=statuses))
    console.print(f"Status: {completed.status.value}")
    return completed
