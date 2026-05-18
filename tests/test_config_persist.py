from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from autoagent.config import (
    CONFIG_FIELD_KEYS,
    AgentSettings,
    load_user_toml,
    settings_as_dict,
    write_user_config,
)


def test_write_user_config_merges_and_orders_keys(tmp_path: Path, monkeypatch: Any) -> None:
    import autoagent.config as config_module

    cfg = tmp_path / "config.toml"
    monkeypatch.setattr(config_module, "_USER_CONFIG", cfg)

    write_user_config({"default_model": "model-a", "auto_approve": True})
    write_user_config({"log_level": "INFO"})

    data = load_user_toml()
    assert data["default_model"] == "model-a"
    assert data["auto_approve"] is True
    assert data["log_level"] == "INFO"

    text = cfg.read_text(encoding="utf-8")
    assert text.index("default_model") < text.index("log_level")


def test_write_user_config_rejects_unknown_keys(tmp_path: Path, monkeypatch: Any) -> None:
    import autoagent.config as config_module

    cfg = tmp_path / "config.toml"
    monkeypatch.setattr(config_module, "_USER_CONFIG", cfg)

    with pytest.raises(ValueError, match="Unknown config keys"):
        write_user_config({"not_a_setting": 1})


def test_settings_as_dict_includes_all_fields() -> None:
    settings = AgentSettings()
    data = settings_as_dict(settings)
    assert set(data) == CONFIG_FIELD_KEYS
