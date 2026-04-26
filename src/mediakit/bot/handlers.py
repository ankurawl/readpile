"""Bot handlers — message and command handlers."""

import io
import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

from mediakit.core.detector import detect_url_type, URLType
from mediakit.transcribers.youtube import (
    transcribe_youtube,
    get_youtube_metadata,
    get_youtube_transcript,
    VideoNotFoundError,
    TranscriptNotAvailableError,
)
from mediakit.scrapers.article import scrape_article
from mediakit.transcribers.audio import transcribe_from_url
from mediakit.summarizer.engine import summarize
from mediakit.summarizer.providers import get_provider, LLMConnectionError
from mediakit.bot.whitelist import is_whitelisted, add_to_whitelist, remove_from_whitelist, load_whitelist
from mediakit.bot.preferences import get_preferences, set_preference, add_to_history, get_history
from mediakit.bot.telegram_formatter import (
    format_summary_message,
    create_summary_document,
    format_error_message,
    format_processing_status,
)

logger = logging.getLogger(__name__)

URL_PATTERN = re.compile(
    r'https?://[^\s<>\"\']+',
)


def _get_config(context: ContextTypes.DEFAULT_TYPE) -> dict:
    return context.bot_data.get("config", {})


async def start_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Welcome to MediaKit Bot!\n\n"
        "Send me any URL and I'll summarize it for you.\n"
        "Supported: YouTube, blogs, articles, podcasts, audio/video.\n\n"
        "Commands:\n"
        "/help - List available commands\n"
        "/whoami - Show your chat ID\n"
        "/set_language <code> - Set transcript language\n"
        "/set_style <brief|detailed> - Set summary style\n"
        "/history - Show recently processed items"
    )


async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_text(
        "Available commands:\n\n"
        "/start - Welcome message\n"
        "/help - This help message\n"
        "/whoami - Show your chat ID\n"
        "/set_language <code> - Set transcript language (e.g., en, es, hi)\n"
        "/set_style <brief|detailed> - Set summary style\n"
        "/history - Show recently processed items\n\n"
        "Admin commands:\n"
        "/admin_add <chat_id> - Add user to whitelist\n"
        "/admin_remove <chat_id> - Remove user from whitelist\n"
        "/admin_list - Show whitelisted users\n\n"
        "Or just send any URL to get a summary!"
    )


async def whoami_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat_id = update.effective_chat.id
    await update.message.reply_text(f"Your chat ID: {chat_id}")


async def set_language_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = _get_config(context)
    admin_chat_id = config.get("admin_chat_id", 0)
    data_dir = config.get("data_dir", "./data")
    chat_id = update.effective_chat.id

    if not is_whitelisted(chat_id, admin_chat_id, data_dir):
        return

    if not context.args:
        await update.message.reply_text("Usage: /set_language <language_code>\nExample: /set_language es")
        return

    lang = context.args[0]
    set_preference(chat_id, "language", lang, data_dir)
    await update.message.reply_text(f"Language set to: {lang}")


async def set_style_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = _get_config(context)
    admin_chat_id = config.get("admin_chat_id", 0)
    data_dir = config.get("data_dir", "./data")
    chat_id = update.effective_chat.id

    if not is_whitelisted(chat_id, admin_chat_id, data_dir):
        return

    if not context.args:
        await update.message.reply_text("Usage: /set_style <brief|detailed>")
        return

    style = context.args[0]
    try:
        set_preference(chat_id, "style", style, data_dir)
        await update.message.reply_text(f"Style set to: {style}")
    except ValueError as e:
        await update.message.reply_text(str(e))


async def history_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = _get_config(context)
    admin_chat_id = config.get("admin_chat_id", 0)
    data_dir = config.get("data_dir", "./data")
    chat_id = update.effective_chat.id

    if not is_whitelisted(chat_id, admin_chat_id, data_dir):
        return

    history = get_history(chat_id, data_dir)
    if not history:
        await update.message.reply_text("No items processed yet.")
        return

    lines = []
    for entry in reversed(history[-10:]):
        title = entry.get("title", "Unknown")
        url = entry.get("url", "")
        processed = entry.get("processed_at", "")[:10]
        lines.append(f"- {title}\n  {url} ({processed})")

    await update.message.reply_text("Recent items:\n\n" + "\n\n".join(lines))


async def admin_add_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = _get_config(context)
    admin_chat_id = config.get("admin_chat_id", 0)
    data_dir = config.get("data_dir", "./data")
    chat_id = update.effective_chat.id

    if chat_id != admin_chat_id:
        await update.message.reply_text("You are not authorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /admin_add <chat_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid chat_id. Must be an integer.")
        return

    added = add_to_whitelist(target_id, data_dir)
    if added:
        await update.message.reply_text(f"Added {target_id} to whitelist.")
    else:
        await update.message.reply_text(f"{target_id} is already whitelisted.")


async def admin_remove_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = _get_config(context)
    admin_chat_id = config.get("admin_chat_id", 0)
    data_dir = config.get("data_dir", "./data")
    chat_id = update.effective_chat.id

    if chat_id != admin_chat_id:
        await update.message.reply_text("You are not authorized.")
        return

    if not context.args:
        await update.message.reply_text("Usage: /admin_remove <chat_id>")
        return

    try:
        target_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("Invalid chat_id. Must be an integer.")
        return

    removed = remove_from_whitelist(target_id, data_dir)
    if removed:
        await update.message.reply_text(f"Removed {target_id} from whitelist.")
    else:
        await update.message.reply_text(f"{target_id} was not in the whitelist.")


async def admin_list_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = _get_config(context)
    admin_chat_id = config.get("admin_chat_id", 0)
    data_dir = config.get("data_dir", "./data")
    chat_id = update.effective_chat.id

    if chat_id != admin_chat_id:
        await update.message.reply_text("You are not authorized.")
        return

    wl = load_whitelist(data_dir)
    if not wl:
        await update.message.reply_text("Whitelist is empty (admin is always allowed).")
    else:
        ids = "\n".join(str(x) for x in sorted(wl))
        await update.message.reply_text(f"Whitelisted chat IDs:\n{ids}")


async def _handle_youtube(url: str, language: str, config: dict) -> tuple[str, str, dict]:
    """Process a YouTube URL. Returns (summary, transcript, metadata_dict)."""
    metadata = get_youtube_metadata(url)
    transcript = get_youtube_transcript(metadata["video_id"], language)
    provider = get_provider(config)
    summary = summarize(transcript, provider, metadata=metadata)
    return summary, transcript, metadata


async def _handle_article(url: str, config: dict) -> tuple[str, str, dict]:
    """Process a blog/article URL via Playwright. Returns (summary, text, metadata_dict)."""
    from playwright.async_api import async_playwright

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url, wait_until="domcontentloaded")
            html = await page.content()
        finally:
            await browser.close()

    content_item = scrape_article(url, html)
    provider = get_provider(config)
    summary = summarize(content_item.text, provider, metadata={"title": content_item.title})
    metadata = {
        "title": content_item.title,
        "channel": content_item.author or "",
        "duration": "",
        "url": url,
    }
    return summary, content_item.text, metadata


async def _handle_audio_video(url: str, config: dict) -> tuple[str, str, dict]:
    """Process an audio/video URL. Returns (summary, transcript, metadata_dict)."""
    content_item = transcribe_from_url(url)
    provider = get_provider(config)
    summary = summarize(content_item.text, provider, metadata={"title": content_item.title})
    metadata = {
        "title": content_item.title,
        "channel": content_item.channel or "",
        "duration": content_item.duration or "",
        "url": url,
    }
    return summary, content_item.text, metadata


async def url_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = _get_config(context)
    admin_chat_id = config.get("admin_chat_id", 0)
    data_dir = config.get("data_dir", "./data")
    chat_id = update.effective_chat.id
    text = update.message.text or ""

    match = URL_PATTERN.search(text)
    if not match:
        return

    if not is_whitelisted(chat_id, admin_chat_id, data_dir):
        username = update.effective_user.username if update.effective_user else "unknown"
        logger.warning(f"Unauthorized: chat_id {chat_id} (@{username})")
        return

    url = match.group(0)

    prefs = get_preferences(chat_id, data_dir)
    language = prefs.get("language", "en")
    style = prefs.get("style", "detailed")

    status_msg = await update.message.reply_text(format_processing_status("detecting"))

    try:
        url_type = detect_url_type(url)

        if url_type == URLType.youtube:
            await status_msg.edit_text(format_processing_status("metadata"))
            summary, transcript, metadata = await _handle_youtube(url, language, config)

        elif url_type == URLType.blog:
            await status_msg.edit_text(format_processing_status("scraping"))
            summary, transcript, metadata = await _handle_article(url, config)

        elif url_type in (URLType.audio_file, URLType.video):
            await status_msg.edit_text(format_processing_status("downloading"))
            summary, transcript, metadata = await _handle_audio_video(url, config)

        else:
            # Default fallback: treat as article/blog
            await status_msg.edit_text(format_processing_status("scraping"))
            summary, transcript, metadata = await _handle_article(url, config)

        await status_msg.edit_text(format_processing_status("formatting"))

        msg_text = format_summary_message(metadata, summary, style)
        await status_msg.edit_text(msg_text, parse_mode="HTML")

        doc_bytes, doc_filename = create_summary_document(metadata, summary, transcript)
        await update.message.reply_document(
            document=io.BytesIO(doc_bytes),
            filename=doc_filename,
        )

        add_to_history(chat_id, {
            "title": metadata.get("title", ""),
            "url": metadata.get("url", url),
            "type": url_type.value,
        }, data_dir)

    except VideoNotFoundError as e:
        await status_msg.edit_text(format_error_message(str(e)), parse_mode="HTML")
    except TranscriptNotAvailableError as e:
        await status_msg.edit_text(format_error_message(str(e)), parse_mode="HTML")
    except LLMConnectionError as e:
        await status_msg.edit_text(format_error_message(str(e)), parse_mode="HTML")
    except Exception as e:
        logger.exception("Error processing URL")
        await status_msg.edit_text(
            format_error_message("An unexpected error occurred. Please try again."),
            parse_mode="HTML",
        )
