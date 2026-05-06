"""Site crawler — recursive site-wide URL discovery."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlparse

if TYPE_CHECKING:
    from playwright.async_api import Page

logger = logging.getLogger(__name__)

_SKIP_EXTENSIONS = frozenset(
    [".pdf", ".png", ".jpg", ".jpeg", ".gif", ".svg", ".zip", ".csv", ".xlsx"]
)


def _check_deps() -> None:
    """Verify site crawling dependencies are installed."""
    try:
        import playwright  # noqa: F401
    except ImportError:
        raise SystemExit(
            "Site crawling requires playwright.\n"
            "Install with:\n"
            "  pip install readpile\n"
            "  or: pip install playwright\n"
        )


class SiteCrawler:
    """Async BFS crawler that discovers all URLs under a site prefix."""

    def __init__(
        self,
        base_url: str,
        max_depth: int = 10,
        scope: str = "prefix",
        headless: bool = True,
        max_pages: int | None = None,
    ):
        self.base_url = base_url
        self.max_depth = max_depth
        self.scope = scope
        self.headless = headless
        self.max_pages = max_pages

    async def crawl(self) -> list[str]:
        """BFS crawl returning a sorted list of discovered URLs."""
        _check_deps()
        from playwright.async_api import async_playwright

        site_prefix = self._derive_site_prefix(self.base_url, self.scope)
        logger.info(f"Crawling {self.base_url} (prefix={site_prefix}, depth={self.max_depth})")

        from readpile.core.browser import launch_chromium, launch_persistent_chromium

        async with async_playwright() as p:
            if not self.headless:
                profile_dir = Path.home() / ".readpile" / "browser_profile"
                profile_dir.mkdir(parents=True, exist_ok=True)
                context = await launch_persistent_chromium(
                    p,
                    user_data_dir=str(profile_dir),
                    headless=False,
                    viewport={"width": 1280, "height": 900},
                    accept_downloads=True,
                    ignore_https_errors=True,
                )
                page = context.pages[0] if context.pages else await context.new_page()
                browser = None
            else:
                browser = await launch_chromium(p, headless=True)
                context = await browser.new_context(
                    viewport={"width": 1280, "height": 900}
                )
                page = await context.new_page()

            try:
                visited: set[str] = set()
                queue: list[tuple[str, int]] = [(self.base_url, 0)]

                while queue:
                    if self.max_pages is not None and len(visited) >= self.max_pages:
                        break

                    url, depth = queue.pop(0)
                    clean = url.split("#")[0].split("?")[0].rstrip("/")
                    if clean in visited or depth > self.max_depth:
                        continue
                    visited.add(clean)

                    try:
                        await page.goto(
                            url, wait_until="networkidle", timeout=30000
                        )
                        await page.wait_for_timeout(1500)
                    except Exception as e:
                        logger.warning(f"Skipping {url}: {e}")
                        continue

                    if depth < self.max_depth:
                        links = await self._discover_links(page, site_prefix)
                        for link in links:
                            if link.rstrip("/") not in visited:
                                queue.append((link, depth + 1))

                return sorted(visited)

            finally:
                await context.close()
                if browser:
                    await browser.close()

    @staticmethod
    def _derive_site_prefix(url: str, scope: str) -> str:
        """Derive the URL prefix that bounds the crawl."""
        parsed = urlparse(url)
        if scope == "domain":
            return f"{parsed.scheme}://{parsed.netloc}"

        path_parts = parsed.path.strip("/").split("/")
        if "sites.google.com" in parsed.netloc and len(path_parts) >= 2:
            prefix_path = "/".join(path_parts[:2])
        elif len(path_parts) >= 2:
            prefix_path = "/".join(path_parts[:-1])
        else:
            prefix_path = path_parts[0] if path_parts else ""
        return f"{parsed.scheme}://{parsed.netloc}/{prefix_path}"

    @staticmethod
    async def _discover_links(page: Page, site_prefix: str) -> list[str]:
        """Use JS evaluation to find all same-prefix links on the page."""
        raw_links: list[str] = await page.evaluate(
            """(prefix) => {
                return [...new Set(
                    Array.from(document.querySelectorAll('a[href]'))
                        .map(a => a.href.split('#')[0].split('?')[0].replace(/\\/$/, ''))
                        .filter(h => h.startsWith(prefix)
                            && !h.match(/\\.(pdf|png|jpe?g|gif|svg|zip|csv|xlsx?)$/i))
                )];
            }""",
            site_prefix,
        )
        return raw_links
