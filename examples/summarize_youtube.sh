#!/bin/bash
# summarize_youtube.sh -- Summarize a YouTube video with configurable length
#
# Usage:
#   ./summarize_youtube.sh <youtube-url> [length]
#
# Arguments:
#   youtube-url   YouTube video URL (required)
#   length        Summary length: small, medium, long (default: medium)
#
# Examples:
#   ./summarize_youtube.sh https://youtube.com/watch?v=dQw4w9WgXcQ
#   ./summarize_youtube.sh https://youtube.com/watch?v=dQw4w9WgXcQ small
#   ./summarize_youtube.sh https://youtu.be/dQw4w9WgXcQ long

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <youtube-url> [length]" >&2
    echo "  length: small, medium, long (default: medium)" >&2
    exit 1
fi

URL="$1"
LENGTH="${2:-medium}"

echo "Transcribing: $URL" >&2
echo "Summary length: $LENGTH" >&2
echo "" >&2

transcribe "$URL" | summarize --length "$LENGTH"
