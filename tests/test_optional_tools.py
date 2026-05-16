from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from autoagent.tools import (
    ApiRequestTool,
    BrowserSnapshotTool,
    FileListTool,
    PythonSandboxTool,
    ToolExecutionError,
    WebFetchTool,
    WebSearchTool,
)


class FakeWebResponse:
    def __init__(self, text: str, url: str = "https://example.com", status_code: int = 200) -> None:
        self.text = text
        self.url = url
        self.status_code = status_code
        self.headers = {"content-type": "text/html"}
        self.is_success = 200 <= status_code < 300

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise RuntimeError("bad status")


class FakeWebClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    def __enter__(self) -> FakeWebClient:
        return self

    def __exit__(self, *args: Any) -> None:
        del args

    def get(self, url: str, **kwargs: Any) -> FakeWebResponse:
        del kwargs
        if "duckduckgo" in url:
            return FakeWebResponse(
                '<a class="result__a" href="https://example.com/a">Result A</a>',
                url,
            )
        return FakeWebResponse(
            "<html><body><script>x</script><h1>Hello</h1><p>World</p></body></html>",
            url,
        )


class FakeApiResponse:
    status_code = 201
    headers = {"content-type": "application/json"}
    is_success = True
    text = '{"ok": true}'

    def json(self) -> dict[str, bool]:
        return {"ok": True}


class FakeApiClient:
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        del args, kwargs

    def __enter__(self) -> FakeApiClient:
        return self

    def __exit__(self, *args: Any) -> None:
        del args

    def request(self, method: str, url: str, **kwargs: Any) -> FakeApiResponse:
        del method, url, kwargs
        return FakeApiResponse()


def test_file_list_tool_lists_workspace_entries(tmp_path: Path) -> None:
    workspace = tmp_path / "workspace"
    (workspace / "a.txt").parent.mkdir(parents=True)
    (workspace / "a.txt").write_text("a", encoding="utf-8")

    result = FileListTool(workspace).run({"path": "."})

    assert result.output["entries"] == ["a.txt"]


def test_python_sandbox_runs_code_and_reports_missing_code(tmp_path: Path) -> None:
    tool = PythonSandboxTool(tmp_path)

    result = tool.run({"code": "print(2 + 2)"})

    assert result.ok is True
    assert result.output["stdout"].strip() == "4"
    with pytest.raises(ToolExecutionError, match="code"):
        tool.run({})


def test_python_sandbox_reports_nonzero_exit(tmp_path: Path) -> None:
    result = PythonSandboxTool(tmp_path).run({"code": "raise SystemExit(3)"})

    assert result.ok is False
    assert result.output["returncode"] == 3


def test_web_fetch_and_search_parse_results(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("autoagent.tools.web.httpx.Client", FakeWebClient)

    fetch_result = WebFetchTool().run({"url": "https://example.com"})
    search_result = WebSearchTool().run({"query": "agents", "limit": 1})

    assert "Hello" in fetch_result.output["text"]
    assert search_result.output["results"] == [
        {"title": "Result A", "url": "https://example.com/a"}
    ]


def test_web_tools_validate_required_inputs() -> None:
    with pytest.raises(ToolExecutionError, match="url"):
        WebFetchTool().run({})
    with pytest.raises(ToolExecutionError, match="query"):
        WebSearchTool().run({})


def test_api_request_tool_validates_and_executes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("autoagent.tools.api.httpx.Client", FakeApiClient)
    tool = ApiRequestTool()
    monkeypatch.setattr(tool, "_is_private_host", lambda hostname: False)

    result = tool.run({"method": "POST", "url": "https://api.example.com/items", "json": {"a": 1}})

    assert result.ok is True
    assert result.output["status_code"] == 201
    assert result.output["body"] == {"ok": True}


def test_api_request_tool_blocks_invalid_inputs() -> None:
    tool = ApiRequestTool()

    with pytest.raises(ToolExecutionError, match="Unsupported"):
        tool.run({"method": "TRACE", "url": "https://example.com"})
    with pytest.raises(ToolExecutionError, match="hostname"):
        tool.run({"url": "https:///broken"})


def test_browser_tool_reports_missing_playwright() -> None:
    with pytest.raises(ToolExecutionError, match="Playwright"):
        BrowserSnapshotTool().run({"url": "https://example.com"})
