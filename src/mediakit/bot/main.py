"""Bot main — entry point for the Telegram bot."""

import logging
import os
import sys

from mediakit.core.config import load_config

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Dependency guard
# ---------------------------------------------------------------------------


def _check_deps() -> None:
    """Verify Telegram bot dependencies are installed."""
    try:
        import telegram  # noqa: F401
    except ImportError:
        raise SystemExit(
            "The Telegram bot requires python-telegram-bot. Install with:\n"
            "  pip install 'mediakit[bot]'\n"
            "  or: pip install python-telegram-bot\n"
        )


def main() -> None:
    """Entry point. Loads config, registers handlers, starts polling."""
    _check_deps()

    from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters

    from mediakit.bot.handlers import (
        start_handler,
        help_handler,
        whoami_handler,
        set_language_handler,
        set_style_handler,
        history_handler,
        admin_add_handler,
        admin_remove_handler,
        admin_list_handler,
        url_message_handler,
    )

    config = load_config()

    token = config.get("bot", {}).get("token") or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Missing bot token. Set it in config.toml [bot] or TELEGRAM_BOT_TOKEN env var.")
        sys.exit(1)

    admin_chat_id_str = os.getenv("ADMIN_CHAT_ID", "")
    if not admin_chat_id_str:
        print("Missing ADMIN_CHAT_ID. Set it in environment.")
        sys.exit(1)

    try:
        admin_chat_id = int(admin_chat_id_str)
    except ValueError:
        print(f"ADMIN_CHAT_ID must be an integer, got: {admin_chat_id_str}")
        sys.exit(1)

    data_dir = os.getenv("DATA_DIR", "./data")
    os.makedirs(data_dir, exist_ok=True)

    app = ApplicationBuilder().token(token).build()

    app.bot_data["config"] = {
        "admin_chat_id": admin_chat_id,
        "data_dir": data_dir,
        **config,
    }

    app.add_handler(CommandHandler("start", start_handler))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("whoami", whoami_handler))
    app.add_handler(CommandHandler("set_language", set_language_handler))
    app.add_handler(CommandHandler("set_style", set_style_handler))
    app.add_handler(CommandHandler("history", history_handler))
    app.add_handler(CommandHandler("admin_add", admin_add_handler))
    app.add_handler(CommandHandler("admin_remove", admin_remove_handler))
    app.add_handler(CommandHandler("admin_list", admin_list_handler))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, url_message_handler))

    logger.info("Bot started")
    app.run_polling()
