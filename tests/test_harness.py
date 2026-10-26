"""Comprehensive test suite for Telegram Assistant Harness."""

import os
import pytest
import asyncio
from pathlib import Path

from src.config import Settings, parse_raw_env_file, settings
from src.tools.registry import registry
from src.tools.file_tools import (
    read_file,
    write_file,
    edit_file,
    list_dir,
    search_files,
    file_info,
    delete_file,
)
from src.tools.env_tools import (
    get_env_variable,
    list_env_keys,
    read_env_file_contents,
)
from src.tools.bash_tools import execute_bash
from src.models.base import extract_xml_tool_calls, Message, ToolCall, ModelResponse, BaseModelClient
from src.agent.harness import AgentHarness
from src.bot.formatters import split_message_chunks


def test_complex_password_env_parsing(tmp_path: Path):
    """Requirement 3: Can read env regardless password."""
    env_file = tmp_path / ".env.test"
    env_file.write_text(
        'DB_PASS="p@$$w0rd!#%^&*()_+=~`{}[]|;:\'<>,.?/"\n'
        'SPECIAL_TOKEN=\'complex$token#with=equals&and!quotes"\'\n'
        'SIMPLE_KEY=simple_val\n'
        'EXPORTED_PASS=export "sec#ret$pass="\n',
        encoding="utf-8",
    )

    parsed = parse_raw_env_file(env_file)
    assert parsed["DB_PASS"] == "p@$$w0rd!#%^&*()_+=~`{}[]|;:'<>,.?/"
    assert parsed["SPECIAL_TOKEN"] == 'complex$token#with=equals&and!quotes"'
    assert parsed["SIMPLE_KEY"] == "simple_val"
    assert "sec#ret$pass=" in parsed["EXPORTED_PASS"]


def test_file_operations(tmp_path: Path):
    """Requirement 4: can access file."""
    test_file = tmp_path / "test_doc.txt"

    # 1. Write file
    write_res = write_file(str(test_file), "Line 1\nLine 2\nLine 3\nTargetText\nLine 5")
    assert "successfully written" in write_res
    assert test_file.exists()

    # 2. Read file
    read_res = read_file(str(test_file), start_line=2, end_line=4)
    assert "Line 2" in read_res
    assert "Line 3" in read_res
    assert "TargetText" in read_res
    assert "Line 1" not in read_res

    # 3. Edit file
    edit_res = edit_file(str(test_file), target="TargetText", replacement="ReplacedContent")
    assert "Success" in edit_res
    assert "ReplacedContent" in test_file.read_text(encoding="utf-8")

    # 4. Search files
    search_res = search_files(pattern="ReplacedContent", path=str(tmp_path))
    assert "ReplacedContent" in search_res

    # 5. File info
    info_res = file_info(str(test_file))
    assert "is_file: True" in info_res

    # 6. Delete file
    del_res = delete_file(str(test_file))
    assert "deleted" in del_res
    assert not test_file.exists()


def test_limitations_enforcement():
    """Requirement 5: Limitations saved in .md and enforced."""
    # Forbidden path access blocked
    res = read_file("/etc/shadow")
    assert "restricted" in res.lower() or "permission" in res.lower()

    # Forbidden delete path blocked
    del_res = delete_file("/etc")
    assert "forbidden" in del_res.lower()

    # Forbidden bash command blocked
    loop = asyncio.new_event_loop()
    try:
        bash_res = loop.run_until_complete(execute_bash("rm -rf /"))
        assert "blocked" in bash_res.lower() or "forbidden" in bash_res.lower()
    finally:
        loop.close()


def test_xml_tool_call_extraction():
    """Requirement 6: Support XML format tool calls."""
    raw = (
        "I will now inspect the environment.\n"
        "<tool_call>\n"
        '{"name": "get_env_variable", "arguments": {"key": "DATABASE_PASSWORD"}}\n'
        "</tool_call>\n"
        "Let me know if you need anything else."
    )
    cleaned, calls = extract_xml_tool_calls(raw)
    assert len(calls) == 1
    assert calls[0].name == "get_env_variable"
    assert calls[0].arguments == {"key": "DATABASE_PASSWORD"}
    assert "<tool_call>" not in cleaned


def test_telegram_message_chunker():
    """Requirement 2: Telegram chunker for large messages."""
    long_code = "```python\n" + ("x = 1\n" * 1500) + "```"
    chunks = split_message_chunks(long_code, max_length=1000)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 1050
        # Code block tags properly balanced
        assert chunk.count("```") % 2 == 0


def test_tool_registry_dispatch(tmp_path: Path):
    """Test registry dispatch and execution."""
    sample_file = tmp_path / "dispatch_test.txt"
    loop = asyncio.new_event_loop()
    try:
        res = loop.run_until_complete(
            registry.dispatch("write_file", {"path": str(sample_file), "content": "Hello Dispatch"})
        )
        assert "successfully written" in res
        assert sample_file.read_text() == "Hello Dispatch"

        read_res = loop.run_until_complete(
            registry.dispatch("read_file", {"path": str(sample_file)})
        )
        assert "Hello Dispatch" in read_res
    finally:
        loop.close()


class MockModelClient(BaseModelClient):
    """Mock client for testing agent loop execution."""
    def __init__(self, responses):
        self.responses = list(responses)
        self.call_count = 0

    async def generate(self, messages, tools=None, model_name=None, temperature=None, max_tokens=None):
        resp = self.responses[self.call_count]
        self.call_count += 1
        return resp


def test_agent_harness_multi_step_loop(tmp_path: Path, monkeypatch):
    """Test agent harness multi-step tool execution loop."""
    harness = AgentHarness()
    target_file = tmp_path / "agent_created.txt"

    # Step 1: Model calls write_file
    resp1 = ModelResponse(
        content="I will write a file.",
        tool_calls=[ToolCall(name="write_file", arguments={"path": str(target_file), "content": "Agent was here"})],
    )
    # Step 2: Model finishes with final message
    resp2 = ModelResponse(
        content="Done! I have created the file for you.",
        tool_calls=[],
    )

    mock_client = MockModelClient([resp1, resp2])

    from src.models.factory import model_factory
    monkeypatch.setattr(model_factory, "get_client", lambda provider=None: (mock_client, "mock-model"))

    loop = asyncio.new_event_loop()
    try:
        final_answer = loop.run_until_complete(
            harness.run("test_session_123", "Please create a file for me.")
        )
        assert "Done! I have created the file for you." in final_answer
        assert target_file.exists()
        assert target_file.read_text() == "Agent was here"
        assert mock_client.call_count == 2
    finally:
        loop.close()
