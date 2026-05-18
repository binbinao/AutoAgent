"""Normalize and enrich LLM-generated plans so tools receive valid arguments."""

from __future__ import annotations

from typing import Any

from autoagent.task_mode import TaskMode

_DEFAULT_REPORT_PATH = ".autoagent/reports/report.md"
_SEARCH_TOOLS = frozenset({"web.search"})
_FETCH_TOOLS = frozenset({"web.fetch"})


def _node_list(data: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = data.get("nodes")
    if not isinstance(nodes, list):
        return []
    return [n for n in nodes if isinstance(n, dict)]


def _ensure_tool_args(node: dict[str, Any]) -> dict[str, Any]:
    raw = node.get("tool_args")
    return dict(raw) if isinstance(raw, dict) else {}


def _infer_search_query(description: str, goal: str) -> str:
    text = description.strip()
    if len(text) >= 12:
        return text[:200]
    return goal.strip()[:200]


def _terminal_synthesis_description(existing: str, *, mode: TaskMode) -> str:
    base = existing.strip()
    if mode is TaskMode.QUICK:
        path = _DEFAULT_REPORT_PATH
        suffix = f"\n\n综合依赖步骤输出，撰写简洁 Markdown 结果；如需落盘则 file.write 到 {path}。"
    else:
        suffix = (
            f"\n\n使用 web.search / web.fetch 回顾依赖节点发现，撰写完整 Markdown 研究报告，"
            f"并用 file.write 保存到 {_DEFAULT_REPORT_PATH}。"
        )
    return (base + suffix).strip() if base else suffix.strip()


def enrich_plan_data(
    data: dict[str, Any],
    goal: str,
    *,
    mode: TaskMode = TaskMode.RESEARCH,
) -> None:
    """Mutate plan JSON in-place: fill missing tool_args and fix terminal synthesis nodes."""
    nodes = _node_list(data)
    if not nodes:
        return

    for node in nodes:
        tool = node.get("tool_name")
        args = _ensure_tool_args(node)
        desc = str(node.get("description", ""))

        if tool in _SEARCH_TOOLS:
            query = str(args.get("query", "")).strip()
            if not query:
                args["query"] = _infer_search_query(desc, goal)
            if "limit" not in args:
                args["limit"] = 3 if mode is TaskMode.QUICK else 5
            node["tool_args"] = args

        elif tool in _FETCH_TOOLS:
            node["tool_args"] = args

        elif tool == "file.write":
            if not str(args.get("path", "")).strip():
                args["path"] = _DEFAULT_REPORT_PATH
            if "content" not in args:
                args["content"] = ""
            node["tool_args"] = args

        elif tool is None:
            node["tool_args"] = {}

    terminal = nodes[-1]
    terminal_tool = terminal.get("tool_name")
    if terminal_tool == "file.write":
        terminal["tool_name"] = None
        terminal["tool_args"] = {}
        terminal["description"] = _terminal_synthesis_description(
            str(terminal.get("description", "")),
            mode=mode,
        )
    elif terminal_tool is None and "file.write" not in str(terminal.get("description", "")):
        terminal["description"] = _terminal_synthesis_description(
            str(terminal.get("description", "")),
            mode=mode,
        )

    data["nodes"] = nodes
