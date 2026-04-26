from datetime import date
from unittest.mock import patch
from mediakit.scrapers.article import scrape_article, _extract_title, _extract_date, _extract_author, _extract_tags, _html_to_markdown, _clean_markdown
from mediakit.core.models import ContentType
from bs4 import BeautifulSoup

SAMPLE_HTML = '''<!DOCTYPE html>
<html>
<head>
    <meta property="og:title" content="Test Blog Post Title">
    <meta property="article:published_time" content="2026-04-25T10:00:00Z">
    <meta name="author" content="John Doe">
    <meta name="keywords" content="python, testing, cli">
</head>
<body>
<article>
    <h1>Test Blog Post Title</h1>
    <p>This is the first paragraph of a test blog post. It has enough content to be meaningful for testing purposes and should be extracted properly.</p>
    <p>This is the second paragraph with more detail about the topic at hand. We need sufficient content length for readability extraction.</p>
    <h2>A Subheading</h2>
    <p>More content under the subheading. This section covers additional details that are important for the article's completeness.</p>
    <ul>
        <li>Point one about testing</li>
        <li>Point two about extraction</li>
        <li>Point three about conversion</li>
    </ul>
    <p>Final paragraph wrapping up the article with conclusions and next steps for the reader to consider.</p>
</article>
</body>
</html>'''

def test_scrape_article_returns_content_item():
    item = scrape_article("https://example.com/blog/test-post", SAMPLE_HTML)
    assert item.content_type == ContentType.article
    assert item.title == "Test Blog Post Title"
    assert item.source_url == "https://example.com/blog/test-post"
    assert len(item.text) > 0

def test_extract_title_og():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    title = _extract_title(soup)
    assert title == "Test Blog Post Title"

def test_extract_title_h1_fallback():
    html = "<html><body><article><h1>H1 Title</h1></article></body></html>"
    soup = BeautifulSoup(html, "lxml")
    title = _extract_title(soup)
    assert title == "H1 Title"

def test_extract_title_tag_fallback():
    html = "<html><head><title>Page Title | Site Name</title></head><body></body></html>"
    soup = BeautifulSoup(html, "lxml")
    title = _extract_title(soup)
    assert title == "Page Title"

def test_extract_date_meta():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    d = _extract_date("https://example.com/test", soup)
    assert d == date(2026, 4, 25)

def test_extract_date_from_url():
    html = "<html><body></body></html>"
    soup = BeautifulSoup(html, "lxml")
    d = _extract_date("https://example.com/2026/03/15/post", soup)
    assert d == date(2026, 3, 15)

def test_extract_author():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    author = _extract_author(soup)
    assert author == "John Doe"

def test_extract_tags():
    soup = BeautifulSoup(SAMPLE_HTML, "lxml")
    tags = _extract_tags(soup)
    assert "python" in tags
    assert "testing" in tags

def test_html_to_markdown():
    html = "<h2>Title</h2><p>Paragraph text.</p>"
    md = _html_to_markdown(html)
    assert "##" in md or "Title" in md
    assert "Paragraph text" in md

def test_clean_markdown():
    text = "Line 1\n\n\n\n\n\nLine 2\n  trailing  "
    cleaned = _clean_markdown(text)
    assert "\n\n\n\n" not in cleaned
