"""Local model client for Telegram Assistant Harness (Ollama, vLLM, LM Studio, llama.cpp)."""

from __future__ import annotations
import logging
from typing import Any, Dict, List, Optional
from src.config import settings
from src.models.openai_client import OpenAIClient
from src.models.base import Message, ModelResponse

logger = logging.getLogger(__name__)


class LocalModelClient(OpenAIClient):
    """Client for local models served via Ollama, vLLM, LM Studio, or llama.cpp."""

    def __init__(
        self,
        base_url: Optional[str] = None,
        model_name: Optional[str] = None,
        api_key: Optional[str] = None,
    ):
        base_url = base_url or settings.local_base_url
        api_key = api_key or settings.local_api_key or "ollama"
        super().__init__(api_key=api_key, base_url=base_url)
        self.default_model = model_name or settings.local_model

    async def generate(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ModelResponse:
        model = model_name or self.default_model
        return await super().generate(
            messages=messages,
            tools=tools,
            model_name=model,
            temperature=temperature,
            max_tokens=max_tokens,
        )
