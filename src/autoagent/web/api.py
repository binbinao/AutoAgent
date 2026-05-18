from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.responses import Response

from autoagent.config import AgentSettings
from autoagent.web.service import RunService

_STATIC_DIR = Path(__file__).resolve().parent / "static"


class RunCreateRequest(BaseModel):
    goal: str = Field(min_length=1, max_length=4000)
    llm: bool = True
    approve: bool = True
    task_mode: str | None = None


class ConfigUpdateRequest(BaseModel):
    default_model: str | None = None
    workspace: str | None = None
    default_task_mode: str | None = None
    auto_approve: bool | None = None
    memory_path: str | None = None
    chroma_path: str | None = None
    semantic_memory_backend: str | None = None
    python_timeout_seconds: int | None = None
    use_docker_sandbox: bool | None = None
    log_level: str | None = None
    react_max_steps: int | None = None
    react_max_steps_quick: int | None = None
    max_context_tokens: int | None = None
    state_path: str | None = None
    log_path: str | None = None


def create_app(settings: AgentSettings | None = None) -> FastAPI:
    service = RunService(settings)
    app = FastAPI(title="AutoAgent", version="0.1.0")

    @app.middleware("http")
    async def disable_api_cache(request: Request, call_next) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/config")
    def config() -> dict[str, Any]:
        return service.full_config()

    @app.put("/api/config")
    def update_config(body: ConfigUpdateRequest) -> dict[str, Any]:
        updates = body.model_dump(exclude_none=True)
        if not updates:
            raise HTTPException(status_code=400, detail="No config fields provided")
        try:
            return service.update_config(updates)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/history")
    def history(limit: int = 20) -> list[dict[str, Any]]:
        return service.list_history(limit=limit)

    @app.get("/api/reports")
    def reports() -> list[dict[str, Any]]:
        return service.list_reports()

    @app.get("/api/reports/{name}")
    def report_content(name: str) -> dict[str, str]:
        try:
            body = service.read_report(name)
        except FileNotFoundError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"name": Path(name).name, "content": body}

    @app.get("/api/runs")
    def list_runs(limit: int = 20) -> list[dict[str, Any]]:
        return [record.to_dict() for record in service.store.list_recent(limit=limit)]

    @app.get("/api/runs/{run_id}")
    def get_run(run_id: str) -> dict[str, Any]:
        record = service.store.get(run_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Run not found")
        return record.to_dict()

    @app.post("/api/runs")
    def create_run(body: RunCreateRequest) -> dict[str, Any]:
        try:
            record = service.start_run(
                goal=body.goal,
                llm=body.llm,
                approve=body.approve,
                task_mode=body.task_mode,
            )
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return record.to_dict()

    @app.post("/api/runs/{run_id}/approve")
    def approve_run(run_id: str) -> dict[str, Any]:
        try:
            record = service.approve_run(run_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail="Run not found") from exc
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return record.to_dict()

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(_STATIC_DIR / "index.html")

    app.mount("/static", StaticFiles(directory=_STATIC_DIR), name="static")
    return app
