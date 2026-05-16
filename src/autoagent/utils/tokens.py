from __future__ import annotations

_CHARS_PER_TOKEN = 4


def count_tokens_approx(text: str) -> int:
    """Rough token count: ~4 chars per token (GPT-style)."""
    return max(1, len(text) // _CHARS_PER_TOKEN)


def fits_in_context(messages: list[dict[str, str]], max_tokens: int = 4_096) -> bool:
    """Return True if the total approximate token count is within *max_tokens*."""
    total = sum(count_tokens_approx(m.get("content", "")) for m in messages)
    return total <= max_tokens


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate *text* to at most *max_tokens* (approximate)."""
    max_chars = max_tokens * _CHARS_PER_TOKEN
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…[truncated]"


__all__ = ["count_tokens_approx", "fits_in_context", "truncate_to_tokens"]
