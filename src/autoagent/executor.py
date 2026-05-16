from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from autoagent.models import NodeExecutionResult, Plan, PlanNode, ToolResult
from autoagent.tools import ToolRegistry
from autoagent.tools.base import ToolExecutionError

if TYPE_CHECKING:
    from autoagent.react import ReActAgent

ReActStepCallback = Callable[[str, str, str], None]


class DAGExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        react_agent: ReActAgent | None = None,
        on_react_step: ReActStepCallback | None = None,
    ) -> None:
        self.registry = registry
        self.react_agent = react_agent
        self.on_react_step = on_react_step

    def execute(self, plan: Plan) -> list[NodeExecutionResult]:
        return asyncio.run(self.execute_async(plan))

    async def execute_async(self, plan: Plan) -> list[NodeExecutionResult]:
        results: list[NodeExecutionResult] = []
        completed: set[str] = set()
        failed: set[str] = set()
        skipped: set[str] = set()

        while True:
            for node_id in plan.nodes_to_skip(
                completed=completed, failed=failed, skipped=skipped
            ):
                if node_id in skipped:
                    continue
                skipped.add(node_id)
                started_at = datetime.now(UTC)
                results.append(
                    NodeExecutionResult(
                        node_id=node_id,
                        tool_result=ToolResult(
                            ok=False,
                            error="Skipped: dependency failed or was skipped",
                        ),
                        started_at=started_at,
                        finished_at=datetime.now(UTC),
                    )
                )

            ready = plan.ready_nodes(completed=completed, failed=failed, skipped=skipped)
            if not ready:
                break

            batch = await asyncio.gather(
                *[asyncio.to_thread(self._execute_node_timed, node) for node in ready]
            )
            for node, (started_at, tool_result) in zip(ready, batch, strict=True):
                results.append(
                    NodeExecutionResult(
                        node_id=node.id,
                        tool_result=tool_result,
                        started_at=started_at,
                        finished_at=datetime.now(UTC),
                    )
                )
                if tool_result.ok:
                    completed.add(node.id)
                else:
                    failed.add(node.id)

        return results

    def _execute_node_timed(self, node: PlanNode) -> tuple[datetime, ToolResult]:
        started_at = datetime.now(UTC)
        return started_at, self._execute_node(node)

    def _execute_node(self, node: PlanNode) -> ToolResult:
        if node.tool_name is None:
            if self.react_agent is not None:
                model = node.model
                if self.on_react_step is not None:
                    return self.react_agent.run(
                        node.description,
                        model=model,
                        on_step=self.on_react_step,
                    )
                return self.react_agent.run(node.description, model=model)
            return ToolResult(
                ok=False,
                error="No ReAct agent configured for a node without tool_name",
            )

        last_error: str = ""
        for attempt in range(max(0, node.max_retries) + 1):
            try:
                return self.registry.run(node.tool_name, node.tool_args)
            except ToolExecutionError as exc:
                last_error = str(exc)
                if attempt < node.max_retries:
                    continue
        return ToolResult(
            ok=False,
            error=f"Failed after {node.max_retries + 1} attempt(s): {last_error}",
        )
