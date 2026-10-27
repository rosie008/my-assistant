"""Bash execution tool for Telegram Assistant Harness."""

from __future__ import annotations
import asyncio
import os
import signal
from src.config import settings
from src.tools.registry import tool


@tool(description="Execute a bash shell command in the workspace directory. Output is captured.")
async def execute_bash(command: str) -> str:
    """Execute a bash command with timeout and safety checks."""
    # Check forbidden commands
    lower_cmd = command.strip().lower()
    for forbidden in settings.forbidden_commands:
        if forbidden.lower() in lower_cmd:
            return f"Error: Command execution blocked. Matches forbidden rule '{forbidden}' in LIMITATIONS.md."

    timeout = settings.command_timeout_seconds
    try:
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=str(settings.workspace_root),
            start_new_session=True,
        )

        communicate_task = asyncio.create_task(proc.communicate())
        try:
            stdout_data, stderr_data = await asyncio.wait_for(asyncio.shield(communicate_task), timeout=timeout)
        except asyncio.TimeoutError:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                pass
            try:
                await asyncio.wait_for(asyncio.shield(communicate_task), timeout=2)
            except asyncio.TimeoutError:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except (ProcessLookupError, PermissionError):
                    pass
                await communicate_task
            return f"Error: Command timed out after {timeout} seconds."

        stdout_str = stdout_data.decode("utf-8", errors="replace")
        stderr_str = stderr_data.decode("utf-8", errors="replace")

        exit_code = proc.returncode
        result = []
        if stdout_str:
            result.append(f"STDOUT:\n{stdout_str.rstrip()}")
        if stderr_str:
            result.append(f"STDERR:\n{stderr_str.rstrip()}")
        if exit_code != 0:
            result.append(f"Exit code: {exit_code}")

        combined = "\n".join(result) if result else "(command produced no output)"

        max_len = int(settings.limitations_md_settings.get("max_output_length", 10000))
        if len(combined) > max_len:
            combined = combined[:max_len] + f"\n... (Output truncated at {max_len} characters)"

        return combined

    except Exception as e:
        return f"Error executing bash command: {type(e).__name__}: {str(e)}"
