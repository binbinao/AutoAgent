"""Named tool presets and registry construction."""

from __future__ import annotations

from collections.abc import Iterable
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from autoagent.tools.api import ApiRequestTool
from autoagent.tools.base import BaseTool, EchoTool, ToolExecutionError, ToolRegistry
from autoagent.tools.browser import BrowserSnapshotTool
from autoagent.tools.file_tools import FileListTool, FileReadTool, FileWriteTool
from autoagent.tools.python_sandbox import PythonSandboxTool
from autoagent.tools.web import WebFetchTool, WebSearchTool

if TYPE_CHECKING:
    from autoagent.config import AgentSettings
    from autoagent.task_mode import TaskMode

BROWSER_TOOL = "browser.snapshot"

PRESET_TOOL_NAMES: dict[str, tuple[str, ...]] = {
    "minimal": (
        "echo",
        "file.read",
        "file.write",
        "file.list",
    ),
    "web-research": (
        "web.search",
        "web.fetch",
        "file.read",
        "file.write",
        "file.list",
    ),
    "full": (
        "echo",
        "file.read",
        "file.write",
        "file.list",
        "web.search",
        "web.fetch",
        "python.run",
        "api.request",
    ),
}

PRESET_ALIASES: dict[str, str] = {
    "web": "web-research",
    "research": "web-research",
    "default": "web-research",
}


class ToolPreset(StrEnum):
    MINIMAL = "minimal"
    WEB_RESEARCH = "web-research"
    FULL = "full"


def playwright_available() -> bool:
    try:
        import playwright  # noqa: F401

        return True
    except ImportError:
        return False


def parse_tool_preset(value: str | ToolPreset | None, *, default: str = "web-research") -> str:
    if value is None:
        return default
    if isinstance(value, ToolPreset):
        return value.value
    normalized = value.strip().lower()
    if normalized in PRESET_ALIASES:
        normalized = PRESET_ALIASES[normalized]
    if normalized in PRESET_TOOL_NAMES:
        return normalized
    allowed = ", ".join(sorted(PRESET_TOOL_NAMES))
    raise ValueError(f"Unknown tool preset {value!r}; use one of: {allowed}")


def parse_enabled_tools(value: str | None) -> list[str] | None:
    if value is None or not str(value).strip():
        return None
    names = [part.strip() for part in str(value).split(",") if part.strip()]
    if not names:
        return None
    _validate_tool_names(names)
    return names


def list_presets() -> list[dict[str, str | tuple[str, ...]]]:
    return [
        {
            "id": preset_id,
            "tools": PRESET_TOOL_NAMES[preset_id],
            "includes_browser_when_available": preset_id in ("web-research", "full"),
        }
        for preset_id in PRESET_TOOL_NAMES
    ]


def preset_for_task_mode(task_mode: TaskMode | None) -> str | None:
    if task_mode is None:
        return None
    from autoagent.task_mode import TaskMode

    if task_mode is TaskMode.QUICK:
        return ToolPreset.MINIMAL.value
    return ToolPreset.WEB_RESEARCH.value


def resolve_tool_names(
    settings: AgentSettings,
    *,
    preset: str | ToolPreset | None = None,
    task_mode: TaskMode | None = None,
) -> list[str]:
    """Resolve enabled tool names: explicit list > CLI preset > config preset > task mode."""
    explicit = parse_enabled_tools(settings.enabled_tools)
    if explicit is not None:
        return explicit

    preset_id = preset or settings.default_tool_preset or preset_for_task_mode(task_mode)
    preset_id = parse_tool_preset(preset_id)

    names = list(PRESET_TOOL_NAMES[preset_id])
    browser_preset = preset_id in (ToolPreset.WEB_RESEARCH.value, ToolPreset.FULL.value)
    if browser_preset and playwright_available() and BROWSER_TOOL not in names:
        names.append(BROWSER_TOOL)
    return names


def _validate_tool_names(names: Iterable[str]) -> None:
    known = set(_all_known_tool_names())
    unknown = [name for name in names if name not in known]
    if unknown:
        raise ValueError(f"Unknown tool names: {', '.join(unknown)}")


def _all_known_tool_names() -> tuple[str, ...]:
    base = set(PRESET_TOOL_NAMES[ToolPreset.FULL.value])
    base.add(BROWSER_TOOL)
    return tuple(sorted(base))


def create_tool(name: str, workspace: Path, settings: AgentSettings) -> BaseTool:
    if name == "echo":
        return EchoTool()
    if name == "file.read":
        return FileReadTool(workspace)
    if name == "file.write":
        return FileWriteTool(workspace)
    if name == "file.list":
        return FileListTool(workspace)
    if name == "web.search":
        return WebSearchTool()
    if name == "web.fetch":
        return WebFetchTool()
    if name == "python.run":
        return PythonSandboxTool(
            workspace,
            timeout_seconds=settings.python_timeout_seconds,
            use_docker=settings.use_docker_sandbox,
        )
    if name == "api.request":
        return ApiRequestTool()
    if name == BROWSER_TOOL:
        return BrowserSnapshotTool()
    raise ToolExecutionError(f"Unknown tool: {name}")


def build_registry_from_settings(
    workspace: Path,
    settings: AgentSettings,
    *,
    preset: str | ToolPreset | None = None,
    task_mode: TaskMode | None = None,
) -> ToolRegistry:
    names = resolve_tool_names(settings, preset=preset, task_mode=task_mode)
    tools = [create_tool(name, workspace, settings) for name in names]
    return ToolRegistry.with_tools(tools)
