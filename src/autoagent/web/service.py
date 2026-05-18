from __future__ import annotations

import io
import threading
from pathlib import Path
from typing import Any

from rich.console import Console

from autoagent.cli.app import _resolve_task_mode, build_orchestrator
from autoagent.cli.run_flow import execute_approved_run
from autoagent.config import (
    CONFIG_FIELD_SPECS,
    AgentSettings,
    load_user_toml,
    settings_as_dict,
    user_config_path,
    write_user_config,
)
from autoagent.memory import EpisodicMemory
from autoagent.models import AgentRun, Plan, RunStatus
from autoagent.output_locale import parse_output_locale
from autoagent.report import _DEFAULT_REPORT_DIR, ensure_run_report
from autoagent.run_state import RunProgress
from autoagent.task_mode import TaskMode, parse_task_mode
from autoagent.tools.presets import list_presets, resolve_tool_names
from autoagent.utils.logging import new_trace_id
from autoagent.web.serializers import agent_run_status, node_statuses_from_results, plan_to_dict
from autoagent.web.store import RunStore, WebRunRecord


class RunService:
    def __init__(self, settings: AgentSettings | None = None) -> None:
        self.settings = settings or AgentSettings()
        self.store = RunStore()

    def reload_settings(self) -> None:
        self.settings = AgentSettings()

    def public_config(self) -> dict[str, Any]:
        payload = self.full_config()
        effective = payload["effective"]
        default_mode = parse_task_mode(effective["default_task_mode"])
        return {
            "default_model": effective["default_model"],
            "workspace": effective["workspace"],
            "auto_approve": effective["auto_approve"],
            "reports_dir": _DEFAULT_REPORT_DIR,
            "default_task_mode": effective["default_task_mode"],
            "task_modes": [m.value for m in TaskMode],
            "default_tool_preset": effective["default_tool_preset"],
            "tool_presets": list_presets(),
            "enabled_tools": resolve_tool_names(self.settings, task_mode=default_mode),
        }

    def full_config(self) -> dict[str, Any]:
        user_file = load_user_toml()
        default_mode = parse_task_mode(self.settings.default_task_mode)
        return {
            "user_config_path": str(user_config_path()),
            "effective": settings_as_dict(self.settings),
            "user_file": {
                spec["key"]: user_file[spec["key"]]
                for spec in CONFIG_FIELD_SPECS
                if spec["key"] in user_file
            },
            "fields": list(CONFIG_FIELD_SPECS),
            "task_modes": [m.value for m in TaskMode],
            "reports_dir": _DEFAULT_REPORT_DIR,
            "tooling": {
                "default_tool_preset": self.settings.default_tool_preset,
                "tool_presets": list_presets(),
                "effective_tools": resolve_tool_names(self.settings, task_mode=default_mode),
            },
        }

    def update_config(self, updates: dict[str, Any]) -> dict[str, Any]:
        write_user_config(updates)
        self.reload_settings()
        return self.full_config()

    def list_history(self, *, limit: int = 20) -> list[dict[str, Any]]:
        memory = EpisodicMemory(self.settings.memory_path)
        try:
            tasks = memory.list_tasks(limit=limit)
        finally:
            memory.close()
        return [
            {
                "id": task.id,
                "goal": task.goal,
                "plan_summary": task.plan_summary,
                "outcome": task.outcome,
                "created_at": task.created_at.isoformat(),
            }
            for task in tasks
        ]

    def list_reports(self) -> list[dict[str, Any]]:
        reports_dir = self.settings.workspace / _DEFAULT_REPORT_DIR
        if not reports_dir.is_dir():
            return []
        items: list[dict[str, Any]] = []
        for path in sorted(reports_dir.glob("*.md"), key=lambda p: p.stat().st_mtime, reverse=True):
            items.append(
                {
                    "name": path.name,
                    "path": str(path.relative_to(self.settings.workspace)),
                    "size": path.stat().st_size,
                    "modified_at": path.stat().st_mtime,
                }
            )
        return items

    def read_report(self, name: str) -> str:
        safe = Path(name).name
        path = (self.settings.workspace / _DEFAULT_REPORT_DIR / safe).resolve()
        root = (self.settings.workspace / _DEFAULT_REPORT_DIR).resolve()
        path.relative_to(root)
        if not path.is_file():
            raise FileNotFoundError(safe)
        return path.read_text(encoding="utf-8")

    def start_run(
        self,
        *,
        goal: str,
        llm: bool,
        approve: bool,
        task_mode: str | None = None,
        locale: str | None = "en",
    ) -> WebRunRecord:
        goal = goal.strip()
        if not goal:
            raise ValueError("Goal is required")

        try:
            mode = parse_task_mode(task_mode or self.settings.default_task_mode)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc
        try:
            output_locale = parse_output_locale(locale)
        except ValueError as exc:
            raise ValueError(str(exc)) from exc

        new_trace_id()
        orchestrator, report_router = build_orchestrator(
            self.settings,
            use_llm_planner=llm,
            console=None,
            task_mode=mode,
            output_locale=output_locale,
        )
        agent_run = orchestrator.plan(goal)
        record = WebRunRecord(
            id=agent_run.id,
            goal=goal,
            status=agent_run_status(agent_run),
            plan=plan_to_dict(agent_run.plan),
            task_mode=mode.value,
            locale=output_locale.value,
        )
        self.store.put(record)

        if agent_run.status is RunStatus.AWAITING_APPROVAL and not approve:
            return record

        thread = threading.Thread(
            target=self._execute_run,
            args=(orchestrator, agent_run, report_router, mode),
            daemon=True,
        )
        thread.start()
        return record

    def approve_run(self, run_id: str) -> WebRunRecord:
        record = self.store.get(run_id)
        if record is None:
            raise KeyError(run_id)
        if record.status != RunStatus.AWAITING_APPROVAL.value:
            raise ValueError(f"Run {run_id} is not awaiting approval")

        mode = _resolve_task_mode(record.task_mode, self.settings)
        output_locale = parse_output_locale(record.locale)
        orchestrator, report_router = build_orchestrator(
            self.settings,
            use_llm_planner=True,
            console=None,
            task_mode=mode,
            output_locale=output_locale,
        )
        if record.plan is None:
            raise ValueError("Run has no plan to execute")
        plan = Plan.model_validate(
            {
                "goal": record.plan["goal"],
                "nodes": [
                    {
                        "id": node["id"],
                        "description": node["description"],
                        "tool_name": node.get("tool_name"),
                        "tool_args": {},
                        "dependencies": node.get("dependencies", []),
                    }
                    for node in record.plan.get("nodes", [])
                ],
            }
        )
        agent_run = AgentRun(id=run_id, goal=record.goal, plan=plan, status=RunStatus.APPROVED)

        thread = threading.Thread(
            target=self._execute_run,
            args=(orchestrator, agent_run, report_router, mode),
            daemon=True,
        )
        thread.start()
        self.store.update(run_id, status=RunStatus.RUNNING.value)
        updated = self.store.get(run_id)
        if updated is None:
            raise KeyError(run_id)
        return updated

    def _execute_run(
        self,
        orchestrator: Any,
        agent_run: AgentRun,
        report_router: Any,
        task_mode: TaskMode,
    ) -> None:
        run_id = agent_run.id
        self.store.update(run_id, status=RunStatus.RUNNING.value, progress=[])

        def on_progress(progress: RunProgress) -> None:
            self.store.update(run_id, progress=list(progress.messages))

        console = Console(file=io.StringIO(), width=100, highlight=False)
        try:
            completed = execute_approved_run(
                orchestrator,
                agent_run,
                self.settings,
                console=console,
                report_router=report_router,
                on_progress=on_progress,
                task_mode=task_mode,
            )
            path = ensure_run_report(
                goal=agent_run.goal,
                run_id=agent_run.id,
                results=completed.results,
                workspace=self.settings.workspace,
                router=report_router,
                report_synthesizer=orchestrator.executor.report_synthesizer,
                mode=task_mode,
            )
            report_path: str | None = None
            report_name: str | None = None
            if path is not None:
                report_path = str(path.resolve())
                report_name = path.name

            current = self.store.get(run_id)
            messages = current.progress if current is not None else []
            self.store.update(
                run_id,
                status=completed.status.value,
                plan=plan_to_dict(agent_run.plan),
                node_statuses=node_statuses_from_results(completed.results),
                progress=messages,
                report_path=report_path,
                report_name=report_name,
            )
        except Exception as exc:
            self.store.update(run_id, status=RunStatus.FAILED.value, error=str(exc))
