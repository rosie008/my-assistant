"""System prompt builder incorporating Markdown configurations and limitations."""

from __future__ import annotations
import platform
from datetime import datetime
from src.config import settings
from src.tools.registry import registry


class PromptBuilder:
    """Assembles dynamic system prompts for the Telegram Assistant."""

    @staticmethod
    def build_system_prompt(include_xml_tools: bool = True) -> str:
        """Construct the complete system prompt from markdown files and environment."""
        parts = []

        # 1. Base persona from SYSTEM_PROMPT.md
        if settings.raw_system_prompt:
            parts.append(settings.raw_system_prompt.strip())
        else:
            parts.append("You are a helpful Telegram AI assistant.")

        # 2. Environment Context
        env_context = (
            f"\n## Environment Context\n"
            f"- Current Date/Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"- Operating System: {platform.system()} {platform.release()}\n"
            f"- Workspace Root: {settings.workspace_root}\n"
            f"- Python Version: {platform.python_version()}\n"
        )
        parts.append(env_context)

        # 3. Active Operational Boundaries from LIMITATIONS.md
        if settings.raw_limitations_md:
            limitations_section = (
                f"\n## Mandatory Operational Limitations & Safety Rules\n"
                f"You MUST strictly adhere to these limitations saved in LIMITATIONS.md:\n\n"
                f"{settings.raw_limitations_md.strip()}\n"
            )
            parts.append(limitations_section)

        # 4. XML Tool Catalog (for local models or fallback)
        if include_xml_tools:
            parts.append("\n## Available Tools\n")
            parts.append(registry.get_xml_prompt())

        return "\n\n".join(parts)
