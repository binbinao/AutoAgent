from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

from autoagent.models import AgentRun, RunStatus


class RunProgress(BaseModel):
    completed_nodes: list[str] = Field(default_factory=list)
    failed_nodes: list[str] = Field(default_factory=list)
    skipped_nodes: list[str] = Field(default_factory=list)
    messages: list[str] = Field(default_factory=list)

    def append_message(self, message: str, *, max_messages: int = 50) -> None:
        self.messages.append(message)
        if len(self.messages) > max_messages:
            self.messages = self.messages[-max_messages:]


class RunSnapshot(BaseModel):
    run: AgentRun
    progress: RunProgress = Field(default_factory=RunProgress)
    pid: int | None = None
    detached: bool = False
    log_path: str | None = None


def save_run_snapshot(path: Path, snapshot: RunSnapshot) -> None:
    path = path.expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(snapshot.model_dump_json(), encoding="utf-8")


def load_run_snapshot(path: Path) -> RunSnapshot | None:
    path = path.expanduser()
    if not path.is_file():
        return None
    raw = path.read_text(encoding="utf-8")
    if '"run"' in raw[:200]:
        return RunSnapshot.model_validate_json(raw)
    run = AgentRun.model_validate_json(raw)
    return RunSnapshot(run=run)


def save_run_state(path: Path, run: AgentRun) -> None:
    """Backward-compatible: persist only the agent run inside a snapshot envelope."""
    save_run_snapshot(path, RunSnapshot(run=run))


def load_run_state(path: Path) -> AgentRun | None:
    snapshot = load_run_snapshot(path)
    return snapshot.run if snapshot is not None else None


def clear_run_state(path: Path) -> None:
    path = path.expanduser()
    if path.is_file():
        path.unlink()


clear_run_snapshot = clear_run_state

TERMINAL_RUN_STATUSES = frozenset({RunStatus.COMPLETED, RunStatus.FAILED})
