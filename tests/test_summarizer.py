from unittest.mock import MagicMock
from mediakit.summarizer.engine import summarize, calculate_target_length


def test_target_length_small():
    text = " ".join(["word"] * 1000)
    target = calculate_target_length(text, "small")
    assert target == 50  # min(100, 50) = 50


def test_target_length_medium():
    text = " ".join(["word"] * 1000)
    target = calculate_target_length(text, "medium")
    assert target == 200  # 20% of 1000


def test_target_length_long():
    text = " ".join(["word"] * 1000)
    target = calculate_target_length(text, "long")
    assert target == 400  # 40% of 1000


def test_target_length_floor():
    text = " ".join(["word"] * 10)
    target = calculate_target_length(text, "small")
    assert target == 30  # floor is 30


def test_summarize_calls_provider():
    mock_provider = MagicMock()
    mock_provider.generate.return_value = "## Summary\nThis is a summary."
    result = summarize("Some long text to summarize. " * 50, mock_provider, "medium")
    mock_provider.generate.assert_called_once()
    assert "Summary" in result


def test_summarize_with_metadata():
    mock_provider = MagicMock()
    mock_provider.generate.return_value = "## Summary\nSummary text."
    metadata = {"title": "Video Title", "channel": "Channel", "duration": "10:00"}
    result = summarize("Text content. " * 50, mock_provider, "medium", metadata)
    # Check that metadata was included in the prompt
    call_args = mock_provider.generate.call_args[0][0]
    assert "Video Title" in call_args


def test_summarize_chunked():
    mock_provider = MagicMock()
    mock_provider.generate.return_value = "## Summary\nChunk summary."
    # Create text over 100K chars to trigger chunking
    long_text = "A paragraph of text. " * 10000
    result = summarize(long_text, mock_provider, "medium")
    # Should call generate multiple times (chunks + synthesis)
    assert mock_provider.generate.call_count > 1
