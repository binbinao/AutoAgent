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


def test_plan_allows_partial_dependencies_only_for_sink_react_nodes() -> None:
    plan = Plan(
        goal="g",
        nodes=[
            PlanNode(id="a", description="a", tool_name="echo"),
            PlanNode(
                id="fetch_ok",
                description="ok",
                tool_name="echo",
                tool_args={"text": "data"},
                dependencies=["a"],
            ),
            PlanNode(id="fetch_bad", description="bad", tool_name="echo", dependencies=["a"]),
            PlanNode(id="mid", description="mid", tool_name=None, dependencies=["fetch_bad"]),
            PlanNode(
                id="sink",
                description="sink",
                tool_name=None,
                dependencies=["fetch_ok", "fetch_bad", "mid"],
            ),
        ],
    )

    assert plan.allows_partial_dependencies(plan.node_map()["mid"]) is False
    assert plan.allows_partial_dependencies(plan.node_map()["sink"]) is True


def test_plan_ready_nodes_runs_sink_synthesis_when_some_deps_failed() -> None:
    plan = Plan(
        goal="research",
        nodes=[
            PlanNode(
                id="fetch_ok",
                description="ok",
                tool_name="echo",
                tool_args={"text": "ok-data"},
            ),
            PlanNode(id="fetch_bad", description="bad", tool_name="echo", max_retries=0),
            PlanNode(
                id="synthesize",
                description="synthesize",
                tool_name=None,
                dependencies=["fetch_ok", "fetch_bad"],
            ),
        ],
    )

    ready = plan.ready_nodes(
        completed={"fetch_ok"},
        failed={"fetch_bad"},
        skipped=set(),
    )

    assert [n.id for n in ready] == ["synthesize"]


def test_plan_nodes_to_skip_skips_sink_synthesis_only_when_all_deps_failed() -> None:
    plan = Plan(
        goal="research",
        nodes=[
            PlanNode(id="fetch_bad", description="bad", tool_name="echo"),
            PlanNode(
                id="synthesize",
                description="synthesize",
                tool_name=None,
                dependencies=["fetch_bad"],
            ),
        ],
    )

    assert plan.nodes_to_skip(failed={"fetch_bad"}, skipped=set(), completed=set()) == [
        "synthesize"
    ]

    plan2 = Plan(
        goal="research",
        nodes=[
            PlanNode(
                id="fetch_ok",
                description="ok",
                tool_name="echo",
                tool_args={"text": "x"},
            ),
            PlanNode(id="fetch_bad", description="bad", tool_name="echo"),
            PlanNode(
                id="synthesize",
                description="synthesize",
                tool_name=None,
                dependencies=["fetch_ok", "fetch_bad"],
            ),
        ],
    )

    assert (
        plan2.nodes_to_skip(
            completed={"fetch_ok"},
            failed={"fetch_bad"},
            skipped=set(),
        )
        == []
    )


def test_executor_runs_sink_synthesis_when_some_fetch_deps_failed() -> None:
    from typing import Any

    class FailTool(BaseTool):
        name = "fail"
        description = "fail"

        def run(self, args: dict[str, Any]) -> ToolResult:
            raise ToolExecutionError("fetch failed")

    class CaptureRouter:
        def __init__(self) -> None:
            self.memory_context = ""

        def complete(self, messages: list[dict[str, str]], *, model: str | None = None) -> str:
            del model
            self.memory_context = messages[0]["content"]
            return "Synthesis complete."

    from autoagent.react import ReActAgent

    registry = ToolRegistry.with_tools([FailTool(), EchoTool()])
    router = CaptureRouter()
    agent = ReActAgent(router, registry, max_steps=1)  # type: ignore[arg-type]
    executor = DAGExecutor(registry, react_agent=agent)
    plan = Plan(
        goal="partial research",
        nodes=[
            PlanNode(
                id="fetch_ok",
                description="ok",
                tool_name="echo",
                tool_args={"text": "source-body"},
            ),
            PlanNode(id="fetch_bad", description="bad", tool_name="fail", max_retries=0),
            PlanNode(
                id="synthesize",
                description="Write report from partial sources",
                tool_name=None,
                dependencies=["fetch_ok", "fetch_bad"],
            ),
        ],
    )

    results = executor.execute(plan)
    by_id = {r.node_id: r for r in results}

    assert by_id["fetch_ok"].tool_result.ok is True
    assert by_id["fetch_bad"].tool_result.ok is False
    assert by_id["synthesize"].tool_result.ok is True
    assert "skipped" not in (by_id["synthesize"].tool_result.error or "").lower()
    assert "source-body" in router.memory_context
    assert "fetch_bad" in router.memory_context
    assert "failed" in router.memory_context.lower()


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
