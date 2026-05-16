from __future__ import annotations

from pathlib import Path
from typing import Any

from autoagent.models import ToolResult
from autoagent.tools.base import BaseTool, ToolExecutionError


def resolve_workspace_path(workspace: Path, raw_path: str) -> Path:
    root = workspace.expanduser().resolve()
    target = (root / raw_path).resolve()
    try:
        target.relative_to(root)
    except ValueError as exc:
        raise ToolExecutionError(f"Path is outside workspace: {raw_path}") from exc
    return target


class FileReadTool(BaseTool):
    name = "file.read"
    description = "Read a UTF-8 text file within the configured workspace."

    def __init__(self, workspace: Path | str) -> None:
        self.workspace = Path(workspace)

    def run(self, args: dict[str, Any]) -> ToolResult:
        raw_path = str(args.get("path", ""))
        if not raw_path:
            raise ToolExecutionError("Missing required argument: path")

        path = resolve_workspace_path(self.workspace, raw_path)
        try:
            content = path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise ToolExecutionError(f"File not found: {raw_path}") from exc
        return ToolResult(output={"path": raw_path, "content": content})


class FileWriteTool(BaseTool):
    name = "file.write"
    description = "Write a UTF-8 text file within the configured workspace."

    def __init__(self, workspace: Path | str) -> None:
        self.workspace = Path(workspace)

    def run(self, args: dict[str, Any]) -> ToolResult:
        raw_path = str(args.get("path", ""))
        content = str(args.get("content", ""))
        if not raw_path:
            raise ToolExecutionError("Missing required argument: path")

        path = resolve_workspace_path(self.workspace, raw_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return ToolResult(output={"path": raw_path, "bytes": len(content.encode("utf-8"))})


class FileListTool(BaseTool):
    name = "file.list"
    description = "List files below a directory within the configured workspace."

    def __init__(self, workspace: Path | str) -> None:
        self.workspace = Path(workspace)

    def run(self, args: dict[str, Any]) -> ToolResult:
        raw_path = str(args.get("path", "."))
        path = resolve_workspace_path(self.workspace, raw_path)
        if not path.exists():
            raise ToolExecutionError(f"Directory not found: {raw_path}")
        if not path.is_dir():
            raise ToolExecutionError(f"Path is not a directory: {raw_path}")

        files = [
            str(child.relative_to(self.workspace.resolve())) for child in sorted(path.iterdir())
        ]
        return ToolResult(output={"path": raw_path, "entries": files})
