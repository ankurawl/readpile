#!/bin/bash
set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate 2>/dev/null || true
python -m pytest tests/ \
    -m "not slow and not network and not audio" \
    -v \
    "$@"
