"""Codex app-server client using credentials managed by the Codex CLI.

The assistant never reads Codex's credential files.  ``codex login --device-auth``
is performed by the operator, and this adapter starts the authenticated local
app-server over stdio for each request.
"""

from __future__ import annotations

import asyncio
import json
import logging
import shutil
import subprocess
import time
from typing import Any, Dict, List, Optional

from src.config import settings
from src.models.base import BaseModelClient, Message, ModelResponse, ToolCall

logger = logging.getLogger(__name__)


class CodexCliError(RuntimeError):
    """A safe, user-facing Codex CLI integration error."""


class CodexCliClient(BaseModelClient):
    def __init__(self, executable: Optional[str] = None, timeout: float = 120.0):
        self.executable = executable or settings.codex_cli_path
        self.timeout = timeout
        self._readiness_result: Optional[tuple[bool, str]] = None
        self._readiness_checked_at = 0.0

    @staticmethod
    def is_available(executable: str = "codex") -> bool:
        return bool(shutil.which(executable))

    @classmethod
    def login_status(cls, executable: str = "codex") -> tuple[bool, str]:
        """Check the CLI-managed login without reading credential files.

        The CLI owns device-auth credentials.  Running ``codex login status``
        is the supported, non-interactive way to determine whether the bot's
        process can use them.
        """
        if not cls.is_available(executable):
            return False, f"Codex CLI not found at '{executable}'"

        try:
            completed = subprocess.run(
                [executable, "login", "status"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return False, f"Unable to check Codex CLI login: {exc}"

        # Do not include command output here: some CLI versions can add
        # account details to it, and status is only used as a readiness check.
        status_text = f"{completed.stdout}\n{completed.stderr}".lower()
        if completed.returncode == 0 and "logged in" in status_text:
            return True, "Codex CLI login is active"
        return False, "Codex CLI is not logged in; run `codex login --device-auth` as the bot user"

    @classmethod
    def readiness(cls, executable: str = "codex") -> tuple[bool, str]:
        """Return whether the executable and its CLI-managed login are ready."""
        return cls.login_status(executable)

    async def _async_login_status(self) -> tuple[bool, str]:
        """Check CLI-managed login without blocking the event loop."""
        if not self.is_available(self.executable):
            return False, f"Codex CLI not found at '{self.executable}'"
        try:
            proc = await asyncio.create_subprocess_exec(
                self.executable, "login", "status",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                return False, "Timed out checking Codex CLI login"
        except OSError as exc:
            return False, f"Unable to check Codex CLI login: {exc}"

        status_text = f"{stdout.decode(errors='replace')}\n{stderr.decode(errors='replace')}".lower()
        if proc.returncode == 0 and "logged in" in status_text:
            return True, "Codex CLI login is active"
        return False, "Codex CLI is not logged in; run `codex login --device-auth` as the bot user"

    async def _check_readiness(self) -> tuple[bool, str]:
        """Check CLI login asynchronously and cache successful results."""
        now = time.monotonic()
        cache_seconds = settings.codex_readiness_cache_seconds
        if (
            self._readiness_result is not None
            and self._readiness_result[0]
            and now - self._readiness_checked_at < cache_seconds
        ):
            return self._readiness_result

        result = await self._async_login_status()
        self._readiness_result = result
        self._readiness_checked_at = time.monotonic()
        return result

    @staticmethod
    def _input(messages: List[Message]) -> str:
        parts = []
        for msg in messages:
            content = msg.content or ""
            if msg.role == "tool":
                parts.append(f"[tool result {msg.tool_call_id or msg.name or ''}]\n{content}")
            elif msg.role == "assistant" and msg.tool_calls:
                calls = ", ".join(f"{c.name}({json.dumps(c.arguments)})" for c in msg.tool_calls)
                parts.append(f"[assistant tool calls: {calls}]\n{content}")
            else:
                parts.append(f"[{msg.role}]\n{content}")
        return "\n\n".join(parts)

    @staticmethod
    def _initialize_params() -> Dict[str, Any]:
        """Declare the protocol features needed by this app-server client."""
        return {
            "clientInfo": {
                "name": "telegram-assistant",
                "title": "Telegram Assistant",
                "version": "1.0",
            },
            # ``dynamicTools`` on ``thread/start`` is an experimental
            # app-server field. Newer Codex CLI releases reject it unless
            # this capability was explicitly negotiated during initialize.
            "capabilities": {"experimentalApi": True},
        }

    async def _rpc(self, proc: asyncio.subprocess.Process, request_id: int, method: str, params: Dict[str, Any]) -> Dict[str, Any]:
        payload = json.dumps({"jsonrpc": "2.0", "id": request_id, "method": method, "params": params}) + "\n"
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(payload.encode())
        await proc.stdin.drain()
        while True:
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), self.timeout)
            except asyncio.TimeoutError as exc:
                raise CodexCliError(f"Timed out waiting for Codex {method} response") from exc
            if not line:
                stderr = (await proc.stderr.read()).decode(errors="replace") if proc.stderr else ""
                raise self._app_server_error(stderr)
            try:
                message = json.loads(line)
            except json.JSONDecodeError:
                continue
            if message.get("id") == request_id:
                if "error" in message:
                    raise CodexCliError(str(message["error"].get("message", "Codex request failed")))
                return message.get("result", {})

    async def _notify(self, proc: asyncio.subprocess.Process, method: str, params: Dict[str, Any]) -> None:
        assert proc.stdin is not None
        proc.stdin.write((json.dumps({"jsonrpc": "2.0", "method": method, "params": params}) + "\n").encode())
        await proc.stdin.drain()

    @staticmethod
    def _app_server_error(stderr: str) -> CodexCliError:
        """Translate known local-runtime failures without exposing credentials."""
        normalized = stderr.lower()
        if "user namespaces" in normalized or "unprivileged_userns" in normalized:
            return CodexCliError(
                "Codex CLI is logged in, but its Linux sandbox cannot start because "
                "unprivileged user namespaces are blocked. Enable bubblewrap/user namespaces "
                "or the distribution's bwrap AppArmor profile, then restart the bot."
            )
        detail = stderr.strip().replace("\n", " ")[:200]
        return CodexCliError(f"Codex app-server exited unexpectedly{(': ' + detail) if detail else ''}")

    @staticmethod
    def _item_text(item: Dict[str, Any]) -> str:
        """Extract text from either supported app-server message-item shape."""
        text = item.get("text") or item.get("content") or ""
        if isinstance(text, list):
            return "".join(x.get("text", "") for x in text if isinstance(x, dict))
        return str(text)

    async def _collect_turn(self, proc: asyncio.subprocess.Process) -> tuple[str, List[ToolCall]]:
        """Read notifications for a started turn until its terminal status.

        App-server stdout contains JSON-RPC replies as well as notifications.
        In particular, a reply with an error must not be mistaken for an
        unrelated notification and leave the caller waiting for a timeout.
        """
        assert proc.stdout is not None
        messages: Dict[str, Dict[str, Any]] = {}
        message_order: List[str] = []
        calls: List[ToolCall] = []

        def message_state(item_id: str) -> Dict[str, Any]:
            if item_id not in messages:
                messages[item_id] = {"deltas": [], "completed_text": ""}
                message_order.append(item_id)
            return messages[item_id]

        while True:
            try:
                line = await asyncio.wait_for(proc.stdout.readline(), self.timeout)
            except asyncio.TimeoutError as exc:
                raise CodexCliError("Timed out waiting for Codex turn completion") from exc
            if not line:
                stderr = (await proc.stderr.read()).decode(errors="replace") if proc.stderr else ""
                raise self._app_server_error(stderr)
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            # Dynamic tools are client-executed RPC requests from app-server.
            # They carry both a method and an id, so handle them before
            # filtering ordinary JSON-RPC responses. Without this branch the
            # server waits for a tool result until the turn times out.
            if event.get("method") == "item/tool/call" and "id" in event:
                params = event.get("params", {})
                if not isinstance(params, dict):
                    params = {}
                tool_name = str(params.get("tool", ""))
                arguments = params.get("arguments", {})
                if not isinstance(arguments, dict):
                    result_text = "Error: Tool arguments must be a JSON object."
                    success = False
                else:
                    try:
                        # Import lazily so the model adapter remains usable
                        # without importing/registering the application's tool
                        # modules at module load time.
                        from src.tools.registry import registry

                        result_text = await registry.dispatch(tool_name, arguments)
                        success = not result_text.lower().startswith(("error", "permission error"))
                    except Exception as exc:
                        logger.exception("Codex dynamic tool failed: %s", tool_name)
                        result_text = f"Error executing tool '{tool_name}': {type(exc).__name__}: {exc}"
                        success = False

                assert proc.stdin is not None
                reply = {
                    "jsonrpc": "2.0",
                    "id": event["id"],
                    "result": {
                        "contentItems": [{"type": "inputText", "text": str(result_text)}],
                        "success": success,
                    },
                }
                proc.stdin.write((json.dumps(reply) + "\n").encode())
                await proc.stdin.drain()
                continue

            # Ordinary JSON-RPC responses have an id but no method. Errors are
            # terminal; successful acknowledgements can be ignored here.
            if "id" in event:
                error = event.get("error")
                if error:
                    detail = error.get("message") if isinstance(error, dict) else None
                    raise CodexCliError(detail or "Codex request failed")
                continue

            method = event.get("method", "")
            params = event.get("params", {})
            if not isinstance(params, dict):
                continue

            if method == "item/agentMessage/delta":
                # itemId is part of the current protocol. Retain a fallback
                # for older versions which omitted it for a single message.
                item_id = str(params.get("itemId") or params.get("id") or "__agent_message__")
                message_state(item_id)["deltas"].append(str(params.get("delta", "")))
                continue

            item = params.get("item", {})
            if isinstance(item, dict):
                item_type = item.get("type", "")
                if item_type in ("agentMessage", "message"):
                    item_id = str(item.get("id") or params.get("itemId") or "__agent_message__")
                    state = message_state(item_id)
                    # A completed item is a fallback only. Its text duplicates
                    # the deltas emitted for the same item on newer CLIs.
                    state["completed_text"] = self._item_text(item)
                elif item_type in ("functionCall", "function_call"):
                    args = item.get("arguments", {})
                    if isinstance(args, str):
                        try:
                            args = json.loads(args) if args else {}
                        except json.JSONDecodeError:
                            args = {}
                    if not isinstance(args, dict):
                        args = {}
                    calls.append(ToolCall(id=item.get("callId") or item.get("id", ""), name=item.get("name", ""), arguments=args))

            if method in ("turn/completed", "turn/complete"):
                turn = params.get("turn", {})
                status = turn.get("status") if isinstance(turn, dict) else None
                if status != "completed":
                    error = turn.get("error", {}) if isinstance(turn, dict) else {}
                    detail = error.get("message") if isinstance(error, dict) else None
                    raise CodexCliError(detail or f"Codex turn {status or 'did not complete'}")
                break

        content = "".join(
            "".join(messages[item_id]["deltas"]) or messages[item_id]["completed_text"]
            for item_id in message_order
        )
        return content, calls

    async def _cleanup_process(self, proc: asyncio.subprocess.Process) -> None:
        """Terminate and reap the app-server on every exit path."""
        if proc.returncode is not None:
            return
        try:
            proc.terminate()
        except ProcessLookupError:
            # The child exited after the returncode check; it still needs to
            # be reaped below.
            pass
        try:
            await asyncio.wait_for(proc.wait(), timeout=5)
        except asyncio.TimeoutError:
            proc.kill()
            await proc.wait()

    async def generate(self, messages: List[Message], tools: Optional[List[Dict[str, Any]]] = None,
                       model_name: Optional[str] = None, temperature: Optional[float] = None,
                       max_tokens: Optional[int] = None) -> ModelResponse:
        if not self.is_available(self.executable):
            raise CodexCliError(f"Codex CLI not found at '{self.executable}'. Install it and run `codex login --device-auth`.")

        logged_in, login_message = await self._check_readiness()
        if not logged_in:
            raise CodexCliError(login_message)

        try:
            proc = await asyncio.create_subprocess_exec(
                self.executable, "app-server", "--stdio",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
        except OSError as exc:
            raise CodexCliError(f"Unable to start Codex CLI: {exc}") from exc
        try:
            await self._rpc(proc, 1, "initialize", self._initialize_params())
            await self._notify(proc, "initialized", {})
            thread = await self._rpc(proc, 3, "thread/start", {
                "model": model_name or settings.openai_model,
                "ephemeral": True,
                "cwd": str(settings.workspace_root),
                "approvalPolicy": "never",
                "sandbox": "read-only",
                # Older app-server versions accept dynamicTools here. Newer
                # versions may ignore unknown fields, while keeping this field
                # preserves the assistant's existing function-tool loop on
                # compatible CLI releases.
                "dynamicTools": [
                    {"type": "function", "name": t["function"]["name"],
                     "description": t["function"].get("description", ""),
                     "inputSchema": t["function"].get("parameters", {})}
                    for t in (tools or []) if t.get("type") == "function"
                ],
            })
            thread_id = thread.get("thread", {}).get("id") or thread.get("threadId")
            if not thread_id:
                raise CodexCliError("Codex app-server did not return a thread id")
            await self._rpc(proc, 4, "turn/start", {"threadId": thread_id, "input": [{"type": "text", "text": self._input(messages)}]})
            content, calls = await self._collect_turn(proc)
            return ModelResponse(content=content, tool_calls=calls, finish_reason="stop", raw=None)
        finally:
            await self._cleanup_process(proc)
