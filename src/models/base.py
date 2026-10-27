"""Base definitions for model clients in Telegram Assistant Harness."""

from __future__ import annotations
import json
import re
import uuid
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    """Normalized tool call structure."""
    id: str = Field(default_factory=lambda: f"call_{uuid.uuid4().hex[:8]}")
    name: str
    arguments: Dict[str, Any]
    provider_metadata: Optional[Dict[str, Any]] = None


class Message(BaseModel):
    """Normalized message representation across providers."""
    role: str  # "system", "user", "assistant", "tool"
    content: Optional[str] = ""
    tool_calls: Optional[List[ToolCall]] = None
    tool_call_id: Optional[str] = None
    name: Optional[str] = None
    provider_metadata: Optional[Dict[str, Any]] = None


class ModelResponse(BaseModel):
    """Normalized response from any model provider."""
    content: Optional[str] = ""
    tool_calls: List[ToolCall] = Field(default_factory=list)
    finish_reason: Optional[str] = None
    raw: Any = None
    provider_metadata: Optional[Dict[str, Any]] = None


def extract_xml_tool_calls(text: str) -> tuple[str, List[ToolCall]]:
    """Extract XML tool calls from generated text.

    Format:
    <tool_call>
    {"name": "read_file", "arguments": {"path": "main.py"}}
    </tool_call>
    """
    if not text or "<tool_call>" not in text:
        return text, []

    tool_calls: List[ToolCall] = []
    # Pattern to match <tool_call>...</tool_call>
    pattern = re.compile(r"<tool_call>\s*(.*?)\s*</tool_call>", re.DOTALL)

    cleaned_text = text
    for match in pattern.finditer(text):
        raw_json = match.group(1).strip()
        try:
            data = json.loads(raw_json)
            name = data.get("name")
            if not name:
                continue

            # Arguments can be nested or flat
            if "arguments" in data and isinstance(data["arguments"], dict):
                args = data["arguments"]
            else:
                args = {k: v for k, v in data.items() if k != "name"}

            tool_calls.append(ToolCall(name=name, arguments=args))
        except Exception:
            continue

    # Remove tool_call blocks from conversational text
    cleaned_text = pattern.sub("", text).strip()
    return cleaned_text, tool_calls


class BaseModelClient(ABC):
    """Abstract interface for all model backends."""

    @abstractmethod
    async def generate(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ModelResponse:
        """Generate a response from the model."""
        pass
