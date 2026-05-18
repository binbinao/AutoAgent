"""Output locale: language for planner, ReAct, and synthesized reports."""

from __future__ import annotations

from enum import StrEnum


class OutputLocale(StrEnum):
    EN = "en"
    ZH = "zh"


def parse_output_locale(
    value: str | OutputLocale | None,
    *,
    default: OutputLocale = OutputLocale.EN,
) -> OutputLocale:
    if value is None:
        return default
    if isinstance(value, OutputLocale):
        return value
    normalized = value.strip().lower()
    for locale in OutputLocale:
        if normalized == locale.value:
            return locale
    aliases = {
        "en-us": OutputLocale.EN,
        "en_gb": OutputLocale.EN,
        "english": OutputLocale.EN,
        "zh-cn": OutputLocale.ZH,
        "zh_cn": OutputLocale.ZH,
        "chinese": OutputLocale.ZH,
        "cn": OutputLocale.ZH,
    }
    if normalized in aliases:
        return aliases[normalized]
    raise ValueError(f"Unknown output locale {value!r}; use 'en' or 'zh'")
