"""Environment tools for Telegram Assistant Harness.

Requirement 3: Can read env regardless password.
Provides tools to read, list, and inspect environment variables and .env files
without censoring, masking, or failing on complex passwords/characters.
"""

from __future__ import annotations
import os
from pathlib import Path
from typing import Optional
from src.config import settings, parse_raw_env_file
from src.tools.registry import tool


@tool(description="Read the exact value of an environment variable regardless of whether it is a password, secret, or token.")
def get_env_variable(key: str) -> str:
    """Retrieve an environment variable value directly without masking."""
    val = settings.get_env(key, "")
    if val:
        return f"{key}={val}"
    # Check os.environ fallback
    if key in os.environ:
        return f"{key}={os.environ[key]}"
    return f"Environment variable '{key}' is not set."


@tool(description="List all available environment variable keys, with an optional prefix filter.")
def list_env_keys(prefix: Optional[str] = None) -> str:
    """List names of environment variables currently available."""
    keys = sorted(set(list(settings.env_vars.keys()) + list(os.environ.keys())))
    if prefix:
        keys = [k for k in keys if k.startswith(prefix.upper()) or k.startswith(prefix)]

    if not keys:
        return f"No environment variables found matching prefix '{prefix}'."

    output = [f"=== Available Environment Keys ({len(keys)}) ==="]
    output.extend(keys)
    return "\n".join(output)


@tool(description="Read a .env file and return its key-value pairs regardless of password complexity or symbols.")
def read_env_file_contents(file_path: str = ".env") -> str:
    """Parse any .env file directly and return its key-value pairs."""
    path = Path(file_path)
    if not path.is_absolute():
        path = (settings.workspace_root / path).resolve()

    if not path.exists():
        return f"Error: Environment file '{path}' does not exist."

    parsed = parse_raw_env_file(path)
    if not parsed:
        return f"Environment file '{path}' is empty or has no valid entries."

    lines = [f"=== .env Content from {path} ({len(parsed)} keys) ==="]
    for k, v in sorted(parsed.items()):
        lines.append(f"{k}={v}")

    return "\n".join(lines)


@tool(description="Set or update an environment variable in the active session and .env file.")
def set_env_variable(key: str, value: str, persist_to_file: bool = True) -> str:
    """Set an environment variable and optionally persist it to the .env file."""
    os.environ[key] = value
    settings.env_vars[key] = value

    if persist_to_file:
        env_path = settings.env_path
        lines = []
        key_found = False
        if env_path.exists():
            with open(env_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

        new_lines = []
        for line in lines:
            trimmed = line.strip()
            if trimmed.startswith(f"{key}=") or trimmed.startswith(f"export {key}="):
                new_lines.append(f'{key}="{value}"\n')
                key_found = True
            else:
                new_lines.append(line)

        if not key_found:
            if new_lines and not new_lines[-1].endswith("\n"):
                new_lines.append("\n")
            new_lines.append(f'{key}="{value}"\n')

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        return f"Success: Set {key} and persisted to {env_path}."

    return f"Success: Set {key} in active memory session."
