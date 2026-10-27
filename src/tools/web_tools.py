"""Website reachability checks for the assistant harness."""

from __future__ import annotations

import asyncio
from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from urllib.parse import urlsplit
from typing import Any, Dict, Optional

import httpx

from src.tools.registry import get_tool_session_id, tool


_RETRYABLE_STATUSES = {408, 425, 429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 4
_MAX_PAGE_BYTES = 256_000
_MAX_PAGE_CHARS = 30_000

# Cookies are scoped to the Telegram/CLI conversation id supplied by the
# harness, and HTTPX still enforces each cookie's domain/path/expiry rules.
# Keep jars in memory so they survive tool calls without writing credentials
# or session tokens to disk.
_SESSION_COOKIES: Dict[str, httpx.Cookies] = {}
_SESSION_LOCKS: Dict[str, asyncio.Lock] = {}


@tool(description=(
    "Check whether a website URL is reachable over HTTP or HTTPS. Follows redirects, "
    "retries temporary network failures, and reports the final HTTP status code. "
    "Use this instead of composing a curl command when asked to check a URL."
))
async def check_website(url: str) -> str:
    """Fetch a URL with redirects and retries for transient network failures."""
    candidate = url.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "Error: Provide a complete http:// or https:// URL."
    if parsed.username is not None or parsed.password is not None:
        return "Error: URLs containing embedded credentials are not supported."

    last_error: Exception | None = None
    last_status: int | None = None
    for attempt in range(_MAX_ATTEMPTS):
        try:
            # A new client per attempt forces a fresh DNS lookup and TCP/TLS
            # connection. Reusing a pool can keep retrying a stale connection
            # when a VPN route or tunnel has just recovered.
            timeout = httpx.Timeout(20.0, connect=10.0)
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                trust_env=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; WebsiteCheck/1.0)"},
            ) as client:
                async with client.stream("GET", candidate) as response:
                    last_status = response.status_code
                    if response.status_code not in _RETRYABLE_STATUSES or attempt + 1 == _MAX_ATTEMPTS:
                        return (
                            f"HTTP {response.status_code} {response.reason_phrase}\n"
                            f"Final URL: {response.url}\n"
                            f"Content-Type: {response.headers.get('content-type', 'unknown')}"
                        )
                    retry_after = _retry_after_seconds(response.headers.get("retry-after"))
        except httpx.RequestError as exc:
            last_error = exc
            retry_after = None

        if attempt + 1 < _MAX_ATTEMPTS:
            delay = retry_after if retry_after is not None else min(0.5 * (2 ** attempt), 4.0)
            await asyncio.sleep(delay)

    if last_error is not None:
        return (
            f"Network error after {_MAX_ATTEMPTS} attempts: "
            f"{type(last_error).__name__}: {last_error}. "
            "The assistant uses the host network routes and HTTP(S)_PROXY/NO_PROXY settings. "
            "Confirm the VPN is connected for this process and that its VPN DNS/routes are active."
        )
    return f"HTTP {last_status} after {_MAX_ATTEMPTS} attempts; the server kept returning a temporary error."


@tool(description=(
    "Make an HTTP request to a website while retaining its login cookies for later "
    "web_request calls in this conversation. Use this for cookie-based website login "
    "and for reading authenticated pages or navigation menus. Supports form or JSON "
    "submissions. It cannot run JavaScript or complete interactive SSO flows."
))
async def web_request(
    url: str,
    method: str = "GET",
    form_data: Optional[Dict[str, str]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
) -> str:
    """Request a page using cookies retained for this assistant conversation."""
    session_id = get_tool_session_id()
    if not session_id:
        return "Error: No assistant conversation session is available for authenticated web requests."

    candidate = url.strip()
    parsed = urlsplit(candidate)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        return "Error: Provide a complete http:// or https:// URL."
    if parsed.username is not None or parsed.password is not None:
        return "Error: URLs containing embedded credentials are not supported."
    if form_data is not None and json_data is not None:
        return "Error: Provide either form_data or json_data, not both."

    request_method = method.upper().strip()
    if request_method not in {"GET", "POST", "PUT", "PATCH", "DELETE"}:
        return "Error: method must be GET, POST, PUT, PATCH, or DELETE."

    # Lazily create a lock per conversation. The lock ensures simultaneous
    # requests in one chat do not race while updating the shared cookie jar.
    lock = _SESSION_LOCKS.setdefault(session_id, asyncio.Lock())
    async with lock:
        cookies = _SESSION_COOKIES.setdefault(session_id, httpx.Cookies())
        timeout = httpx.Timeout(20.0, connect=10.0)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                trust_env=True,
                cookies=cookies,
                headers={"User-Agent": "Mozilla/5.0 (compatible; AssistantWeb/1.0)"},
            ) as client:
                async with client.stream(
                    request_method,
                    candidate,
                    data=form_data,
                    json=json_data,
                    headers=headers,
                ) as response:
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        remaining = _MAX_PAGE_BYTES - len(body)
                        if remaining <= 0:
                            break
                        body.extend(chunk[:remaining])
                        if len(chunk) > remaining:
                            break
                    status = response.status_code
                    reason = response.reason_phrase
                    content_type = response.headers.get("content-type", "unknown")
                    final_url = response.url
                    encoding = response.encoding or "utf-8"
                    truncated = len(body) >= _MAX_PAGE_BYTES
                    # HTTPX owns a copy of the initial jar, so publish the
                    # response's updated cookies for the next tool call.
                    _SESSION_COOKIES[session_id] = httpx.Cookies(client.cookies)
            text = bytes(body).decode(encoding, errors="replace")
        except httpx.RequestError as exc:
            return f"Network error: {type(exc).__name__}. Check the URL and network connection."

    # Omit query and fragment values from the echoed URL since they may contain
    # one-time codes or other credentials.
    safe_url = str(final_url.copy_with(query=None, fragment=None))
    if len(text) > _MAX_PAGE_CHARS:
        text = text[:_MAX_PAGE_CHARS]
        truncated = True
    suffix = f"\n[Response truncated; maximum {_MAX_PAGE_CHARS} characters.]" if truncated else ""
    return (
        f"HTTP {status} {reason}\nFinal URL: {safe_url}\nContent-Type: {content_type}\n\n"
        f"{text}{suffix}"
    )


def _retry_after_seconds(value: str | None) -> float | None:
    """Parse Retry-After as seconds/date, keeping retry waits bounded."""
    if not value:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            retry_at = parsedate_to_datetime(value)
            if retry_at.tzinfo is None:
                retry_at = retry_at.replace(tzinfo=timezone.utc)
            seconds = (retry_at - datetime.now(timezone.utc)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return min(max(seconds, 0.0), 5.0)
