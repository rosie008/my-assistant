"""Session memory manager for Telegram Assistant."""

from __future__ import annotations
from typing import Any, Dict, List, Optional
from src.models.base import Message, ToolCall


class SessionMemory:
    """Maintains conversation history for a specific chat or session."""

    def __init__(self, session_id: str, max_turns: int = 40):
        self.session_id = session_id
        self.max_turns = max_turns
        self.messages: List[Message] = []

    def add_user_message(self, content: str) -> None:
        self.messages.append(Message(role="user", content=content))
        self._prune()

    def add_assistant_message(
        self,
        content: Optional[str],
        tool_calls: Optional[List[ToolCall]] = None,
        provider_metadata: Optional[Dict[str, Any]] = None,
    ) -> None:
        self.messages.append(
            Message(
                role="assistant",
                content=content,
                tool_calls=tool_calls,
                provider_metadata=provider_metadata,
            )
        )
        self._prune()

    def add_tool_response(self, tool_name: str, tool_call_id: Optional[str], content: str) -> None:
        self.messages.append(
            Message(
                role="tool",
                name=tool_name,
                tool_call_id=tool_call_id,
                content=content,
            )
        )
        self._prune()

    def clear(self) -> None:
        """Clear session memory."""
        self.messages.clear()

    def get_messages(self) -> List[Message]:
        return list(self.messages)

    def _prune(self) -> None:
        """Prune older conversation turns if exceeding max_turns while preserving tool exchanges."""
        user_indices = [i for i, m in enumerate(self.messages) if m.role == "user"]
        if len(user_indices) > self.max_turns:
            keep_from_idx = user_indices[-self.max_turns]
            self.messages = self.messages[keep_from_idx:]
        elif not user_indices and len(self.messages) > self.max_turns * 2:
            self.messages = self.messages[-self.max_turns:]

        # Safety: never leave an orphaned tool response at the beginning of history
        while self.messages and self.messages[0].role == "tool":
            self.messages.pop(0)


class MemoryManager:
    """Manages multi-user or multi-chat sessions."""

    def __init__(self):
        self._sessions: Dict[str, SessionMemory] = {}

    def get_session(self, session_id: str) -> SessionMemory:
        if session_id not in self._sessions:
            self._sessions[session_id] = SessionMemory(session_id)
        return self._sessions[session_id]

    def clear_session(self, session_id: str) -> None:
        if session_id in self._sessions:
            self._sessions[session_id].clear()


# Global memory manager
memory_manager = MemoryManager()
