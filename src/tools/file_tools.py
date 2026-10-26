"""File access tools for Telegram Assistant Harness.

Provides full file manipulation capabilities:
- read_file
- write_file
- edit_file
- list_dir
- search_files
- file_info
- delete_file

Enforces security rules from LIMITATIONS.md.
"""

from __future__ import annotations
import os
import re
from pathlib import Path
from typing import Optional, List, Dict, Any
from src.config import settings
from src.tools.registry import tool


def _resolve_safe_path(path_str: str) -> Path:
    """Resolve path and verify against forbidden security boundaries."""
    raw_path = Path(path_str).expanduser()
    if not raw_path.is_absolute():
        resolved = (settings.workspace_root / raw_path).resolve()
    else:
        resolved = raw_path.resolve()

    resolved_str = str(resolved)
    for forbidden in settings.forbidden_paths:
        forbidden_clean = forbidden.rstrip("/")
        if not forbidden_clean:
            if resolved_str == "/":
                raise PermissionError(f"Access to path '{resolved_str}' is restricted by LIMITATIONS.md")
        elif resolved_str == forbidden_clean or resolved_str.startswith(forbidden_clean + "/"):
            raise PermissionError(f"Access to path '{resolved_str}' is restricted by LIMITATIONS.md")

    return resolved


@tool(description="Read the contents of a file. Supports optional start_line and end_line (1-indexed).")
def read_file(path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> str:
    """Read contents of a file with optional line filtering."""
    try:
        resolved = _resolve_safe_path(path)
        if not resolved.exists():
            return f"Error: File '{path}' does not exist."
        if not resolved.is_file():
            return f"Error: '{path}' is a directory, not a file. Use list_dir instead."

        size = resolved.stat().st_size
        max_bytes = settings.max_file_read_bytes
        if size > max_bytes and start_line is None and end_line is None:
            return (
                f"Warning: File '{path}' size ({size} bytes) exceeds limit ({max_bytes} bytes). "
                f"Please specify start_line and end_line to inspect specific portions."
            )

        with open(resolved, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        total_lines = len(lines)
        start_idx = max(0, (start_line - 1) if start_line is not None else 0)
        end_idx = min(total_lines, end_line if end_line is not None else total_lines)

        selected_lines = lines[start_idx:end_idx]
        output = []
        for idx, line_content in enumerate(selected_lines, start=start_idx + 1):
            output.append(f"{idx}: {line_content.rstrip('\r\n')}")

        header = f"=== File: {resolved} ({start_idx+1}-{end_idx} of {total_lines} lines) ===\n"
        return header + "\n".join(output)

    except PermissionError as pe:
        return f"Permission Error: {pe}"
    except Exception as e:
        return f"Error reading file '{path}': {type(e).__name__}: {str(e)}"


@tool(description="Write text content to a file. Automatically creates parent directories.")
def write_file(path: str, content: str, overwrite: bool = True) -> str:
    """Create or overwrite a file with given text content."""
    try:
        resolved = _resolve_safe_path(path)
        if resolved.exists() and not overwrite:
            return f"Error: File '{path}' already exists and overwrite is set to False."

        resolved.parent.mkdir(parents=True, exist_ok=True)
        with open(resolved, "w", encoding="utf-8") as f:
            f.write(content)

        return f"Success: File '{path}' successfully written ({len(content)} characters)."

    except PermissionError as pe:
        return f"Permission Error: {pe}"
    except Exception as e:
        return f"Error writing file '{path}': {type(e).__name__}: {str(e)}"


@tool(description="Replace an exact target string with a replacement string inside an existing file.")
def edit_file(path: str, target: str, replacement: str) -> str:
    """Search and replace target string in a file."""
    try:
        resolved = _resolve_safe_path(path)
        if not resolved.exists():
            return f"Error: File '{path}' does not exist."

        with open(resolved, "r", encoding="utf-8") as f:
            content = f.read()

        if target not in content:
            return f"Error: Target text not found in '{path}'. Make sure whitespace and formatting match exactly."

        occurrences = content.count(target)
        new_content = content.replace(target, replacement)

        with open(resolved, "w", encoding="utf-8") as f:
            f.write(new_content)

        return f"Success: Replaced {occurrences} occurrence(s) in '{path}'."

    except PermissionError as pe:
        return f"Permission Error: {pe}"
    except Exception as e:
        return f"Error editing file '{path}': {type(e).__name__}: {str(e)}"


@tool(description="List files and subdirectories in a given directory path.")
def list_dir(path: str = ".", recursive: bool = False, max_depth: int = 2) -> str:
    """List directory contents with sizes and file types."""
    try:
        resolved = _resolve_safe_path(path)
        if not resolved.exists():
            return f"Error: Directory '{path}' does not exist."
        if not resolved.is_dir():
            return f"Error: '{path}' is not a directory."

        results = []
        base_depth = len(resolved.parts)

        if not recursive:
            entries = sorted(resolved.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower()))
            for entry in entries:
                if entry.name.startswith(".venv") or entry.name == ".git":
                    continue
                type_indicator = "[DIR]" if entry.is_dir() else f"[{entry.stat().st_size} B]"
                results.append(f"{type_indicator:>10}  {entry.name}")
        else:
            for root, dirs, files in os.walk(resolved):
                curr_depth = len(Path(root).parts) - base_depth
                # Skip hidden/large dirs
                dirs[:] = [d for d in dirs if d not in (".git", ".venv", "__pycache__", "node_modules")]
                if curr_depth >= max_depth:
                    dirs.clear()

                rel_root = os.path.relpath(root, resolved)
                if rel_root != ".":
                    results.append(f"[DIR]       {rel_root}/")

                for f in sorted(files):
                    fpath = Path(root) / f
                    try:
                        size = fpath.stat().st_size
                    except Exception:
                        size = 0
                    rel_file = os.path.relpath(fpath, resolved)
                    results.append(f"[{size} B] {rel_file}")

        header = f"=== Directory Listing: {resolved} ({len(results)} items) ===\n"
        return header + ("\n".join(results) if results else "(empty directory)")

    except PermissionError as pe:
        return f"Permission Error: {pe}"
    except Exception as e:
        return f"Error listing directory '{path}': {type(e).__name__}: {str(e)}"


@tool(description="Search for regex pattern across files in directory.")
def search_files(pattern: str, path: str = ".", file_pattern: Optional[str] = None) -> str:
    """Grep-like pattern search across text files in directory."""
    try:
        resolved = _resolve_safe_path(path)
        if not resolved.exists():
            return f"Error: Path '{path}' does not exist."

        regex = re.compile(pattern)
        matches: List[str] = []

        file_filter = re.compile(file_pattern) if file_pattern else None

        for root, dirs, files in os.walk(resolved):
            dirs[:] = [d for d in dirs if d not in (".git", ".venv", "__pycache__", "node_modules")]
            for filename in files:
                if file_filter and not file_filter.search(filename):
                    continue

                filepath = Path(root) / filename
                try:
                    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                        for line_num, line in enumerate(f, start=1):
                            if regex.search(line):
                                rel_path = filepath.relative_to(resolved)
                                matches.append(f"{rel_path}:{line_num}: {line.strip()}")
                                if len(matches) >= 50:
                                    matches.append("... (Search truncated at 50 results)")
                                    return "\n".join(matches)
                except Exception:
                    continue

        if not matches:
            return f"No matches found for pattern '{pattern}' in '{path}'."
        return "\n".join(matches)

    except Exception as e:
        return f"Error searching files: {str(e)}"


@tool(description="Get metadata information about a file or directory.")
def file_info(path: str) -> str:
    """Retrieve file metadata: size, timestamps, permissions."""
    try:
        resolved = _resolve_safe_path(path)
        if not resolved.exists():
            return f"Error: File or directory '{path}' does not exist."

        stat = resolved.stat()
        info = {
            "path": str(resolved),
            "is_file": resolved.is_file(),
            "is_dir": resolved.is_dir(),
            "size_bytes": stat.st_size,
            "modified_time": stat.st_mtime,
            "created_time": stat.st_ctime,
            "mode": oct(stat.st_mode),
        }
        return "\n".join(f"{k}: {v}" for k, v in info.items())
    except Exception as e:
        return f"Error getting info for '{path}': {str(e)}"


@tool(description="Delete a file inside workspace.")
def delete_file(path: str) -> str:
    """Delete a file subject to forbidden delete paths."""
    try:
        resolved = _resolve_safe_path(path)
        resolved_str = str(resolved)

        for forbidden in settings.forbidden_delete_paths:
            forbidden_clean = forbidden.rstrip("/")
            if not forbidden_clean:
                if resolved_str == "/":
                    return f"Permission Denied: Deleting root '{resolved_str}' is forbidden by LIMITATIONS.md."
            elif resolved_str == forbidden_clean or resolved_str.startswith(forbidden_clean + "/"):
                return f"Permission Denied: Deleting '{resolved_str}' is forbidden by LIMITATIONS.md."

        if not resolved.exists():
            return f"Error: File '{path}' does not exist."
        if resolved.is_dir():
            return f"Error: '{path}' is a directory. Cannot delete directories with delete_file."

        resolved.unlink()
        return f"Success: File '{path}' deleted."

    except PermissionError as pe:
        return f"Permission Error: {pe}"
    except Exception as e:
        return f"Error deleting file '{path}': {str(e)}"
