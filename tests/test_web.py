from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient  # noqa: E402

from autoagent.config import AgentSettings  # noqa: E402
from autoagent.web.api import create_app  # noqa: E402


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    settings = AgentSettings(
        workspace=tmp_path,
        memory_path=tmp_path / "memory.db",
    )
    return TestClient(create_app(settings))


def test_health_and_config(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    cfg = client.get("/api/config").json()
    assert "default_model" in cfg
    assert "workspace" in cfg


def test_index_served(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "AutoAgent" in res.text


def test_create_run_heuristic(client: TestClient) -> None:
    res = client.post(
        "/api/runs",
        json={"goal": "echo hello", "llm": False, "approve": True},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["goal"] == "echo hello"
    assert data["id"]


def test_list_reports_returns_list(client: TestClient) -> None:
    reports = client.get("/api/reports").json()
    assert isinstance(reports, list)
