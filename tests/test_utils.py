from __future__ import annotations

import pytest

from autoagent.utils.logging import configure_logging, get_trace_id, new_trace_id
from autoagent.utils.tokens import count_tokens_approx, fits_in_context, truncate_to_tokens


def test_new_trace_id_generates_unique_ids() -> None:
    a = new_trace_id()
    b = new_trace_id()

    assert len(a) == 8
    assert a != b


def test_get_trace_id_returns_current_id() -> None:
    tid = new_trace_id()

    assert get_trace_id() == tid


def test_configure_logging_does_not_raise() -> None:
    configure_logging("ERROR")


def test_configure_logging_includes_trace_id(capsys: pytest.CaptureFixture[str]) -> None:
    tid = new_trace_id()
    configure_logging("INFO")
    from loguru import logger

    logger.info("probe-message")
    captured = capsys.readouterr()
    assert tid in captured.err
    assert "probe-message" in captured.err


def test_count_tokens_approx_at_least_one() -> None:
    assert count_tokens_approx("") >= 1
    assert count_tokens_approx("hello world") > 0


def test_fits_in_context_accepts_short_messages() -> None:
    messages = [{"role": "user", "content": "hi"}]

    assert fits_in_context(messages, max_tokens=100) is True


def test_fits_in_context_rejects_long_messages() -> None:
    long_content = "a" * 10_000
    messages = [{"role": "user", "content": long_content}]

    assert fits_in_context(messages, max_tokens=10) is False


def test_truncate_to_tokens_leaves_short_text_unchanged() -> None:
    text = "short"

    assert truncate_to_tokens(text, max_tokens=100) == text


def test_truncate_to_tokens_truncates_long_text() -> None:
    text = "a" * 1_000

    result = truncate_to_tokens(text, max_tokens=10)

    assert len(result) < len(text)
    assert result.endswith("[truncated]")
