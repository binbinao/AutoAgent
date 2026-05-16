from autoagent.executor import DAGExecutor
from autoagent.models import Plan, PlanNode, RunStatus
from autoagent.orchestrator import ManualApprover, Orchestrator, StaticPlanner
from autoagent.tools import EchoTool, ToolRegistry


def test_orchestrator_requires_approval_before_execution() -> None:
    plan = Plan(
        goal="summarize a topic",
        nodes=[
            PlanNode(
                id="step1",
                description="Echo topic",
                tool_name="echo",
                tool_args={"text": "AI"},
            )
        ],
    )
    orchestrator = Orchestrator(
        planner=StaticPlanner(plan),
        approver=ManualApprover(auto_approve=False),
        executor=DAGExecutor(ToolRegistry.with_tools([EchoTool()])),
    )

    run = orchestrator.plan("summarize a topic")

    assert run.status is RunStatus.AWAITING_APPROVAL
    assert run.results == []


def test_orchestrator_executes_approved_dag_in_order() -> None:
    plan = Plan(
        goal="two step task",
        nodes=[
            PlanNode(id="first", description="First", tool_name="echo", tool_args={"text": "1"}),
            PlanNode(
                id="second",
                description="Second",
                tool_name="echo",
                tool_args={"text": "2"},
                dependencies=["first"],
            ),
        ],
    )
    orchestrator = Orchestrator(
        planner=StaticPlanner(plan),
        approver=ManualApprover(auto_approve=False),
        executor=DAGExecutor(ToolRegistry.with_tools([EchoTool()])),
    )

    run = orchestrator.plan("two step task")
    completed = orchestrator.execute(run, approved=True)

    assert completed.status is RunStatus.COMPLETED
    assert [result.node_id for result in completed.results] == ["first", "second"]
    assert [result.tool_result.output["text"] for result in completed.results] == ["1", "2"]


def test_executor_retries_failing_tool_and_returns_error_result() -> None:
    """A node whose tool always raises should exhaust retries and yield ok=False."""
    from typing import Any

    from autoagent.models import ToolResult
    from autoagent.tools.base import BaseTool, ToolExecutionError

    class AlwaysFailTool(BaseTool):
        name = "always_fail"
        description = "Always raises."

        def run(self, args: dict[str, Any]) -> ToolResult:
            raise ToolExecutionError("intentional failure")

    registry = ToolRegistry.with_tools([AlwaysFailTool()])
    executor = DAGExecutor(registry)
    plan = Plan(
        goal="fail test",
        nodes=[PlanNode(id="t1", description="fail", tool_name="always_fail", max_retries=1)],
    )
    results = executor.execute(plan)

    assert results[0].tool_result.ok is False
    assert "attempt" in (results[0].tool_result.error or "").lower()


def test_executor_succeeds_on_second_attempt() -> None:
    """A tool that fails once then succeeds should produce ok=True."""
    from typing import Any

    from autoagent.models import ToolResult
    from autoagent.tools.base import BaseTool, ToolExecutionError

    class FlakyTool(BaseTool):
        name = "flaky"
        description = "Fails first, succeeds second."
        _calls = 0

        def run(self, args: dict[str, Any]) -> ToolResult:
            FlakyTool._calls += 1
            if FlakyTool._calls == 1:
                raise ToolExecutionError("first call fails")
            return ToolResult(ok=True, output={"msg": "ok"})

    registry = ToolRegistry.with_tools([FlakyTool()])
    executor = DAGExecutor(registry)
    plan = Plan(
        goal="flaky test",
        nodes=[PlanNode(id="t1", description="flaky", tool_name="flaky", max_retries=2)],
    )
    results = executor.execute(plan)

    assert results[0].tool_result.ok is True
