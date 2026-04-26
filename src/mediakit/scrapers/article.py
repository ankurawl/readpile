"""Article scraper — extract clean article content from web pages.

Migrated from blog-scraper's extractor.py (ContentExtractor) and
converter.py (MarkdownConverter).  Produces a ``ContentItem`` with
markdown text and rich metadata.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from bs4 import BeautifulSoup

from mediakit.core.models import ContentItem, ContentType


# ── dependency guard ──────────────────────────────────────────────


def _check_deps() -> None:
    """Verify scraping dependencies are installed."""
    missing: list[str] = []
    for mod in ("bs4", "lxml", "readability", "markdownify"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        raise SystemExit(
            f"Article scraping requires: {', '.join(missing)}.\n"
            "Install with:\n"
            '  pip install mediakit\n'
            "  or: pip install beautifulsoup4 lxml readability-lxml markdownify\n"
        )


# ── public entry point ─────────────────────────────────────────────


def scrape_article(url: str, html: str) -> ContentItem:
    """Extract article content and metadata, returning a ``ContentItem``.

    Parameters
    ----------
    url:
        The source URL of the page (used for date extraction and stored
        as ``source_url``).
    html:
        Raw HTML of the page.
    """
    _check_deps()

    from bs4 import BeautifulSoup

    soup = BeautifulSoup(html, "lxml")
    article_html = _extract_article_html(html)
    title = _extract_title(soup)
    pub_date = _extract_date(url, soup)
    author = _extract_author(soup)
    tags = _extract_tags(soup)

    markdown = _html_to_markdown(article_html)
    markdown = _clean_markdown(markdown)

    return ContentItem(
        content_type=ContentType.article,
        text=markdown,
        title=title,
        source_url=url,
        date=pub_date,
        author=author,
        tags=tags,
    )


# ── HTML extraction ────────────────────────────────────────────────


def _extract_article_html(html: str) -> str:
    """Use readability-lxml to pull the main article content.

    Falls back to ``<article>``, ``<main>``, or ``<body>`` if readability
    fails.
    """
    from bs4 import BeautifulSoup
    from readability import Document

    try:
        doc = Document(html)
        return doc.summary()
    except Exception:
        soup = BeautifulSoup(html, "lxml")
        for tag in ["article", "main"]:
            el = soup.find(tag)
            if el:
                return str(el)
        body = soup.find("body")
        return str(body) if body else html


# ── metadata helpers ───────────────────────────────────────────────


def _extract_title(soup: BeautifulSoup) -> str:
    """Extract the page title.

    Priority: og:title > h1 inside article/main > any h1 > <title> tag
    (with site suffix stripped).
    """
    # og:title
    og_title = soup.find("meta", property="og:title")
    if og_title and og_title.get("content", "").strip():
        return og_title["content"].strip()

    # h1 inside article or main
    for container in [soup.find("article"), soup.find("main")]:
        if container:
            h1 = container.find("h1")
            if h1 and h1.get_text(strip=True):
                return h1.get_text(strip=True)

    # Any h1
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)

    # <title> tag — strip common site-name suffixes
    title_tag = soup.find("title")
    if title_tag and title_tag.get_text(strip=True):
        title = title_tag.get_text(strip=True)
        for sep in [" | ", " - ", " — ", " – ", " :: "]:
            if sep in title:
                title = title.split(sep)[0].strip()
                break
        return title

    return "Untitled"


def _extract_date(url: str, soup: BeautifulSoup) -> date | None:
    """Extract the publishing date from multiple sources.

    Checks (in order): article:published_time meta tags, Schema.org
    ``datePublished``, ``<time datetime>``, misc date meta tags, and
    finally a date pattern embedded in the URL.
    """
    # 1. meta article:published_time
    for prop in [
        "article:published_time",
        "article:published",
        "og:article:published_time",
    ]:
        meta = soup.find("meta", property=prop)
        if meta and meta.get("content"):
            d = _parse_date_string(meta["content"])
            if d:
                return d

    # 2. Schema.org datePublished
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = data[0] if data else {}
            date_str = data.get("datePublished", "")
            if date_str:
                d = _parse_date_string(date_str)
                if d:
                    return d
        except (json.JSONDecodeError, AttributeError):
            continue

    # 3. <time datetime="...">
    time_el = soup.find("time", attrs={"datetime": True})
    if time_el:
        d = _parse_date_string(time_el["datetime"])
        if d:
            return d

    # 4. Date meta tags
    for name in ["date", "DC.date", "pubdate", "publish_date"]:
        meta = soup.find("meta", attrs={"name": name})
        if meta and meta.get("content"):
            d = _parse_date_string(meta["content"])
            if d:
                return d

    # 5. Date pattern in URL
    url_date = _extract_date_from_url(url)
    if url_date:
        return url_date

    return None


def _parse_date_string(date_str: str) -> date | None:
    """Try multiple date formats, falling back to ISO parsing."""
    date_str = date_str.strip()
    formats = [
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%B %d, %Y",
        "%b %d, %Y",
        "%d %B %Y",
        "%d %b %Y",
        "%m/%d/%Y",
        "%Y-%m-%dT%H:%M:%SZ",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt).date()
        except ValueError:
            continue

    # ISO fallback — strip trailing timezone offset first
    try:
        clean = re.sub(r"[+-]\d{2}:\d{2}$", "", date_str)
        return datetime.fromisoformat(clean).date()
    except (ValueError, TypeError):
        pass

    return None


def _extract_date_from_url(url: str) -> date | None:
    """Extract a date from URL patterns like ``/2024/03/15/`` or ``/2024-03-15``."""
    # /YYYY/MM/DD/
    match = re.search(r"/(\d{4})/(\d{2})/(\d{2})/", url)
    if match:
        try:
            return date(int(match[1]), int(match[2]), int(match[3]))
        except ValueError:
            pass

    # /YYYY-MM-DD
    match = re.search(r"/(\d{4})-(\d{2})-(\d{2})", url)
    if match:
        try:
            return date(int(match[1]), int(match[2]), int(match[3]))
        except ValueError:
            pass

    # /YYYY/MM/ (day unknown — default to 1st)
    match = re.search(r"/(\d{4})/(\d{2})/", url)
    if match:
        try:
            return date(int(match[1]), int(match[2]), 1)
        except ValueError:
            pass

    return None


def _extract_tags(soup: BeautifulSoup) -> list[str]:
    """Extract tags/categories from the page.

    Sources: meta keywords, ``rel="tag"`` links, elements with
    tag/category/label classes, and Schema.org ``keywords``.
    """
    tags: set[str] = set()

    # meta keywords
    meta_kw = soup.find("meta", attrs={"name": "keywords"})
    if meta_kw and meta_kw.get("content"):
        for kw in meta_kw["content"].split(","):
            kw = kw.strip().lower()
            if kw and len(kw) < 50:
                tags.add(kw)

    # Links with rel="tag"
    for a in soup.find_all("a", rel="tag"):
        text = a.get_text(strip=True).lower()
        if text and len(text) < 50:
            tags.add(text)

    # Links in elements with tag/category classes
    for el in soup.find_all(class_=re.compile(r"tag|category|label", re.I)):
        if el.name == "a":
            text = el.get_text(strip=True).lower()
            if text and len(text) < 50:
                tags.add(text)
        else:
            for a in el.find_all("a"):
                text = a.get_text(strip=True).lower()
                if text and len(text) < 50:
                    tags.add(text)

    # Schema.org keywords
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = data[0] if data else {}
            keywords = data.get("keywords", [])
            if isinstance(keywords, str):
                keywords = [k.strip() for k in keywords.split(",")]
            for kw in keywords:
                kw = kw.strip().lower()
                if kw and len(kw) < 50:
                    tags.add(kw)
        except (json.JSONDecodeError, AttributeError):
            continue

    return sorted(tags)


def _extract_author(soup: BeautifulSoup) -> str | None:
    """Extract the author name.

    Sources: meta author tag, Schema.org author (dict, string, or list),
    and elements with author/byline classes.
    """
    # meta author
    meta = soup.find("meta", attrs={"name": "author"})
    if meta and meta.get("content", "").strip():
        return meta["content"].strip()

    # Schema.org author
    for script in soup.find_all("script", {"type": "application/ld+json"}):
        try:
            data = json.loads(script.string or "")
            if isinstance(data, list):
                data = data[0] if data else {}
            author = data.get("author", {})
            if isinstance(author, dict):
                name = author.get("name", "")
                if name:
                    return name.strip()
            elif isinstance(author, str):
                return author.strip()
            elif isinstance(author, list) and author:
                first = author[0]
                if isinstance(first, dict):
                    return first.get("name", "").strip() or None
                elif isinstance(first, str):
                    return first.strip()
        except (json.JSONDecodeError, AttributeError):
            continue

    # Element with author/byline class
    for el in soup.find_all(class_=re.compile(r"author|byline", re.I)):
        text = el.get_text(strip=True)
        text = re.sub(r"^by\s+", "", text, flags=re.I).strip()
        if text and len(text) < 100:
            return text

    return None


# ── markdown conversion ───────────────────────────────────────────


def _html_to_markdown(html: str) -> str:
    """Convert HTML to markdown via markdownify.

    Uses ATX-style headings, strips non-content elements (script, style,
    nav, footer, aside), and converts a curated set of block/inline tags.
    """
    from markdownify import markdownify as md

    return md(
        html,
        heading_style="ATX",
        bullets="-",
        convert=[
            "p", "h1", "h2", "h3", "h4", "h5", "h6",
            "a", "img",
            "ul", "ol", "li",
            "blockquote", "pre", "code",
            "table", "thead", "tbody", "tr", "th", "td",
            "strong", "em", "b", "i",
            "br", "hr",
            "figure", "figcaption",
        ],
    )


def _clean_markdown(text: str) -> str:
    """Post-process markdown for readability.

    - Collapses runs of >2 blank lines.
    - Strips residual wrapper HTML tags (div, span, section, ...).
    - Fixes broken link whitespace.
    - Strips trailing whitespace per line.
    """
    # Collapse excessive blank lines
    text = re.sub(r"\n{4,}", "\n\n\n", text)

    # Remove residual HTML wrapper tags
    text = re.sub(
        r"</?(?:div|span|section|header|footer|aside)[^>]*>", "", text
    )

    # Fix broken link formatting — [text]( url ) -> [text](url)
    text = re.sub(r"\[([^\]]*)\]\(\s+", r"[\1](", text)
    text = re.sub(r"\[([^\]]*)\]\(([^)]*?)\s+\)", r"[\1](\2)", text)

    # Strip trailing whitespace from each line
    text = "\n".join(line.rstrip() for line in text.split("\n"))

    # Strip leading/trailing whitespace from the whole document
    text = text.strip()

    return text
