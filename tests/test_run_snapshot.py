from __future__ import annotations

from pathlib import Path

from autoagent.models import AgentRun, Plan, PlanNode, RunStatus
from autoagent.run_state import (
    RunProgress,
    RunSnapshot,
    clear_run_snapshot,
    load_run_snapshot,
    save_run_snapshot,
)


def test_run_snapshot_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    plan = Plan(goal="g", nodes=[PlanNode(id="a", description="A", tool_name="echo")])
    run = AgentRun(goal="g", plan=plan, status=RunStatus.RUNNING)
    snap = RunSnapshot(
        run=run,
        progress=RunProgress(completed_nodes=["a"], messages=["started a"]),
        pid=12345,
        detached=True,
    )

    save_run_snapshot(path, snap)
    loaded = load_run_snapshot(path)

    assert loaded is not None
    assert loaded.pid == 12345
    assert loaded.detached is True
    assert loaded.progress.completed_nodes == ["a"]


def test_load_run_snapshot_legacy_agent_run_json(tmp_path: Path) -> None:
    path = tmp_path / "legacy.json"
    plan = Plan(goal="g", nodes=[PlanNode(id="a", description="A", tool_name="echo")])
    run = AgentRun(goal="g", plan=plan, status=RunStatus.FAILED)
    path.write_text(run.model_dump_json(), encoding="utf-8")

    loaded = load_run_snapshot(path)

    assert loaded is not None
    assert loaded.run.status is RunStatus.FAILED
    assert loaded.progress.completed_nodes == []


def test_clear_run_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "state.json"
    save_run_snapshot(path, RunSnapshot(run=AgentRun(goal="g", plan=Plan(goal="g", nodes=[]))))
    clear_run_snapshot(path)
    assert load_run_snapshot(path) is None
