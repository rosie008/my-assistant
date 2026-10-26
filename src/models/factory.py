"""Model client factory and router for Telegram Assistant Harness."""

from __future__ import annotations
import logging
from typing import Dict, Optional, Tuple
from src.config import settings
from src.models.base import BaseModelClient
from src.models.gemini_client import GeminiClient
from src.models.openai_client import OpenAIClient
from src.models.local_client import LocalModelClient

logger = logging.getLogger(__name__)


class ModelFactory:
    """Factory creating and routing requests to model providers."""

    def __init__(self):
        self._clients: Dict[str, BaseModelClient] = {}
        self.active_provider: str = settings.default_provider
        self.active_model_override: Optional[str] = None

    def get_client(self, provider: Optional[str] = None) -> Tuple[BaseModelClient, str]:
        """Get model client and active model name for requested or default provider."""
        provider_name = (provider or self.active_provider).lower()

        if provider_name in ("gemini", "agy", "google"):
            if "gemini" not in self._clients:
                self._clients["gemini"] = GeminiClient()
            client = self._clients["gemini"]
            model = self.active_model_override or settings.gemini_model
            return client, model

        elif provider_name in ("openai", "codex", "gpt"):
            if "openai" not in self._clients:
                self._clients["openai"] = OpenAIClient()
            client = self._clients["openai"]
            model = self.active_model_override or settings.openai_model
            return client, model

        elif provider_name in ("local", "ollama", "vllm", "lmstudio"):
            if "local" not in self._clients:
                self._clients["local"] = LocalModelClient()
            client = self._clients["local"]
            model = self.active_model_override or settings.local_model
            return client, model

        else:
            raise ValueError(
                f"Unknown model provider: '{provider_name}'. "
                f"Available providers: 'gemini', 'openai', 'local'"
            )

    def set_active_provider(self, provider: str) -> None:
        """Switch active provider."""
        provider = provider.lower()
        if provider not in ("gemini", "openai", "local", "codex"):
            raise ValueError(f"Unsupported provider: {provider}")
        self.active_provider = "openai" if provider == "codex" else provider
        self.active_model_override = None

    def set_active_model(self, model_name: str) -> None:
        """Override active model name."""
        self.active_model_override = model_name

    def get_status(self) -> Dict[str, Any]:
        """Return readiness status for all providers."""
        return {
            "active_provider": self.active_provider,
            "active_model_override": self.active_model_override,
            "gemini": {
                "model": settings.gemini_model,
                "has_api_key": bool(settings.gemini_api_key),
                "device_login_supported": True,
            },
            "openai": {
                "model": settings.openai_model,
                "has_api_key": bool(settings.openai_api_key),
            },
            "local": {
                "model": settings.local_model,
                "endpoint": settings.local_base_url,
            },
        }


# Singleton factory instance
model_factory = ModelFactory()
