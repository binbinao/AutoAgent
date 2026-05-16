from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from pydantic import Field
from pydantic.fields import FieldInfo
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource, SettingsConfigDict

_USER_CONFIG = Path.home() / ".autoagent" / "config.toml"


def user_config_path() -> Path:
    return _USER_CONFIG


class _UserTomlSettingsSource(PydanticBaseSettingsSource):
    def get_field_value(
        self,
        field: FieldInfo,
        field_name: str,
    ) -> tuple[Any, str, bool]:
        return None, field_name, False

    def __call__(self) -> dict[str, Any]:
        if not _USER_CONFIG.is_file():
            return {}
        with _USER_CONFIG.open("rb") as handle:
            data = tomllib.load(handle)
        return {str(key): value for key, value in data.items()}


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
            _UserTomlSettingsSource(settings_cls),
            dotenv_settings,
            env_settings,
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
    react_max_steps: int = 10
    max_context_tokens: int = 8192
    use_docker_sandbox: bool = True
    state_path: Path = Field(default_factory=lambda: Path.home() / ".autoagent" / "run_state.json")
