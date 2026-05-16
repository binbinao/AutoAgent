from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

from autoagent.models import Plan, PlanNode

T = TypeVar("T")


async def run_plan_batches(
    plan: Plan,
    *,
    execute_batch: Callable[[list[PlanNode]], Awaitable[list[T]]],
) -> list[list[T]]:
    """Execute *plan* in dependency waves; each wave may run nodes in parallel."""
    completed: set[str] = set()
    failed: set[str] = set()
    skipped: set[str] = set()
    all_batches: list[list[T]] = []

    while True:
        for node_id in plan.nodes_to_skip(completed=completed, failed=failed, skipped=skipped):
            skipped.add(node_id)

        ready = plan.ready_nodes(completed=completed, failed=failed, skipped=skipped)
        if not ready:
            break

        batch_results = await execute_batch(ready)
        all_batches.append(batch_results)

        for node, result in zip(ready, batch_results, strict=True):
            ok = getattr(result, "ok", None)
            if ok is None and hasattr(result, "tool_result"):
                ok = result.tool_result.ok
            if ok is False:
                failed.add(node.id)
            else:
                completed.add(node.id)

    return all_batches
