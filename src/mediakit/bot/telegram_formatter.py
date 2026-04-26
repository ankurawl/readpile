"""Telegram formatter — convert markdown to Telegram-safe markup."""

import re
from datetime import datetime
from mediakit.core.archiver import sanitize_filename

TELEGRAM_MSG_LIMIT = 4096
TRUNCATION_SUFFIX = "\n\n... [Full summary attached as file]"


def _extract_section(summary: str, heading: str) -> str:
    """Extract a specific ## section from the summary markdown."""
    pattern = rf"(## {re.escape(heading)}.*?)(?=\n## |\Z)"
    match = re.search(pattern, summary, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def format_summary_message(metadata: dict, summary: str, style: str = "detailed") -> str:
    """Formats summary for Telegram message (HTML parse mode).
    If style='brief', only includes Key Takeaways.
    Truncates to 4096 chars with note if needed."""
    title = metadata.get("title", "")
    channel = metadata.get("channel", "")
    duration = metadata.get("duration", "")
    url = metadata.get("url", "")

    header = f"<b>{title}</b>\n{channel} | {duration}\n{url}\n\n"

    if style == "brief":
        body = _extract_section(summary, "Key Takeaways")
        body = _md_to_html(body)
    else:
        body = _md_to_html(summary)

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


def create_summary_document(metadata: dict, summary: str, transcript: str) -> tuple[bytes, str]:
    """Returns (file_bytes, filename) for sending as Telegram document."""
    processed = datetime.now().strftime("%Y-%m-%d %H:%M")
    content = f"""# {metadata.get("title", "")}

- **Channel**: {metadata.get("channel", "")}
- **Duration**: {metadata.get("duration", "")}
- **URL**: {metadata.get("url", "")}
- **Processed**: {processed}

---

{summary}

---

## Full Transcript

{transcript}
"""
    date_str = datetime.now().strftime("%Y-%m-%d")
    sanitized = sanitize_filename(metadata.get("title", "untitled"))
    filename = f"{date_str}_{sanitized}.md"
    return content.encode("utf-8"), filename


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
        "summarizing": "Summarizing with LLM...",
        "formatting": "Formatting output...",
    }
    return steps.get(step, f"{step}...")
