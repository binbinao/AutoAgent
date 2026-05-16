from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from autoagent.dag.plan_mutator import PlanMutator
from autoagent.models import NodeExecutionResult, Plan, PlanNode, ToolResult
from autoagent.tools import ToolRegistry
from autoagent.tools.base import ToolExecutionError

if TYPE_CHECKING:
    from autoagent.react import ReActAgent

ReActStepCallback = Callable[[str, str, str], None]
NodeFinishedCallback = Callable[[Plan, NodeExecutionResult], None]


class DAGExecutor:
    def __init__(
        self,
        registry: ToolRegistry,
        *,
        react_agent: ReActAgent | None = None,
        on_react_step: ReActStepCallback | None = None,
        on_node_finished: NodeFinishedCallback | None = None,
        plan_mutator: PlanMutator | None = None,
    ) -> None:
        self.registry = registry
        self.react_agent = react_agent
        self.on_react_step = on_react_step
        self.on_node_finished = on_node_finished
        self.plan_mutator = plan_mutator

    def execute(self, plan: Plan) -> list[NodeExecutionResult]:
        return asyncio.run(self.execute_async(plan))

    async def execute_async(self, plan: Plan) -> list[NodeExecutionResult]:
        results: list[NodeExecutionResult] = []
        completed: set[str] = set()
        failed: set[str] = set()
        skipped: set[str] = set()
        current_plan = plan

        while True:
            for node_id in current_plan.nodes_to_skip(
                completed=completed, failed=failed, skipped=skipped
            ):
                if node_id in skipped:
                    continue
                skipped.add(node_id)
                started_at = datetime.now(UTC)
                skipped_result = NodeExecutionResult(
                    node_id=node_id,
                    tool_result=ToolResult(
                        ok=False,
                        error="Skipped: dependency failed or was skipped",
                    ),
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                )
                results.append(skipped_result)
                self._notify_node_finished(current_plan, skipped_result)

            ready = current_plan.ready_nodes(
                completed=completed, failed=failed, skipped=skipped
            )
            if not ready:
                break

            batch = await asyncio.gather(
                *[self._execute_node_timed_async(node) for node in ready]
            )
            for node, (started_at, tool_result) in zip(ready, batch, strict=True):
                node_result = NodeExecutionResult(
                    node_id=node.id,
                    tool_result=tool_result,
                    started_at=started_at,
                    finished_at=datetime.now(UTC),
                )
                results.append(node_result)
                if tool_result.ok:
                    completed.add(node.id)
                else:
                    failed.add(node.id)
                current_plan = self._notify_node_finished(current_plan, node_result)

        return results

    def _notify_node_finished(self, plan: Plan, result: NodeExecutionResult) -> Plan:
        if self.on_node_finished is not None:
            self.on_node_finished(plan, result)
        if self.plan_mutator is not None:
            return self.plan_mutator.apply(plan, result)
        return plan

    async def _execute_node_timed_async(self, node: PlanNode) -> tuple[datetime, ToolResult]:
        started_at = datetime.now(UTC)
        if node.tool_name is None:
            return started_at, await asyncio.to_thread(self._execute_node, node)
        return started_at, await self._execute_node_async(node)

    def _execute_node_timed(self, node: PlanNode) -> tuple[datetime, ToolResult]:
        started_at = datetime.now(UTC)
        return started_at, self._execute_node(node)

    async def _execute_node_async(self, node: PlanNode) -> ToolResult:
        if node.tool_name is None:
            return self._execute_node(node)

        last_error: str = ""
        for attempt in range(max(0, node.max_retries) + 1):
            try:
                return await self.registry.run_async(node.tool_name, node.tool_args)
            except ToolExecutionError as exc:
                last_error = str(exc)
                if attempt < node.max_retries:
                    continue
        return ToolResult(
            ok=False,
            error=f"Failed after {node.max_retries + 1} attempt(s): {last_error}",
        )

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
