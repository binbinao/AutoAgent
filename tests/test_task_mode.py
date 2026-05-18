from __future__ import annotations

import pytest

from autoagent.task_mode import TaskMode, parse_task_mode


def test_parse_task_mode_values() -> None:
    assert parse_task_mode("quick") is TaskMode.QUICK
    assert parse_task_mode("research") is TaskMode.RESEARCH
    assert parse_task_mode(TaskMode.QUICK) is TaskMode.QUICK


def test_parse_task_mode_aliases() -> None:
    assert parse_task_mode("light") is TaskMode.QUICK
    assert parse_task_mode("deep") is TaskMode.RESEARCH


def test_parse_task_mode_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown task mode"):
        parse_task_mode("turbo")
