from __future__ import annotations

from typing import Any

import httpx
import pytest

from autoagent.tools.api import ApiRequestTool
from autoagent.tools.base import ToolRegistry


@pytest.mark.asyncio
async def test_api_request_tool_run_async(monkeypatch: Any) -> None:
    class FakeResponse:
        status_code = 200
        headers = {"content-type": "application/json"}
        is_success = True

        def json(self) -> dict[str, str]:
            return {"ok": True}

        @property
        def text(self) -> str:
            return '{"ok": true}'

    class FakeAsyncClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        async def __aenter__(self) -> FakeAsyncClient:
            return self

        async def __aexit__(self, *args: object) -> None:
            del args

        async def request(self, method: str, url: str, **kwargs: object) -> FakeResponse:
            del method, kwargs
            assert url == "https://example.com/api"
            return FakeResponse()

    monkeypatch.setattr(httpx, "AsyncClient", FakeAsyncClient)

    tool = ApiRequestTool()
    result = await tool.run_async({"url": "https://example.com/api"})

    assert result.ok is True
    assert result.output["body"] == {"ok": True}


@pytest.mark.asyncio
async def test_registry_run_async_delegates_to_tool() -> None:
    class StubApi(ApiRequestTool):
        async def run_async(self, args: dict[str, Any]) -> Any:
            from autoagent.models import ToolResult

            return ToolResult(ok=True, output={"stub": True})

    registry = ToolRegistry.with_tools([StubApi()])
    result = await registry.run_async("api.request", {"url": "https://example.com"})

    assert result.output.get("stub") is True
