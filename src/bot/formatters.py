"""Formatting utilities for Telegram messages and output chunking."""

from __future__ import annotations
from typing import List

TELEGRAM_MAX_MESSAGE_LENGTH = 4000


def split_message_chunks(text: str, max_length: int = TELEGRAM_MAX_MESSAGE_LENGTH) -> List[str]:
    """Split a long text message into safe chunks preserving code blocks and lines."""
    if not text:
        return [""]

    if len(text) <= max_length:
        return [text]

    chunks: List[str] = []
    lines = text.split("\n")
    current_chunk: List[str] = []
    current_len = 0
    in_code_block = False
    code_block_lang = ""

    for line in lines:
        line_len = len(line) + 1  # +1 for newline

        # Check code fence
        if line.strip().startswith("```"):
            if not in_code_block:
                in_code_block = True
                code_block_lang = line.strip()[3:].strip()
            else:
                in_code_block = False
                code_block_lang = ""

        if current_len + line_len > max_length and current_chunk:
            # If we are inside a code block, close it before chunking and reopen in next chunk
            if in_code_block:
                current_chunk.append("```")
            chunks.append("\n".join(current_chunk))

            current_chunk = []
            if in_code_block:
                current_chunk.append(f"```{code_block_lang}")
                current_len = len(current_chunk[0]) + 1
            else:
                current_len = 0

        current_chunk.append(line)
        current_len += line_len

    if current_chunk:
        chunks.append("\n".join(current_chunk))

    return chunks
