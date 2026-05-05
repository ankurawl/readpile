"""robots.txt compliance checker."""

import urllib.robotparser
from urllib.parse import urlparse


class RobotsChecker:
    """Checks robots.txt compliance before crawling."""

    USER_AGENT = "readpile/1.0"

    def __init__(self, base_url: str):
        self.base_url = base_url
        parsed = urlparse(base_url)
        self.robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        self.parser = urllib.robotparser.RobotFileParser()
        self._loaded = False

    def load(self):
        """Fetch and parse robots.txt. Allows all if not found."""
        try:
            self.parser.set_url(self.robots_url)
            self.parser.read()
            self._loaded = True
        except Exception:
            self._loaded = False

    def can_fetch(self, url: str) -> bool:
        """Check if URL is allowed by robots.txt."""
        if not self._loaded:
            return True
        return self.parser.can_fetch(self.USER_AGENT, url)

    def crawl_delay(self) -> float | None:
        """Return crawl-delay from robots.txt, if specified."""
        if not self._loaded:
            return None
        try:
            delay = self.parser.crawl_delay(self.USER_AGENT)
            return float(delay) if delay is not None else None
        except Exception:
            return None
