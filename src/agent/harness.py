"""Telegram Assistant Harness: Multi-step reasoning and tool execution loop."""

from __future__ import annotations
import logging
from typing import Any, Callable, Dict, List, Optional, Awaitable
from src.config import settings
from src.tools.registry import registry
from src.models.base import Message, ToolCall
from src.models.factory import model_factory
from src.agent.memory import memory_manager
from src.agent.prompt_builder import PromptBuilder

logger = logging.getLogger(__name__)


class AgentHarness:
    """Core agent harness implementing the reasoning and tool execution loop."""

    def __init__(self):
        self.memory_manager = memory_manager
        self.prompt_builder = PromptBuilder()

    async def run(
        self,
        session_id: str,
        user_input: str,
        on_status_update: Optional[Callable[[str], Awaitable[None]]] = None,
    ) -> str:
        """Execute the agent loop for a user query."""
        session = self.memory_manager.get_session(session_id)
        session.add_user_message(user_input)

        # Prepare system prompt
        system_prompt = self.prompt_builder.build_system_prompt()

        # Get active model client
        client, model_name = model_factory.get_client()
        tools_schema = registry.get_openai_tools()

        max_iterations = settings.max_tool_iterations
        current_iteration = 0

        final_response_text = ""

        while current_iteration < max_iterations:
            current_iteration += 1

            # Prepare message sequence for model
            messages = [Message(role="system", content=system_prompt)] + session.get_messages()

            if on_status_update and current_iteration == 1:
                await on_status_update(f"🤔 Thinking ({model_name})...")

            try:
                response = await client.generate(
                    messages=messages,
                    tools=tools_schema,
                    model_name=model_name,
                )
            except Exception as e:
                logger.exception("Model generation error in agent loop")
                error_msg = f"❌ Error communicating with model ({model_name}): {str(e)}"
                if on_status_update:
                    await on_status_update(error_msg)
                return error_msg

            # Check if model made any tool calls
            if not response.tool_calls:
                final_response_text = response.content or "(No response generated)"
                session.add_assistant_message(final_response_text)
                break

            # Handle tool calls
            session.add_assistant_message(response.content, tool_calls=response.tool_calls)

            for tool_call in response.tool_calls:
                fn_name = tool_call.name
                fn_args = tool_call.arguments

                if on_status_update:
                    # Short human-readable status
                    args_summary = ", ".join(f"{k}={repr(v)[:30]}" for k, v in fn_args.items())
                    await on_status_update(f"🔧 Calling `{fn_name}({args_summary})`...")

                # Execute tool
                logger.info(f"Agent executing tool: {fn_name} with args: {fn_args}")
                output = await registry.dispatch(fn_name, fn_args)

                # Store tool observation in session memory
                session.add_tool_response(
                    tool_name=fn_name,
                    tool_call_id=tool_call.id,
                    content=output,
                )

        if current_iteration >= max_iterations and not final_response_text:
            final_response_text = (
                f"⚠️ Reached maximum allowed tool iterations ({max_iterations}). "
                "The task could not be fully completed within the configured limit."
            )
            session.add_assistant_message(final_response_text)

        return final_response_text


# Global harness instance
harness = AgentHarness()
