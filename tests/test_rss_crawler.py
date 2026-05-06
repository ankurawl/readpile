from time import struct_time
from unittest.mock import patch, MagicMock
from readpile.crawlers.rss import (
    crawl_rss,
    crawl_rss_detailed,
    _get_entry_url,
    _has_audio_enclosure,
)

MOCK_RSS_FEED = {
    "feed": {"title": "Test Podcast"},
    "entries": [
        {
            "title": "Episode 3",
            "link": "https://podcast.com/ep3",
            "published_parsed": (2026, 4, 25, 0, 0, 0, 0, 0, 0),
            "enclosures": [{"href": "https://podcast.com/ep3.mp3", "type": "audio/mpeg"}],
        },
        {
            "title": "Episode 2",
            "link": "https://podcast.com/ep2",
            "published_parsed": (2026, 4, 20, 0, 0, 0, 0, 0, 0),
            "enclosures": [{"href": "https://podcast.com/ep2.mp3", "type": "audio/mpeg"}],
        },
        {
            "title": "Episode 1",
            "link": "https://podcast.com/ep1",
            "published_parsed": (2026, 4, 15, 0, 0, 0, 0, 0, 0),
            "enclosures": [{"href": "https://podcast.com/ep1.mp3", "type": "audio/mpeg"}],
        },
    ],
    "bozo": False,
}

MOCK_BLOG_FEED = {
    "feed": {"title": "Test Blog"},
    "entries": [
        {"title": "Post 2", "link": "https://blog.com/post-2", "published_parsed": (2026, 4, 25, 0, 0, 0, 0, 0, 0)},
        {"title": "Post 1", "link": "https://blog.com/post-1", "published_parsed": (2026, 4, 20, 0, 0, 0, 0, 0, 0)},
    ],
    "bozo": False,
}


@patch("readpile.crawlers.rss.feedparser.parse")
def test_crawl_podcast_rss(mock_parse):
    mock_parse.return_value = MagicMock(**MOCK_RSS_FEED)
    mock_parse.return_value.entries = [MagicMock(**e) for e in MOCK_RSS_FEED["entries"]]
    for entry, data in zip(mock_parse.return_value.entries, MOCK_RSS_FEED["entries"]):
        entry.get = data.get
        entry.keys = data.keys
        if "enclosures" in data:
            entry.enclosures = [MagicMock(**enc) for enc in data["enclosures"]]
            for enc_mock, enc_data in zip(entry.enclosures, data["enclosures"]):
                enc_mock.get = enc_data.get

    urls = crawl_rss("https://podcast.com/feed.xml")
    assert len(urls) == 3
    # Should prefer audio enclosure URLs
    assert any("mp3" in u for u in urls)


@patch("readpile.crawlers.rss.feedparser.parse")
def test_crawl_blog_rss(mock_parse):
    mock_parse.return_value = MagicMock(**MOCK_BLOG_FEED)
    mock_parse.return_value.entries = [MagicMock(**e) for e in MOCK_BLOG_FEED["entries"]]
    for entry, data in zip(mock_parse.return_value.entries, MOCK_BLOG_FEED["entries"]):
        entry.get = data.get
        entry.keys = data.keys
        entry.enclosures = []

    urls = crawl_rss("https://blog.com/feed.xml")
    assert len(urls) == 2
    assert "https://blog.com/post-2" in urls


@patch("readpile.crawlers.rss.feedparser.parse")
def test_crawl_rss_recent(mock_parse):
    mock_parse.return_value = MagicMock(**MOCK_RSS_FEED)
    mock_parse.return_value.entries = [MagicMock(**e) for e in MOCK_RSS_FEED["entries"]]
    for entry, data in zip(mock_parse.return_value.entries, MOCK_RSS_FEED["entries"]):
        entry.get = data.get
        entry.keys = data.keys
        entry.enclosures = []

    urls = crawl_rss("https://podcast.com/feed.xml", recent=2)
    assert len(urls) == 2


@patch("readpile.crawlers.rss.feedparser.parse")
def test_crawl_rss_empty(mock_parse):
    mock_parse.return_value = MagicMock(entries=[], bozo=False)
    urls = crawl_rss("https://empty.com/feed.xml")
    assert urls == []


# ---------------------------------------------------------------------------
# Helpers for crawl_rss_detailed tests
# ---------------------------------------------------------------------------

MOCK_MIXED_FEED = {
    "feed": {
        "title": "Lenny's Newsletter",
        "subtitle": "Product management insights",
    },
    "entries": [
        {
            "title": "Podcast Ep 3: Growth",
            "link": "https://lenny.com/p/ep3",
            "author": "Lenny Rachitsky",
            "summary": "<p>A deep dive into <b>growth</b> strategies.</p>",
            "published_parsed": (2026, 4, 25, 0, 0, 0, 0, 0, 0),
            "itunes_duration": "01:15:30",
            "enclosures": [{"href": "https://lenny.com/ep3.mp3", "type": "audio/mpeg"}],
        },
        {
            "title": "Podcast Ep 2: Retention",
            "link": "https://lenny.com/p/ep2",
            "author": "Lenny Rachitsky",
            "summary": "Episode about retention.",
            "published_parsed": (2026, 4, 20, 0, 0, 0, 0, 0, 0),
            "enclosures": [{"href": "https://lenny.com/ep2.mp3", "type": "audio/mpeg"}],
        },
        {
            "title": "Article: PM Tips",
            "link": "https://lenny.com/p/pm-tips",
            "author": "Lenny Rachitsky",
            "summary": "Top 10 PM tips.",
            "published_parsed": (2026, 4, 22, 0, 0, 0, 0, 0, 0),
        },
        {
            "title": "Article: Hiring",
            "link": "https://lenny.com/p/hiring",
            "author": "Lenny Rachitsky",
            "summary": "How to hire PMs.",
            "published_parsed": (2026, 4, 18, 0, 0, 0, 0, 0, 0),
        },
        {
            "title": "Podcast Ep 1: Pricing",
            "link": "https://lenny.com/p/ep1",
            "author": "Lenny Rachitsky",
            "summary": "Pricing strategies.",
            "published_parsed": (2026, 4, 15, 0, 0, 0, 0, 0, 0),
            "enclosures": [{"href": "https://lenny.com/ep1.mp3", "type": "audio/mpeg"}],
        },
    ],
    "bozo": False,
}


def _make_feed_mock(feed_data):
    """Create a feedparser-compatible mock from a dict."""
    mock = MagicMock()
    mock.bozo = feed_data["bozo"]

    # Feed-level metadata
    feed_meta = MagicMock()
    feed_meta.get = feed_data["feed"].get
    mock.feed = feed_meta

    # Entries
    mock_entries = []
    for e in feed_data["entries"]:
        # Convert tuple dates to struct_time (feedparser returns struct_time)
        entry_data = dict(e)
        for date_field in ("published_parsed", "updated_parsed"):
            if date_field in entry_data and isinstance(entry_data[date_field], tuple):
                entry_data[date_field] = struct_time(entry_data[date_field])

        entry = MagicMock()
        entry.get = entry_data.get
        entry.keys = entry_data.keys
        if "enclosures" in entry_data:
            enc_list = []
            for enc in entry_data["enclosures"]:
                enc_mock = MagicMock()
                enc_mock.get = enc.get
                enc_list.append(enc_mock)
            entry.enclosures = enc_list
        else:
            entry.enclosures = []
        mock_entries.append(entry)
    mock.entries = mock_entries
    return mock


@patch("readpile.crawlers.rss.feedparser.parse")
def test_crawl_rss_detailed_mixed_feed(mock_parse):
    mock_parse.return_value = _make_feed_mock(MOCK_MIXED_FEED)
    feed_info, entries = crawl_rss_detailed("https://lenny.com/feed")
    assert len(entries) == 5
    audio_entries = [e for e in entries if e["type"] == "audio"]
    article_entries = [e for e in entries if e["type"] == "article"]
    assert len(audio_entries) == 3
    assert len(article_entries) == 2


@patch("readpile.crawlers.rss.feedparser.parse")
def test_crawl_rss_detailed_audio_only(mock_parse):
    mock_parse.return_value = _make_feed_mock(MOCK_MIXED_FEED)
    feed_info, entries = crawl_rss_detailed("https://lenny.com/feed", audio_only=True)
    assert len(entries) == 3
    assert all(e["type"] == "audio" for e in entries)
    assert feed_info["episode_count"] == 3


@patch("readpile.crawlers.rss.feedparser.parse")
def test_crawl_rss_detailed_metadata_fields(mock_parse):
    mock_parse.return_value = _make_feed_mock(MOCK_MIXED_FEED)
    _, entries = crawl_rss_detailed("https://lenny.com/feed", audio_only=True)
    ep = entries[0]  # newest podcast episode (Ep 3)
    assert ep["title"] == "Podcast Ep 3: Growth"
    assert ep["url"] == "https://lenny.com/p/ep3"
    assert ep["date"] == "2026-04-25"
    assert ep["author"] == "Lenny Rachitsky"
    assert ep["type"] == "audio"
    assert ep["audio_url"] == "https://lenny.com/ep3.mp3"
    assert ep["duration"] == "01:15:30"
    assert ep["description"] is not None


@patch("readpile.crawlers.rss.feedparser.parse")
def test_crawl_rss_detailed_html_description(mock_parse):
    mock_parse.return_value = _make_feed_mock(MOCK_MIXED_FEED)
    _, entries = crawl_rss_detailed("https://lenny.com/feed", audio_only=True)
    ep3 = entries[0]
    assert "<b>" not in ep3["description"]
    assert "<p>" not in ep3["description"]
    assert "growth" in ep3["description"].lower()


@patch("readpile.crawlers.rss.feedparser.parse")
def test_crawl_rss_detailed_description_truncation(mock_parse):
    long_desc = "x" * 500
    feed_data = {
        "feed": {"title": "Test"},
        "entries": [
            {
                "title": "Post",
                "link": "https://test.com/post",
                "summary": long_desc,
                "published_parsed": (2026, 4, 25, 0, 0, 0, 0, 0, 0),
            },
        ],
        "bozo": False,
    }
    mock_parse.return_value = _make_feed_mock(feed_data)
    _, entries = crawl_rss_detailed("https://test.com/feed")
    assert len(entries[0]["description"]) <= 300


@patch("readpile.crawlers.rss.feedparser.parse")
def test_crawl_rss_detailed_missing_fields(mock_parse):
    feed_data = {
        "feed": {},
        "entries": [
            {"link": "https://test.com/post"},
        ],
        "bozo": False,
    }
    mock_parse.return_value = _make_feed_mock(feed_data)
    feed_info, entries = crawl_rss_detailed("https://test.com/feed")
    e = entries[0]
    assert e["title"] == "Untitled"
    assert e["author"] is None
    assert e["date"] is None
    assert feed_info["feed_title"] is None


@patch("readpile.crawlers.rss.feedparser.parse")
def test_crawl_rss_detailed_no_link(mock_parse):
    feed_data = {
        "feed": {"title": "Podcast"},
        "entries": [
            {
                "title": "Ep 1",
                "published_parsed": (2026, 4, 25, 0, 0, 0, 0, 0, 0),
                "enclosures": [{"href": "https://pod.com/ep1.mp3", "type": "audio/mpeg"}],
            },
        ],
        "bozo": False,
    }
    mock_parse.return_value = _make_feed_mock(feed_data)
    _, entries = crawl_rss_detailed("https://pod.com/feed")
    assert entries[0]["url"] == "https://pod.com/ep1.mp3"
    assert entries[0]["audio_url"] == "https://pod.com/ep1.mp3"


@patch("readpile.crawlers.rss.feedparser.parse")
def test_crawl_rss_detailed_recent_limit(mock_parse):
    mock_parse.return_value = _make_feed_mock(MOCK_MIXED_FEED)
    _, entries = crawl_rss_detailed("https://lenny.com/feed", recent=2)
    assert len(entries) == 2


@patch("readpile.crawlers.rss.feedparser.parse")
def test_crawl_rss_detailed_feed_info(mock_parse):
    mock_parse.return_value = _make_feed_mock(MOCK_MIXED_FEED)
    feed_info, entries = crawl_rss_detailed("https://lenny.com/feed")
    assert feed_info["feed_title"] == "Lenny's Newsletter"
    assert feed_info["feed_description"] == "Product management insights"
    assert feed_info["episode_count"] == 5


@patch("readpile.crawlers.rss.feedparser.parse")
def test_crawl_rss_detailed_multiple_enclosures(mock_parse):
    feed_data = {
        "feed": {"title": "Podcast"},
        "entries": [
            {
                "title": "Ep 1",
                "link": "https://pod.com/ep1",
                "published_parsed": (2026, 4, 25, 0, 0, 0, 0, 0, 0),
                "enclosures": [
                    {"href": "https://pod.com/cover.jpg", "type": "image/jpeg"},
                    {"href": "https://pod.com/ep1.mp3", "type": "audio/mpeg"},
                ],
            },
        ],
        "bozo": False,
    }
    mock_parse.return_value = _make_feed_mock(feed_data)
    _, entries = crawl_rss_detailed("https://pod.com/feed")
    assert entries[0]["audio_url"] == "https://pod.com/ep1.mp3"
    assert entries[0]["type"] == "audio"


@patch("readpile.crawlers.rss.feedparser.parse")
def test_crawl_rss_detailed_no_audio_entries(mock_parse):
    mock_parse.return_value = _make_feed_mock(MOCK_BLOG_FEED)
    feed_info, entries = crawl_rss_detailed("https://blog.com/feed", audio_only=True)
    assert entries == []
    assert feed_info["episode_count"] == 0
