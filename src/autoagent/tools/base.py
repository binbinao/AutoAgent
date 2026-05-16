from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any

from autoagent.models import ToolResult


class ToolExecutionError(RuntimeError):
    """Raised when a tool cannot be executed safely or successfully."""


class BaseTool(ABC):
    name: str
    description: str

    @abstractmethod
    def run(self, args: dict[str, Any]) -> ToolResult:
        raise NotImplementedError

    async def run_async(self, args: dict[str, Any]) -> ToolResult:
        return await asyncio.to_thread(self.run, args)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, BaseTool] = {}

    @classmethod
    def with_tools(cls, tools: Iterable[BaseTool]) -> ToolRegistry:
        registry = cls()
        for tool in tools:
            registry.register(tool)
        return registry

    def register(self, tool: BaseTool) -> None:
        if tool.name in self._tools:
            raise ToolExecutionError(f"Tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def run(self, name: str, args: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolExecutionError(f"Unknown tool: {name}")
        return tool.run(args)

    async def run_async(self, name: str, args: dict[str, Any]) -> ToolResult:
        tool = self._tools.get(name)
        if tool is None:
            raise ToolExecutionError(f"Unknown tool: {name}")
        return await tool.run_async(args)

    @property
    def names(self) -> list[str]:
        return sorted(self._tools)


class EchoTool(BaseTool):
    name = "echo"
    description = "Return the provided arguments. Useful for dry-runs and tests."

    def run(self, args: dict[str, Any]) -> ToolResult:
        return ToolResult(ok=True, output=dict(args))
