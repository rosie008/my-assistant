# Personal Telegram Assistant & Agent Harness

A simple, lightweight, and capable personal AI assistant built in Python that connects directly to Telegram.
It provides file access, reads environment variables (regardless of passwords), executes safe tasks, and supports Gemini/AGY, OpenAI/Codex, or Local models via API keys or device login.

---

## 🌟 Key Features

1. **Telegram Assistant (`python-telegram-bot`)**:
   - Conversational chat with typing indicator.
   - Status updates during tool execution (e.g. `🔧 Calling read_file(...)`).
   - Handles file and photo uploads from Telegram users.
   - Send files to users via `/file <path>`.
   - Automatic message chunker preventing Telegram's 4096-character limit errors.

2. **File System Tools**:
   - Read, write, edit, list, search, inspect, and delete workspace files.

3. **Read Environment Variables (Regardless of Passwords)**:
   - Preserves passwords, hashes, symbols, quotes, and whitespace (`!@#$%^&*()_+=~`{}[]|;:'<>,.?/`).
   - Query values in chat with `/env <KEY>` or CLI with `python main.py --check-env`.

4. **Markdown-Driven Configuration & Limitations**:
   - [`CONFIG.md`](CONFIG.md): Provider, model selection, temperature, timeouts, bot settings.
   - [`LIMITATIONS.md`](LIMITATIONS.md): Forbidden paths, size limits, allowed tools.
   - [`SYSTEM_PROMPT.md`](SYSTEM_PROMPT.md): Assistant instructions and personality.
   - Hot-reloadable live using `/reload` in Telegram without restarting.

5. **Multi-Model Provider**:
   - **Google Gemini / AGY**: via API Key or Device Login (Application Default Credentials).
   - **OpenAI / Codex**: via API key or Codex CLI device login.
   - **Local Models**: via Ollama, vLLM, or LM Studio with OpenAI-compatible API.

---

## 🚀 How to Run

### 1. Set Your Telegram Token & API Keys
In [`.env`](.env):
```bash
TELEGRAM_BOT_TOKEN=your_telegram_bot_token_here
DEFAULT_PROVIDER=gemini
GEMINI_API_KEY=your_gemini_api_key_here
OPENAI_API_KEY=your_openai_api_key_here
# Or use a ChatGPT/Codex login managed by the official Codex CLI:
OPENAI_AUTH_MODE=codex_cli
```

For headless machines, install the official Codex CLI and run `python main.py --codex-device-login` (or `codex login --device-auth`) as the same OS user that runs the bot. Complete the displayed URL and one-time code, then set `OPENAI_AUTH_MODE=codex_cli`. Credentials remain managed by Codex; this assistant does not read or copy them. Use `python main.py --device-login` to verify the login. To switch back, set `OPENAI_AUTH_MODE=api_key` and provide `OPENAI_API_KEY`.

On Linux, Codex also needs a working bubblewrap/user-namespace sandbox. If the bot reports that user namespaces are blocked, fix the host's bubblewrap or AppArmor configuration; this is separate from device authentication.

### 2. Verify Your Configuration
```bash
# Check loaded environment variables & passwords
.venv/bin/python main.py --check-env

# Check active configuration & limitations from markdown files
.venv/bin/python main.py --status
```

### 3. Start the Bot
```bash
.venv/bin/python main.py
```

### 4. Interactive Terminal Mode (Optional)
If you want to test or chat from terminal without opening Telegram:
```bash
.venv/bin/python main.py --cli
```
