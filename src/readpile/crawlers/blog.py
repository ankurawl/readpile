"""Blog crawler — discover and enumerate blog post URLs."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING
from urllib.parse import urljoin, urldefrag, urlparse

if TYPE_CHECKING:
    from bs4 import BeautifulSoup
    from playwright.async_api import BrowserContext, Page

from readpile.core.robots import RobotsChecker


# ---------------------------------------------------------------------------
# Dependency guard
# ---------------------------------------------------------------------------


def _check_deps() -> None:
    """Verify blog crawling dependencies are installed."""
    missing: list[str] = []
    try:
        import playwright  # noqa: F401
    except ImportError:
        missing.append("playwright")
    try:
        import bs4  # noqa: F401
    except ImportError:
        missing.append("beautifulsoup4")
    try:
        import lxml  # noqa: F401
    except ImportError:
        missing.append("lxml")
    if missing:
        raise SystemExit(
            f"Blog crawling requires: {', '.join(missing)}.\n"
            "Install with:\n"
            "  pip install readpile\n"
            f"  or: pip install {' '.join(missing)}\n"
        )

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Detection
# ---------------------------------------------------------------------------


@dataclass
class DetectionResult:
    """Result of blog post classification."""

    is_blog_post: bool
    confidence: float
    reasons: list[str] = field(default_factory=list)


class BlogPostDetector:
    """Classifies whether a URL/page is a blog post using multi-signal scoring."""

    THRESHOLD = 0.5

    # URL patterns that increase score
    BLOG_URL_PATTERNS: list[tuple[str, float]] = [
        (r"/blog/[^/]+", 0.2),
        (r"/post/", 0.2),
        (r"/posts/[^/]+", 0.2),
        (r"/article/", 0.2),
        (r"/articles/[^/]+", 0.2),
        (r"/\d{4}/\d{2}/\d{2}/", 0.3),
        (r"/\d{4}/\d{2}/[^/]+", 0.25),
        (r"/\d{4}-\d{2}-\d{2}", 0.25),
        (r"/news/[^/]+", 0.15),
    ]

    # URL patterns that decrease score
    NON_BLOG_URL_PATTERNS: list[tuple[str, float]] = [
        (r"/about/?$", -0.5),
        (r"/contact/?$", -0.5),
        (r"/privacy/?$", -0.5),
        (r"/terms/?$", -0.5),
        (r"/legal/?$", -0.5),
        (r"/login/?$", -0.8),
        (r"/signup/?$", -0.8),
        (r"/register/?$", -0.8),
        (r"/category/[^/]*/?$", -0.3),
        (r"/tag/[^/]*/?$", -0.3),
        (r"/tags/?$", -0.3),
        (r"/categories/?$", -0.3),
        (r"/page/\d+/?$", -0.3),
        (r"/search", -0.5),
        (r"/feed/?$", -0.5),
        (r"/rss/?$", -0.5),
        (r"/wp-admin", -0.8),
        (r"/wp-login", -0.8),
        (r"/author/[^/]*/?$", -0.2),
        (r"/archive/?$", -0.3),
        (r"/#[^/]*$", -0.1),
    ]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, url: str, html: str) -> DetectionResult:
        """Run all detection heuristics and return scored result."""
        _check_deps()
        from bs4 import BeautifulSoup

        score = 0.0
        reasons: list[str] = []

        s, r = self._score_url_patterns(url)
        score += s
        reasons.extend(r)

        soup = BeautifulSoup(html, "lxml")

        s, r = self._score_page_structure(soup)
        score += s
        reasons.extend(r)

        s, r = self._score_content_length(soup)
        score += s
        reasons.extend(r)

        s, r = self._score_link_density(soup)
        score += s
        reasons.extend(r)

        # Clamp to [0, 1]
        score = max(0.0, min(1.0, score))

        return DetectionResult(
            is_blog_post=score >= self.THRESHOLD,
            confidence=score,
            reasons=reasons,
        )

    def detect_url_only(self, url: str) -> float:
        """Quick URL-only scoring for pre-filtering."""
        score, _ = self._score_url_patterns(url)
        return score

    # ------------------------------------------------------------------
    # Scoring helpers
    # ------------------------------------------------------------------

    def _score_url_patterns(self, url: str) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []

        for pattern, weight in self.BLOG_URL_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                score += weight
                reasons.append(f"URL matches blog pattern '{pattern}' (+{weight})")
                break  # Take strongest match only

        for pattern, weight in self.NON_BLOG_URL_PATTERNS:
            if re.search(pattern, url, re.IGNORECASE):
                score += weight
                reasons.append(f"URL matches non-blog pattern '{pattern}' ({weight})")
                break

        return score, reasons

    def _score_page_structure(self, soup: BeautifulSoup) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []

        # <article> tag
        if soup.find("article"):
            score += 0.2
            reasons.append("<article> tag found (+0.2)")

        # <time> or datetime attribute
        if soup.find("time") or soup.find(attrs={"datetime": True}):
            score += 0.15
            reasons.append("<time> element found (+0.15)")

        # Schema.org BlogPosting or Article
        schema_scripts = soup.find_all("script", {"type": "application/ld+json"})
        for script in schema_scripts:
            try:
                data = json.loads(script.string or "")
                if isinstance(data, list):
                    data = data[0] if data else {}
                schema_type = data.get("@type", "")
                if isinstance(schema_type, list):
                    schema_type = " ".join(schema_type)
                if any(
                    t in schema_type
                    for t in ["BlogPosting", "Article", "NewsArticle"]
                ):
                    score += 0.3
                    reasons.append(f"Schema.org {schema_type} markup (+0.3)")
                    break
            except (json.JSONDecodeError, AttributeError):
                continue

        # og:type == article
        og_type = soup.find("meta", property="og:type")
        if og_type and og_type.get("content", "").lower() == "article":
            score += 0.15
            reasons.append("og:type=article (+0.15)")

        # Author meta or byline
        if (
            soup.find("meta", attrs={"name": "author"})
            or soup.find(class_=re.compile(r"author|byline", re.I))
            or soup.find(attrs={"rel": "author"})
        ):
            score += 0.1
            reasons.append("Author/byline found (+0.1)")

        # Single h1 (typical of post pages vs index)
        h1s = soup.find_all("h1")
        if len(h1s) == 1:
            score += 0.1
            reasons.append("Single <h1> found (+0.1)")

        return score, reasons

    def _score_content_length(self, soup: BeautifulSoup) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []

        # Get text from main content area
        main = soup.find("article") or soup.find("main") or soup.find(role="main")
        if main:
            text = main.get_text(separator=" ", strip=True)
        else:
            text = soup.get_text(separator=" ", strip=True)

        word_count = len(text.split())

        if word_count > 1000:
            score += 0.2
            reasons.append(f"Long content ({word_count} words) (+0.2)")
        elif word_count > 500:
            score += 0.15
            reasons.append(f"Substantial content ({word_count} words) (+0.15)")
        elif word_count < 200:
            score -= 0.15
            reasons.append(f"Very short content ({word_count} words) (-0.15)")

        return score, reasons

    def _score_link_density(self, soup: BeautifulSoup) -> tuple[float, list[str]]:
        score = 0.0
        reasons: list[str] = []

        main = (
            soup.find("article")
            or soup.find("main")
            or soup.find(role="main")
            or soup.body
        )
        if not main:
            return score, reasons

        text = main.get_text(separator=" ", strip=True)
        links = main.find_all("a")
        link_text = " ".join(a.get_text(strip=True) for a in links)

        text_len = len(text) or 1
        link_ratio = len(link_text) / text_len

        if link_ratio > 0.5:
            score -= 0.2
            reasons.append(f"High link density ({link_ratio:.2f}) (-0.2)")
        elif link_ratio < 0.1:
            score += 0.1
            reasons.append(f"Low link density ({link_ratio:.2f}) (+0.1)")

        return score, reasons


# ---------------------------------------------------------------------------
# Crawler
# ---------------------------------------------------------------------------


class BlogCrawler:
    """Discovers blog post URLs from a starting page using Playwright."""

    # Max pagination pages to follow
    MAX_PAGINATION_PAGES = 50
    # Max scroll attempts for infinite scroll
    MAX_SCROLL_ATTEMPTS = 10
    # Max depth for following listing pages
    MAX_LISTING_DEPTH = 2

    def __init__(
        self,
        browser_context: BrowserContext,
        base_url: str,
        delay: float = 1.0,
        max_posts: int | None = None,
        robots: RobotsChecker | None = None,
    ):
        self.browser_context = browser_context
        self.base_url = base_url
        parsed = urlparse(base_url)
        self.base_domain = parsed.netloc
        self.base_scheme = parsed.scheme
        self.delay = delay
        self.max_posts = max_posts
        self.robots = robots
        self.visited: set[str] = set()
        self.detector = BlogPostDetector()

    async def crawl(self) -> list[str]:
        """Discover blog post URLs. Returns a deduplicated, sorted list."""
        _check_deps()
        logger.info(f"Starting crawl from {self.base_url}")

        page = await self.browser_context.new_page()
        try:
            # Fetch starting page
            html = await self._fetch_page(page, self.base_url)
            if not html:
                logger.error(f"Failed to fetch starting URL: {self.base_url}")
                return []

            # Collect all candidate URLs
            candidates: set[str] = set()

            # Check if starting URL itself is a blog post
            detection = self.detector.detect(self.base_url, html)
            if detection.is_blog_post:
                logger.info(
                    f"Starting URL is itself a blog post "
                    f"(score={detection.confidence:.2f})"
                )
                candidates.add(self.base_url)

            # Extract links from the starting page
            links = self._extract_links(html, self.base_url)
            logger.info(f"Found {len(links)} links on starting page")

            # Pre-filter candidates by URL pattern
            for link in links:
                url_score = self.detector.detect_url_only(link)
                if url_score > -0.3:  # Not obviously non-blog
                    candidates.add(link)

            # Handle pagination on starting page
            paginated_links = await self._follow_pagination(page, html, self.base_url)
            for link in paginated_links:
                url_score = self.detector.detect_url_only(link)
                if url_score > -0.3:
                    candidates.add(link)

            # Handle infinite scroll
            scroll_links = await self._handle_infinite_scroll(page, self.base_url)
            for link in scroll_links:
                url_score = self.detector.detect_url_only(link)
                if url_score > -0.3:
                    candidates.add(link)

            # Remove starting URL from candidates if it is a listing page
            if not detection.is_blog_post and self.base_url in candidates:
                candidates.discard(self.base_url)

            logger.info(f"Total candidate URLs after crawling: {len(candidates)}")

            # Apply max_posts limit
            candidate_list = sorted(candidates)
            if self.max_posts:
                candidate_list = candidate_list[: self.max_posts]

            return candidate_list

        finally:
            await page.close()

    # ------------------------------------------------------------------
    # Page fetching
    # ------------------------------------------------------------------

    async def fetch_post_html(self, page: Page, url: str) -> str | None:
        """Fetch a single post page. Used by the main orchestrator."""
        return await self._fetch_page(page, url)

    async def _fetch_page(self, page: Page, url: str) -> str | None:
        """Load URL via Playwright, wait for content, return HTML."""
        if self.robots and not self.robots.can_fetch(url):
            logger.warning(f"Blocked by robots.txt: {url}")
            return None

        if url in self.visited:
            return None
        self.visited.add(url)

        if self.delay > 0 and len(self.visited) > 1:
            await asyncio.sleep(self.delay)

        try:
            response = await page.goto(
                url, wait_until="domcontentloaded", timeout=30000
            )
            if response and response.status >= 400:
                logger.warning(f"HTTP {response.status} for {url}")
                return None

            # Wait a bit for dynamic content
            await page.wait_for_timeout(2000)
            return await page.content()
        except Exception as e:
            logger.warning(f"Failed to fetch {url}: {e}")
            return None

    # ------------------------------------------------------------------
    # Link extraction
    # ------------------------------------------------------------------

    def _extract_links(self, html: str, page_url: str) -> list[str]:
        """Extract all same-domain links from HTML."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")
        links: set[str] = set()

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if not href or href.startswith(("#", "javascript:", "mailto:", "tel:")):
                continue

            absolute_url = self._normalize_url(href, page_url)
            if absolute_url and self._is_same_domain(absolute_url):
                links.add(absolute_url)

        return sorted(links)

    # ------------------------------------------------------------------
    # Pagination
    # ------------------------------------------------------------------

    async def _follow_pagination(
        self, page: Page, html: str, page_url: str
    ) -> list[str]:
        """Follow pagination links to discover more post URLs."""
        all_links: list[str] = []
        current_html = html
        current_url = page_url
        pages_followed = 0

        while pages_followed < self.MAX_PAGINATION_PAGES:
            next_url = self._detect_next_page(current_html, current_url)
            if not next_url or next_url in self.visited:
                break

            logger.info(f"Following pagination: {next_url}")
            await asyncio.sleep(self.delay)

            current_html = await self._fetch_page(page, next_url)
            if not current_html:
                break

            current_url = next_url
            new_links = self._extract_links(current_html, current_url)
            all_links.extend(new_links)
            pages_followed += 1

            if self.max_posts and len(all_links) >= self.max_posts:
                break

        if pages_followed > 0:
            logger.info(
                f"Followed {pages_followed} pagination pages, "
                f"found {len(all_links)} additional links"
            )

        return all_links

    def _detect_next_page(self, html: str, page_url: str) -> str | None:
        """Look for next-page indicators in HTML."""
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "lxml")

        # rel="next"
        next_link = soup.find("a", rel="next")
        if next_link and next_link.get("href"):
            return self._normalize_url(next_link["href"], page_url)

        # Links with "next" text
        for a in soup.find_all("a", href=True):
            text = a.get_text(strip=True).lower()
            if text in [
                "next",
                "next page",
                "newer posts",
                "next →",
                "next »",
                "older posts",
                "older entries",
                "load more",
            ]:
                url = self._normalize_url(a["href"], page_url)
                if url and self._is_same_domain(url):
                    return url

        # aria-label="next"
        next_aria = soup.find("a", attrs={"aria-label": re.compile(r"next", re.I)})
        if next_aria and next_aria.get("href"):
            return self._normalize_url(next_aria["href"], page_url)

        return None

    # ------------------------------------------------------------------
    # Infinite scroll
    # ------------------------------------------------------------------

    async def _handle_infinite_scroll(self, page: Page, url: str) -> list[str]:
        """Handle infinite scroll by scrolling and collecting new links."""
        all_links: set[str] = set()

        try:
            # Get initial links
            html = await page.content()
            initial_links = set(self._extract_links(html, url))
            all_links.update(initial_links)

            no_new_content_count = 0

            for _ in range(self.MAX_SCROLL_ATTEMPTS):
                # Scroll to bottom
                await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                await page.wait_for_timeout(2000)

                # Try clicking "Load More" buttons
                for selector in [
                    'button:text-matches("load more", "i")',
                    'button:text-matches("show more", "i")',
                    'a:text-matches("load more", "i")',
                    '[class*="load-more"]',
                    '[class*="loadmore"]',
                ]:
                    try:
                        btn = page.locator(selector).first
                        if await btn.is_visible():
                            await btn.click()
                            await page.wait_for_timeout(2000)
                            break
                    except Exception:
                        continue

                # Check for new links
                html = await page.content()
                current_links = set(self._extract_links(html, url))
                new_links = current_links - all_links

                if not new_links:
                    no_new_content_count += 1
                    if no_new_content_count >= 3:
                        break
                else:
                    no_new_content_count = 0
                    all_links.update(new_links)
                    logger.info(f"Infinite scroll: found {len(new_links)} new links")

                if self.max_posts and len(all_links) >= self.max_posts:
                    break

        except Exception as e:
            logger.warning(f"Infinite scroll handling error: {e}")

        return sorted(all_links)

    # ------------------------------------------------------------------
    # URL helpers
    # ------------------------------------------------------------------

    def _normalize_url(self, url: str, base_url: str) -> str | None:
        """Convert relative URLs to absolute, strip fragments."""
        try:
            absolute = urljoin(base_url, url)
            defragged, _ = urldefrag(absolute)
            # Remove trailing slash for consistency (except root)
            parsed = urlparse(defragged)
            if parsed.path != "/" and defragged.endswith("/"):
                defragged = defragged.rstrip("/")
            return defragged
        except Exception:
            return None

    def _is_same_domain(self, url: str) -> bool:
        """Check if URL belongs to the same domain."""
        try:
            parsed = urlparse(url)
            # Match domain, allowing www prefix differences
            url_domain = parsed.netloc.lower().removeprefix("www.")
            base_domain = self.base_domain.lower().removeprefix("www.")
            return url_domain == base_domain
        except Exception:
            return False
