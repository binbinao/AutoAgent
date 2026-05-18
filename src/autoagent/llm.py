from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from litellm import completion

from autoagent.memory import SemanticMemory
from autoagent.models import Plan
from autoagent.plan_enrichment import enrich_plan_data
from autoagent.prompts import PLANNER_SYSTEM_PROMPT

_dotenv_loaded = False


def resolve_litellm_model(requested: str | None, default_model: str) -> str:
    """Pick the LiteLLM model id to call.

    Planner JSON may set bare names like ``gpt-4``; those lack a provider prefix and
    are ignored in favor of ``default_model``.
    """
    if not requested:
        return default_model
    if "/" not in requested:
        return default_model
    return requested


def _coerce_plan_node_models(data: dict[str, Any], default_model: str) -> None:
    """Drop per-node model overrides that do not match the configured default."""
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        return
    for node in nodes:
        if not isinstance(node, dict):
            continue
        if node.get("model") not in (None, default_model):
            node["model"] = None


def _ensure_dotenv() -> None:
    global _dotenv_loaded
    if not _dotenv_loaded:
        load_dotenv(Path.cwd() / ".env", override=False)
        _dotenv_loaded = True


class LiteLLMRouter:
    def __init__(self, default_model: str) -> None:
        self.default_model = default_model

    def complete(self, messages: list[dict[str, str]], *, model: str | None = None) -> str:
        _ensure_dotenv()
        resolved = resolve_litellm_model(model, self.default_model)
        response = completion(model=resolved, messages=messages)
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

        content = self.router.complete(
            [
                {"role": "system", "content": PLANNER_SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            model=self.model,
        )
        data: dict[str, Any] = json.loads(_extract_json(content))
        data.setdefault("goal", goal)
        _coerce_plan_node_models(data, self.router.default_model)
        enrich_plan_data(data, goal)
        return Plan.model_validate(data)


def _extract_json(text: str) -> str:
    """Strip markdown fences if the model wrapped JSON."""
    stripped = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", stripped)
    if fence:
        return fence.group(1).strip()
    return stripped
