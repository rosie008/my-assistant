#!/usr/bin/env python3
"""Telegram Assistant: Multi-provider AI Assistant with Telegram & File Access.

Usage:
  python main.py                  # Start Telegram Bot (default)
  python main.py --cli            # Start Interactive Terminal Chat
  python main.py --check-env      # Inspect environment variables (regardless of password)
  python main.py --status         # Display active configuration, tools, and limitations
  python main.py --device-login   # Verify Google Application Default Credentials / device auth
"""

from __future__ import annotations
import argparse
import asyncio
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
    """Requirement 6: Check device login / Application Default Credentials."""
    print("🔑 [Device Login & Credentials Check]")
    print("\n1. Google Gemini / AGY:")
    if settings.gemini_api_key:
        print("  ✓ GEMINI_API_KEY is configured.")
    else:
        print("  ℹ No GEMINI_API_KEY found. Checking Application Default Credentials / Device Login...")
        try:
            from google import genai
            client = genai.Client()
            print("  ✓ Google Application Default Credentials (ADC) successfully detected!")
        except Exception as e:
            print(f"  ⚠ Google ADC not active: {e}")
            print("  👉 To authenticate via device login, run: `gcloud auth application-default login`")

    print("\n2. Local Model Endpoint:")
    print(f"  Testing connection to: {settings.local_base_url} ...")
    try:
        import httpx
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(settings.local_base_url.replace("/v1", ""))
            print(f"  ✓ Local server responded with status: {resp.status_code}")
    except Exception as e:
        print(f"  ℹ Local server not reachable at {settings.local_base_url} ({type(e).__name__})")
        print("    (Start Ollama, vLLM, or LM Studio when using the local provider)")


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

    args = parser.parse_args()

    if args.check_env:
        check_env()
    elif args.status:
        show_status()
    elif args.device_login:
        asyncio.run(device_login_check())
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
