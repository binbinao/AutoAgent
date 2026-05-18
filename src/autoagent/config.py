from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any, Literal

from pydantic import Field
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

_USER_CONFIG = Path.home() / ".autoagent" / "config.toml"

ConfigFieldType = Literal["string", "path", "bool", "int", "select"]

CONFIG_FIELD_SPECS: tuple[dict[str, Any], ...] = (
    {
        "key": "default_model",
        "type": "string",
        "env": "AUTOAGENT_DEFAULT_MODEL",
        "description": "Default LLM model (LiteLLM id, e.g. openai/gpt-4o-mini).",
    },
    {
        "key": "workspace",
        "type": "path",
        "env": "AUTOAGENT_WORKSPACE",
        "description": "Workspace root for file tools and reports.",
    },
    {
        "key": "default_task_mode",
        "type": "select",
        "options": ["research", "quick"],
        "env": "AUTOAGENT_DEFAULT_TASK_MODE",
        "description": "Default task mode when not specified.",
    },
    {
        "key": "default_tool_preset",
        "type": "select",
        "options": ["minimal", "web-research", "full"],
        "env": "AUTOAGENT_DEFAULT_TOOL_PRESET",
        "description": "Default tool preset when not overridden (minimal, web-research, full).",
    },
    {
        "key": "enabled_tools",
        "type": "string",
        "env": "AUTOAGENT_ENABLED_TOOLS",
        "description": "Comma-separated tool names; overrides presets when set.",
    },
    {
        "key": "auto_approve",
        "type": "bool",
        "env": "AUTOAGENT_AUTO_APPROVE",
        "description": "Automatically approve plans without manual confirmation.",
    },
    {
        "key": "memory_path",
        "type": "path",
        "env": "AUTOAGENT_MEMORY_PATH",
        "description": "SQLite episodic memory database path.",
    },
    {
        "key": "chroma_path",
        "type": "path",
        "env": "AUTOAGENT_CHROMA_PATH",
        "description": "ChromaDB data directory (semantic memory).",
    },
    {
        "key": "semantic_memory_backend",
        "type": "select",
        "options": ["memory", "chroma"],
        "env": "AUTOAGENT_SEMANTIC_MEMORY_BACKEND",
        "description": "Semantic memory backend: in-process or ChromaDB.",
    },
    {
        "key": "python_timeout_seconds",
        "type": "int",
        "env": "AUTOAGENT_PYTHON_TIMEOUT_SECONDS",
        "description": "Timeout for python.run sandbox (seconds).",
    },
    {
        "key": "use_docker_sandbox",
        "type": "bool",
        "env": "AUTOAGENT_USE_DOCKER_SANDBOX",
        "description": "Prefer Docker for python.run when available.",
    },
    {
        "key": "log_level",
        "type": "select",
        "options": ["DEBUG", "INFO", "WARNING", "ERROR"],
        "env": "AUTOAGENT_LOG_LEVEL",
        "description": "Application log level.",
    },
    {
        "key": "react_max_steps",
        "type": "int",
        "env": "AUTOAGENT_REACT_MAX_STEPS",
        "description": "Max ReAct steps per node (research mode).",
    },
    {
        "key": "react_max_steps_quick",
        "type": "int",
        "env": "AUTOAGENT_REACT_MAX_STEPS_QUICK",
        "description": "Max ReAct steps per node (quick mode).",
    },
    {
        "key": "max_context_tokens",
        "type": "int",
        "env": "AUTOAGENT_MAX_CONTEXT_TOKENS",
        "description": "Context window budget for prompts.",
    },
    {
        "key": "state_path",
        "type": "path",
        "env": "AUTOAGENT_STATE_PATH",
        "description": "Detached run state snapshot file.",
    },
    {
        "key": "log_path",
        "type": "path",
        "env": "AUTOAGENT_LOG_PATH",
        "description": "Run log file path.",
    },
)

CONFIG_FIELD_KEYS: frozenset[str] = frozenset(spec["key"] for spec in CONFIG_FIELD_SPECS)


def user_config_path() -> Path:
    return _USER_CONFIG


def load_user_toml() -> dict[str, Any]:
    if not _USER_CONFIG.is_file():
        return {}
    with _USER_CONFIG.open("rb") as handle:
        data = tomllib.load(handle)
    return {str(key): value for key, value in data.items()}


def _format_toml_value(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, Path):
        value = str(value)
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    msg = f"Unsupported TOML value type: {type(value)!r}"
    raise TypeError(msg)


def write_user_config(updates: dict[str, Any]) -> Path:
    """Merge updates into ~/.autoagent/config.toml and return the path."""
    unknown = set(updates) - CONFIG_FIELD_KEYS
    if unknown:
        msg = f"Unknown config keys: {', '.join(sorted(unknown))}"
        raise ValueError(msg)

    merged = load_user_toml()
    for key, value in updates.items():
        merged[key] = value

    lines: list[str] = []
    for spec in CONFIG_FIELD_SPECS:
        key = spec["key"]
        if key not in merged:
            continue
        lines.append(f"{key} = {_format_toml_value(merged[key])}")
    lines.append("")

    _USER_CONFIG.parent.mkdir(parents=True, exist_ok=True)
    _USER_CONFIG.write_text("\n".join(lines), encoding="utf-8")
    return _USER_CONFIG


class _UserTomlSettingsSource(PydanticBaseSettingsSource):
    def get_field_value(
        self,
        field: FieldInfo,
        field_name: str,
    ) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        return load_user_toml()


class AgentSettings(BaseSettings):
    """Layered: defaults → ~/.autoagent/config.toml → .env → AUTOAGENT_* env vars."""

    model_config = SettingsConfigDict(
        env_prefix="AUTOAGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        return (
            init_settings,
            env_settings,
            dotenv_settings,
            _UserTomlSettingsSource(settings_cls),
            file_secret_settings,
        )

    workspace: Path = Field(default_factory=Path.cwd)
    default_model: str = "gpt-4o-mini"
    memory_path: Path = Field(default_factory=lambda: Path.home() / ".autoagent" / "memory.db")
    chroma_path: Path = Field(default_factory=lambda: Path.home() / ".autoagent" / "chroma")
    auto_approve: bool = False
    python_timeout_seconds: int = 10
    log_level: str = "WARNING"
    semantic_memory_backend: str = "memory"  # "memory" | "chroma"
    default_task_mode: str = "research"
    default_tool_preset: str = "web-research"
    enabled_tools: str | None = None
    react_max_steps: int = 15
    react_max_steps_quick: int = 8
    max_context_tokens: int = 8192
    use_docker_sandbox: bool = True
    state_path: Path = Field(default_factory=lambda: Path.home() / ".autoagent" / "run_state.json")
    log_path: Path = Field(default_factory=lambda: Path.home() / ".autoagent" / "run.log")


def settings_as_dict(settings: AgentSettings) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for spec in CONFIG_FIELD_SPECS:
        key = spec["key"]
        raw = getattr(settings, key)
        if isinstance(raw, Path):
            data[key] = str(raw.resolve())
        else:
            data[key] = raw
    return data
