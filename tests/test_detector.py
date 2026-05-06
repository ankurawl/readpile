"""Tests for readpile.core.detector — URL type detection and YouTube ID extraction."""

from readpile.core.detector import detect_url_type, URLType, extract_youtube_video_id


# --- YouTube ---


def test_youtube_standard():
    assert detect_url_type("https://www.youtube.com/watch?v=abc123") == URLType.youtube


def test_youtube_short():
    assert detect_url_type("https://youtu.be/abc123") == URLType.youtube


def test_youtube_shorts():
    assert detect_url_type("https://youtube.com/shorts/abc123") == URLType.youtube


def test_youtube_live():
    assert detect_url_type("https://youtube.com/live/abc123") == URLType.youtube


def test_youtube_playlist():
    assert detect_url_type("https://youtube.com/playlist?list=PL123") == URLType.youtube


# --- RSS ---


def test_rss_xml():
    assert detect_url_type("https://example.com/feed.xml") == URLType.rss


def test_rss_rss():
    assert detect_url_type("https://example.com/blog.rss") == URLType.rss


def test_rss_feed_path():
    assert detect_url_type("https://example.com/feed") == URLType.rss


def test_rss_atom():
    assert detect_url_type("https://example.com/atom.xml") == URLType.rss


# --- Audio ---


def test_audio_mp3():
    assert detect_url_type("https://example.com/episode.mp3") == URLType.audio_file


def test_audio_wav():
    assert detect_url_type("https://example.com/audio.wav") == URLType.audio_file


def test_audio_m4a():
    assert detect_url_type("https://example.com/audio.m4a") == URLType.audio_file


# --- Video ---


def test_video_vimeo():
    assert detect_url_type("https://vimeo.com/123456") == URLType.video


def test_video_loom():
    assert detect_url_type("https://www.loom.com/share/abc") == URLType.video


# --- YouTube channel ---


def test_youtube_channel_handle():
    assert detect_url_type("https://www.youtube.com/@howiaipodcast") == URLType.youtube_channel


def test_youtube_channel_id():
    assert detect_url_type("https://www.youtube.com/channel/UCBcRF18a7Qf58cCRy5xuWwQ") == URLType.youtube_channel


def test_youtube_channel_custom():
    assert detect_url_type("https://www.youtube.com/c/Fireship") == URLType.youtube_channel


def test_youtube_channel_user():
    assert detect_url_type("https://www.youtube.com/user/someuser") == URLType.youtube_channel


def test_youtube_channel_with_videos_subpath():
    assert detect_url_type("https://www.youtube.com/@handle/videos") == URLType.youtube_channel


def test_audio_in_feed_path():
    """MP3 URLs with /feed/ in path should be audio, not RSS."""
    assert detect_url_type("https://api.substack.com/feed/podcast/123/ep.mp3") == URLType.audio_file


# --- Blog (default) ---


def test_blog_default():
    assert detect_url_type("https://example.com/blog/my-post") == URLType.blog


def test_blog_generic():
    assert detect_url_type("https://example.com/some-page") == URLType.blog


# --- YouTube video ID extraction ---


def test_extract_id_standard():
    assert (
        extract_youtube_video_id("https://youtube.com/watch?v=dQw4w9WgXcQ")
        == "dQw4w9WgXcQ"
    )


def test_extract_id_short():
    assert (
        extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    )


def test_extract_id_shorts():
    assert (
        extract_youtube_video_id("https://youtube.com/shorts/dQw4w9WgXcQ")
        == "dQw4w9WgXcQ"
    )


def test_extract_id_invalid():
    assert extract_youtube_video_id("https://example.com") is None
