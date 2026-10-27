"""Tool Registry for Telegram Assistant Harness.

Provides:
- Tool registration with typing and docstrings.
- JSON schema generation for OpenAI/Gemini function calling.
- XML definition formatting for prompting.
- Safe execution with error handling and parameter injection.
"""

from __future__ import annotations
import asyncio
import inspect
import json
import logging
from typing import Any, Callable, Dict, List, Optional, get_type_hints
from pydantic import BaseModel, create_model

logger = logging.getLogger(__name__)


class Tool:
    """Represents an agent executable tool."""

    def __init__(self, fn: Callable, name: Optional[str] = None, description: Optional[str] = None,
                 timeout_seconds: Optional[float] = None):
        self.fn = fn
        self.name = name or fn.__name__
        self.description = description or (inspect.getdoc(fn) or "").strip()
        self.timeout_seconds = timeout_seconds
        self.signature = inspect.signature(fn)
        self.type_hints = get_type_hints(fn)
        self.pydantic_model = self._create_pydantic_model()

    def _create_pydantic_model(self) -> type[BaseModel]:
        """Generate a Pydantic model representing the tool's parameters."""
        fields: Dict[str, Any] = {}
        for param_name, param in self.signature.parameters.items():
            if param_name in ("self", "cls"):
                continue

            param_type = self.type_hints.get(param_name, Any)
            default = ... if param.default == inspect.Parameter.empty else param.default
            fields[param_name] = (param_type, default)

        return create_model(f"{self.name}_Args", **fields)

    def to_openai_schema(self) -> Dict[str, Any]:
        """Convert tool to OpenAI/Gemini function call schema."""
        schema = self.pydantic_model.model_json_schema()
        # Clean up schema for standard function calling
        properties = schema.get("properties", {})
        required = schema.get("required", [])

        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required,
                },
            },
        }

    def to_xml_schema(self) -> str:
        """Convert tool to XML definition."""
        schema = self.pydantic_model.model_json_schema()
        return (
            f"<tool_description>\n"
            f"<tool_name>{self.name}</tool_name>\n"
            f"<description>{self.description}</description>\n"
            f"<parameters>\n{json.dumps(schema.get('properties', {}), indent=2)}\n</parameters>\n"
            f"</tool_description>"
        )

    async def execute(self, **kwargs) -> Any:
        """Execute the tool function, awaiting if async."""
        try:
            # Validate through pydantic model
            validated = self.pydantic_model(**kwargs)
            kwargs = validated.model_dump()
        except Exception as e:
            return f"Error: Invalid arguments for tool '{self.name}': {str(e)}"

        try:
            if inspect.iscoroutinefunction(self.fn):
                operation = self.fn(**kwargs)
            else:
                # File tools are synchronous and may touch slow or disconnected
                # mounts (for example, a VPN-backed directory under ~/). Never
                # run them on the event loop: one blocked stat()/readdir() would
                # otherwise prevent Telegram updates and all other tools from
                # being processed.
                operation = asyncio.to_thread(self.fn, **kwargs)
            if self.timeout_seconds is None:
                result = await operation
            else:
                result = await asyncio.wait_for(operation, timeout=self.timeout_seconds)
            return result
        except asyncio.TimeoutError:
            if self.timeout_seconds is None:
                return f"Error executing tool '{self.name}': TimeoutError"
            return (f"Error: Tool '{self.name}' timed out after {self.timeout_seconds:g} seconds. "
                    "The directory may be slow or unavailable; verify the path or try again later.")
        except Exception as e:
            logger.exception(f"Tool {self.name} failed with error: {e}")
            return f"Error executing tool '{self.name}': {type(e).__name__}: {str(e)}"


class ToolRegistry:
    """Registry maintaining active tools and providing dispatch capabilities."""

    def __init__(self):
        self._tools: Dict[str, Tool] = {}

    def register(self, fn: Optional[Callable] = None, *, name: Optional[str] = None,
                 description: Optional[str] = None, timeout_seconds: Optional[float] = None):
        """Decorator or function to register a tool."""
        def decorator(f: Callable) -> Callable:
            tool = Tool(f, name=name, description=description, timeout_seconds=timeout_seconds)
            self._tools[tool.name] = tool
            return f

        if fn is not None:
            return decorator(fn)
        return decorator

    def get(self, name: str) -> Optional[Tool]:
        return self._tools.get(name)

    def list_tools(self) -> List[Tool]:
        return list(self._tools.values())

    def get_openai_tools(self) -> List[Dict[str, Any]]:
        return [tool.to_openai_schema() for tool in self._tools.values()]

    def get_xml_prompt(self) -> str:
        """Returns XML formatted tool catalog."""
        lines = ["<tools>"]
        for tool in self._tools.values():
            lines.append(tool.to_xml_schema())
        lines.append("</tools>")
        return "\n".join(lines)

    async def dispatch(self, tool_name: str, arguments: Dict[str, Any]) -> str:
        """Dispatch and execute a tool call, returning formatted string output."""
        tool = self.get(tool_name)
        if not tool:
            return f"Error: Tool '{tool_name}' not found. Available tools: {list(self._tools.keys())}"

        result = await tool.execute(**arguments)
        if isinstance(result, (dict, list)):
            try:
                return json.dumps(result, indent=2, ensure_ascii=False)
            except Exception:
                return str(result)
        return str(result)


# Global registry instance
registry = ToolRegistry()
tool = registry.register
