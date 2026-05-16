from __future__ import annotations

from collections.abc import Callable

from rich.console import Console
from rich.progress import BarColumn, Progress, TaskProgressColumn, TextColumn
from rich.tree import Tree

from autoagent.models import NodeStatus, Plan

_STATUS_STYLE = {
    NodeStatus.PENDING: "dim",
    NodeStatus.RUNNING: "bold blue",
    NodeStatus.COMPLETED: "bold green",
    NodeStatus.FAILED: "bold red",
    NodeStatus.SKIPPED: "yellow",
}


def render_plan_tree(
    plan: Plan,
    *,
    statuses: dict[str, NodeStatus] | None = None,
) -> Tree:
    statuses = statuses or {}
    tree = Tree(f"[bold cyan]{plan.goal}[/bold cyan]")
    for node in plan.topological_nodes():
        status = statuses.get(node.id, node.status)
        style = _STATUS_STYLE.get(status, "")
        tool = node.tool_name or "react"
        deps = ", ".join(node.dependencies) if node.dependencies else "—"
        tree.add(f"[{style}]{node.id}[/{style}] ({tool}) deps={deps} — {node.description}")
    return tree


def execution_progress(console: Console | None = None) -> Progress:
    return Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    )


def make_react_step_printer(console: Console) -> Callable[[str, str, str], None]:
    def on_step(thought: str, action: str, observation: str) -> None:
        console.print(f"[italic dim]Thought:[/italic dim] {thought[:200]}")
        if action:
            console.print(f"[bold]Action:[/bold] {action}")
        if observation:
            console.print(f"Observation: {observation[:300]}")

    return on_step
