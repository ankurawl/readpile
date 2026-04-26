"""Tests for mediakit.core.models — ContentItem and ContentType."""

from datetime import date

from mediakit.core.models import ContentItem, ContentType


# --- ContentType enum ---


def test_content_type_values():
    assert ContentType.article.value == "article"
    assert ContentType.youtube.value == "youtube"
    assert ContentType.audio.value == "audio"
    assert ContentType.podcast.value == "podcast"
    assert ContentType.webpage.value == "webpage"


# --- word_count auto-calculation ---


def test_word_count_auto():
    item = ContentItem(
        text="one two three four five",
        title="T",
        source_url="u",
        content_type=ContentType.article,
    )
    assert item.word_count == 5


# --- to_yaml_header ---


def test_yaml_header_all_fields():
    item = ContentItem(
        text="body",
        title="My Title",
        source_url="https://ex.com",
        content_type=ContentType.youtube,
        date=date(2026, 4, 25),
        author="Author",
        tags=["a", "b"],
        duration="1:23:45",
        channel="Ch",
    )
    header = item.to_yaml_header()
    assert 'title: "My Title"' in header
    assert "source_url: https://ex.com" in header
    assert "content_type: youtube" in header
    assert "date: 2026-04-25" in header
    assert 'author: "Author"' in header
    assert "tags: [a, b]" in header
    assert "duration:" in header
    assert "channel:" in header


def test_yaml_header_omits_none():
    item = ContentItem(
        text="body",
        title="T",
        source_url="u",
        content_type=ContentType.article,
    )
    header = item.to_yaml_header()
    assert "author" not in header
    assert "duration" not in header
    assert "channel" not in header


# --- to_stdout ---


def test_to_stdout():
    item = ContentItem(
        text="body text",
        title="T",
        source_url="u",
        content_type=ContentType.article,
    )
    output = item.to_stdout()
    assert output.startswith("---")
    assert "body text" in output


# --- from_stdin round-trip ---


def test_from_stdin_roundtrip():
    item = ContentItem(
        text="Hello world.",
        title="Test",
        source_url="https://ex.com",
        content_type=ContentType.article,
        date=date(2026, 1, 15),
        author="Me",
        tags=["x", "y"],
    )
    parsed = ContentItem.from_stdin(item.to_stdout())
    assert parsed.title == item.title
    assert parsed.source_url == item.source_url
    assert parsed.content_type == item.content_type
    assert parsed.author == item.author
    assert parsed.tags == item.tags
    assert parsed.text.strip() == item.text.strip()


# --- from_stdin_batch ---


def test_batch_roundtrip():
    items = [
        ContentItem(
            text="First",
            title="A",
            source_url="u1",
            content_type=ContentType.article,
        ),
        ContentItem(
            text="Second",
            title="B",
            source_url="u2",
            content_type=ContentType.youtube,
        ),
    ]
    batch_str = ContentItem.to_batch(items)
    parsed = ContentItem.from_stdin_batch(batch_str)
    assert len(parsed) == 2
    assert parsed[0].title == "A"
    assert parsed[1].title == "B"


# --- Edge cases ---


def test_special_chars_title():
    item = ContentItem(
        text="body",
        title='Title with "quotes" & stuff',
        source_url="u",
        content_type=ContentType.article,
    )
    parsed = ContentItem.from_stdin(item.to_stdout())
    assert "quotes" in parsed.title


def test_empty_text():
    item = ContentItem(
        text="",
        title="Empty",
        source_url="u",
        content_type=ContentType.article,
    )
    assert item.word_count == 0
