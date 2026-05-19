"""Feed and channel discovery — async helpers extracted from mcp_server.py."""

from __future__ import annotations


def _ensure_scheme(url: str) -> str:
    if url and not url.startswith(("http://", "https://")):
        return "https://" + url
    return url


async def resolve_youtube_feed(url: str) -> str | None:
    """Resolve a YouTube channel URL to its RSS feed URL."""
    import re
    import httpx

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url, headers={"User-Agent": "readpile/0.1"})
            resp.raise_for_status()
            html = resp.text
    except Exception:
        return None

    channel_id = None

    match = re.search(r'"externalId"\s*:\s*"(UC[A-Za-z0-9_-]+)"', html)
    if match:
        channel_id = match.group(1)

    if not channel_id:
        match = re.search(r'"channelId"\s*:\s*"(UC[A-Za-z0-9_-]+)"', html)
        if match:
            channel_id = match.group(1)

    if not channel_id:
        match = re.search(r'youtube\.com/channel/(UC[A-Za-z0-9_-]+)', html)
        if match:
            channel_id = match.group(1)

    if not channel_id:
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "lxml")
        canonical = soup.find("link", rel="canonical")
        if canonical and canonical.get("href"):
            match = re.search(
                r'youtube\.com/channel/(UC[A-Za-z0-9_-]+)',
                canonical["href"],
            )
            if match:
                channel_id = match.group(1)

    if channel_id:
        return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"

    return None


async def discover_feed(
    url: str, prefer_keywords: list[str] | None = None,
) -> str | None:
    """Discover an RSS/Atom feed URL from a website URL."""
    import asyncio
    from urllib.parse import urlparse

    import httpx
    from bs4 import BeautifulSoup

    from readpile.core.detector import detect_url_type, URLType

    if detect_url_type(url) == URLType.rss:
        return url

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15.0) as client:
            resp = await client.get(url, headers={"User-Agent": "readpile/0.1"})
            resp.raise_for_status()
            html = resp.text
    except Exception:
        html = ""

    parsed = urlparse(url)
    base = f"{parsed.scheme}://{parsed.netloc}"

    candidates: list[str] = []
    if html:
        soup = BeautifulSoup(html, "lxml")
        rss_links = soup.find_all(
            "link", rel="alternate", type="application/rss+xml",
        )
        atom_links = soup.find_all(
            "link", rel="alternate", type="application/atom+xml",
        )
        all_links = rss_links + atom_links

        if prefer_keywords:
            preferred = [
                lnk for lnk in all_links
                if lnk.get("title") and any(
                    kw in lnk["title"].lower() for kw in prefer_keywords
                )
            ]
            ordered = preferred + [l for l in all_links if l not in preferred]
        else:
            ordered = all_links

        for lnk in ordered:
            href = lnk.get("href")
            if href:
                if href.startswith("/"):
                    href = base + href
                if href not in candidates:
                    candidates.append(href)

    patterns = [
        f"{base}/feed", f"{base}/feed.xml", f"{base}/rss",
        f"{base}/rss.xml", f"{base}/atom.xml",
    ]
    if prefer_keywords and "podcast" in prefer_keywords:
        patterns.insert(1, f"{base}/podcast/feed")
    for pattern in patterns:
        if pattern not in candidates:
            candidates.append(pattern)

    import feedparser

    for candidate in candidates:
        try:
            feed = await asyncio.wait_for(
                asyncio.to_thread(feedparser.parse, candidate),
                timeout=10.0,
            )
            if feed.entries:
                return candidate
        except Exception:
            continue

    return None


async def discover_podcast_feed(url: str) -> str | None:
    """Discover a podcast RSS feed URL from a website URL."""
    return await discover_feed(url, prefer_keywords=["podcast", "audio"])
