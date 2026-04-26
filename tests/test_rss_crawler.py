from unittest.mock import patch, MagicMock
from mediakit.crawlers.rss import crawl_rss, _get_entry_url, _has_audio_enclosure

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


@patch("mediakit.crawlers.rss.feedparser.parse")
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


@patch("mediakit.crawlers.rss.feedparser.parse")
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


@patch("mediakit.crawlers.rss.feedparser.parse")
def test_crawl_rss_recent(mock_parse):
    mock_parse.return_value = MagicMock(**MOCK_RSS_FEED)
    mock_parse.return_value.entries = [MagicMock(**e) for e in MOCK_RSS_FEED["entries"]]
    for entry, data in zip(mock_parse.return_value.entries, MOCK_RSS_FEED["entries"]):
        entry.get = data.get
        entry.keys = data.keys
        entry.enclosures = []

    urls = crawl_rss("https://podcast.com/feed.xml", recent=2)
    assert len(urls) == 2


@patch("mediakit.crawlers.rss.feedparser.parse")
def test_crawl_rss_empty(mock_parse):
    mock_parse.return_value = MagicMock(entries=[], bozo=False)
    urls = crawl_rss("https://empty.com/feed.xml")
    assert urls == []
