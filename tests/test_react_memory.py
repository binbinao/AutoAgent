from __future__ import annotations

from autoagent.memory import WorkingMemory
from autoagent.react import ReActAgent
from autoagent.tools import EchoTool, ToolRegistry
from autoagent.utils.tokens import fits_in_context


class FakeRouter:
    def __init__(self, responses: list[str]) -> None:
        self.responses = responses
        self.calls = 0

    def complete(self, messages: list[dict[str, str]], *, model: str | None = None) -> str:
        del messages, model
        text = self.responses[self.calls]
        self.calls += 1
        return text


def test_react_trims_messages_when_context_exceeded() -> None:
    registry = ToolRegistry.with_tools([EchoTool()])
    router = FakeRouter(["Final answer without JSON."])
    agent = ReActAgent(router, registry, max_steps=1, max_context_tokens=50)  # type: ignore[arg-type]
    long_task = "x" * 500
    result = agent.run(long_task)
    assert result.ok is True


def test_react_on_step_callback_receives_action_and_observation() -> None:
    registry = ToolRegistry.with_tools([EchoTool()])
    responses = [
        '{"action": {"tool": "echo", "args": {"text": "hi"}}}',
        "done",
    ]
    router = FakeRouter(responses)
    steps: list[tuple[str, str, str]] = []

    def on_step(thought: str, action: str, observation: str) -> None:
        steps.append((thought, action, observation))

    agent = ReActAgent(router, registry, max_steps=5)  # type: ignore[arg-type]
    agent.run("task", on_step=on_step)

    assert len(steps) >= 1
    assert "echo" in steps[0][1]


def test_working_memory_as_messages() -> None:
    wm = WorkingMemory(max_items=2)
    wm.add(role="user", content="a")
    wm.add(role="assistant", content="b")
    wm.add(role="user", content="c")
    assert len(wm.as_messages()) == 2
    assert fits_in_context(wm.as_messages(), max_tokens=1000)
