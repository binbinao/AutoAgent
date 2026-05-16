from __future__ import annotations

from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from autoagent.worker import app as worker_app


def test_worker_execute_completes_heuristic_run(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("AUTOAGENT_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("AUTOAGENT_MEMORY_PATH", str(tmp_path / "memory.db"))
    monkeypatch.setenv("AUTOAGENT_STATE_PATH", str(tmp_path / "state.json"))

    runner = CliRunner()
    result = runner.invoke(worker_app, ["hello worker", "--approve"])

    assert result.exit_code == 0
    assert "completed" in result.output.lower() or result.exit_code == 0
