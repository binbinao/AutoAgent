from __future__ import annotations

from pathlib import Path

import pytest

from autoagent.cli.app import build_registry
from autoagent.config import AgentSettings
from autoagent.task_mode import TaskMode
from autoagent.tools.presets import (
    parse_tool_preset,
    resolve_tool_names,
)


def _settings(tmp_path: Path, **kwargs: object) -> AgentSettings:
    return AgentSettings(
        workspace=tmp_path,
        python_timeout_seconds=1,
        use_docker_sandbox=False,
        **kwargs,
    )


def test_parse_tool_preset_aliases() -> None:
    assert parse_tool_preset("web") == "web-research"
    assert parse_tool_preset("research") == "web-research"


def test_parse_tool_preset_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown tool preset"):
        parse_tool_preset("bogus")


def test_minimal_preset_excludes_web_and_python(tmp_path: Path) -> None:
    settings = _settings(tmp_path, default_tool_preset="minimal")
    names = resolve_tool_names(settings, task_mode=TaskMode.QUICK)
    assert "echo" in names
    assert "file.read" in names
    assert "web.search" not in names
    assert "python.run" not in names


def test_web_research_preset_includes_web_tools(tmp_path: Path) -> None:
    settings = _settings(tmp_path, default_tool_preset="web-research")
    names = resolve_tool_names(settings, task_mode=TaskMode.RESEARCH)
    assert "web.search" in names
    assert "web.fetch" in names
    assert "python.run" not in names


def test_full_preset_includes_python_and_api(tmp_path: Path) -> None:
    settings = _settings(tmp_path, default_tool_preset="full")
    names = resolve_tool_names(settings)
    assert "python.run" in names
    assert "api.request" in names


def test_enabled_tools_override_preset(tmp_path: Path) -> None:
    settings = _settings(tmp_path, enabled_tools="echo,file.read")
    names = resolve_tool_names(settings, preset="full")
    assert names == ["echo", "file.read"]


def test_task_mode_maps_to_preset_when_unset(tmp_path: Path) -> None:
    settings = _settings(tmp_path, default_tool_preset="")
    quick = resolve_tool_names(settings, task_mode=TaskMode.QUICK)
    research = resolve_tool_names(settings, task_mode=TaskMode.RESEARCH)
    assert "web.search" not in quick
    assert "web.search" in research


def test_build_registry_full_has_python(tmp_path: Path) -> None:
    settings = _settings(tmp_path, default_tool_preset="full")
    registry = build_registry(tmp_path, settings, tool_preset="full")
    assert "python.run" in registry.names


def test_build_registry_web_research_lacks_python(tmp_path: Path) -> None:
    settings = _settings(tmp_path)
    registry = build_registry(
        tmp_path,
        settings,
        tool_preset="web-research",
        task_mode=TaskMode.RESEARCH,
    )
    assert "web.search" in registry.names
    assert "python.run" not in registry.names
