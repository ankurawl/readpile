#!/bin/bash
set -e
cd "$(dirname "$0")/.."
source .venv/bin/activate 2>/dev/null || true
python -m pytest tests/ \
    --cov=readpile \
    --cov-report=term-missing \
    --cov-report=html:htmlcov \
    -v \
    "$@"
echo "Coverage report: htmlcov/index.html"
