"""Build task history trees from episodic records."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from autoagent.memory import EpisodicTask


def build_history_tree(tasks: list[EpisodicTask]) -> list[dict[str, Any]]:
    """Group flat tasks into root items with nested children (newest roots first)."""
    by_parent: dict[str | None, list[EpisodicTask]] = {}
    for task in tasks:
        by_parent.setdefault(task.parent_task_id, []).append(task)

    for group in by_parent.values():
        group.sort(key=lambda t: t.created_at, reverse=True)

    def task_to_dict(task: EpisodicTask) -> dict[str, Any]:
        children = by_parent.get(task.id, [])
        return {
            "id": task.id,
            "goal": task.goal,
            "plan_summary": task.plan_summary,
            "outcome": task.outcome,
            "status": task.outcome,
            "created_at": task.created_at.isoformat(),
            "run_id": task.run_id,
            "node_id": task.node_id,
            "reports": report_entries(list(task.report_paths)),
            "children": [task_to_dict(child) for child in children],
        }

    roots = by_parent.get(None, [])
    return [task_to_dict(root) for root in roots]


def report_entries(paths: list[str]) -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for path in paths:
        name = Path(path).name
        items.append({"name": name, "path": path})
    return items
