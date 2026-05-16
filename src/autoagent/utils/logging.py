from __future__ import annotations

import sys
from contextvars import ContextVar
from uuid import uuid4

from loguru import logger

_trace_id: ContextVar[str] = ContextVar("trace_id", default="")


def get_trace_id() -> str:
    """Return the current trace ID (empty string if unset)."""
    return _trace_id.get()


def new_trace_id() -> str:
    """Generate a fresh trace ID, store it in context, and return it."""
    tid = str(uuid4())[:8]
    _trace_id.set(tid)
    return tid


def _patcher_trace_id(record: dict) -> None:
    record["extra"].setdefault("trace_id", get_trace_id() or "-")


def configure_logging(level: str = "WARNING") -> None:
    """Configure loguru with a compact, human-readable format and trace_id in each line."""
    logger.remove()
    logger.configure(patcher=_patcher_trace_id)
    logger.add(
        sys.stderr,
        level=level,
        format="{time:HH:mm:ss} | {level: <8} | {extra[trace_id]} | {function} | {message}",
        colorize=False,
    )


__all__ = ["configure_logging", "get_trace_id", "logger", "new_trace_id"]
