"""URL normalization for dedup comparison."""

from __future__ import annotations

from urllib.parse import urlparse, urlencode, parse_qs, urlunparse

_TRACKING_PARAMS = frozenset({
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "ref", "source", "fbclid", "gclid",
})


def normalize_url(url: str) -> str:
    """Normalize a URL for dedup: strip tracking params, trailing slash,
    www prefix, lowercase hostname."""
    if not url:
        return url

    parsed = urlparse(url)

    scheme = parsed.scheme.lower() or "https"
    hostname = (parsed.hostname or "").lower().removeprefix("www.")
    port = f":{parsed.port}" if parsed.port and parsed.port not in (80, 443) else ""
    netloc = f"{hostname}{port}"

    path = parsed.path.rstrip("/") or ""

    query_params = parse_qs(parsed.query, keep_blank_values=True)
    filtered = {
        k: v for k, v in query_params.items()
        if k.lower() not in _TRACKING_PARAMS
    }
    query = urlencode(filtered, doseq=True) if filtered else ""

    return urlunparse((scheme, netloc, path, "", query, parsed.fragment))
