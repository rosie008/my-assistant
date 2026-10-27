#!/usr/bin/env python3
"""Telegram Assistant: Multi-provider AI Assistant with Telegram & File Access.

Usage:
  python main.py                  # Start Telegram Bot (default)
  python main.py --cli            # Start Interactive Terminal Chat
  python main.py --check-env      # Inspect environment variables (regardless of password)
  python main.py --status         # Display active configuration, tools, and limitations
  python main.py --device-login   # Verify Gemini and Codex device authentication
  python main.py --codex-device-login  # Start the Codex CLI device-login flow
"""

from __future__ import annotations
import argparse
import asyncio
import subprocess
import sys
from src.config import settings
from src.models.factory import model_factory
from src.tools.registry import registry
import src.tools  # Register all tools
from src.agent.harness import harness


def print_banner():
    banner = r"""
  ██████╗  ██████╗ ███████╗███████╗
  ██╔══██╗██╔═══██╗██╔════╝██╔════╝
  ██████╔╝██║   ██║███████╗█████╗  
  ██╔══██╗██║   ██║╚════██║██╔══╝  
  ██║  ██║╚██████╔╝███████║███████╗
  ╚═╝  ╚═╝ ╚═════╝ ╚══════╝╚══════╝
    """
    print(banner)
    print(" 🤖 Personal Telegram Assistant & Tool Harness")
    print(f" • Default Provider: {settings.default_provider}")
    print(f" • Workspace Root:   {settings.workspace_root}")
    print(f" • Tools Registered: {len(registry.list_tools())}")
    print("-" * 65)


def check_env():
    """Requirement 3: Can read env regardless password."""
    print("🔐 [Environment Variables Inspection]")
    print(f"Loaded from: {settings.env_path}\n")

    test_keys = [
        "TELEGRAM_BOT_TOKEN",
        "DEFAULT_PROVIDER",
        "GEMINI_API_KEY",
        "GEMINI_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_AUTH_MODE",
        "CODEX_CLI_PATH",
        "OPENAI_MODEL",
        "LOCAL_BASE_URL",
        "LOCAL_MODEL",
        "DATABASE_PASSWORD",
        "SPECIAL_TOKEN",
        "REDIS_SECRET",
    ]

    for key in test_keys:
        val = settings.get_env(key, "")
        if val:
            display_val = val if len(val) <= 45 else val[:42] + "..."
            print(f"  ✓ {key:<24} = {display_val}")
        else:
            print(f"  ✗ {key:<24} = (not set)")

    print("\nAll values, including passwords with symbols and quotes, loaded properly!")


def show_status():
    """Display active configuration and limitations from markdown files."""
    print("⚙️  [Active Configuration - CONFIG.md]")
    for k, v in settings.config_md_settings.items():
        print(f"  • {k:<25}: {v}")

    print("\n🛡️  [Active Limitations - LIMITATIONS.md]")
    for k, v in settings.limitations_md_settings.items():
        print(f"  • {k:<25}: {v}")

    print("\n🔧 [Registered Tools]")
    for t in registry.list_tools():
        print(f"  • {t.name:<22}: {t.description[:60]}...")


async def device_login_check():
    """Check Gemini ADC and the login managed by the Codex CLI."""
    print("🔑 [Device Login & Credentials Check]")
    print("\n1. Google Gemini / AGY:")
    if settings.gemini_api_key:
        print("  ✓ GEMINI_API_KEY is configured.")
    else:
        print("  ℹ No GEMINI_API_KEY found. Checking Application Default Credentials / Device Login...")
        try:
            # Isolate this optional probe so a platform-specific Google
            # credential lookup cannot keep the CLI process alive indefinitely.
            proc = await asyncio.create_subprocess_exec(
                sys.executable,
                "-c",
                "import google.auth; google.auth.default()",
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL,
            )
            try:
                await asyncio.wait_for(proc.wait(), timeout=5)
            except asyncio.TimeoutError:
                proc.kill()
                await proc.wait()
                print("  ⚠ Google ADC check timed out after 5 seconds.")
            else:
                if proc.returncode == 0:
                    print("  ✓ Google Application Default Credentials (ADC) successfully detected!")
                else:
                    print("  ⚠ Google ADC not active.")
                    print("  👉 To authenticate via device login, run: `gcloud auth application-default login`")
        except Exception as e:
            print(f"  ⚠ Google ADC not active: {e}")
            print("  👉 To authenticate via device login, run: `gcloud auth application-default login`")

    print("\n2. OpenAI / Codex CLI:")
    from src.models.codex_cli_client import CodexCliClient
    ready, detail = CodexCliClient.readiness(settings.codex_cli_path)
    marker = "✓" if ready else "⚠"
    print(f"  {marker} {detail}")
    if not ready:
        print("  👉 Run: `python main.py --codex-device-login`")

    print("\n3. Local Model Endpoint:")
    print(f"  Testing connection to: {settings.local_base_url} ...")
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(settings.local_base_url.replace("/v1", ""))
            print(f"  ✓ Local server responded with status: {resp.status_code}")
    except Exception as e:
        print(f"  ℹ Local server not reachable at {settings.local_base_url} ({type(e).__name__})")
        print("    (Start Ollama, vLLM, or LM Studio when using the local provider)")


def codex_device_login() -> int:
    """Hand device authentication to the official Codex CLI.

    This intentionally forwards the interactive flow rather than attempting to
    read, create, or copy any Codex credential files.
    """
    from src.models.codex_cli_client import CodexCliClient

    executable = settings.codex_cli_path
    if not CodexCliClient.is_available(executable):
        print(f"⚠️ Codex CLI not found at '{executable}'. Install Codex or set CODEX_CLI_PATH.")
        return 1
    print("Starting Codex device login. Complete the URL and code shown by Codex.")
    try:
        return subprocess.run([executable, "login", "--device-auth"], check=False).returncode
    except OSError as exc:
        print(f"⚠️ Unable to start Codex CLI: {exc}")
        return 1


async def run_cli():
    """Interactive CLI chat mode for testing the harness without Telegram."""
    print_banner()
    client, model = model_factory.get_client()
    print(f"Starting CLI session with provider: '{model_factory.active_provider}' | model: '{model}'")
    print("Commands: /switch <provider>, /model <name>, /clear, /tools, /exit\n")

    session_id = "cli_session"

    while True:
        try:
            user_input = input("\nYou > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not user_input:
            continue

        if user_input.lower() in ("/exit", "/quit"):
            print("Goodbye.")
            break

        if user_input.startswith("/switch "):
            provider = user_input.split(maxsplit=1)[1].strip()
            try:
                model_factory.set_active_provider(provider)
                c, m = model_factory.get_client()
                print(f"Switched provider to '{provider}' (Model: {m})")
            except Exception as e:
                print(f"Error: {e}")
            continue

        if user_input.startswith("/model "):
            new_model = user_input.split(maxsplit=1)[1].strip()
            model_factory.set_active_model(new_model)
            print(f"Model set to '{new_model}'")
            continue

        if user_input == "/clear":
            harness.memory_manager.clear_session(session_id)
            print("Memory cleared.")
            continue

        if user_input == "/tools":
            for t in registry.list_tools():
                print(f"  • {t.name}: {t.description}")
            continue

        async def status_callback(msg: str):
            print(f"  {msg}")

        response = await harness.run(
            session_id=session_id,
            user_input=user_input,
            on_status_update=status_callback,
        )
        print(f"\nAssistant >\n{response}")


def main():
    parser = argparse.ArgumentParser(description="Telegram Assistant Harness")
    parser.add_argument("--cli", action="store_true", help="Run interactive CLI chat")
    parser.add_argument("--bot", action="store_true", help="Run Telegram bot")
    parser.add_argument("--check-env", action="store_true", help="Inspect loaded environment variables")
    parser.add_argument("--status", action="store_true", help="Display harness configuration and limitations")
    parser.add_argument("--device-login", action="store_true", help="Verify device login / ADC credentials")
    parser.add_argument("--codex-device-login", action="store_true", help="Start Codex CLI device authentication")

    args = parser.parse_args()

    if args.check_env:
        check_env()
    elif args.status:
        show_status()
    elif args.device_login:
        asyncio.run(device_login_check())
    elif args.codex_device_login:
        sys.exit(codex_device_login())
    elif args.cli:
        asyncio.run(run_cli())
    else:
        # Default: Start Telegram bot
        print_banner()
        token = settings.telegram_bot_token
        if not token or token == "your_telegram_bot_token_here":
            print("⚠️  TELEGRAM_BOT_TOKEN is not configured in .env!")
            print("👉 To run Telegram bot, add your bot token in .env.")
            print("💡 You can run interactive CLI mode right now using:")
            print("   python main.py --cli\n")
            print("Or check environment variables using:")
            print("   python main.py --check-env\n")
            sys.exit(1)

        from src.bot.telegram_bot import run_telegram_bot
        run_telegram_bot()


if __name__ == "__main__":
    main()
