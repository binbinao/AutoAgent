"""Research report synthesis and persistence for DAG runs."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from pathlib import Path
from typing import Any

from autoagent.llm import LiteLLMRouter
from autoagent.models import NodeExecutionResult, ToolResult
from autoagent.output_locale import OutputLocale
from autoagent.prompts import report_synthesis_prompt
from autoagent.task_mode import TaskMode
from autoagent.tools.base import ToolExecutionError
from autoagent.tools.file_tools import resolve_workspace_path

MIN_REPORT_BYTES = 800
_CONTEXT_PER_NODE = 8_000
_CONTEXT_TOTAL = 90_000
_DEFAULT_REPORT_DIR = ".autoagent/reports"

ReportSynthesizer = Callable[[str, str], str]


def slugify_goal(goal: str, *, max_len: int = 48) -> str:
    slug = re.sub(r"[^\w\s-]", "", goal, flags=re.UNICODE).strip().lower()
    slug = re.sub(r"[-\s]+", "-", slug)
    return (slug[:max_len].strip("-") or "report")


def default_report_path(workspace: Path, run_id: str, goal: str) -> Path:
    return workspace / _DEFAULT_REPORT_DIR / f"{slugify_goal(goal)}-{run_id[:8]}.md"


def format_tool_result_output(result: ToolResult, *, max_chars: int = _CONTEXT_PER_NODE) -> str:
    output = result.output
    if "results" in output and isinstance(output["results"], list):
        lines: list[str] = []
        for item in output["results"]:
            if not isinstance(item, dict):
                continue
            title = str(item.get("title", "")).strip()
            url = str(item.get("url", item.get("href", ""))).strip()
            snippet = str(item.get("snippet", "")).strip()
            if url and title:
                line = f"- [{title}]({url})"
            elif title:
                line = f"- {title}"
            else:
                continue
            if snippet:
                line += f": {snippet}"
            lines.append(line)
        if lines:
            query = output.get("query", "")
            header = f"Search query: {query}\n\n" if query else ""
            return (header + "\n".join(lines))[:max_chars]
    if "url" in output and "text" in output:
        url = output.get("url", "")
        text = str(output["text"])
        return f"Source: {url}\n\n{text[: max_chars - len(str(url)) - 20]}"
    if "text" in output:
        return str(output["text"])[:max_chars]
    if "content" in output:
        return str(output["content"])[:max_chars]
    if "answer" in output:
        return str(output["answer"])[:max_chars]
    return json.dumps(output, ensure_ascii=False)[:max_chars]


def format_execution_context(
    results_by_id: dict[str, ToolResult],
    dependency_ids: list[str] | None = None,
) -> str:
    node_ids = dependency_ids if dependency_ids else list(results_by_id.keys())
    sections: list[str] = []
    for node_id in node_ids:
        result = results_by_id.get(node_id)
        if result is None or not result.ok:
            continue
        body = format_tool_result_output(result)
        if not body.strip():
            continue
        sections.append(f"## {node_id}\n\n{body}")
    body = "\n\n".join(sections)
    if len(body) > _CONTEXT_TOTAL:
        return body[:_CONTEXT_TOTAL] + "\n\n…(truncated)"
    return body


def format_results_list(results: list[NodeExecutionResult]) -> str:
    by_id = {item.node_id: item.tool_result for item in results if item.tool_result.ok}
    return format_execution_context(by_id)


def find_substantial_report_path(
    results: list[NodeExecutionResult],
    workspace: Path,
    *,
    min_bytes: int = MIN_REPORT_BYTES,
) -> Path | None:
    best_path: Path | None = None
    best_size = 0
    root = workspace.expanduser().resolve()

    for item in results:
        output = item.tool_result.output
        if not item.tool_result.ok or "path" not in output:
            continue
        raw_path = str(output["path"])
        try:
            path = resolve_workspace_path(workspace, raw_path)
        except (ToolExecutionError, OSError, ValueError):
            continue
        if not path.is_file():
            continue
        size = path.stat().st_size
        if size >= min_bytes and size > best_size:
            try:
                path.relative_to(root)
            except ValueError:
                continue
            best_path = path
            best_size = size

    return best_path


def assemble_markdown_fallback(goal: str, context: str) -> str:
    return (
        f"# Research Report\n\n"
        f"**Goal:** {goal}\n\n"
        f"## Collected findings\n\n"
        f"{context.strip() or '_No collected context._'}\n"
    )


def synthesize_report_markdown(
    router: LiteLLMRouter,
    *,
    goal: str,
    context: str,
    mode: TaskMode = TaskMode.RESEARCH,
    locale: OutputLocale = OutputLocale.EN,
) -> str:
    system_prompt = report_synthesis_prompt(mode, locale=locale)
    min_expand_bytes = 400 if mode is TaskMode.QUICK else MIN_REPORT_BYTES
    content = router.complete(
        [
            {"role": "system", "content": system_prompt},
            {
                "role": "user",
                "content": (
                    f"# Research goal\n{goal}\n\n"
                    f"# Collected findings (from DAG tools — treat as primary evidence)\n\n"
                    f"{context[:_CONTEXT_TOTAL]}"
                ),
            },
        ]
    )
    text = content.strip()
    if len(text) < min_expand_bytes:
        expanded = router.complete(
            [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": (
                        f"Goal:\n{goal}\n\nFindings:\n{context[:_CONTEXT_TOTAL]}\n\n"
                        "Previous draft was too short. Expand with more sections, "
                        "detail, tables, and cited sources from the findings."
                    ),
                },
            ]
        )
        if len(expanded.strip()) > len(text):
            text = expanded.strip()
    return text if text else assemble_markdown_fallback(goal, context)


def make_report_synthesizer(
    router: LiteLLMRouter,
    *,
    mode: TaskMode = TaskMode.RESEARCH,
    locale: OutputLocale = OutputLocale.EN,
) -> ReportSynthesizer:
    def synthesize(task: str, context: str) -> str:
        return synthesize_report_markdown(
            router, goal=task, context=context, mode=mode, locale=locale
        )

    return synthesize


def prepare_file_write_tool_args(
    tool_args: dict[str, Any],
    *,
    goal: str,
    results_by_id: dict[str, ToolResult],
    dependencies: list[str],
    synthesizer: ReportSynthesizer | None,
    workspace: Path,
) -> dict[str, Any]:
    args = dict(tool_args)
    content = str(args.get("content", "")).strip()
    raw_path = str(args.get("path", "")).strip()

    if len(content) >= MIN_REPORT_BYTES:
        return args

    context = format_execution_context(results_by_id, dependencies or None)
    if not context.strip():
        context = format_execution_context(results_by_id, None)

    if context.strip():
        if synthesizer is not None:
            args["content"] = synthesizer(goal, context)
        else:
            args["content"] = assemble_markdown_fallback(goal, context)
    elif not content:
        args["content"] = assemble_markdown_fallback(goal, "")

    if not raw_path:
        args["path"] = f"{_DEFAULT_REPORT_DIR}/{slugify_goal(goal)}.md"

    if raw_path:
        try:
            target = resolve_workspace_path(workspace, raw_path)
            if target.exists() and target.stat().st_size >= MIN_REPORT_BYTES:
                args["content"] = target.read_text(encoding="utf-8")
                return args
        except (ToolExecutionError, OSError, ValueError):
            pass

    return args


def ensure_run_report(
    *,
    goal: str,
    run_id: str,
    results: list[NodeExecutionResult],
    workspace: Path,
    router: LiteLLMRouter | None = None,
    report_synthesizer: ReportSynthesizer | None = None,
    mode: TaskMode = TaskMode.RESEARCH,
) -> Path | None:
    """Write a report file when execution did not produce a substantial one."""
    existing = find_substantial_report_path(results, workspace)
    if existing is not None:
        return existing

    context = format_results_list(results)
    if not context.strip():
        return None

    if report_synthesizer is not None:
        body = report_synthesizer(goal, context)
    elif router is not None:
        body = synthesize_report_markdown(router, goal=goal, context=context, mode=mode)
    else:
        body = assemble_markdown_fallback(goal, context)

    if len(body.encode("utf-8")) < MIN_REPORT_BYTES:
        body = assemble_markdown_fallback(goal, f"{context}\n\n{body}")

    path = default_report_path(workspace, run_id, goal)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path
