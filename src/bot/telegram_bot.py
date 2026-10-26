"""Telegram Bot Interface for Telegram Assistant.

Requirement 2: Can connect and communicate via telegram bot.
Features:
- Full conversational interaction with Telegram assistant
- Streaming / typing indicators and tool execution notifications
- Document / file upload and download support
- Model switching (/model, /provider)
- Markdown limitations and config inspection (/limits, /config, /reload)
- Direct environment querying (/env)
"""

from __future__ import annotations
import asyncio
import logging
from pathlib import Path
from typing import Optional
from telegram import Update
from telegram.constants import ChatAction, ParseMode
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from src.config import settings
from src.agent.harness import harness
from src.agent.memory import memory_manager
from src.models.factory import model_factory
from src.bot.formatters import split_message_chunks

logger = logging.getLogger(__name__)


def is_authorized(user_id: int) -> bool:
    """Check if Telegram user is allowed to interact with the bot."""
    if settings.allow_all_users:
        return True
    return user_id in settings.allowed_telegram_users


async def send_safe_message(update: Update, text: str) -> None:
    """Send text split into safe chunks with Markdown fallback."""
    chunks = split_message_chunks(text)
    for chunk in chunks:
        if not chunk.strip():
            continue
        try:
            await update.effective_message.reply_text(chunk, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            # Fallback to plain text if Markdown syntax error occurs
            await update.effective_message.reply_text(chunk)


# --- Command Handlers ---

async def start_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_authorized(user.id):
        await update.effective_message.reply_text("⛔ Access denied. Your user ID is not authorized.")
        return

    client, model = model_factory.get_client()
    welcome_text = (
        f"👋 **Hello {user.first_name}!**\n\n"
        f"I am your personal AI Assistant with direct file and system access.\n\n"
        f"🔹 **Active Provider:** `{model_factory.active_provider}`\n"
        f"🔹 **Active Model:** `{model}`\n"
        f"🔹 **Workspace Root:** `{settings.workspace_root}`\n\n"
        f"**Commands:**\n"
        f"• `/help` - View usage guide & capabilities\n"
        f"• `/model [name]` - View or switch model\n"
        f"• `/provider [name]` - Switch provider (`gemini`, `openai`, `local`)\n"
        f"• `/status` - Check assistant status\n"
        f"• `/limits` - View rules from `LIMITATIONS.md`\n"
        f"• `/config` - View settings from `CONFIG.md`\n"
        f"• `/reload` - Reload markdown configs & .env dynamically\n"
        f"• `/clear` - Reset conversation memory\n"
        f"• `/env [key]` - Read environment variable\n"
        f"• `/file <path>` - Download a file from workspace\n\n"
        f"Send me a message or upload a document to get started!"
    )
    await send_safe_message(update, welcome_text)


async def help_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_authorized(user.id):
        return

    help_text = (
        "📖 **Telegram Assistant Guide**\n\n"
        "**What I can do:**\n"
        "1. 📂 **File Access:** Read, write, edit, search, and list workspace files.\n"
        "2. 🔐 **Environment Variables:** Read any `.env` variable regardless of passwords.\n"
        "3. ⚡ **Command Execution:** Run shell commands safely within timeouts.\n"
        "4. 📥 **File Transfers:** Upload documents or photos directly to the chat, or request files with `/file <path>`.\n"
        "5. ⚙️ **Configurable Limits:** All rules and limits are saved in `CONFIG.md` and `LIMITATIONS.md`.\n\n"
        "**Supported Providers:**\n"
        "• Google Gemini / AGY (`/provider gemini`)\n"
        "• OpenAI / Codex (`/provider openai`)\n"
        "• Local Models (Ollama/vLLM) (`/provider local`)\n"
    )
    await send_safe_message(update, help_text)


async def model_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_authorized(user.id):
        return

    args = context.args
    if not args:
        client, model = model_factory.get_client()
        await update.effective_message.reply_text(
            f"Current active model: `{model}` (Provider: `{model_factory.active_provider}`)\n"
            f"To switch model: `/model <model_name>`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    new_model = args[0].strip()
    model_factory.set_active_model(new_model)
    await update.effective_message.reply_text(
        f"✅ Active model updated to: `{new_model}`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def provider_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_authorized(user.id):
        return

    args = context.args
    if not args:
        await update.effective_message.reply_text(
            f"Active provider: `{model_factory.active_provider}`\n"
            f"Usage: `/provider <gemini|openai|local>`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    new_provider = args[0].strip().lower()
    try:
        model_factory.set_active_provider(new_provider)
        client, model = model_factory.get_client()
        await update.effective_message.reply_text(
            f"✅ Switched provider to `{new_provider}` (Model: `{model}`)",
            parse_mode=ParseMode.MARKDOWN,
        )
    except Exception as e:
        await update.effective_message.reply_text(f"❌ Error switching provider: {str(e)}")


async def status_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_authorized(user.id):
        return

    status = model_factory.get_status()
    session = memory_manager.get_session(str(update.effective_chat.id))
    status_text = (
        f"📊 **System Status**\n\n"
        f"• **Active Provider:** `{status['active_provider']}`\n"
        f"• **Model Override:** `{status['active_model_override'] or 'None'}`\n"
        f"• **Session Turns:** `{len(session.messages)}`\n"
        f"• **Workspace:** `{settings.workspace_root}`\n\n"
        f"**Provider Status:**\n"
        f"• **Gemini:** Model `{status['gemini']['model']}` (API Key: `{'Set' if status['gemini']['has_api_key'] else 'ADC/Device'}`)\n"
        f"• **OpenAI:** Model `{status['openai']['model']}` (API Key: `{'Set' if status['openai']['has_api_key'] else 'Missing'}`)\n"
        f"• **Local:** Model `{status['local']['model']}` (URL: `{status['local']['endpoint']}`)\n"
    )
    await send_safe_message(update, status_text)


async def limits_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_authorized(user.id):
        return

    if settings.raw_limitations_md:
        await send_safe_message(update, f"📋 **LIMITATIONS.md Content:**\n\n{settings.raw_limitations_md}")
    else:
        await update.effective_message.reply_text("LIMITATIONS.md is empty or missing.")


async def config_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_authorized(user.id):
        return

    if settings.raw_config_md:
        await send_safe_message(update, f"⚙️ **CONFIG.md Content:**\n\n{settings.raw_config_md}")
    else:
        await update.effective_message.reply_text("CONFIG.md is empty or missing.")


async def reload_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_authorized(user.id):
        return

    settings.reload()
    await update.effective_message.reply_text("🔄 Successfully reloaded `CONFIG.md`, `LIMITATIONS.md`, and `.env`!")


async def clear_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_authorized(user.id):
        return

    chat_id = str(update.effective_chat.id)
    memory_manager.clear_session(chat_id)
    await update.effective_message.reply_text("🧹 Conversation memory cleared.")


async def env_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Read environment variable regardless of password/secret."""
    user = update.effective_user
    if not is_authorized(user.id):
        return

    args = context.args
    if not args:
        await update.effective_message.reply_text("Usage: `/env <KEY_NAME>`", parse_mode=ParseMode.MARKDOWN)
        return

    key = args[0].strip()
    val = settings.get_env(key, None)
    if val is not None:
        await update.effective_message.reply_text(f"`{key}` = `{val}`", parse_mode=ParseMode.MARKDOWN)
    else:
        await update.effective_message.reply_text(f"Environment variable `{key}` is not set.", parse_mode=ParseMode.MARKDOWN)


async def file_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send a workspace file to the user as a Telegram document."""
    user = update.effective_user
    if not is_authorized(user.id):
        return

    args = context.args
    if not args:
        await update.effective_message.reply_text("Usage: `/file <relative_file_path>`", parse_mode=ParseMode.MARKDOWN)
        return

    path_str = " ".join(args).strip()
    target = (settings.workspace_root / path_str).resolve()
    if not target.exists() or not target.is_file():
        await update.effective_message.reply_text(f"File not found: `{path_str}`", parse_mode=ParseMode.MARKDOWN)
        return

    await update.effective_message.reply_document(document=target.open("rb"), filename=target.name)


# --- Message & Document Handlers ---

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not is_authorized(user.id):
        await update.effective_message.reply_text("⛔ Access denied.")
        return

    text = update.effective_message.text
    if not text:
        return

    chat_id = update.effective_chat.id
    status_msg = None

    # Continuous typing task
    stop_typing = asyncio.Event()

    async def keep_typing():
        while not stop_typing.is_set():
            try:
                await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)
            except Exception:
                pass
            try:
                await asyncio.wait_for(stop_typing.wait(), timeout=4.0)
            except asyncio.TimeoutError:
                pass

    typing_task = asyncio.create_task(keep_typing())

    async def on_status(msg: str):
        nonlocal status_msg
        try:
            if status_msg is None:
                status_msg = await update.effective_message.reply_text(msg, parse_mode=ParseMode.MARKDOWN)
            else:
                await status_msg.edit_text(msg, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass

    try:
        response_text = await harness.run(
            session_id=str(chat_id),
            user_input=text,
            on_status_update=on_status,
        )
    finally:
        stop_typing.set()
        await typing_task

    # Clean up status message if it was sent
    if status_msg:
        try:
            await status_msg.delete()
        except Exception:
            pass

    await send_safe_message(update, response_text)


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle document or photo sent by user, saving it to workspace."""
    user = update.effective_user
    if not is_authorized(user.id):
        await update.effective_message.reply_text("⛔ Access denied.")
        return

    doc = update.effective_message.document
    photo = update.effective_message.photo
    caption = update.effective_message.caption or ""

    download_dir = settings.download_dir

    if doc:
        file_obj = await context.bot.get_file(doc.file_id)
        filename = doc.file_name or f"file_{doc.file_id[:8]}"
        destination = download_dir / filename
        await file_obj.download_to_drive(destination)
        file_desc = f"User uploaded a document '{filename}' (size: {doc.file_size} bytes) saved to '{destination}'."
    elif photo:
        largest_photo = photo[-1]
        file_obj = await context.bot.get_file(largest_photo.file_id)
        filename = f"photo_{largest_photo.file_id[:8]}.jpg"
        destination = download_dir / filename
        await file_obj.download_to_drive(destination)
        file_desc = f"User uploaded a photo saved to '{destination}'."
    else:
        return

    prompt = f"{file_desc}\nUser message / caption: {caption}" if caption else file_desc
    chat_id = update.effective_chat.id

    await update.effective_message.reply_text(f"📥 Received and saved to `{destination.relative_to(settings.workspace_root)}`", parse_mode=ParseMode.MARKDOWN)

    # Trigger agent response
    response = await harness.run(session_id=str(chat_id), user_input=prompt)
    await send_safe_message(update, response)


def create_telegram_application() -> Application:
    """Create and configure Telegram Application instance."""
    token = settings.telegram_bot_token
    if not token or token == "your_telegram_bot_token_here":
        raise ValueError(
            "TELEGRAM_BOT_TOKEN is not configured! "
            "Please provide a valid bot token in your .env file."
        )

    app = ApplicationBuilder().token(token).build()

    # Commands
    app.add_handler(CommandHandler("start", start_cmd))
    app.add_handler(CommandHandler("help", help_cmd))
    app.add_handler(CommandHandler("model", model_cmd))
    app.add_handler(CommandHandler("provider", provider_cmd))
    app.add_handler(CommandHandler("status", status_cmd))
    app.add_handler(CommandHandler("limits", limits_cmd))
    app.add_handler(CommandHandler("config", config_cmd))
    app.add_handler(CommandHandler("reload", reload_cmd))
    app.add_handler(CommandHandler("clear", clear_cmd))
    app.add_handler(CommandHandler("reset", clear_cmd))
    app.add_handler(CommandHandler("env", env_cmd))
    app.add_handler(CommandHandler("file", file_cmd))

    # Messages & Documents
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.PHOTO, handle_document))

    return app


def run_telegram_bot() -> None:
    """Run Telegram bot polling loop."""
    app = create_telegram_application()
    logger.info("Starting Telegram Assistant Bot polling...")
    print("🚀 Telegram Assistant Bot is running! Press Ctrl+C to stop.")
    app.run_polling()
