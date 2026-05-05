from datetime import date
from pathlib import Path
from readpile.core.archiver import sanitize_filename, generate_filename, Archiver
from readpile.core.models import ContentItem, ContentType

# sanitize_filename tests
def test_sanitize_basic():
    assert sanitize_filename("Hello World") == "hello-world"

def test_sanitize_special_chars():
    result = sanitize_filename("Test: A Blog Post! (2024)")
    assert ":" not in result
    assert "!" not in result
    assert "(" not in result

def test_sanitize_unicode():
    result = sanitize_filename("Cafe resume naive")
    assert isinstance(result, str)
    assert len(result) > 0

def test_sanitize_truncation():
    long_title = "a" * 200
    result = sanitize_filename(long_title, max_length=80)
    assert len(result) <= 80

def test_sanitize_no_trailing_hyphen():
    result = sanitize_filename("test---", max_length=80)
    assert not result.endswith("-")

def test_sanitize_collapse_hyphens():
    result = sanitize_filename("a   b   c")
    assert "--" not in result

# generate_filename tests
def test_generate_with_date():
    item = ContentItem(text="body", title="My Post", source_url="u", content_type=ContentType.article, date=date(2026, 4, 25))
    filename = generate_filename(item)
    assert filename.startswith("2026-04-25_")
    assert filename.endswith(".md")
    assert "my-post" in filename

def test_generate_without_date():
    item = ContentItem(text="body", title="No Date Post", source_url="u", content_type=ContentType.article)
    filename = generate_filename(item)
    assert filename.endswith(".md")
    # Should use today's date
    assert "_" in filename

# Archiver tests
def test_archiver_save(tmp_path):
    item = ContentItem(text="Body text.", title="Saved Post", source_url="https://ex.com", content_type=ContentType.article, date=date(2026, 1, 1))
    archiver = Archiver(str(tmp_path))
    path = archiver.save(item)
    assert path.exists()
    content = path.read_text()
    assert "Saved Post" in content
    assert "Body text." in content

def test_archiver_dedup(tmp_path):
    item = ContentItem(text="Body.", title="Same Title", source_url="u", content_type=ContentType.article, date=date(2026, 1, 1))
    archiver = Archiver(str(tmp_path))
    path1 = archiver.save(item)
    path2 = archiver.save(item)
    assert path1 != path2
    assert path1.exists()
    assert path2.exists()
    # Second file should have _2 suffix
    assert "_2" in path2.name

def test_archiver_creates_dir(tmp_path):
    new_dir = tmp_path / "subdir" / "output"
    archiver = Archiver(str(new_dir))
    item = ContentItem(text="Body.", title="T", source_url="u", content_type=ContentType.article)
    path = archiver.save(item)
    assert new_dir.exists()
    assert path.exists()

def test_archiver_yaml_in_saved_file(tmp_path):
    item = ContentItem(text="Content here.", title="YAML Test", source_url="https://ex.com/test", content_type=ContentType.article, date=date(2026, 3, 15), author="Author Name")
    archiver = Archiver(str(tmp_path))
    path = archiver.save(item)
    content = path.read_text()
    assert "---" in content
    assert "YAML Test" in content
    assert "https://ex.com/test" in content
