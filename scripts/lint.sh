#!/bin/bash
set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate 2>/dev/null || true
python -m ruff check src/ tests/
python -m ruff format --check src/ tests/
