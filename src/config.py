"""Configuration loader for Telegram Assistant.

Loads:
1. Environment variables from `.env` regardless of passwords/special characters.
2. Configuration settings from `CONFIG.md`.
3. Limitations and boundaries from `LIMITATIONS.md`.
4. Base system persona from `SYSTEM_PROMPT.md`.
"""

from __future__ import annotations
import os
import re
import json
from pathlib import Path
from typing import Any, Dict, List, Optional
from dotenv import dotenv_values, load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_MD_PATH = BASE_DIR / "CONFIG.md"
LIMITATIONS_MD_PATH = BASE_DIR / "LIMITATIONS.md"
SYSTEM_PROMPT_MD_PATH = BASE_DIR / "SYSTEM_PROMPT.md"
ENV_PATH = BASE_DIR / ".env"


def parse_raw_env_file(filepath: Path) -> Dict[str, str]:
    """Robustly parse .env file preserving complex passwords and symbols.

    Handles:
    - Quoted values ("...", '...')
    - Passwords containing #, $, =, quotes, symbols
    - Unquoted values with symbols
    - Comments only when starting with # at line start or preceded by whitespace outside quotes
    """
    if not filepath.exists():
        return {}

    env_dict: Dict[str, str] = {}
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        if line.startswith("export "):
            line = line[len("export "):].strip()

        # Find the first '='
        if "=" not in line:
            continue

        key, val = line.split("=", 1)
        key = key.strip()
        val = val.strip()

        # Handle quoted values
        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
            val = val[1:-1]
        else:
            # If unquoted, strip trailing comment if preceded by space and #
            comment_idx = val.find(" #")
            if comment_idx != -1:
                val = val[:comment_idx].strip()

        env_dict[key] = val

    return env_dict


def _split_markdown_row(line: str) -> List[str]:
    """Split a markdown table row by pipe '|', ignoring pipes inside quotes or brackets."""
    parts: List[str] = []
    current: List[str] = []
    in_quote = False
    quote_char = ""
    bracket_depth = 0

    for ch in line:
        if ch in ('"', "'"):
            if not in_quote:
                in_quote = True
                quote_char = ch
            elif quote_char == ch:
                in_quote = False
        elif not in_quote and ch in ("[", "{", "("):
            bracket_depth += 1
        elif not in_quote and ch in ("]", "}", ")"):
            bracket_depth = max(0, bracket_depth - 1)
        elif ch == "|" and not in_quote and bracket_depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(ch)

    if current:
        parts.append("".join(current).strip())

    return [p for p in parts if p]


def parse_markdown_table_settings(filepath: Path) -> Dict[str, Any]:
    """Extract configuration keys and values from markdown tables."""
    if not filepath.exists():
        return {}

    settings: Dict[str, Any] = {}
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    ignored_keys = {"setting", "parameter", "rule", "tool category", "---", "--", "-"}

    for line in content.splitlines():
        line = line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue

        cols = _split_markdown_row(line)
        if len(cols) < 2:
            continue

        raw_key = cols[0].strip("` *")
        raw_val = cols[1].strip("` ")

        if raw_key.lower() in ignored_keys or raw_key.startswith("-"):
            continue

        # Try to parse as JSON (for booleans, numbers, lists, objects)
        try:
            val = json.loads(raw_val)
        except Exception:
            val = raw_val

        settings[raw_key] = val

    return settings


class Settings:
    """Central settings manager for the Telegram assistant harness."""

    def __init__(self, base_dir: Optional[Path] = None):
        self.base_dir = base_dir or BASE_DIR
        self.env_path = self.base_dir / ".env"
        self.config_md_path = self.base_dir / "CONFIG.md"
        self.limitations_md_path = self.base_dir / "LIMITATIONS.md"
        self.system_prompt_md_path = self.base_dir / "SYSTEM_PROMPT.md"

        self.env_vars: Dict[str, str] = {}
        self.config_md_settings: Dict[str, Any] = {}
        self.limitations_md_settings: Dict[str, Any] = {}
        self.raw_system_prompt: str = ""
        self.raw_limitations_md: str = ""
        self.raw_config_md: str = ""

        self.reload()

    def reload(self) -> None:
        """Reload all configuration files, markdown docs, and environment variables."""
        # 1. Load .env using standard dotenv + raw robust parser
        load_dotenv(dotenv_path=self.env_path, override=True)
        raw_env = parse_raw_env_file(self.env_path)
        # Update os.environ with raw_env in case python-dotenv stripped complex symbols
        for k, v in raw_env.items():
            os.environ[k] = v
        self.env_vars = {**os.environ, **raw_env}

        # 2. Parse CONFIG.md
        self.config_md_settings = parse_markdown_table_settings(self.config_md_path)
        if self.config_md_path.exists():
            self.raw_config_md = self.config_md_path.read_text(encoding="utf-8", errors="replace")

        # 3. Parse LIMITATIONS.md
        self.limitations_md_settings = parse_markdown_table_settings(self.limitations_md_path)
        if self.limitations_md_path.exists():
            self.raw_limitations_md = self.limitations_md_path.read_text(encoding="utf-8", errors="replace")

        # 4. Load SYSTEM_PROMPT.md
        if self.system_prompt_md_path.exists():
            self.raw_system_prompt = self.system_prompt_md_path.read_text(encoding="utf-8", errors="replace")
        else:
            self.raw_system_prompt = "You are a helpful Telegram AI assistant."

    # --- Property Accessors ---

    @property
    def telegram_bot_token(self) -> str:
        return self.get_env("TELEGRAM_BOT_TOKEN", "")

    @property
    def allowed_telegram_users(self) -> List[int]:
        # Check env first, then CONFIG.md
        env_allowed = self.get_env("TELEGRAM_ALLOWED_USERS", "").strip()
        if env_allowed:
            try:
                return [int(u.strip()) for u in env_allowed.split(",") if u.strip().isdigit()]
            except Exception:
                pass
        md_allowed = self.config_md_settings.get("allowed_user_ids", [])
        if isinstance(md_allowed, list):
            return [int(u) for u in md_allowed if str(u).isdigit()]
        return []

    @property
    def allow_all_users(self) -> bool:
        val = self.config_md_settings.get("allow_all_users", True)
        if isinstance(val, bool):
            return val
        return str(val).lower() in ("true", "1", "yes")

    @property
    def default_provider(self) -> str:
        # Priority: ENV -> CONFIG.md -> "gemini"
        return self.get_env("DEFAULT_PROVIDER", self.config_md_settings.get("default_provider", "gemini")).lower()

    @property
    def gemini_api_key(self) -> str:
        return self.get_env("GEMINI_API_KEY", self.get_env("GOOGLE_API_KEY", ""))

    @property
    def gemini_model(self) -> str:
        return self.get_env("GEMINI_MODEL", self.config_md_settings.get("gemini_model", "gemini-2.5-flash"))

    @property
    def openai_api_key(self) -> str:
        return self.get_env("OPENAI_API_KEY", "")

    @property
    def openai_auth_mode(self) -> str:
        """OpenAI authentication: API key or the locally logged-in Codex CLI."""
        value = self.get_env("OPENAI_AUTH_MODE", "").strip().lower()
        if not value:
            return "api_key" if self.openai_api_key else "codex_cli"
        aliases = {"api": "api_key", "key": "api_key", "codex": "codex_cli", "cli": "codex_cli"}
        mode = aliases.get(value, value)
        if mode not in ("api_key", "codex_cli"):
            raise ValueError("OPENAI_AUTH_MODE must be 'api_key' or 'codex_cli'")
        return mode

    @property
    def codex_cli_path(self) -> str:
        return self.get_env("CODEX_CLI_PATH", "codex")

    @property
    def openai_model(self) -> str:
        return self.get_env("OPENAI_MODEL", self.config_md_settings.get("openai_model", "gpt-4o"))

    @property
    def local_base_url(self) -> str:
        return self.get_env("LOCAL_BASE_URL", self.config_md_settings.get("local_base_url", "http://localhost:11434/v1"))

    @property
    def local_model(self) -> str:
        return self.get_env("LOCAL_MODEL", self.config_md_settings.get("local_model", "qwen2.5-coder:7b"))

    @property
    def local_api_key(self) -> str:
        return self.get_env("LOCAL_API_KEY", "ollama")

    @property
    def max_tool_iterations(self) -> int:
        return int(self.config_md_settings.get("max_tool_iterations", 15))

    @property
    def temperature(self) -> float:
        return float(self.config_md_settings.get("temperature", 0.3))

    @property
    def max_tokens(self) -> int:
        return int(self.config_md_settings.get("max_tokens", 4096))

    @property
    def max_file_read_bytes(self) -> int:
        return int(self.limitations_md_settings.get("max_file_read_bytes", 1048576))

    @property
    def command_timeout_seconds(self) -> int:
        return int(self.limitations_md_settings.get("command_timeout_seconds", 45))

    @property
    def max_directory_depth(self) -> int:
        return max(0, int(self.limitations_md_settings.get("max_directory_depth", 5)))

    @property
    def max_directory_entries(self) -> int:
        return max(1, int(self.limitations_md_settings.get("max_directory_entries", 500)))

    @property
    def max_search_files(self) -> int:
        return max(1, int(self.limitations_md_settings.get("max_search_files", 500)))

    @property
    def max_search_file_bytes(self) -> int:
        return max(1, int(self.limitations_md_settings.get("max_search_file_bytes", 1048576)))

    @property
    def codex_readiness_cache_seconds(self) -> float:
        return max(0.0, float(self.config_md_settings.get("codex_readiness_cache_seconds", 300)))

    @property
    def forbidden_paths(self) -> List[str]:
        val = self.limitations_md_settings.get("forbidden_paths", ["/etc/shadow", "/etc/sudoers"])
        return val if isinstance(val, list) else []

    @property
    def forbidden_delete_paths(self) -> List[str]:
        val = self.limitations_md_settings.get("forbidden_delete_paths", ["/", "/bin", "/sbin", "/usr", "/etc"])
        return val if isinstance(val, list) else []

    @property
    def forbidden_commands(self) -> List[str]:
        val = self.limitations_md_settings.get("forbidden_commands", ["rm -rf /"])
        return val if isinstance(val, list) else []

    @property
    def workspace_root(self) -> Path:
        rel_root = self.config_md_settings.get("workspace_root", ".")
        return (self.base_dir / rel_root).resolve()

    @property
    def download_dir(self) -> Path:
        rel_dir = self.config_md_settings.get("download_dir", "workspace/downloads")
        target = (self.base_dir / rel_dir).resolve()
        target.mkdir(parents=True, exist_ok=True)
        return target

    def get_env(self, key: str, default: str = "") -> str:
        """Retrieve any environment variable, including passwords and secrets."""
        return self.env_vars.get(key, os.environ.get(key, default))


# Singleton instance
settings = Settings()
