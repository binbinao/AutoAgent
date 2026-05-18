"""Background worker entrypoint for detached ``autoagent run --detach`` jobs."""

from __future__ import annotations

import typer
from rich.console import Console

from autoagent.cli.app import _resolve_settings, _resolve_task_mode, build_orchestrator
from autoagent.cli.run_flow import execute_approved_run
from autoagent.models import RunStatus
from autoagent.run_state import RunSnapshot, save_run_snapshot
from autoagent.utils.logging import configure_logging, new_trace_id

app = typer.Typer(help="AutoAgent background worker.", add_completion=False)
_console = Console(stderr=True)


@app.command()
def main(
    goal: str,
    approve: bool = typer.Option(True, "--approve", "-y"),
    model: str | None = typer.Option(None, "--model", "-m"),
    llm: bool = typer.Option(False, "--llm"),
    mode: str | None = typer.Option(None, "--mode", "-M"),
    tool_preset: str | None = typer.Option(None, "--tool-preset"),
) -> None:
    """Plan and execute *goal* (used by ``autoagent run --detach``)."""
    new_trace_id()
    settings = _resolve_settings(model)
    task_mode = _resolve_task_mode(mode, settings)
    configure_logging(settings.log_level)
    orchestrator, report_router = build_orchestrator(
        settings,
        use_llm_planner=llm,
        console=None,
        task_mode=task_mode,
        tool_preset=tool_preset,
    )

    agent_run = orchestrator.plan(goal)
    if agent_run.status is RunStatus.AWAITING_APPROVAL and not approve:
        save_run_snapshot(
            settings.state_path,
            RunSnapshot(run=agent_run, detached=True, log_path=str(settings.log_path)),
        )
        _console.print("[red]Plan requires approval; re-run with --approve[/red]")
        raise typer.Exit(1)

    snapshot = RunSnapshot(
        run=agent_run.with_update(status=RunStatus.RUNNING),
        detached=True,
        log_path=str(settings.log_path),
    )
    save_run_snapshot(settings.state_path, snapshot)

    try:
        execute_approved_run(
            orchestrator,
            agent_run,
            settings,
            console=_console,
            snapshot=snapshot,
            report_router=report_router,
            task_mode=task_mode,
        )
    except Exception:
        failed = agent_run.with_update(status=RunStatus.FAILED)
        save_run_snapshot(
            settings.state_path,
            RunSnapshot(run=failed, detached=True, log_path=str(settings.log_path)),
        )
        raise


if __name__ == "__main__":
    app()
