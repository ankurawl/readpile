from datetime import date
from readpile.core.models import ContentItem, ContentType

def test_batch_delimiter_splitting():
    batch = "---\ntitle: \"A\"\nsource_url: u1\ncontent_type: article\n---\nBody A\n\n---CONTENT_ITEM---\n\n---\ntitle: \"B\"\nsource_url: u2\ncontent_type: youtube\n---\nBody B"
    items = ContentItem.from_stdin_batch(batch)
    assert len(items) == 2
    assert items[0].title == "A"
    assert items[1].title == "B"

def test_batch_single_item_no_delimiter():
    single = "---\ntitle: \"Only One\"\nsource_url: u\ncontent_type: article\n---\nSingle body"
    items = ContentItem.from_stdin_batch(single)
    assert len(items) == 1
    assert items[0].title == "Only One"

def test_batch_roundtrip():
    items = [
        ContentItem(text="First body.", title="First", source_url="u1", content_type=ContentType.article, date=date(2026, 1, 1)),
        ContentItem(text="Second body.", title="Second", source_url="u2", content_type=ContentType.youtube, channel="Ch"),
        ContentItem(text="Third body.", title="Third", source_url="u3", content_type=ContentType.audio),
    ]
    batch_str = ContentItem.to_batch(items)
    parsed = ContentItem.from_stdin_batch(batch_str)
    assert len(parsed) == 3
    assert parsed[0].title == "First"
    assert parsed[1].title == "Second"
    assert parsed[1].content_type == ContentType.youtube
    assert parsed[2].title == "Third"

def test_batch_yaml_preservation():
    item = ContentItem(text="Body.", title="Preserved", source_url="https://ex.com", content_type=ContentType.article, date=date(2026, 6, 15), author="Auth", tags=["a", "b"])
    batch_str = ContentItem.to_batch([item])
    parsed = ContentItem.from_stdin_batch(batch_str)
    assert parsed[0].source_url == "https://ex.com"
    assert parsed[0].author == "Auth"
    assert parsed[0].tags == ["a", "b"]

def test_batch_empty_input():
    items = ContentItem.from_stdin_batch("")
    assert items == [] or len(items) == 0

def test_batch_whitespace_around_delimiter():
    batch = "---\ntitle: \"X\"\nsource_url: u\ncontent_type: article\n---\nBody X\n\n  ---CONTENT_ITEM---  \n\n---\ntitle: \"Y\"\nsource_url: v\ncontent_type: article\n---\nBody Y"
    items = ContentItem.from_stdin_batch(batch)
    assert len(items) == 2
