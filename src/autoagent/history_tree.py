"""Build task history trees from episodic records."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from autoagent.memory import EpisodicTask
from autoagent.report import _DEFAULT_REPORT_DIR

REPORT_DIR = _DEFAULT_REPORT_DIR


def resolve_task_reports(task: EpisodicTask, workspace: Path) -> list[str]:
    """Return validated report paths for a task, backfilling from disk by run_id when needed."""
    paths: list[str] = list(task.report_paths)
    root = workspace.resolve()

    if task.run_id:
        reports_dir = root / REPORT_DIR
        if reports_dir.is_dir():
            suffix = f"-{task.run_id[:8]}.md"
            matches = sorted(reports_dir.glob(f"*{suffix}"), key=lambda p: p.stat().st_mtime)
            for candidate in matches:
                if not candidate.is_file():
                    continue
                rel = str(candidate.relative_to(root))
                if rel not in paths:
                    paths.append(rel)

    valid: list[str] = []
    for rel in paths:
        if (root / rel).is_file():
            valid.append(rel)
    return valid


def build_history_tree(tasks: list[EpisodicTask], *, workspace: Path) -> list[dict[str, Any]]:
    """Group flat tasks into root items with nested children (newest roots first)."""
    by_parent: dict[str | None, list[EpisodicTask]] = {}
    for task in tasks:
        by_parent.setdefault(task.parent_task_id, []).append(task)

    for group in by_parent.values():
        group.sort(key=lambda t: t.created_at, reverse=True)

    def task_to_dict(task: EpisodicTask) -> dict[str, Any]:
        children = by_parent.get(task.id, [])
        reports = (
            report_entries(resolve_task_reports(task, workspace))
            if task.parent_task_id is None
            else []
        )
        return {
            "id": task.id,
            "goal": task.goal,
            "plan_summary": task.plan_summary,
            "outcome": task.outcome,
            "status": task.outcome,
            "created_at": task.created_at.isoformat(),
            "run_id": task.run_id,
            "node_id": task.node_id,
            "reports": reports,
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
