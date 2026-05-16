from __future__ import annotations

from typing import Any

from autoagent.models import Plan, PlanNode
from autoagent.react import ReActAgent
from autoagent.tools import EchoTool, ToolRegistry


class FakeRouter:
    """Deterministic router that returns pre-configured responses in order."""

    def __init__(self, responses: list[str]) -> None:
        self._iter = iter(responses)

    def complete(self, messages: list[dict[str, Any]], *, model: str | None = None) -> str:
        del messages, model
        return next(self._iter)


def make_agent(responses: list[str], max_steps: int = 10) -> ReActAgent:
    registry = ToolRegistry.with_tools([EchoTool()])
    return ReActAgent(FakeRouter(responses), registry, max_steps=max_steps)  # type: ignore[arg-type]


def test_react_agent_returns_plain_text_as_final_answer() -> None:
    agent = make_agent(["The answer is 42."])

    result = agent.run("What is the answer?")

    assert result.ok is True
    assert result.output["answer"] == "The answer is 42."
    assert result.output["steps"] == 1


def test_react_agent_calls_tool_then_answers() -> None:
    action = '{"action": {"tool": "echo", "args": {"text": "ping"}}}'
    agent = make_agent([action, "Done. Echo returned ping."])

    result = agent.run("Echo ping then summarise.")

    assert result.ok is True
    assert "Done" in result.output["answer"]
    assert result.output["steps"] == 2


def test_react_agent_exceeds_max_steps() -> None:
    action = '{"action": {"tool": "echo", "args": {"text": "x"}}}'
    agent = make_agent([action] * 5, max_steps=3)

    result = agent.run("Keep echoing forever.")

    assert result.ok is False
    assert result.error is not None
    assert "max_steps" in result.error


def test_react_agent_records_tool_error_as_observation() -> None:
    """If a tool raises, the agent continues with the error as an Observation."""
    final_answer = "I encountered an error but recovered."
    missing_action = '{"action": {"tool": "no_such_tool", "args": {}}}'
    agent = make_agent([missing_action, final_answer])

    result = agent.run("Try a missing tool.")

    assert result.ok is True
    assert "recovered" in result.output["answer"]


def test_react_agent_parse_action_valid() -> None:
    text = 'Thinking… {"action": {"tool": "echo", "args": {"x": 1}}} done'
    action = ReActAgent._parse_action(text)

    assert action == {"tool": "echo", "args": {"x": 1}}


def test_react_agent_parse_action_none_when_no_block() -> None:
    assert ReActAgent._parse_action("Plain text with no JSON.") is None


def test_react_agent_parse_action_none_on_malformed_json() -> None:
    assert ReActAgent._parse_action('{"action": {broken}}') is None


def test_executor_uses_react_agent_for_node_without_tool_name() -> None:
    from autoagent.executor import DAGExecutor

    registry = ToolRegistry.with_tools([EchoTool()])
    agent = ReActAgent(FakeRouter(["Final answer."]), registry, max_steps=1)  # type: ignore[arg-type]
    executor = DAGExecutor(registry, react_agent=agent)

    plan = Plan(
        goal="use react",
        nodes=[PlanNode(id="t1", description="summarise something")],  # tool_name=None
    )
    results = executor.execute(plan)

    assert len(results) == 1
    assert results[0].tool_result.ok is True


def test_executor_without_react_agent_returns_error_for_tool_name_none() -> None:
    from autoagent.executor import DAGExecutor

    registry = ToolRegistry.with_tools([EchoTool()])
    executor = DAGExecutor(registry)  # no react_agent

    plan = Plan(
        goal="will fail",
        nodes=[PlanNode(id="t1", description="needs react")],  # tool_name=None
    )
    results = executor.execute(plan)

    assert results[0].tool_result.ok is False
    assert results[0].tool_result.error is not None
