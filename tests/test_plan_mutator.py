from __future__ import annotations

from datetime import UTC, datetime

from autoagent.dag.plan_mutator import ExtendNodesMutator
from autoagent.executor import DAGExecutor
from autoagent.models import NodeExecutionResult, Plan, PlanNode, ToolResult
from autoagent.tools import EchoTool, ToolRegistry
from autoagent.tools.base import BaseTool, ToolExecutionError


class ExtendEchoTool(BaseTool):
    name = "extend_echo"
    description = "Echo and request plan extension."

    def run(self, args: dict) -> ToolResult:
        return ToolResult(
            ok=True,
            output={
                "text": str(args.get("text", "")),
                "extend_nodes": [
                    {
                        "id": "follow_up",
                        "description": "Follow-up step",
                        "tool_name": "echo",
                        "tool_args": {"text": "done"},
                        "dependencies": ["root"],
                    }
                ],
            },
        )


def test_extend_nodes_mutator_adds_nodes_from_tool_output() -> None:
    mutator = ExtendNodesMutator()
    plan = Plan(
        goal="g",
        nodes=[PlanNode(id="root", description="root", tool_name="extend_echo")],
    )
    result = NodeExecutionResult(
        node_id="root",
        tool_result=ToolResult(ok=True, output={"extend_nodes": [{"id": "n2", "description": "d", "tool_name": "echo"}]}),
    )

    extended = mutator.apply(plan, result)

    assert len(extended.nodes) == 2
    assert extended.nodes[1].id == "n2"


def test_executor_applies_mutator_during_run() -> None:
    registry = ToolRegistry.with_tools([ExtendEchoTool(), EchoTool()])
    executor = DAGExecutor(registry, plan_mutator=ExtendNodesMutator())
    plan = Plan(
        goal="dynamic",
        nodes=[PlanNode(id="root", description="r", tool_name="extend_echo", tool_args={"text": "x"})],
    )

    results = executor.execute(plan)

    assert len(results) == 2
    assert results[0].node_id == "root"
    assert results[1].node_id == "follow_up"
    assert results[1].tool_result.ok is True
