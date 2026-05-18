from __future__ import annotations

from pathlib import Path

from autoagent.history_tree import build_history_tree
from autoagent.memory import EpisodicMemory, record_run_history
from autoagent.models import (
    AgentRun,
    NodeExecutionResult,
    Plan,
    PlanNode,
    RunStatus,
    ToolResult,
)


def test_record_run_history_creates_root_and_children(tmp_path: Path) -> None:

    plan = Plan(
        goal="root goal",
        nodes=[
            PlanNode(id="n1", description="search web", tool_name="echo", tool_args={}),
            PlanNode(id="n2", description="write file", tool_name="echo", tool_args={}),
        ],
    )
    run = AgentRun(goal="root goal", plan=plan, status=RunStatus.COMPLETED)
    results = [
        NodeExecutionResult(
            node_id="n1",
            tool_result=ToolResult(ok=True, output={"answer": "ok"}),
        ),
        NodeExecutionResult(
            node_id="n2",
            tool_result=ToolResult(ok=False, error="failed"),
        ),
    ]
    report = tmp_path / ".autoagent" / "reports" / "root-abc12345.md"
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text("# report", encoding="utf-8")

    db = tmp_path / "mem.db"
    root_id = record_run_history(
        db,
        workspace=tmp_path,
        agent_run=run,
        outcome="completed",
        results=results,
        report_path=report,
    )

    memory = EpisodicMemory(db)
    try:
        root = memory.get_task(root_id)
        assert root is not None
        assert root.parent_task_id is None
        assert root.run_id == run.id
        assert list(root.report_paths) == [".autoagent/reports/root-abc12345.md"]

        children = memory.list_children([root_id])
        assert len(children) == 2
        assert {c.node_id for c in children} == {"n1", "n2"}
        assert all(c.parent_task_id == root_id for c in children)
    finally:
        memory.close()


def test_build_history_tree_groups_children_under_root() -> None:
    from datetime import UTC, datetime

    from autoagent.memory import EpisodicTask

    created = datetime.now(UTC)
    root = EpisodicTask(
        id="r1",
        goal="main",
        plan_summary="plan",
        outcome="completed",
        created_at=created,
        run_id="run-1",
        report_paths=[".autoagent/reports/a.md"],
    )
    child = EpisodicTask(
        id="c1",
        goal="child step",
        plan_summary="echo",
        outcome="completed",
        created_at=created,
        parent_task_id="r1",
        node_id="n1",
    )
    tree = build_history_tree([root, child])
    assert len(tree) == 1
    assert tree[0]["id"] == "r1"
    assert tree[0]["reports"][0]["name"] == "a.md"
    assert len(tree[0]["children"]) == 1
    assert tree[0]["children"][0]["id"] == "c1"


def test_episodic_memory_migrates_legacy_schema(tmp_path: Path) -> None:
    legacy = tmp_path / "legacy.db"
    import sqlite3

    conn = sqlite3.connect(legacy)
    conn.execute(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            goal TEXT NOT NULL,
            plan_summary TEXT NOT NULL,
            outcome TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        "INSERT INTO tasks VALUES (?, ?, ?, ?, ?)",
        ("old", "g", "p", "done", "2020-01-01T00:00:00+00:00"),
    )
    conn.commit()
    conn.close()

    memory = EpisodicMemory(legacy)
    try:
        task = memory.get_task("old")
        assert task is not None
        assert task.parent_task_id is None
        task_id = memory.record_task(
            goal="new",
            plan_summary="p",
            outcome="done",
            parent_task_id="old",
            node_id="x",
        )
        child = memory.get_task(task_id)
        assert child is not None
        assert child.parent_task_id == "old"
    finally:
        memory.close()
