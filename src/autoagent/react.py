"""ReAct (Reason + Act) agent loop."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from autoagent.llm import LiteLLMRouter
from autoagent.memory import WorkingMemory
from autoagent.models import ToolResult
from autoagent.prompts import REACT_SYSTEM_PROMPT
from autoagent.tools.base import ToolExecutionError, ToolRegistry
from autoagent.utils.tokens import fits_in_context, truncate_to_tokens

ReActStepCallback = Callable[[str, str, str], None]


class ReActAgent:
    """Runs a Thought → Action → Observation loop until a final answer or timeout."""

    def __init__(
        self,
        router: LiteLLMRouter,
        registry: ToolRegistry,
        *,
        max_steps: int = 10,
        model: str | None = None,
        max_context_tokens: int = 8_192,
        working_memory: WorkingMemory | None = None,
    ) -> None:
        self.router = router
        self.registry = registry
        self.max_steps = max_steps
        self.model = model
        self.max_context_tokens = max_context_tokens
        self.working_memory = working_memory or WorkingMemory(max_items=40)

    def run(
        self,
        task: str,
        *,
        model: str | None = None,
        on_step: ReActStepCallback | None = None,
        memory_context: str = "",
    ) -> ToolResult:
        tools_desc = "\n".join(f"  - {name}" for name in self.registry.names)
        memory_block = memory_context.strip()
        if memory_block:
            memory_block = f"Relevant context from memory:\n{memory_block}\n"
        system = REACT_SYSTEM_PROMPT.format(tools=tools_desc, memory_context=memory_block)
        messages: list[dict[str, str]] = [
            {"role": "system", "content": system},
            {"role": "user", "content": task},
        ]
        self.working_memory.add(role="user", content=task)

        node_model = model or self.model

        for step in range(self.max_steps):
            trimmed = self._trim_messages(messages)
            response = self.router.complete(trimmed, model=node_model)
            messages.append({"role": "assistant", "content": response})
            self.working_memory.add(role="assistant", content=response)

            action = self._parse_action(response)
            if action is None:
                if on_step is not None:
                    on_step(response, "", "")
                return ToolResult(
                    ok=True,
                    output={"answer": response, "steps": step + 1},
                )

            tool_name = str(action.get("tool", ""))
            tool_args: dict[str, Any] = dict(action.get("args", {}))
            action_repr = json.dumps({"tool": tool_name, "args": tool_args}, ensure_ascii=False)

            try:
                result = self.registry.run(tool_name, tool_args)
                observation = json.dumps(result.output, ensure_ascii=False)
            except ToolExecutionError as exc:
                observation = f"Error: {exc}"

            if on_step is not None:
                on_step(response, action_repr, observation)

            messages.append({"role": "user", "content": f"Observation: {observation}"})
            self.working_memory.add(role="user", content=f"Observation: {observation}")

        return ToolResult(
            ok=False,
            output={},
            error=f"Exceeded max_steps ({self.max_steps}) without a final answer",
        )

    def _trim_messages(self, messages: list[dict[str, str]]) -> list[dict[str, str]]:
        if fits_in_context(messages, self.max_context_tokens):
            return messages
        system = messages[0]
        rest = messages[1:]
        while rest and not fits_in_context([system, *rest], self.max_context_tokens):
            rest = rest[1:]
        if not rest:
            rest = [
                {
                    "role": "user",
                    "content": truncate_to_tokens(
                        messages[-1].get("content", ""),
                        self.max_context_tokens // 2,
                    ),
                }
            ]
        return [system, *rest]

    @staticmethod
    def _parse_action(text: str) -> dict[str, Any] | None:
        start = text.find('{"action"')
        if start == -1:
            return None

        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data: dict[str, Any] = json.loads(text[start : i + 1])
                        action = data.get("action")
                        if isinstance(action, dict):
                            return action
                    except json.JSONDecodeError:
                        pass
                    return None
        return None


__all__ = ["ReActAgent", "ReActStepCallback"]
