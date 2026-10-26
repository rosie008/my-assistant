"""Session memory manager for Telegram Assistant."""

from __future__ import annotations
from typing import Dict, List, Optional
from src.models.base import Message


class SessionMemory:
    """Maintains conversation history for a specific chat or session."""

    def __init__(self, session_id: str, max_turns: int = 40):
        self.session_id = session_id
        self.max_turns = max_turns
        self.messages: List[Message] = []

    def add_user_message(self, content: str) -> None:
        self.messages.append(Message(role="user", content=content))
        self._prune()

    def add_assistant_message(self, content: Optional[str], tool_calls: Optional[List] = None) -> None:
        self.messages.append(Message(role="assistant", content=content, tool_calls=tool_calls))
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
        """Prune older conversation turns if exceeding max_turns while preserving pairs."""
        if len(self.messages) > self.max_turns * 2:
            # Keep the most recent messages
            self.messages = self.messages[-self.max_turns:]


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
