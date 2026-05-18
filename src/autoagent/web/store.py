from __future__ import annotations

import threading
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any


@dataclass
class WebRunRecord:
    id: str
    goal: str
    status: str
    plan: dict[str, Any] | None = None
    node_statuses: dict[str, str] = field(default_factory=dict)
    progress: list[str] = field(default_factory=list)
    report_path: str | None = None
    report_name: str | None = None
    error: str | None = None
    task_mode: str = "research"
    created_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "goal": self.goal,
            "status": self.status,
            "plan": self.plan,
            "node_statuses": self.node_statuses,
            "progress": self.progress,
            "report_path": self.report_path,
            "report_name": self.report_name,
            "error": self.error,
            "task_mode": self.task_mode,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


class RunStore:
    def __init__(self) -> None:
        self._runs: dict[str, WebRunRecord] = {}
        self._lock = threading.Lock()

    def get(self, run_id: str) -> WebRunRecord | None:
        with self._lock:
            return self._runs.get(run_id)

    def list_recent(self, *, limit: int = 20) -> list[WebRunRecord]:
        with self._lock:
            items = sorted(self._runs.values(), key=lambda r: r.updated_at, reverse=True)
        return items[:limit]

    def put(self, record: WebRunRecord) -> None:
        with self._lock:
            record.updated_at = datetime.now(UTC).isoformat()
            self._runs[record.id] = record

    def update(self, run_id: str, **fields: Any) -> WebRunRecord | None:
        with self._lock:
            record = self._runs.get(run_id)
            if record is None:
                return None
            for key, value in fields.items():
                setattr(record, key, value)
            record.updated_at = datetime.now(UTC).isoformat()
            return record
