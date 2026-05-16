from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from rich.console import Console
from typer.testing import CliRunner

from autoagent.cli import app, build_orchestrator, build_registry
from autoagent.config import AgentSettings
from autoagent.llm import LiteLLMRouter, LLMPlanner
from autoagent.memory import EpisodicMemory, InMemorySemanticMemory
from autoagent.models import RunStatus


class FakeMessage:
    content = json.dumps(
        {
            "goal": "g",
            "nodes": [
                {
                    "id": "n1",
                    "description": "d",
                    "tool_name": "echo",
                    "tool_args": {"text": "x"},
                    "dependencies": [],
                }
            ],
        }
    )


class FakeChoice:
    message = FakeMessage()


class FakeCompletionResponse:
    choices = [FakeChoice()]


def test_litellm_router_and_planner(monkeypatch: Any) -> None:
    import autoagent.llm as llm_module

    monkeypatch.setattr(llm_module, "completion", lambda **kwargs: FakeCompletionResponse())

    router = LiteLLMRouter("fake-model")
    planner = LLMPlanner(router)
    plan = planner.create_plan("g")

    assert router.complete([{"role": "user", "content": "hi"}])
    assert plan.nodes[0].tool_name == "echo"


def test_in_memory_semantic_memory_searches_by_terms() -> None:
    memory = InMemorySemanticMemory()

    memory.add(text="agent planning and execution")
    memory.add(text="unrelated note")

    assert memory.search("planning agent") == ["agent planning and execution"]


def test_settings_can_be_overridden_with_environment(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.setenv("AUTOAGENT_WORKSPACE", str(tmp_path))
    monkeypatch.setenv("AUTOAGENT_AUTO_APPROVE", "true")

    settings = AgentSettings()

    assert settings.workspace == tmp_path
    assert settings.auto_approve is True


def test_build_registry_contains_core_tools(tmp_path: Path) -> None:
    settings = AgentSettings(workspace=tmp_path, python_timeout_seconds=1, use_docker_sandbox=False)
    registry = build_registry(tmp_path, settings)

    assert "echo" in registry.names
    assert "file.read" in registry.names
    assert "python.run" in registry.names


def test_build_orchestrator_auto_approves(tmp_path: Path) -> None:
    settings = AgentSettings(workspace=tmp_path, auto_approve=True)

    run = build_orchestrator(settings).run("hello")

    assert run.status is RunStatus.COMPLETED


def test_cli_plan_and_run_commands() -> None:
    runner = CliRunner()

    plan_result = runner.invoke(app, ["plan", "hello"])
    run_result = runner.invoke(app, ["run", "hello", "--approve"])

    assert plan_result.exit_code == 0
    assert "awaiting_approval" in plan_result.output
    assert run_result.exit_code == 0
    assert "completed" in run_result.output


def test_cli_history_empty(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("AUTOAGENT_MEMORY_PATH", str(tmp_path / "memory.db"))
    runner = CliRunner()

    result = runner.invoke(app, ["history"])

    assert result.exit_code == 0
    assert "No tasks" in result.output or "history" in result.output.lower()


def test_cli_history_shows_recorded_tasks(tmp_path: Path, monkeypatch: Any) -> None:
    db_path = tmp_path / "memory.db"
    monkeypatch.setenv("AUTOAGENT_MEMORY_PATH", str(db_path))

    mem = EpisodicMemory(db_path)
    mem.record_task(goal="test goal", plan_summary="step1 -> step2", outcome="completed")
    mem.close()

    runner = CliRunner()
    result = runner.invoke(app, ["history"])

    assert result.exit_code == 0
    assert "test goal" in result.output


def test_cli_config_shows_settings() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["config"])

    assert result.exit_code == 0
    assert "default_model" in result.output
    assert "log_level" in result.output
    assert "semantic_memory_backend" in result.output


def test_cli_run_with_model_flag() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["run", "hello", "--approve", "--model", "gpt-3.5-turbo"])

    assert result.exit_code == 0
    assert "completed" in result.output


def test_cli_plan_with_model_flag() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["plan", "hello", "--model", "gpt-3.5-turbo"])

    assert result.exit_code == 0
    assert "awaiting_approval" in result.output


def test_cli_run_interactive_edit_then_approve() -> None:
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["run", "hello"],
        input="e\nCustom edited description\ny\n",
    )

    assert result.exit_code == 0
    assert "completed" in result.output
    assert "Custom edited description" in result.output


def test_cli_run_interactive_reject() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["run", "hello"], input="n\n")

    assert result.exit_code == 1
    assert "rejected" in result.output.lower()


def test_cli_run_invalid_choice_then_approve() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ["run", "hello"], input="maybe\ny\n")

    assert result.exit_code == 0
    assert "completed" in result.output


def test_settings_log_level_and_semantic_backend_defaults() -> None:
    settings = AgentSettings()

    assert settings.log_level == "WARNING"
    assert settings.semantic_memory_backend == "memory"


def test_llm_planner_uses_semantic_context(monkeypatch: Any) -> None:
    import autoagent.llm as llm_module

    captured: list[str] = []

    def fake_completion(**kwargs: object) -> FakeCompletionResponse:
        messages = kwargs["messages"]
        captured.append(messages[-1]["content"])  # type: ignore[index]
        return FakeCompletionResponse()

    monkeypatch.setattr(llm_module, "completion", fake_completion)

    semantic = InMemorySemanticMemory()
    semantic.add(text="When writing tests, always prefer pytest and TDD.")
    router = LiteLLMRouter("fake")
    planner = LLMPlanner(router, semantic=semantic)
    planner.create_plan("write unit tests for the project")

    assert "pytest" in captured[0]
    assert "Relevant knowledge" in captured[0]


def test_cli_config_init_writes_user_toml(tmp_path: Path, monkeypatch: Any) -> None:
    import autoagent.config as config_module

    cfg = tmp_path / "config.toml"
    monkeypatch.setattr(config_module, "_USER_CONFIG", cfg)
    monkeypatch.setattr(config_module, "user_config_path", lambda: cfg)
    runner = CliRunner()

    result = runner.invoke(
        app,
        ["config", "--init"],
        input="\n\nmemory\nn\ny\n",
    )

    assert result.exit_code == 0
    assert cfg.is_file()
    assert "default_model" in cfg.read_text(encoding="utf-8")


def test_cli_status_shows_saved_run(tmp_path: Path, monkeypatch: Any) -> None:
    from autoagent.models import AgentRun, Plan, PlanNode
    from autoagent.run_state import RunSnapshot, save_run_snapshot

    state_path = tmp_path / "run_state.json"
    monkeypatch.setenv("AUTOAGENT_STATE_PATH", str(state_path))
    plan = Plan(
        goal="saved",
        nodes=[PlanNode(id="a", description="A", tool_name="echo")],
    )
    save_run_snapshot(
        state_path,
        RunSnapshot(run=AgentRun(goal="saved", plan=plan, status=RunStatus.FAILED)),
    )

    runner = CliRunner()
    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "saved" in result.output


def test_cli_run_detach_spawns_worker(tmp_path: Path, monkeypatch: Any) -> None:
    import autoagent.cli.app as cli_app

    spawned: list[list[str]] = []

    class FakeProc:
        pid = 4242

    def fake_popen(cmd: list[str], **kwargs: object) -> FakeProc:
        del kwargs
        spawned.append(cmd)
        return FakeProc()

    monkeypatch.setattr(cli_app.subprocess, "Popen", fake_popen)
    monkeypatch.setenv("AUTOAGENT_STATE_PATH", str(tmp_path / "state.json"))
    monkeypatch.setenv("AUTOAGENT_LOG_PATH", str(tmp_path / "run.log"))

    runner = CliRunner()
    result = runner.invoke(app, ["run", "bg task", "--approve", "--detach"])

    assert result.exit_code == 0
    assert spawned
    assert "autoagent.worker" in " ".join(spawned[0])
    assert "4242" in result.output


def test_build_orchestrator_with_llm_includes_react_agent(tmp_path: Path) -> None:
    settings = AgentSettings(workspace=tmp_path, use_docker_sandbox=False)
    orchestrator = build_orchestrator(settings, use_llm_planner=True, console=Console())
    assert orchestrator.executor.react_agent is not None
