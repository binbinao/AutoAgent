from __future__ import annotations

import shutil
import subprocess  # nosec B404
import sys
import tempfile
from pathlib import Path
from typing import Any

from autoagent.models import ToolResult
from autoagent.tools.base import BaseTool, ToolExecutionError


def _docker_bin() -> str | None:
    return shutil.which("docker")


def docker_available() -> bool:
    docker_bin = _docker_bin()
    if docker_bin is None:
        return False
    try:
        completed = subprocess.run(  # noqa: S603  # nosec B603
            [docker_bin, "info"],
            capture_output=True,
            timeout=5,
            check=False,
            shell=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return completed.returncode == 0


class PythonSandboxTool(BaseTool):
    name = "python.run"
    description = (
        "Run Python code in Docker when available, otherwise an isolated subprocess."
    )

    def __init__(
        self,
        workspace: Path | str,
        timeout_seconds: int = 10,
        *,
        use_docker: bool = True,
    ) -> None:
        self.workspace = Path(workspace).expanduser().resolve()
        self.timeout_seconds = timeout_seconds
        self.use_docker = use_docker
        self.workspace.mkdir(parents=True, exist_ok=True)

    def run(self, args: dict[str, Any]) -> ToolResult:
        code = str(args.get("code", ""))
        if not code:
            raise ToolExecutionError("Missing required argument: code")

        if self.use_docker and docker_available():
            return self._run_docker(code)
        return self._run_subprocess(code)

    def _run_docker(self, code: str) -> ToolResult:
        docker_bin = _docker_bin()
        if docker_bin is None:
            return self._run_subprocess(code)
        try:
            completed = subprocess.run(  # noqa: S603  # nosec B603
                [
                    docker_bin,
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "-v",
                    f"{self.workspace}:/work",
                    "-w",
                    "/work",
                    "python:3.11-slim",
                    "python",
                    "-I",
                    "-c",
                    code,
                ],
                capture_output=True,
                text=True,
                timeout=self.timeout_seconds,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise ToolExecutionError("Python execution timed out (docker)") from exc

        return ToolResult(
            ok=completed.returncode == 0,
            output={
                "runtime": "docker",
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            },
            error=completed.stderr if completed.returncode != 0 else None,
        )

    def _run_subprocess(self, code: str) -> ToolResult:
        with tempfile.TemporaryDirectory(dir=self.workspace) as tmp_dir:
            script_path = Path(tmp_dir) / "main.py"
            script_path.write_text(code, encoding="utf-8")
            try:
                completed = subprocess.run(  # noqa: S603  # nosec B603
                    [sys.executable, "-I", str(script_path)],
                    cwd=self.workspace,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout_seconds,
                    check=False,
                    shell=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise ToolExecutionError("Python execution timed out") from exc

        return ToolResult(
            ok=completed.returncode == 0,
            output={
                "runtime": "subprocess",
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            },
            error=completed.stderr if completed.returncode != 0 else None,
        )
