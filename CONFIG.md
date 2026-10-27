# Telegram Assistant Configuration

This file defines runtime settings for your personal Telegram assistant.
You can edit any value here and reload it live with `/reload` in Telegram without restarting the bot.

---

## 1. Active Provider & Model

| Setting | Value | Description |
|---|---|---|
| `default_provider` | `gemini` | Active provider: `gemini`, `openai`, or `local` |
| `gemini_model` | `gemini-3.8-flash` | Current Gemini options: `gemini-4-argon` (flagship), `gemini-3.8-flash` (balanced), `gemini-3.6-flash`, `gemini-3.5-flash-lite` (economy) |
| `openai_model` | `gpt-6.1-sol` | Current OpenAI options: `gpt-6-astra` (flagship), `gpt-6.1-sol` (balanced), `gpt-6.1-terra`, `gpt-6-luna` (economy) |
| `local_model` | `qwen2.5-coder:7b` | Model name on local runner (Ollama, vLLM, LM Studio) |
| `local_base_url` | `http://localhost:11434/v1` | Local OpenAI-compatible API endpoint |

---

## 2. Model Hyperparameters

| Parameter | Value | Description |
|---|---|---|
| `temperature` | `0.3` | Creativity vs determinism (0.0 to 1.0) |
| `max_tokens` | `4096` | Maximum generation tokens per turn |
| `top_p` | `0.95` | Sampling probability threshold |

---

## 3. Assistant Loop Settings

| Setting | Value | Description |
|---|---|---|
| `max_tool_iterations` | `10` | Max sequential tool calls per user query |
| `timeout_seconds` | `120` | Timeout for model generation calls |
| `send_intermediate_status` | `true` | Show tool status updates in Telegram chat |

---

## 4. Telegram Bot Settings

| Setting | Value | Description |
|---|---|---|
| `bot_name` | `PersonalAssistantBot` | Bot display name |
| `allow_all_users` | `true` | Allow any user or restrict to `allowed_user_ids` |
| `allowed_user_ids` | `[]` | Whitelisted Telegram user IDs (e.g. `[12345678]`) |
| `download_dir` | `workspace/downloads` | Folder where files uploaded via Telegram are saved |
| `max_upload_size_mb` | `50` | Maximum file size allowed for downloads/uploads |

---

## 5. Storage & Workspace

| Setting | Value | Description |
|---|---|---|
| `workspace_root` | `.` | Root directory for file access |
| `logs_dir` | `logs` | Directory for logs |
