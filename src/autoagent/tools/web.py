from __future__ import annotations

from typing import Any
from urllib.parse import quote_plus, urlparse

import httpx
from bs4 import BeautifulSoup

from autoagent.models import ToolResult
from autoagent.tools.base import BaseTool, ToolExecutionError


class WebFetchTool(BaseTool):
    name = "web.fetch"
    description = "Fetch a public HTTP(S) page and return extracted text."

    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self.timeout_seconds = timeout_seconds

    def run(self, args: dict[str, Any]) -> ToolResult:
        url = str(args.get("url", ""))
        if not url:
            raise ToolExecutionError("Missing required argument: url")
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ToolExecutionError("Only http and https URLs are supported")

        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = client.get(url)
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"Failed to fetch URL: {url}") from exc

        soup = BeautifulSoup(response.text, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = "\n".join(line.strip() for line in soup.get_text("\n").splitlines() if line.strip())
        return ToolResult(output={"url": str(response.url), "text": text[:20_000]})


class WebSearchTool(BaseTool):
    name = "web.search"
    description = "Search the web through DuckDuckGo HTML results."

    def __init__(self, timeout_seconds: float = 15.0) -> None:
        self.timeout_seconds = timeout_seconds

    def run(self, args: dict[str, Any]) -> ToolResult:
        query = str(args.get("query", ""))
        limit = int(args.get("limit", 5))
        if not query:
            raise ToolExecutionError("Missing required argument: query")

        url = f"https://duckduckgo.com/html/?q={quote_plus(query)}"
        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=True) as client:
                response = client.get(url, headers={"User-Agent": "AutoAgent/0.1"})
                response.raise_for_status()
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"Search request failed: {query}") from exc

        soup = BeautifulSoup(response.text, "html.parser")
        results: list[dict[str, str]] = []
        for link in soup.select("a.result__a")[:limit]:
            href = link.get("href")
            title = link.get_text(" ", strip=True)
            if href and title:
                results.append({"title": title, "url": str(href)})
        return ToolResult(output={"query": query, "results": results})
