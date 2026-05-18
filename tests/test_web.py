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


def test_api_responses_are_not_cached(client: TestClient) -> None:
    assert client.get("/api/health").headers.get("cache-control") == "no-store"


def test_health_and_config(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}
    cfg = client.get("/api/config").json()
    assert "effective" in cfg
    assert "fields" in cfg
    assert cfg["effective"]["default_task_mode"] == "research"
    assert "quick" in cfg["task_modes"]
    assert len(cfg["fields"]) >= 10


def test_index_served(client: TestClient) -> None:
    res = client.get("/")
    assert res.status_code == 200
    assert "AutoAgent" in res.text
    assert "status-badge" in res.text
    assert "plan-graph" in res.text
    assert "dag-graph.js" in res.text
    assert "lang-switch" in res.text
    assert "main-tabs" in res.text
    assert "view-config" in res.text
    assert 'lang="en"' in res.text
    assert "i18n.js" in res.text


def test_update_config_writes_toml(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import autoagent.config as config_module

    cfg_path = tmp_path / "config.toml"
    monkeypatch.setattr(config_module, "_USER_CONFIG", cfg_path)
    monkeypatch.setattr(config_module, "user_config_path", lambda: cfg_path)
    monkeypatch.delenv("AUTOAGENT_DEFAULT_MODEL", raising=False)
    monkeypatch.delenv("AUTOAGENT_AUTO_APPROVE", raising=False)

    settings = AgentSettings(workspace=tmp_path, memory_path=tmp_path / "memory.db")
    client = TestClient(create_app(settings))

    res = client.put(
        "/api/config",
        json={"default_model": "openai/test-model", "auto_approve": True},
    )
    assert res.status_code == 200
    body = res.json()
    assert body["user_file"]["default_model"] == "openai/test-model"
    assert body["user_file"]["auto_approve"] is True
    assert cfg_path.is_file()
    text = cfg_path.read_text(encoding="utf-8")
    assert 'default_model = "openai/test-model"' in text
    assert "auto_approve = true" in text


def test_update_config_rejects_empty_body(client: TestClient) -> None:
    res = client.put("/api/config", json={})
    assert res.status_code == 400


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
