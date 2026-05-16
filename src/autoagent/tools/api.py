from __future__ import annotations

import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

from autoagent.models import ToolResult
from autoagent.tools.base import BaseTool, ToolExecutionError


class ApiRequestTool(BaseTool):
    name = "api.request"
    description = "Call a public HTTP API with basic SSRF protections."

    def __init__(self, timeout_seconds: float = 15.0, allow_private_hosts: bool = False) -> None:
        self.timeout_seconds = timeout_seconds
        self.allow_private_hosts = allow_private_hosts

    def run(self, args: dict[str, Any]) -> ToolResult:
        method = str(args.get("method", "GET")).upper()
        url = str(args.get("url", ""))
        headers = dict(args.get("headers", {}))
        json_body = args.get("json")

        if method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
            raise ToolExecutionError(f"Unsupported HTTP method: {method}")
        if not url:
            raise ToolExecutionError("Missing required argument: url")
        self._validate_url(url)

        try:
            with httpx.Client(timeout=self.timeout_seconds, follow_redirects=False) as client:
                response = client.request(method, url, headers=headers, json=json_body)
        except httpx.HTTPError as exc:
            raise ToolExecutionError(f"API request failed: {url}") from exc

        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            body: Any = response.json()
        else:
            body = response.text[:20_000]
        return ToolResult(
            ok=200 <= response.status_code < 400,
            output={
                "status_code": response.status_code,
                "headers": dict(response.headers),
                "body": body,
            },
            error=None if response.is_success else response.text[:2_000],
        )

    def _validate_url(self, url: str) -> None:
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ToolExecutionError("Only http and https URLs are supported")
        if not parsed.hostname:
            raise ToolExecutionError("URL must include a hostname")
        if not self.allow_private_hosts and self._is_private_host(parsed.hostname):
            raise ToolExecutionError("Private and local network hosts are blocked by default")

    def _is_private_host(self, hostname: str) -> bool:
        try:
            addresses = socket.getaddrinfo(hostname, None, proto=socket.IPPROTO_TCP)
        except socket.gaierror as exc:
            raise ToolExecutionError(f"Cannot resolve hostname: {hostname}") from exc
        for address in addresses:
            ip = ipaddress.ip_address(address[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return True
        return False
