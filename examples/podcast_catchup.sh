#!/bin/bash
# podcast_catchup.sh -- Get short summaries of recent podcast episodes
#
# Usage:
#   ./podcast_catchup.sh <feed-url> [count]
#
# Arguments:
#   feed-url   RSS/Atom feed URL for the podcast (required)
#   count      Number of recent episodes to process (default: 5)
#
# Examples:
#   ./podcast_catchup.sh https://podcast.com/feed.xml
#   ./podcast_catchup.sh https://podcast.com/feed.xml 3
#   ./podcast_catchup.sh https://feeds.simplecast.com/example 10

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <feed-url> [count]" >&2
    echo "  count: number of recent episodes (default: 5)" >&2
    exit 1
fi

FEED_URL="$1"
COUNT="${2:-5}"

echo "Feed:     $FEED_URL" >&2
echo "Episodes: $COUNT most recent" >&2
echo "" >&2

crawl "$FEED_URL" --recent "$COUNT" \
    | transcribe --batch \
    | summarize --batch --length small
