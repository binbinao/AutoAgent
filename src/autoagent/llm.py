from __future__ import annotations

import json
import re
from typing import Any

from litellm import completion

from autoagent.memory import SemanticMemory
from autoagent.models import Plan


class LiteLLMRouter:
    def __init__(self, default_model: str) -> None:
        self.default_model = default_model

    def complete(self, messages: list[dict[str, str]], *, model: str | None = None) -> str:
        response = completion(model=model or self.default_model, messages=messages)
        content = response.choices[0].message.content
        if content is None:
            return ""
        return str(content)


class LLMPlanner:
    def __init__(
        self,
        router: LiteLLMRouter,
        *,
        model: str | None = None,
        semantic: SemanticMemory | None = None,
    ) -> None:
        self.router = router
        self.model = model
        self.semantic = semantic

    def create_plan(self, goal: str) -> Plan:
        context_lines: list[str] = []
        if self.semantic is not None:
            context_lines = self.semantic.search(goal, limit=5)

        user_content = goal
        if context_lines:
            joined = "\n".join(f"- {line}" for line in context_lines)
            user_content = f"{goal}\n\nRelevant knowledge from past tasks:\n{joined}"

        prompt = (
            "Create a JSON execution plan for the goal. "
            "Return only JSON with shape: "
            '{"goal": str, "nodes": [{"id": str, "description": str, '
            '"tool_name": str|null, "tool_args": object, "dependencies": [str], '
            '"model": str|null}]}. '
            "Use tool_name null for steps that need multi-tool reasoning (ReAct). "
            "Available tools: echo, web.search, web.fetch, file.read, file.write, "
            "file.list, python.run, api.request, browser.snapshot."
        )
        content = self.router.complete(
            [
                {"role": "system", "content": prompt},
                {"role": "user", "content": user_content},
            ],
            model=self.model,
        )
        data: dict[str, Any] = json.loads(_extract_json(content))
        data.setdefault("goal", goal)
        return Plan.model_validate(data)


def _extract_json(text: str) -> str:
    """Strip markdown fences if the model wrapped JSON."""
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", stripped)
    if fence:
        return fence.group(1).strip()
    return stripped
