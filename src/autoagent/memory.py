from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Protocol
from uuid import uuid4

if TYPE_CHECKING:
    from autoagent.config import AgentSettings


@dataclass(frozen=True)
class MemoryItem:
    role: str
    content: str
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class WorkingMemory:
    def __init__(self, max_items: int = 20) -> None:
        if max_items < 1:
            raise ValueError("max_items must be positive")
        self.max_items = max_items
        self.items: list[MemoryItem] = []

    def add(self, *, role: str, content: str) -> None:
        self.items.append(MemoryItem(role=role, content=content))
        self.items = self.items[-self.max_items :]

    def render(self) -> str:
        return "\n".join(f"{item.role}: {item.content}" for item in self.items)

    def as_messages(self) -> list[dict[str, str]]:
        """Return items as a list of ``{"role": ..., "content": ...}`` dicts."""
        return [{"role": item.role, "content": item.content} for item in self.items]


@dataclass(frozen=True)
class EpisodicTask:
    id: str
    goal: str
    plan_summary: str
    outcome: str
    created_at: datetime


class EpisodicMemory:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._initialize()

    def _initialize(self) -> None:
        self._connection.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                goal TEXT NOT NULL,
                plan_summary TEXT NOT NULL,
                outcome TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
            """
        )
        self._connection.commit()

    def record_task(self, *, goal: str, plan_summary: str, outcome: str) -> str:
        task_id = str(uuid4())
        created_at = datetime.now(UTC).isoformat()
        self._connection.execute(
            """
            INSERT INTO tasks (id, goal, plan_summary, outcome, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (task_id, goal, plan_summary, outcome, created_at),
        )
        self._connection.commit()
        return task_id

    def get_task(self, task_id: str) -> EpisodicTask | None:
        cursor = self._connection.execute(
            "SELECT id, goal, plan_summary, outcome, created_at FROM tasks WHERE id = ?",
            (task_id,),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return EpisodicTask(
            id=str(row["id"]),
            goal=str(row["goal"]),
            plan_summary=str(row["plan_summary"]),
            outcome=str(row["outcome"]),
            created_at=datetime.fromisoformat(str(row["created_at"])),
        )

    def list_tasks(self, limit: int = 10) -> list[EpisodicTask]:
        """Return the most recent *limit* tasks, newest first."""
        cursor = self._connection.execute(
            "SELECT id, goal, plan_summary, outcome, created_at "
            "FROM tasks ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        rows = cursor.fetchall()
        return [
            EpisodicTask(
                id=str(row["id"]),
                goal=str(row["goal"]),
                plan_summary=str(row["plan_summary"]),
                outcome=str(row["outcome"]),
                created_at=datetime.fromisoformat(str(row["created_at"])),
            )
            for row in rows
        ]

    def close(self) -> None:
        self._connection.close()


class SemanticMemory(Protocol):
    def add(self, *, text: str, metadata: dict[str, str] | None = None) -> str:
        raise NotImplementedError

    def search(self, query: str, limit: int = 5) -> list[str]:
        raise NotImplementedError


class InMemorySemanticMemory:
    def __init__(self) -> None:
        self._items: dict[str, str] = {}

    def add(self, *, text: str, metadata: dict[str, str] | None = None) -> str:
        del metadata
        item_id = str(uuid4())
        self._items[item_id] = text
        return item_id

    def search(self, query: str, limit: int = 5) -> list[str]:
        query_terms = set(re.findall(r"[a-z0-9]+", query.lower()))
        scored = []
        for text in self._items.values():
            text_terms = set(re.findall(r"[a-z0-9]+", text.lower()))
            score = len(query_terms.intersection(text_terms))
            if score:
                scored.append((score, text))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [text for _, text in scored[:limit]]


class ChromaDBSemanticMemory:
    """Persistent vector memory backed by ChromaDB.

    Requires the ``vector`` optional dependency group:
    ``uv sync --extra vector``
    """

    def __init__(self, path: Path | str, collection: str = "autoagent") -> None:
        try:
            import chromadb  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError(
                "chromadb is not installed. Run `uv sync --extra vector` first."
            ) from exc

        self._client = chromadb.PersistentClient(path=str(path))
        self._collection = self._client.get_or_create_collection(collection)

    def add(self, *, text: str, metadata: dict[str, str] | None = None) -> str:
        item_id = str(uuid4())
        self._collection.add(
            ids=[item_id],
            documents=[text],
            metadatas=[metadata or {}],
        )
        return item_id

    def search(self, query: str, limit: int = 5) -> list[str]:
        count = self._collection.count()
        if count == 0:
            return []
        results = self._collection.query(
            query_texts=[query],
            n_results=min(limit, count),
        )
        docs: list[str] = results.get("documents", [[]])[0]
        return list(docs)


def create_semantic_memory(settings: AgentSettings) -> SemanticMemory:
    if settings.semantic_memory_backend == "chroma":
        return ChromaDBSemanticMemory(settings.chroma_path)
    return InMemorySemanticMemory()


def record_task_with_semantic(
    settings: AgentSettings,
    *,
    goal: str,
    plan_summary: str,
    outcome: str,
    lesson: str | None = None,
) -> None:
    """Persist episodic record and optionally distill a lesson into semantic memory."""
    episodic = EpisodicMemory(settings.memory_path)
    episodic.record_task(goal=goal, plan_summary=plan_summary, outcome=outcome)
    episodic.close()
    if lesson:
        semantic = create_semantic_memory(settings)
        semantic.add(
            text=f"Goal: {goal}\nOutcome: {outcome}\nLesson: {lesson}",
            metadata={"goal": goal[:200], "outcome": outcome},
        )
