"""Telegram formatter — convert markdown to Telegram-safe markup."""

import re
from datetime import datetime
from readpile.core.archiver import sanitize_filename

TELEGRAM_MSG_LIMIT = 4096
TRUNCATION_SUFFIX = "\n\n... [Full content attached as file]"


def format_content_message(metadata: dict, content: str, style: str = "detailed") -> str:
    """Formats content for Telegram message (HTML parse mode).
    If style='brief', truncates to first ~500 chars.
    Truncates to 4096 chars with note if needed."""
    title = metadata.get("title", "")
    channel = metadata.get("channel", "")
    duration = metadata.get("duration", "")
    url = metadata.get("url", "")

    header = f"<b>{title}</b>\n{channel} | {duration}\n{url}\n\n"

    if style == "brief":
        body = content[:500]
        if len(content) > 500:
            body += "..."
        body = _md_to_html(body)
    else:
        body = _md_to_html(content)

    message = header + body

    if len(message) > TELEGRAM_MSG_LIMIT:
        max_body = TELEGRAM_MSG_LIMIT - len(header) - len(TRUNCATION_SUFFIX)
        body = body[:max_body]
        message = header + body + TRUNCATION_SUFFIX

    return message


def _md_to_html(text: str) -> str:
    """Convert markdown headings to bold text for Telegram HTML."""
    text = re.sub(r'^## (.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    text = re.sub(r'^### (.+)$', r'<b>\1</b>', text, flags=re.MULTILINE)
    return text


def create_content_document(metadata: dict, content: str) -> tuple[bytes, str]:
    """Returns (file_bytes, filename) for sending as Telegram document."""
    processed = datetime.now().strftime("%Y-%m-%d %H:%M")
    doc = f"""# {metadata.get("title", "")}

- **Channel**: {metadata.get("channel", "")}
- **Duration**: {metadata.get("duration", "")}
- **URL**: {metadata.get("url", "")}
- **Processed**: {processed}

---

{content}
"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    sanitized = sanitize_filename(metadata.get("title", "untitled"))
    filename = f"{date_str}_{sanitized}.md"
    return doc.encode("utf-8"), filename


def format_error_message(error: str) -> str:
    """Formats error for Telegram display."""
    return f"<b>Error</b>\n\n{error}"


def format_processing_status(step: str) -> str:
    """Returns status text for each processing step."""
    steps = {
        "detecting": "Detecting content type...",
        "metadata": "Fetching metadata...",
        "transcript": "Extracting transcript...",
        "scraping": "Scraping article content...",
        "downloading": "Downloading audio...",
        "transcribing": "Transcribing audio...",
        "formatting": "Formatting output...",
    }
    return steps.get(step, f"{step}...")
