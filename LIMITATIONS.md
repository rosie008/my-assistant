# Assistant Safety & Operational Limitations

This file sets the operational boundaries and limitations enforced by the assistant harness.
All file operations, environment reads, and shell commands are checked against these rules.

---

## 1. Tool Permissions

| Tool Category | Enabled | Policy & Limitations |
|---|---|---|
| `file_read` | `true` | Read workspace files up to `max_file_read_bytes` |
| `file_write` | `true` | Create or overwrite files |
| `file_edit` | `true` | Search and replace text inside files |
| `file_delete` | `true` | Delete non-system files |
| `file_list` | `true` | List directory contents up to `max_directory_depth` |
| `file_search` | `true` | Grep / regex search files |
| `env_read` | `true` | Read environment variables regardless of password/secret tags |
| `bash_exec` | `true` | Run shell commands subject to safety boundaries |

---

## 2. File Boundaries & Limits

| Parameter | Value | Rule / Behavior |
|---|---|---|
| `max_file_read_bytes` | `1048576` | Files larger than 1MB require line slicing |
| `max_directory_depth` | `5` | Recursive directory listings will not exceed depth 5 |
| `max_directory_entries` | `500` | Directory listings stop after this many entries and report truncation |
| `filesystem_tool_timeout_seconds` | `15` | Directory listing tools return a timeout error if a filesystem operation stalls |
| `max_search_files` | `500` | Searches inspect at most this many eligible files |
| `max_search_file_bytes` | `1048576` | Searches skip files larger than 1MB |
| `restrict_to_workspace` | `false` | If true, restricts paths strictly to `workspace_root` |
| `forbidden_paths` | `["/etc/shadow", "/etc/sudoers", "/root/.ssh/id_rsa", "/proc/kcore"]` | Critical system paths blocked from read/write |
| `forbidden_delete_paths` | `["/", "/bin", "/sbin", "/usr", "/etc", "/var", "/home", "/lib"]` | Protected directory paths blocked from deletion |

---

## 3. Shell Execution Boundaries (Bash)

| Rule | Value | Description |
|---|---|---|
| `command_timeout_seconds` | `45` | Shell commands terminate automatically after 45 seconds |
| `max_output_length` | `10000` | Output truncated to 10,000 characters to prevent message overflow |
| `forbidden_commands` | `["rm -rf /", ":(){ :|:& };:", "mkfs", "dd if=/dev/zero"]` | Destructive commands explicitly blocked |

---

## 4. Telegram Limits

- **Message Limit**: 4096 characters per Telegram message (chunks handled automatically).
- **Tool Iterations**: Capped at `max_tool_iterations` to prevent infinite execution loops.
- **File Transfers**: Capped at 50MB per media/file attachment.
