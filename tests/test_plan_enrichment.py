from __future__ import annotations

from autoagent.plan_enrichment import enrich_plan_data


def test_enrich_fills_search_query_and_converts_terminal_write_to_react() -> None:
    data = {
        "goal": "Research AI agents",
        "nodes": [
            {
                "id": "search_a",
                "description": "AI agent frameworks 2025",
                "tool_name": "web.search",
                "tool_args": {},
                "dependencies": [],
            },
            {
                "id": "write_report",
                "description": "Save report",
                "tool_name": "file.write",
                "tool_args": {"path": "out.md", "content": "placeholder"},
                "dependencies": ["search_a"],
            },
        ],
    }
    enrich_plan_data(data, "Research AI agents")
    search = data["nodes"][0]
    assert search["tool_args"]["query"] == "AI agent frameworks 2025"
    assert search["tool_args"]["limit"] == 5

    terminal = data["nodes"][-1]
    assert terminal["tool_name"] is None
    assert "file.write" in terminal["description"]


def test_enrich_file_write_gets_default_path() -> None:
    data = {
        "goal": "g",
        "nodes": [
            {
                "id": "search",
                "description": "look up topic",
                "tool_name": "web.search",
                "tool_args": {},
                "dependencies": [],
            },
            {
                "id": "draft",
                "description": "draft notes",
                "tool_name": "file.write",
                "tool_args": {},
                "dependencies": ["search"],
            },
            {
                "id": "finalize",
                "description": "final synthesis",
                "tool_name": None,
                "tool_args": {},
                "dependencies": ["draft"],
            },
        ],
    }
    enrich_plan_data(data, "g")
    draft = data["nodes"][1]
    assert draft["tool_args"]["path"] == ".autoagent/reports/report.md"
    assert draft["tool_args"]["content"] == ""
