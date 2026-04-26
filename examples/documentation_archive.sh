#!/bin/bash
# documentation_archive.sh -- Archive an entire documentation site
#
# Usage:
#   ./documentation_archive.sh <docs-url> [depth] [output-dir]
#
# Arguments:
#   docs-url     Documentation site root URL (required)
#   depth        Max crawl depth (default: 3)
#   output-dir   Directory to save archived docs (default: ./docs-archive)
#
# Examples:
#   ./documentation_archive.sh https://docs.example.com
#   ./documentation_archive.sh https://docs.example.com 5
#   ./documentation_archive.sh https://docs.example.com 3 ./my-docs

set -euo pipefail

if [ $# -lt 1 ]; then
    echo "Usage: $0 <docs-url> [depth] [output-dir]" >&2
    echo "  depth:      max crawl depth (default: 3)" >&2
    echo "  output-dir: directory for saved docs (default: ./docs-archive)" >&2
    exit 1
fi

DOCS_URL="$1"
DEPTH="${2:-3}"
OUTPUT_DIR="${3:-./docs-archive}"

echo "Crawling: $DOCS_URL" >&2
echo "Depth:    $DEPTH" >&2
echo "Output:   $OUTPUT_DIR" >&2
echo "" >&2

crawl "$DOCS_URL" --mode site --depth "$DEPTH" \
    | scrape --batch \
    | archive --dir "$OUTPUT_DIR"

echo "" >&2
echo "Done. Documentation saved to $OUTPUT_DIR" >&2
