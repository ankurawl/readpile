#!/bin/bash
# batch_blog_download.sh -- Download and archive all posts from a blog
#
# Usage:
#   ./batch_blog_download.sh <blog-url> [output-dir]
#
# Arguments:
#   blog-url     Blog URL or RSS feed to crawl (required)
#   output-dir   Directory to save archived posts (default: ./blog-archive)
#
# Examples:
#   ./batch_blog_download.sh https://example.com/blog
#   ./batch_blog_download.sh https://example.com/blog ./my-blog-backup
#   ./batch_blog_download.sh https://example.com/feed.xml ./rss-archive

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <blog-url> [output-dir]" >&2
    echo "  output-dir: directory for saved posts (default: ./blog-archive)" >&2
    exit 1
fi

URL="$1"
OUTPUT_DIR="${2:-./blog-archive}"

echo "Crawling: $URL" >&2
echo "Output:   $OUTPUT_DIR" >&2
echo "" >&2

crawl "$URL" | scrape --batch | archive --dir "$OUTPUT_DIR"

echo "" >&2
echo "Done. Posts saved to $OUTPUT_DIR" >&2
