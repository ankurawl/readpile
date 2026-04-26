"""Summarization engine — orchestrate content summarization pipelines."""

from __future__ import annotations

from mediakit.summarizer.providers import LLMProvider


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHUNK_SIZE = 50_000  # characters per chunk for long-text splitting
_LONG_TEXT_THRESHOLD = 100_000  # characters — above this we chunk


# ---------------------------------------------------------------------------
# Target length
# ---------------------------------------------------------------------------


def calculate_target_length(text: str, length: str) -> int:
    """Return the target summary length in words.

    Parameters
    ----------
    text:
        The source text to be summarised.
    length:
        One of ``"small"``, ``"medium"``, or ``"long"``.

    Returns
    -------
    int
        Target word count (minimum 30).
    """
    word_count = len(text.split())

    if length == "small":
        target = min(word_count * 0.10, 50)
    elif length == "long":
        target = word_count * 0.40
    else:  # medium (default)
        target = word_count * 0.20

    return max(int(target), 30)


# ---------------------------------------------------------------------------
# Prompt helpers
# ---------------------------------------------------------------------------


def _build_metadata_line(metadata: dict | None) -> str:
    """Format optional metadata into a human-readable header line."""
    if not metadata:
        return ""

    parts: list[str] = []
    if metadata.get("title"):
        parts.append(f"Title: {metadata['title']}")
    if metadata.get("channel"):
        parts.append(f"Channel: {metadata['channel']}")
    if metadata.get("duration"):
        parts.append(f"Duration: {metadata['duration']}")

    if not parts:
        return ""
    return "\n".join(parts)


def _build_prompt(text: str, target_words: int, metadata: dict | None = None) -> str:
    """Assemble the full summarization prompt."""
    metadata_line = _build_metadata_line(metadata)
    metadata_section = f"\n{metadata_line}\n" if metadata_line else ""

    return (
        f"You are an expert content analyst. Analyze this content and "
        f"produce a summary of approximately {target_words} words.\n"
        f"\n"
        f"Structure your response exactly as follows:\n"
        f"\n"
        f"## Summary\n"
        f"3-5 paragraph summary of the main narrative, arguments, and conclusions.\n"
        f"\n"
        f"## Key Takeaways\n"
        f"5-10 bullet points. Each standalone and actionable.\n"
        f"\n"
        f"## Learnings\n"
        f"Specific facts, frameworks, techniques, or mental models mentioned.\n"
        f"\n"
        f"---"
        f"{metadata_section}"
        f"Content:\n"
        f"{text}"
    )


def _build_chunk_prompt(chunk: str, chunk_index: int, total_chunks: int) -> str:
    """Prompt for summarising a single chunk of a larger text."""
    return (
        f"You are an expert content analyst. This is part {chunk_index} of {total_chunks} "
        f"of a longer piece of content. Summarize the key points, arguments, and details "
        f"from this section. Be thorough — your summary will be combined with others.\n"
        f"\n"
        f"Content (part {chunk_index}/{total_chunks}):\n"
        f"{chunk}"
    )


def _build_synthesis_prompt(
    chunk_summaries: list[str],
    target_words: int,
    metadata: dict | None = None,
) -> str:
    """Prompt that merges individual chunk summaries into a final output."""
    metadata_line = _build_metadata_line(metadata)
    metadata_section = f"\n{metadata_line}\n" if metadata_line else ""

    combined = "\n\n---\n\n".join(
        f"[Section {i + 1}]\n{s}" for i, s in enumerate(chunk_summaries)
    )

    return (
        f"You are an expert content analyst. Below are summaries of consecutive "
        f"sections of a single piece of content. Synthesize them into one cohesive "
        f"summary of approximately {target_words} words.\n"
        f"\n"
        f"Structure your response exactly as follows:\n"
        f"\n"
        f"## Summary\n"
        f"3-5 paragraph summary of the main narrative, arguments, and conclusions.\n"
        f"\n"
        f"## Key Takeaways\n"
        f"5-10 bullet points. Each standalone and actionable.\n"
        f"\n"
        f"## Learnings\n"
        f"Specific facts, frameworks, techniques, or mental models mentioned.\n"
        f"\n"
        f"---"
        f"{metadata_section}"
        f"Section summaries:\n"
        f"{combined}"
    )


# ---------------------------------------------------------------------------
# Internal summarization strategies
# ---------------------------------------------------------------------------


def _summarize_single(
    text: str,
    provider: LLMProvider,
    target_words: int,
    metadata: dict | None = None,
) -> str:
    """Summarize a text that fits within a single prompt."""
    prompt = _build_prompt(text, target_words, metadata)
    return provider.generate(prompt)


def _split_into_chunks(text: str, chunk_size: int = _CHUNK_SIZE) -> list[str]:
    """Split *text* at paragraph boundaries into chunks of roughly *chunk_size* chars.

    Paragraphs (delimited by double newlines) are never broken mid-way.
    """
    paragraphs = text.split("\n\n")
    chunks: list[str] = []
    current_chunk: list[str] = []
    current_length = 0

    for para in paragraphs:
        para_len = len(para)

        # If adding this paragraph would exceed the limit and we already
        # have content, flush the current chunk first.
        if current_length + para_len > chunk_size and current_chunk:
            chunks.append("\n\n".join(current_chunk))
            current_chunk = []
            current_length = 0

        current_chunk.append(para)
        current_length += para_len

    # Don't forget the last chunk.
    if current_chunk:
        chunks.append("\n\n".join(current_chunk))

    return chunks


def _summarize_chunked(
    text: str,
    provider: LLMProvider,
    target_words: int,
    metadata: dict | None = None,
) -> str:
    """Summarize a long text by splitting it into chunks, summarizing each,
    then synthesizing the final output."""
    chunks = _split_into_chunks(text)
    total = len(chunks)

    # Phase 1: summarize each chunk independently.
    chunk_summaries: list[str] = []
    for idx, chunk in enumerate(chunks, start=1):
        prompt = _build_chunk_prompt(chunk, idx, total)
        summary = provider.generate(prompt)
        chunk_summaries.append(summary)

    # Phase 2: synthesize chunk summaries into the final result.
    synthesis_prompt = _build_synthesis_prompt(chunk_summaries, target_words, metadata)
    return provider.generate(synthesis_prompt)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def summarize(
    text: str,
    provider: LLMProvider,
    length: str = "medium",
    metadata: dict | None = None,
) -> str:
    """Summarize *text* using the given LLM *provider*.

    Parameters
    ----------
    text:
        The content to summarize (plain text or transcript).
    provider:
        An :class:`~mediakit.summarizer.providers.LLMProvider` instance.
    length:
        Target summary length — ``"small"``, ``"medium"``, or ``"long"``.
    metadata:
        Optional dict with keys like ``title``, ``channel``, ``duration``
        to give the LLM additional context.

    Returns
    -------
    str
        The generated summary in Markdown format.
    """
    target_words = calculate_target_length(text, length)

    if len(text) > _LONG_TEXT_THRESHOLD:
        return _summarize_chunked(text, provider, target_words, metadata)

    return _summarize_single(text, provider, target_words, metadata)
