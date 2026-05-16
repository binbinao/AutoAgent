from pathlib import Path

import pytest

from autoagent.memory import EpisodicMemory, WorkingMemory


def test_working_memory_keeps_recent_items_only() -> None:
    memory = WorkingMemory(max_items=2)

    memory.add(role="system", content="first")
    memory.add(role="assistant", content="second")
    memory.add(role="tool", content="third")

    assert [item.content for item in memory.items] == ["second", "third"]


def test_episodic_memory_records_and_loads_task(tmp_path: Path) -> None:
    memory = EpisodicMemory(tmp_path / "episodes.db")

    task_id = memory.record_task(
        goal="research AI agents",
        plan_summary="search -> synthesize",
        outcome="done",
    )
    task = memory.get_task(task_id)

    assert task is not None
    assert task.goal == "research AI agents"
    assert task.plan_summary == "search -> synthesize"
    assert task.outcome == "done"


def test_episodic_memory_list_tasks_returns_newest_first(tmp_path: Path) -> None:
    memory = EpisodicMemory(tmp_path / "list.db")

    memory.record_task(goal="first", plan_summary="a", outcome="done")
    memory.record_task(goal="second", plan_summary="b", outcome="done")
    memory.record_task(goal="third", plan_summary="c", outcome="done")

    tasks = memory.list_tasks(limit=2)

    assert len(tasks) == 2
    assert tasks[0].goal == "third"
    assert tasks[1].goal == "second"


def test_working_memory_as_messages_round_trips() -> None:
    from autoagent.memory import WorkingMemory

    wm = WorkingMemory(max_items=5)
    wm.add(role="user", content="hello")
    wm.add(role="assistant", content="world")

    msgs = wm.as_messages()

    assert msgs == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "world"},
    ]


def test_chroma_semantic_memory_add_and_search(tmp_path: Path) -> None:
    pytest.importorskip("chromadb")
    from autoagent.memory import ChromaDBSemanticMemory

    mem = ChromaDBSemanticMemory(tmp_path / "chroma")
    mem.add(text="autonomous agent planning with LLMs")
    mem.add(text="unrelated text about cooking")

    results = mem.search("agent planning", limit=1)

    assert len(results) == 1
    assert "agent" in results[0].lower()


def test_chroma_semantic_memory_empty_search(tmp_path: Path) -> None:
    pytest.importorskip("chromadb")
    from autoagent.memory import ChromaDBSemanticMemory

    mem = ChromaDBSemanticMemory(tmp_path / "chroma_empty")
    results = mem.search("anything")

    assert results == []


def test_chroma_semantic_memory_import_error_without_chromadb(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    from autoagent.memory import ChromaDBSemanticMemory

    def fake_import(name: str, *args: object, **kwargs: object) -> object:
        if name == "chromadb":
            raise ImportError("no chromadb")
        import builtins
        return builtins.__import__(name, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr("builtins.__import__", fake_import)

    with pytest.raises(RuntimeError, match="chromadb"):
        ChromaDBSemanticMemory(tmp_path / "x")
