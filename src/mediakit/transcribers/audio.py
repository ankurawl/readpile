"""Audio transcriber -- transcribe audio files using Whisper.

Rewrites the video-to-transcript.sh Whisper pipeline as Python.
Supports whisperx (with alignment and diarization) and openai-whisper
as a fallback.
"""

from __future__ import annotations

import logging
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from mediakit.core.models import ContentItem, ContentType

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _check_whisper_deps() -> None:
    """Verify that whisperx or openai-whisper is importable.

    Raises ``SystemExit`` with install instructions if neither is available.
    """
    try:
        import whisperx  # noqa: F401

        return
    except ImportError:
        pass

    try:
        import whisper  # noqa: F401

        return
    except ImportError:
        pass

    print(
        "Error: No Whisper library found.\n"
        "Install one of:\n"
        "  pip install whisperx          # recommended (alignment + diarization)\n"
        "  pip install openai-whisper    # basic transcription only\n",
        file=sys.stderr,
    )
    raise SystemExit(1)


def _check_ffmpeg() -> None:
    """Verify that ffmpeg is available on PATH.

    Raises ``SystemExit`` with install instructions if missing.
    """
    if not shutil.which("ffmpeg"):
        raise SystemExit(
            "ffmpeg is required for audio transcription but was not found.\n"
            "Install it:\n"
            "  macOS:  brew install ffmpeg\n"
            "  Linux:  sudo apt install ffmpeg\n"
            "  Windows: winget install ffmpeg\n"
        )


def _format_timestamp(seconds: float) -> str:
    """Convert *seconds* to ``[HH:MM:SS]`` bracket format."""
    total = int(seconds)
    h = total // 3600
    m = (total % 3600) // 60
    s = total % 60
    return f"[{h:02d}:{m:02d}:{s:02d}]"


def _normalize_speaker(speaker: str) -> str:
    """Normalize diarization labels.

    ``SPEAKER_00`` becomes ``Speaker 1``, ``SPEAKER_01`` becomes
    ``Speaker 2``, etc.  If the label doesn't match that pattern the
    original string is returned unchanged.
    """
    try:
        num = int(speaker.split("_")[-1]) + 1
        return f"Speaker {num}"
    except (ValueError, IndexError):
        return speaker


# ---------------------------------------------------------------------------
# Subtitle parsing
# ---------------------------------------------------------------------------


def parse_subtitle_file(path: Path) -> str:
    """Parse a VTT or SRT subtitle file into ``[HH:MM:SS] text`` lines.

    Consecutive segments with identical text are deduplicated so that
    auto-generated captions don't repeat.
    """
    content = path.read_text(encoding="utf-8")
    lines = content.split("\n")

    # Timestamp regex covering both VTT and SRT formats.
    ts_pattern = re.compile(
        r"(\d{1,2}:\d{2}:\d{2}[.,]\d{3})\s*-->\s*(\d{1,2}:\d{2}:\d{2}[.,]\d{3})"
    )

    entries: list[tuple[str, str]] = []
    current_time: str | None = None
    current_text_parts: list[str] = []

    def _parse_ts(ts: str) -> str:
        """Convert ``HH:MM:SS.mmm`` or ``MM:SS.mmm`` to ``[HH:MM:SS]``."""
        ts = ts.strip()
        parts = ts.split(":")
        if len(parts) == 3:
            h, m, s = parts
        elif len(parts) == 2:
            h = "0"
            m, s = parts
        else:
            return "[00:00:00]"
        s = s.split(".")[0].split(",")[0]  # drop milliseconds
        return f"[{int(h):02d}:{int(m):02d}:{int(s):02d}]"

    def _flush() -> None:
        nonlocal current_time, current_text_parts
        if current_time and current_text_parts:
            text = " ".join(current_text_parts).strip()
            # Strip VTT/HTML formatting tags
            text = re.sub(r"<[^>]+>", "", text).strip()
            if text:
                entries.append((current_time, text))
        current_time = None
        current_text_parts = []

    for line in lines:
        line = line.strip()

        if not line:
            _flush()
            continue

        # Skip VTT headers / comments / SRT sequence numbers
        if line == "WEBVTT" or line.startswith(("Kind:", "Language:", "NOTE")):
            continue
        if re.match(r"^\d+$", line):
            _flush()
            continue

        m = ts_pattern.match(line)
        if m:
            _flush()
            current_time = _parse_ts(m.group(1))
            continue

        if current_time is not None:
            current_text_parts.append(line)

    _flush()

    # Deduplicate consecutive identical text
    deduped: list[tuple[str, str]] = []
    for ts, text in entries:
        if not deduped or deduped[-1][1] != text:
            deduped.append((ts, text))

    return "\n".join(f"{ts} {text}" for ts, text in deduped)


# ---------------------------------------------------------------------------
# Subtitle extraction via yt-dlp
# ---------------------------------------------------------------------------


def try_extract_subtitles(url: str, output_dir: Path) -> Path | None:
    """Attempt to download subtitles for *url* via ``yt-dlp``.

    Tries VTT first, then SRT as a fallback.  Returns the path to the
    downloaded subtitle file or ``None`` if no subtitles are available.
    """
    if not shutil.which("yt-dlp"):
        logger.debug("yt-dlp not found; skipping subtitle extraction")
        return None

    out_template = str(output_dir / "subs")

    # Try VTT first, then SRT
    for sub_format in ("vtt", "srt"):
        cmd = [
            "yt-dlp",
            "--write-sub",
            "--write-auto-sub",
            "--sub-lang",
            "en.*,en",
            "--sub-format",
            sub_format,
            "--skip-download",
            "--no-warnings",
            "-o",
            out_template,
            url,
        ]

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                timeout=120,
                check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

        # Look for downloaded subtitle files
        for ext in ("vtt", "srt"):
            for sub_file in output_dir.glob(f"subs*.{ext}"):
                if sub_file.stat().st_size > 0:
                    logger.info("Subtitles downloaded (%s)", ext.upper())
                    return sub_file

    logger.info("Could not download subtitles")
    return None


# ---------------------------------------------------------------------------
# Audio download
# ---------------------------------------------------------------------------


def download_audio(url: str, output_dir: Path) -> Path:
    """Download audio from *url* and convert to 16 kHz mono WAV.

    Uses ``yt-dlp`` for extraction and ``ffmpeg`` for re-encoding.
    Falls back to a direct ``curl`` download when ``yt-dlp`` fails.

    Returns the path to the resulting ``.wav`` file.

    Raises ``RuntimeError`` if audio cannot be obtained.
    """
    audio_file = output_dir / "audio.wav"

    # --- Primary path: yt-dlp -------------------------------------------
    if shutil.which("yt-dlp"):
        out_template = str(output_dir / "audio.%(ext)s")
        cmd = [
            "yt-dlp",
            "-x",
            "--audio-format",
            "wav",
            "--no-warnings",
            "-o",
            out_template,
            url,
        ]

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                timeout=600,
                check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        # yt-dlp may produce a file with a different extension
        found = next(output_dir.glob("audio.*"), None)
        if found and found.stat().st_size > 0:
            if found != audio_file:
                # Convert to 16 kHz mono WAV for Whisper
                _ffmpeg_convert(found, audio_file)
                found.unlink(missing_ok=True)
            if audio_file.exists() and audio_file.stat().st_size > 0:
                logger.info("Audio downloaded via yt-dlp")
                return audio_file

    # --- Fallback: direct curl download ---------------------------------
    if shutil.which("curl"):
        raw_path = output_dir / "video_raw"
        try:
            subprocess.run(
                ["curl", "-sL", "--max-time", "300", url, "-o", str(raw_path)],
                capture_output=True,
                timeout=310,
                check=False,
            )
        except (subprocess.TimeoutExpired, FileNotFoundError):
            pass

        if raw_path.exists() and raw_path.stat().st_size > 0:
            _ffmpeg_convert(raw_path, audio_file)
            raw_path.unlink(missing_ok=True)
            if audio_file.exists() and audio_file.stat().st_size > 0:
                logger.info("Audio extracted from direct download")
                return audio_file

    raise RuntimeError(f"Failed to download audio from {url}")


def _ffmpeg_convert(src: Path, dst: Path) -> None:
    """Convert *src* to 16 kHz mono WAV at *dst* via ``ffmpeg``."""
    cmd = [
        "ffmpeg",
        "-i",
        str(src),
        "-ar",
        "16000",
        "-ac",
        "1",
        str(dst),
        "-y",
        "-loglevel",
        "error",
    ]
    subprocess.run(cmd, capture_output=True, timeout=300, check=False)


# ---------------------------------------------------------------------------
# Whisper transcription
# ---------------------------------------------------------------------------


def _transcribe_segments(
    audio_path: Path,
    model: str = "base",
    diarize: bool = False,
) -> list[dict]:
    """Run Whisper on *audio_path* and return a list of segment dicts.

    Each dict has keys ``start``, ``end``, ``text``, and ``speaker``.
    """
    _check_whisper_deps()

    use_whisperx = False
    try:
        import whisperx  # noqa: F811

        use_whisperx = True
    except ImportError:
        pass

    if use_whisperx:
        return _transcribe_whisperx(audio_path, model, diarize)
    else:
        return _transcribe_whisper(audio_path, model)


def _transcribe_whisperx(
    audio_path: Path,
    model_name: str,
    do_diarize: bool,
) -> list[dict]:
    """Transcribe with whisperx (alignment + optional diarization)."""
    import torch
    import whisperx

    device = "cuda" if torch.cuda.is_available() else "cpu"
    compute_type = "float16" if device == "cuda" else "int8"

    logger.info("Transcribing with whisperx (device=%s)...", device)
    wx_model = whisperx.load_model(model_name, device, compute_type=compute_type)
    audio = whisperx.load_audio(str(audio_path))
    result = wx_model.transcribe(audio, batch_size=16)

    # Align
    logger.info("Aligning transcript...")
    model_a, metadata = whisperx.load_align_model(
        language_code=result["language"], device=device
    )
    result = whisperx.align(
        result["segments"],
        model_a,
        metadata,
        audio,
        device,
        return_char_alignments=False,
    )

    # Diarize if requested and HF_TOKEN available
    if do_diarize:
        hf_token = os.environ.get("HF_TOKEN", "")
        if hf_token:
            logger.info("Running speaker diarization...")
            try:
                diarize_model = whisperx.DiarizationPipeline(
                    use_auth_token=hf_token, device=device
                )
                diarize_segments = diarize_model(audio)
                result = whisperx.assign_word_speakers(diarize_segments, result)
            except Exception as exc:
                logger.warning(
                    "Diarization failed: %s. Continuing without speaker labels.", exc
                )
        else:
            logger.warning(
                "No HF_TOKEN set. Skipping speaker diarization. "
                "Set HF_TOKEN env var for speaker identification."
            )

    return _segments_to_dicts(result.get("segments", []))


def _transcribe_whisper(audio_path: Path, model_name: str) -> list[dict]:
    """Transcribe with openai-whisper (no diarization)."""
    import whisper

    logger.info("Transcribing with openai-whisper (no diarization)...")
    w_model = whisper.load_model(model_name)
    result = w_model.transcribe(str(audio_path), verbose=False)

    return _segments_to_dicts(result.get("segments", []))


def _segments_to_dicts(segments: list[dict]) -> list[dict]:
    """Normalize a list of raw Whisper segments into uniform dicts."""
    output: list[dict] = []
    for seg in segments:
        output.append(
            {
                "start": seg.get("start", 0),
                "end": seg.get("end", 0),
                "text": seg.get("text", "").strip(),
                "speaker": seg.get("speaker", ""),
            }
        )
    return output


def _format_segments(segments: list[dict]) -> str:
    """Format segment dicts into timestamped text lines.

    Each line is ``[HH:MM:SS] text`` or ``[HH:MM:SS] **Speaker N**: text``
    when speaker labels are present.
    """
    lines: list[str] = []
    for seg in segments:
        ts = _format_timestamp(seg["start"])
        text = seg["text"]
        speaker = seg.get("speaker", "")

        if speaker:
            label = _normalize_speaker(speaker)
            lines.append(f"{ts} **{label}**: {text}")
        else:
            lines.append(f"{ts} {text}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def transcribe_audio(
    audio_path: Path,
    model: str = "base",
    diarize: bool = False,
) -> ContentItem:
    """Transcribe a local audio file and return a ``ContentItem``.

    Parameters
    ----------
    audio_path:
        Path to an audio file (WAV recommended; ffmpeg-decodable formats
        accepted by Whisper).
    model:
        Whisper model size (``tiny``, ``base``, ``small``, ``medium``,
        ``large``).
    diarize:
        Whether to attempt speaker diarization (requires whisperx and
        ``HF_TOKEN``).

    Returns
    -------
    ContentItem
        With ``content_type=ContentType.audio`` and timestamped transcript.
    """
    _check_ffmpeg()
    segments = _transcribe_segments(audio_path, model=model, diarize=diarize)
    formatted = _format_segments(segments)

    return ContentItem(
        content_type=ContentType.audio,
        text=formatted,
        title=audio_path.stem,
        source_url="",
    )


def transcribe_from_url(
    url: str,
    model: str = "base",
    diarize: bool = False,
) -> ContentItem:
    """Download audio from *url*, transcribe it, and return a ``ContentItem``.

    First attempts to grab subtitles (much faster); falls back to full
    Whisper transcription when subtitles are unavailable.

    Parameters
    ----------
    url:
        A URL supported by ``yt-dlp`` (YouTube, podcast RSS enclosures,
        direct audio links, etc.).
    model:
        Whisper model size.
    diarize:
        Whether to attempt speaker diarization.

    Returns
    -------
    ContentItem
        With ``content_type=ContentType.audio``, timestamped transcript,
        and ``source_url`` set.
    """
    _check_ffmpeg()
    tmpdir = tempfile.mkdtemp(prefix="mediakit_audio_")

    try:
        # Fetch title metadata via yt-dlp
        title = _get_title(url)

        # Try subtitles first (fast path)
        sub_path = try_extract_subtitles(url, Path(tmpdir))
        if sub_path is not None:
            formatted = parse_subtitle_file(sub_path)
            logger.info("Transcript generated from subtitles")
        else:
            # Full Whisper pipeline
            audio_path = download_audio(url, Path(tmpdir))
            segments = _transcribe_segments(
                audio_path, model=model, diarize=diarize
            )
            formatted = _format_segments(segments)
            logger.info("Transcript generated via Whisper")

        return ContentItem(
            content_type=ContentType.audio,
            text=formatted,
            title=title,
            source_url=url,
        )
    finally:
        # Clean up temp files
        shutil.rmtree(tmpdir, ignore_errors=True)


def _get_title(url: str) -> str:
    """Retrieve the media title from *url* via ``yt-dlp --get-title``.

    Returns a sanitized title string, or a generic fallback on failure.
    """
    if not shutil.which("yt-dlp"):
        return "audio"

    try:
        result = subprocess.run(
            ["yt-dlp", "--get-title", "--no-warnings", url],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        title = result.stdout.strip()
        if title:
            return title
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return "audio"
