from __future__ import annotations

from typing import Any

from autoagent.models import ToolResult
from autoagent.tools.base import BaseTool, ToolExecutionError


class BrowserSnapshotTool(BaseTool):
    name = "browser.snapshot"
    description = "Open a page with Playwright and return its title and visible text."

    def run(self, args: dict[str, Any]) -> ToolResult:
        url = str(args.get("url", ""))
        if not url:
            raise ToolExecutionError("Missing required argument: url")

        try:
            from playwright.sync_api import sync_playwright  # type: ignore[import-not-found]
        except ImportError as exc:
            raise ToolExecutionError(
                "Playwright is not installed. Run `uv sync --extra browser` first."
            ) from exc

        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url, wait_until="networkidle")
            title = page.title()
            text = page.locator("body").inner_text(timeout=5_000)
            browser.close()

        return ToolResult(output={"url": url, "title": title, "text": text[:20_000]})
