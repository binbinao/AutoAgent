from __future__ import annotations

import pytest

from autoagent.output_locale import OutputLocale, parse_output_locale
from autoagent.prompts import (
    planner_system_prompt,
    react_system_prompt,
    report_synthesis_prompt,
)
from autoagent.task_mode import TaskMode


def test_parse_output_locale_values() -> None:
    assert parse_output_locale("en") is OutputLocale.EN
    assert parse_output_locale("zh") is OutputLocale.ZH
    assert parse_output_locale("zh-cn") is OutputLocale.ZH


def test_parse_output_locale_rejects_unknown() -> None:
    with pytest.raises(ValueError, match="Unknown output locale"):
        parse_output_locale("fr")


@pytest.mark.parametrize(
    ("locale", "needle"),
    [
        (OutputLocale.EN, "English"),
        (OutputLocale.ZH, "简体中文"),
    ],
)
def test_report_synthesis_prompt_locale(locale: OutputLocale, needle: str) -> None:
    prompt = report_synthesis_prompt(TaskMode.RESEARCH, locale=locale)
    assert needle in prompt


def test_planner_prompt_english_descriptions() -> None:
    prompt = planner_system_prompt(TaskMode.RESEARCH, locale=OutputLocale.EN)
    assert "Write every node description in English." in prompt


def test_planner_prompt_chinese_descriptions() -> None:
    prompt = planner_system_prompt(TaskMode.RESEARCH, locale=OutputLocale.ZH)
    assert "简体中文" in prompt


def test_react_research_prompt_locale_headings() -> None:
    en = react_system_prompt(TaskMode.RESEARCH, locale=OutputLocale.EN)
    zh = react_system_prompt(TaskMode.RESEARCH, locale=OutputLocale.ZH)
    assert "Executive summary" in en
    assert "执行摘要" in zh
