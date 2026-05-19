from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from autoagent.dag.plan_mutator import PlanMutator
from autoagent.models import NodeExecutionResult, Plan, PlanNode, ToolResult
from autoagent.report import (
    ReportSynthesizer,
    format_execution_context,
    prepare_file_write_tool_args,
)
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
        report_synthesizer: ReportSynthesizer | None = None,
        workspace: Path | str | None = None,
    ) -> None:
        self.registry = registry
        self.react_agent = react_agent
        self.on_react_step = on_react_step
        self.on_node_finished = on_node_finished
        self.plan_mutator = plan_mutator
        self.report_synthesizer = report_synthesizer
        self.workspace = Path(workspace or ".")
        self._completed_results: dict[str, ToolResult] = {}
        self._node_results: dict[str, ToolResult] = {}
        self._plan_goal = ""

    def execute(self, plan: Plan) -> list[NodeExecutionResult]:
        return asyncio.run(self.execute_async(plan))

    async def execute_async(self, plan: Plan) -> list[NodeExecutionResult]:
        self._completed_results = {}
        self._node_results = {}
        self._plan_goal = plan.goal
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
                self._record_node_result(node_id, skipped_result.tool_result)
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
                self._record_node_result(node.id, tool_result)
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

        tool_args = (
            self._prepare_file_write_args(node)
            if node.tool_name == "file.write"
            else node.tool_args
        )

        last_error: str = ""
        for attempt in range(max(0, node.max_retries) + 1):
            try:
                return await self.registry.run_async(node.tool_name, tool_args)
            except ToolExecutionError as exc:
                last_error = str(exc)
                if attempt < node.max_retries:
                    continue
        return ToolResult(
            ok=False,
            error=f"Failed after {node.max_retries + 1} attempt(s): {last_error}",
        )

    def _record_node_result(self, node_id: str, tool_result: ToolResult) -> None:
        self._node_results[node_id] = tool_result
        if tool_result.ok:
            self._completed_results[node_id] = tool_result

    def _react_memory_context(self, node: PlanNode) -> str:
        if not node.dependencies:
            return ""
        return format_execution_context(self._node_results, node.dependencies)

    def _execute_node(self, node: PlanNode) -> ToolResult:
        if node.tool_name is None:
            if self.react_agent is not None:
                model = node.model
                memory_context = self._react_memory_context(node)
                if self.on_react_step is not None:
                    return self.react_agent.run(
                        node.description,
                        model=model,
                        on_step=self.on_react_step,
                        memory_context=memory_context,
                    )
                return self.react_agent.run(
                    node.description,
                    model=model,
                    memory_context=memory_context,
                )
            return ToolResult(
                ok=False,
                error="No ReAct agent configured for a node without tool_name",
            )

        tool_args = (
            self._prepare_file_write_args(node)
            if node.tool_name == "file.write"
            else node.tool_args
        )

        last_error: str = ""
        for attempt in range(max(0, node.max_retries) + 1):
            try:
                return self.registry.run(node.tool_name, tool_args)
            except ToolExecutionError as exc:
                last_error = str(exc)
                if attempt < node.max_retries:
                    continue
        return ToolResult(
            ok=False,
            error=f"Failed after {node.max_retries + 1} attempt(s): {last_error}",
        )

    def _prepare_file_write_args(self, node: PlanNode) -> dict[str, object]:
        return prepare_file_write_tool_args(
            node.tool_args,
            goal=node.description or self._plan_goal,
            results_by_id=self._completed_results,
            dependencies=node.dependencies,
            synthesizer=self.report_synthesizer,
            workspace=self.workspace,
        )
