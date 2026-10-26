"""OpenAI / Codex model client for Telegram Assistant Harness."""

from __future__ import annotations
import json
import logging
from typing import Any, Dict, List, Optional
from openai import AsyncOpenAI
from src.config import settings
from src.models.base import BaseModelClient, Message, ModelResponse, ToolCall, extract_xml_tool_calls

logger = logging.getLogger(__name__)


class OpenAIClient(BaseModelClient):
    """Client for OpenAI / Codex / OpenAI-compatible models."""

    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or settings.openai_api_key
        self.base_url = base_url
        self._client: Optional[AsyncOpenAI] = None

    def _get_client(self) -> AsyncOpenAI:
        if self._client is None:
            self._client = AsyncOpenAI(
                api_key=self.api_key or "sk-dummy-key-for-local-or-custom",
                base_url=self.base_url,
            )
        return self._client

    async def generate(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ModelResponse:
        client = self._get_client()
        model = model_name or settings.openai_model
        temp = temperature if temperature is not None else settings.temperature
        tokens = max_tokens or settings.max_tokens

        # Format messages for OpenAI API
        formatted_messages = []
        for msg in messages:
            item: Dict[str, Any] = {"role": msg.role, "content": msg.content or ""}
            if msg.tool_calls:
                item["tool_calls"] = [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {
                            "name": tc.name,
                            "arguments": json.dumps(tc.arguments),
                        },
                    }
                    for tc in msg.tool_calls
                ]
            if msg.role == "tool" and msg.tool_call_id:
                item["tool_call_id"] = msg.tool_call_id
            formatted_messages.append(item)

        kwargs: Dict[str, Any] = {
            "model": model,
            "messages": formatted_messages,
            "max_tokens": tokens,
        }
        # o1 / o3 / reasoning models might not support temperature
        if not (model.startswith("o1") or model.startswith("o3")):
            kwargs["temperature"] = temp

        if tools:
            kwargs["tools"] = tools

        try:
            response = await client.chat.completions.create(**kwargs)
            choice = response.choices[0]
            msg = choice.message
            raw_content = msg.content or ""

            tool_calls: List[ToolCall] = []
            if msg.tool_calls:
                for tc in msg.tool_calls:
                    try:
                        args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                    except Exception:
                        args = {"raw": tc.function.arguments}
                    tool_calls.append(ToolCall(id=tc.id, name=tc.function.name, arguments=args))

            # If no native tool calls, check for XML format in content
            final_content = raw_content
            if not tool_calls and "<tool_call>" in raw_content:
                final_content, tool_calls = extract_xml_tool_calls(raw_content)

            return ModelResponse(
                content=final_content,
                tool_calls=tool_calls,
                finish_reason=choice.finish_reason,
                raw=response,
            )
        except Exception as e:
            logger.exception(f"OpenAI API error: {e}")
            raise
