"""Task mode: lightweight quick runs vs deep research workflows."""

from __future__ import annotations

from enum import StrEnum


class TaskMode(StrEnum):
    """How AutoAgent plans and reports for a goal."""

    QUICK = "quick"
    RESEARCH = "research"


def parse_task_mode(
    value: str | TaskMode | None,
    *,
    default: TaskMode = TaskMode.RESEARCH,
) -> TaskMode:
    if value is None:
        return default
    if isinstance(value, TaskMode):
        return value
    normalized = value.strip().lower()
    for mode in TaskMode:
        if normalized == mode.value:
            return mode
    aliases = {
        "light": TaskMode.QUICK,
        "lite": TaskMode.QUICK,
        "fast": TaskMode.QUICK,
        "deep": TaskMode.RESEARCH,
        "full": TaskMode.RESEARCH,
    }
    if normalized in aliases:
        return aliases[normalized]
    raise ValueError(f"Unknown task mode {value!r}; use 'quick' or 'research'")
