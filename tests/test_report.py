from __future__ import annotations

from pathlib import Path

from autoagent.executor import DAGExecutor
from autoagent.models import NodeExecutionResult, Plan, PlanNode, ToolResult
from autoagent.report import (
    MIN_REPORT_BYTES,
    ensure_run_report,
    find_substantial_report_path,
    format_execution_context,
    prepare_file_write_tool_args,
)
from autoagent.tools import EchoTool, ToolRegistry
from autoagent.tools.file_tools import FileWriteTool


def test_format_execution_context_includes_fetch_text() -> None:
    results = {
        "fetch": ToolResult(ok=True, output={"url": "https://x", "text": "Agent patterns"}),
        "search": ToolResult(ok=True, output={"results": [{"title": "t", "url": "u"}]}),
    }
    text = format_execution_context(results, ["fetch", "search"])
    assert "Agent patterns" in text
    assert "fetch" in text
    assert "[t](u)" in text


def test_find_substantial_report_path_detects_written_file(tmp_path: Path) -> None:
    report = tmp_path / "out.md"
    report.write_text("x" * MIN_REPORT_BYTES, encoding="utf-8")
    results = [
        NodeExecutionResult(
            node_id="write",
            tool_result=ToolResult(
                ok=True,
                output={"path": "out.md", "bytes": report.stat().st_size},
            ),
        )
    ]
    found = find_substantial_report_path(results, tmp_path)
    assert found == report.resolve()


def test_prepare_file_write_fills_empty_content(tmp_path: Path) -> None:
    prior = {
        "research": ToolResult(ok=True, output={"text": "Findings about engineering agents."}),
    }

    def fake_synth(task: str, context: str) -> str:
        assert "engineering" in context
        return f"# Report\n\n{task}\n"

    args = prepare_file_write_tool_args(
        {"path": "reports/test.md", "content": ""},
        goal="Study agents",
        results_by_id=prior,
        dependencies=["research"],
        synthesizer=fake_synth,
        workspace=tmp_path,
    )
    assert args["content"].startswith("# Report")
    assert args["path"] == "reports/test.md"


def test_ensure_run_report_writes_fallback_without_existing_file(tmp_path: Path) -> None:
    results = [
        NodeExecutionResult(
            node_id="fetch",
            tool_result=ToolResult(ok=True, output={"text": "A" * MIN_REPORT_BYTES}),
        )
    ]
    path = ensure_run_report(
        goal="Research topic",
        run_id="abc12345-0000-0000-0000-000000000000",
        results=results,
        workspace=tmp_path,
        router=None,
    )
    assert path is not None
    assert path.is_file()
    assert len(path.read_text(encoding="utf-8")) >= MIN_REPORT_BYTES


def test_executor_fills_empty_file_write_at_runtime(tmp_path: Path) -> None:
    registry = ToolRegistry.with_tools([EchoTool(), FileWriteTool(tmp_path)])

    def synth(task: str, context: str) -> str:
        return f"Synthesized: {context[:40]}"

    executor = DAGExecutor(registry, report_synthesizer=synth)
    plan = Plan(
        goal="Write report",
        nodes=[
            PlanNode(
                id="gather",
                description="gather",
                tool_name="echo",
                tool_args={"text": "raw research notes"},
            ),
            PlanNode(
                id="save",
                description="Write final report",
                tool_name="file.write",
                tool_args={"path": "final.md", "content": ""},
                dependencies=["gather"],
            ),
        ],
    )
    results = executor.execute(plan)
    assert results[-1].tool_result.ok
    written = tmp_path / "final.md"
    assert written.is_file()
    assert "Synthesized" in written.read_text(encoding="utf-8")
