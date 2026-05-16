from pathlib import Path

import pytest

from autoagent.tools import EchoTool, FileReadTool, FileWriteTool, ToolExecutionError, ToolRegistry


def test_tool_registry_runs_registered_tool() -> None:
    registry = ToolRegistry()
    registry.register(EchoTool())

    result = registry.run("echo", {"text": "hello"})

    assert result.ok is True
    assert result.output == {"text": "hello"}


def test_tool_registry_rejects_unknown_tool() -> None:
    registry = ToolRegistry()

    with pytest.raises(ToolExecutionError, match="Unknown tool"):
        registry.run("missing", {})


def test_file_tools_read_and_write_inside_workspace(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    write_tool = FileWriteTool(workspace)
    read_tool = FileReadTool(workspace)

    write_result = write_tool.run({"path": "notes/report.md", "content": "# Report\n"})
    read_result = read_tool.run({"path": "notes/report.md"})

    assert write_result.ok is True
    assert read_result.output["content"] == "# Report\n"
    assert (workspace / "notes" / "report.md").read_text() == "# Report\n"


def test_file_tools_block_path_traversal(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    read_tool = FileReadTool(workspace)

    with pytest.raises(ToolExecutionError, match="outside workspace"):
        read_tool.run({"path": "../secret.txt"})
