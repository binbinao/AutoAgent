"""DAG scheduling: ready nodes, parallel batches, failure isolation."""

from __future__ import annotations

import asyncio

import pytest

from autoagent.dag.scheduler import run_plan_batches
from autoagent.executor import DAGExecutor
from autoagent.models import Plan, PlanNode, ToolResult
from autoagent.tools import EchoTool, ToolRegistry
from autoagent.tools.base import BaseTool, ToolExecutionError


def test_plan_ready_nodes_returns_only_unblocked_pending() -> None:
    plan = Plan(
        goal="g",
        nodes=[
            PlanNode(id="a", description="A", tool_name="echo", tool_args={"text": "a"}),
            PlanNode(
                id="b",
                description="B",
                tool_name="echo",
                tool_args={"text": "b"},
                dependencies=["a"],
            ),
            PlanNode(id="c", description="C", tool_name="echo", tool_args={"text": "c"}),
        ],
    )

    ready = plan.ready_nodes(completed=set(), failed=set(), skipped=set())

    assert {n.id for n in ready} == {"a", "c"}


def test_plan_ready_nodes_excludes_nodes_with_failed_dependency() -> None:
    plan = Plan(
        goal="g",
        nodes=[
            PlanNode(id="a", description="A", tool_name="echo"),
            PlanNode(id="b", description="B", tool_name="echo", dependencies=["a"]),
        ],
    )

    ready = plan.ready_nodes(completed=set(), failed={"a"}, skipped=set())

    assert ready == []


def test_plan_nodes_to_skip_when_dependency_failed() -> None:
    plan = Plan(
        goal="g",
        nodes=[
            PlanNode(id="a", description="A", tool_name="echo"),
            PlanNode(id="b", description="B", tool_name="echo", dependencies=["a"]),
            PlanNode(id="c", description="C", tool_name="echo"),
        ],
    )

    skip = plan.nodes_to_skip(failed={"a"}, skipped=set(), completed=set())

    assert skip == ["b"]


def test_plan_add_node_extends_graph() -> None:
    plan = Plan(
        goal="g",
        nodes=[PlanNode(id="a", description="A", tool_name="echo")],
    )

    extended = plan.add_node(
        PlanNode(id="b", description="B", tool_name="echo", dependencies=["a"])
    )

    assert len(extended.nodes) == 2
    assert extended.nodes[1].id == "b"


@pytest.mark.asyncio
async def test_run_plan_batches_executes_independent_nodes_in_parallel() -> None:
    order: list[str] = []

    class SlowEcho(BaseTool):
        name = "slow_echo"
        description = "slow"

        def run(self, args: dict) -> ToolResult:
            order.append(str(args["id"]))
            return ToolResult(ok=True, output={"id": args["id"]})

    registry = ToolRegistry.with_tools([SlowEcho()])
    executor = DAGExecutor(registry)
    plan = Plan(
        goal="parallel",
        nodes=[
            PlanNode(id="x", description="X", tool_name="slow_echo", tool_args={"id": "x"}),
            PlanNode(id="y", description="Y", tool_name="slow_echo", tool_args={"id": "y"}),
        ],
    )

    async def run_batch(nodes: list[PlanNode]) -> list:
        return await asyncio.gather(
            *[asyncio.to_thread(executor._execute_node, n) for n in nodes]
        )

    batches = await run_plan_batches(plan, execute_batch=run_batch)

    assert len(batches) == 1
    assert len(batches[0]) == 2
    assert set(order) == {"x", "y"}


def test_executor_skips_dependents_of_failed_node_but_runs_independent_branch() -> None:
    from typing import Any

    class FailTool(BaseTool):
        name = "fail"
        description = "fail"

        def run(self, args: dict[str, Any]) -> ToolResult:
            raise ToolExecutionError("boom")

    registry = ToolRegistry.with_tools([FailTool(), EchoTool()])
    executor = DAGExecutor(registry)
    plan = Plan(
        goal="branch",
        nodes=[
            PlanNode(id="bad", description="bad", tool_name="fail", max_retries=0),
            PlanNode(id="after_bad", description="after", tool_name="echo", dependencies=["bad"]),
            PlanNode(
                id="ok",
                description="ok",
                tool_name="echo",
                tool_args={"text": "fine"},
            ),
        ],
    )

    results = executor.execute(plan)
    by_id = {r.node_id: r for r in results}

    assert by_id["bad"].tool_result.ok is False
    assert by_id["after_bad"].tool_result.ok is False
    assert "skipped" in (by_id["after_bad"].tool_result.error or "").lower()
    assert by_id["ok"].tool_result.ok is True
    assert by_id["ok"].tool_result.output.get("text") == "fine"
