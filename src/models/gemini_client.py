"""Google Gemini / AGY model client for Telegram Assistant Harness.

Requirement 6: Supports Gemini via API Key or Device Login (Application Default Credentials).
"""

from __future__ import annotations
import base64
import json
import logging
from typing import Any, Dict, List, Optional
from google import genai
from google.genai import errors, types
from src.config import settings
from src.models.base import BaseModelClient, Message, ModelResponse, ToolCall, extract_xml_tool_calls

logger = logging.getLogger(__name__)


def _convert_schema_types(schema: Dict[str, Any]) -> Dict[str, Any]:
    """Convert JSON schema types to uppercase for Gemini compatibility."""
    if not isinstance(schema, dict):
        return schema

    new_schema = {}
    type_map = {
        "string": "STRING",
        "integer": "INTEGER",
        "number": "NUMBER",
        "boolean": "BOOLEAN",
        "array": "ARRAY",
        "object": "OBJECT",
    }

    for k, v in schema.items():
        if k == "type" and isinstance(v, str) and v.lower() in type_map:
            new_schema[k] = type_map[v.lower()]
        elif k == "properties" and isinstance(v, dict):
            new_schema[k] = {prop_k: _convert_schema_types(prop_v) for prop_k, prop_v in v.items()}
        elif k == "items" and isinstance(v, dict):
            new_schema[k] = _convert_schema_types(v)
        elif k in ("title", "anyOf"):
            # If anyOf is used by Pydantic for Optional types (e.g. integer or null)
            if k == "anyOf" and isinstance(v, list) and v:
                primary = [item for item in v if item.get("type") != "null"]
                if primary:
                    converted = _convert_schema_types(primary[0])
                    new_schema.update(converted)
                continue
            continue
        else:
            new_schema[k] = v

    return new_schema


class GeminiClient(BaseModelClient):
    """Client for Google Gemini / AGY models with API key or device login."""

    def __init__(self, api_key: Optional[str] = None):
        self.api_key = api_key or settings.gemini_api_key
        self._client: Optional[genai.Client] = None

    def _get_client(self) -> genai.Client:
        if self._client is None:
            if self.api_key:
                self._client = genai.Client(api_key=self.api_key)
            else:
                # Device Login / Application Default Credentials fallback
                logger.info("No Gemini API key provided; attempting Application Default Credentials / Device Login.")
                self._client = genai.Client()
        return self._client

    def _convert_tools(self, tools: List[Dict[str, Any]]) -> List[types.Tool]:
        """Convert OpenAI-style tool definitions to Gemini types.Tool."""
        declarations = []
        for t in tools:
            fn = t.get("function", {})
            name = fn.get("name", "")
            description = fn.get("description", "")
            raw_params = fn.get("parameters", {})
            gemini_params = _convert_schema_types(raw_params)

            fd = types.FunctionDeclaration(
                name=name,
                description=description,
                parameters=gemini_params,
            )
            declarations.append(fd)

        return [types.Tool(function_declarations=declarations)] if declarations else []

    async def generate(
        self,
        messages: List[Message],
        tools: Optional[List[Dict[str, Any]]] = None,
        model_name: Optional[str] = None,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
    ) -> ModelResponse:
        client = self._get_client()
        model = model_name or settings.gemini_model
        temp = temperature if temperature is not None else settings.temperature
        tokens = max_tokens or settings.max_tokens

        # Format system instruction and contents
        system_instruction = None
        contents: List[types.Content] = []

        for msg in messages:
            if msg.role == "system":
                system_instruction = msg.content
            elif msg.role == "user":
                contents.append(
                    types.Content(
                        role="user",
                        parts=[types.Part.from_text(text=msg.content or "")],
                    )
                )
            elif msg.role == "assistant":
                gemini_content = None
                if msg.provider_metadata and "gemini_content" in msg.provider_metadata:
                    raw_gc = msg.provider_metadata["gemini_content"]
                    try:
                        if isinstance(raw_gc, types.Content):
                            gemini_content = raw_gc
                        elif isinstance(raw_gc, dict):
                            gemini_content = types.Content.model_validate(raw_gc)
                        elif isinstance(raw_gc, str):
                            gemini_content = types.Content.model_validate_json(raw_gc)
                    except Exception as e:
                        logger.warning("Failed to restore preserved Gemini content: %s", e)
                        gemini_content = None

                if gemini_content is not None:
                    contents.append(gemini_content)
                else:
                    parts: List[types.Part] = []
                    if msg.content:
                        parts.append(types.Part.from_text(text=msg.content))
                    if msg.tool_calls:
                        for tc in msg.tool_calls:
                            p = types.Part.from_function_call(
                                name=tc.name,
                                args=tc.arguments,
                            )
                            if tc.provider_metadata and "thought_signature" in tc.provider_metadata:
                                sig = tc.provider_metadata["thought_signature"]
                                if isinstance(sig, str):
                                    try:
                                        p.thought_signature = base64.b64decode(sig)
                                    except Exception:
                                        p.thought_signature = sig.encode("utf-8")
                                elif isinstance(sig, bytes):
                                    p.thought_signature = sig
                            parts.append(p)
                    contents.append(types.Content(role="model", parts=parts))
            elif msg.role == "tool":
                # Function response part
                tool_output: Dict[str, Any]
                try:
                    tool_output = json.loads(msg.content or "{}")
                    if not isinstance(tool_output, dict):
                        tool_output = {"result": tool_output}
                except Exception:
                    tool_output = {"output": msg.content or ""}

                part = types.Part.from_function_response(
                    name=msg.name or "tool_response",
                    response=tool_output,
                )
                if (
                    contents
                    and contents[-1].role == "user"
                    and contents[-1].parts
                    and any(p.function_response for p in contents[-1].parts)
                ):
                    contents[-1].parts.append(part)
                else:
                    contents.append(types.Content(role="user", parts=[part]))

        gemini_tools = self._convert_tools(tools) if tools else None

        config = types.GenerateContentConfig(
            temperature=temp,
            max_output_tokens=tokens,
            system_instruction=system_instruction,
            tools=gemini_tools,
        )

        try:
            response = await client.aio.models.generate_content(
                model=model,
                contents=contents,
                config=config,
            )

            tool_calls: List[ToolCall] = []
            text_parts: List[str] = []
            provider_metadata: Optional[Dict[str, Any]] = None

            if response.candidates:
                candidate = response.candidates[0]
                if candidate.content and candidate.content.parts:
                    for part in candidate.content.parts:
                        if part.text:
                            text_parts.append(part.text)
                        if part.function_call:
                            fc = part.function_call
                            args_dict = dict(fc.args) if fc.args else {}
                            tc_meta = {}
                            if part.thought_signature:
                                tc_meta["thought_signature"] = (
                                    base64.b64encode(part.thought_signature).decode("ascii")
                                    if isinstance(part.thought_signature, bytes)
                                    else str(part.thought_signature)
                                )
                            tool_calls.append(
                                ToolCall(
                                    name=fc.name,
                                    arguments=args_dict,
                                    provider_metadata=tc_meta if tc_meta else None,
                                )
                            )
                    try:
                        provider_metadata = {
                            "gemini_content": json.loads(candidate.content.model_dump_json())
                        }
                    except Exception as e:
                        logger.warning("Failed to serialize Gemini candidate content: %s", e)

            content_text = "".join(text_parts).strip()

            # XML fallback if native function calling returned no tool calls
            if not tool_calls and "<tool_call>" in content_text:
                content_text, tool_calls = extract_xml_tool_calls(content_text)

            finish_reason = None
            if response.candidates and response.candidates[0].finish_reason:
                finish_reason = getattr(response.candidates[0].finish_reason, "name", str(response.candidates[0].finish_reason))

            return ModelResponse(
                content=content_text,
                tool_calls=tool_calls,
                finish_reason=finish_reason,
                raw=response,
                provider_metadata=provider_metadata,
            )
        except errors.APIError as e:
            err_msg = getattr(e, "message", str(e))
            status_code = getattr(e, "code", getattr(e, "status_code", 400))
            if "thought_signature" in err_msg.lower():
                logger.error(
                    "Gemini API error (%s): Tool-call thought_signature requirement failed. "
                    "History may be missing provider-specific metadata. Details: %s",
                    status_code,
                    err_msg,
                )
            else:
                logger.error("Gemini API error (%s): %s", status_code, err_msg)
            raise
        except Exception as e:
            logger.exception("Gemini API unexpected error: %s", e)
            raise
