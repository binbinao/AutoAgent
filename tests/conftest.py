"""Shared pytest fixtures for AutoAgent tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from autoagent.config import AgentSettings
from autoagent.executor import DAGExecutor
from autoagent.orchestrator import HeuristicPlanner, ManualApprover, Orchestrator
from autoagent.tools import EchoTool, ToolRegistry


@pytest.fixture()
def tmp_registry() -> ToolRegistry:
    return ToolRegistry.with_tools([EchoTool()])


@pytest.fixture()
def tmp_settings(tmp_path: Path) -> AgentSettings:
    return AgentSettings(
        workspace=tmp_path,
        memory_path=tmp_path / ".autoagent" / "memory.db",
        auto_approve=True,
    )


@pytest.fixture()
def auto_orchestrator(tmp_registry: ToolRegistry) -> Orchestrator:
    return Orchestrator(
        planner=HeuristicPlanner(),
        approver=ManualApprover(auto_approve=True),
        executor=DAGExecutor(tmp_registry),
    )
