#!/usr/bin/env bash
# setup.sh — readpile installer for macOS and Linux
# Usage: bash setup.sh
set -euo pipefail

# ── Colors ────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m' # No Color

info()    { echo -e "${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERR]${NC}   $*"; }
step()    { echo -e "\n${CYAN}${BOLD}==> $*${NC}"; }

# ── Navigate to project root ─────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

echo -e "${BOLD}"
echo "  ┌──────────────────────────────────┐"
echo "  │       readpile setup            │"
echo "  │  Your personal media library     │"
echo "  └──────────────────────────────────┘"
echo -e "${NC}"

OS="$(uname -s)"
ARCH="$(uname -m)"
info "Detected OS: $OS ($ARCH)"

ERRORS=0

# ── 1. Check Python version ──────────────────────────────────────────
step "1/8  Checking Python version"

PYTHON=""
for candidate in python3 python; do
    if command -v "$candidate" &>/dev/null; then
        PYTHON="$candidate"
        break
    fi
done

if [ -z "$PYTHON" ]; then
    error "Python not found. Install Python 3.10+ first."
    error "  macOS:  brew install python@3.12"
    error "  Linux:  sudo apt install python3.12 python3.12-venv"
    exit 1
fi

PY_VERSION=$("$PYTHON" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_MAJOR=$("$PYTHON" -c 'import sys; print(sys.version_info.major)')
PY_MINOR=$("$PYTHON" -c 'import sys; print(sys.version_info.minor)')

if [ "$PY_MAJOR" -lt 3 ] || { [ "$PY_MAJOR" -eq 3 ] && [ "$PY_MINOR" -lt 10 ]; }; then
    error "Python >= 3.10 required (found $PY_VERSION)"
    error "  macOS:  brew install python@3.12"
    error "  Linux:  sudo apt install python3.12 python3.12-venv"
    exit 1
fi

success "Python $PY_VERSION ($($PYTHON --version 2>&1))"

# ── 2. Create virtual environment ────────────────────────────────────
step "2/8  Creating virtual environment"

if [ -d ".venv" ]; then
    info "Virtual environment already exists at .venv/"
    # Verify it's usable
    if [ -f ".venv/bin/python" ]; then
        success "Reusing existing .venv/"
    else
        warn "Existing .venv/ appears broken, recreating..."
        rm -rf .venv
        "$PYTHON" -m venv .venv
        success "Created fresh .venv/"
    fi
else
    "$PYTHON" -m venv .venv
    success "Created .venv/"
fi

# Activate
# shellcheck disable=SC1091
source .venv/bin/activate

# Upgrade pip
info "Upgrading pip..."
pip install --upgrade pip --quiet
success "pip upgraded"

# ── 3. Install Python dependencies ──────────────────────────────────
step "3/8  Installing Python dependencies"

info "Installing readpile with all extras (base + audio + bot + mcp + dev)..."
if pip install -e ".[all,dev]" --quiet; then
    success "All Python dependencies installed"
else
    error "Failed to install dependencies. Check the output above."
    ERRORS=$((ERRORS + 1))
fi

# ── 4. Install Playwright browser ───────────────────────────────────
step "4/8  Installing Playwright Chromium browser"

if command -v playwright &>/dev/null || [ -f ".venv/bin/playwright" ]; then
    info "Installing Chromium for Playwright..."
    if python -m playwright install chromium; then
        success "Playwright Chromium installed"
    else
        warn "Playwright Chromium install failed (non-fatal)"
        ERRORS=$((ERRORS + 1))
    fi

    # On Linux, install system dependencies
    if [ "$OS" = "Linux" ]; then
        info "Installing Playwright system dependencies (may require sudo)..."
        if playwright install-deps chromium; then
            success "Playwright system deps installed"
        else
            warn "Could not install Playwright system deps. You may need to run:"
            warn "  sudo python -m playwright install-deps chromium"
            ERRORS=$((ERRORS + 1))
        fi
    fi
else
    warn "Playwright CLI not found. Skipping browser install."
    ERRORS=$((ERRORS + 1))
fi

# ── 5. Check ffmpeg ──────────────────────────────────────────────────
step "5/8  Checking ffmpeg"

if command -v ffmpeg &>/dev/null; then
    FFMPEG_VERSION=$(ffmpeg -version 2>&1 | head -1 | awk '{print $3}')
    success "ffmpeg found (version $FFMPEG_VERSION)"
else
    warn "ffmpeg not found. Audio transcription features will not work."
    echo ""
    if [ "$OS" = "Darwin" ]; then
        warn "Install with:  brew install ffmpeg"
    else
        warn "Install with:  sudo apt install ffmpeg"
    fi
    ERRORS=$((ERRORS + 1))
fi

# ── 6. Detect GPU ───────────────────────────────────────────────────
step "6/8  Detecting GPU"

GPU_DETECTED=""
if [ "$OS" = "Darwin" ]; then
    if [ "$ARCH" = "arm64" ]; then
        GPU_DETECTED="Apple Silicon ($ARCH)"
        success "Apple Silicon detected — Metal acceleration available"
    else
        info "Intel Mac detected — no GPU acceleration"
    fi
elif [ "$OS" = "Linux" ]; then
    if command -v nvidia-smi &>/dev/null; then
        GPU_NAME=$(nvidia-smi --query-gpu=name --format=csv,noheader 2>/dev/null | head -1 || echo "unknown")
        GPU_DETECTED="NVIDIA ($GPU_NAME)"
        success "NVIDIA GPU detected: $GPU_NAME — CUDA acceleration available"
    else
        info "No NVIDIA GPU detected. Whisper will run on CPU (slower)."
    fi
fi

# ── 7. Generate config file ─────────────────────────────────────────
step "7/8  Generating config file"

CONFIG_DIR="$HOME/.readpile"
CONFIG_FILE="$CONFIG_DIR/config.toml"

if [ -f "$CONFIG_FILE" ]; then
    info "Config already exists at $CONFIG_FILE — skipping"
else
    info "Running 'readpile init' to create default config..."
    if readpile init 2>/dev/null; then
        success "Config written to $CONFIG_FILE"
    else
        warn "Could not generate config automatically."
        warn "Run 'readpile init' manually after setup."
        ERRORS=$((ERRORS + 1))
    fi
fi

# ── 8. Run quick tests ─────────────────────────────────────────────
step "8/8  Running quick test suite"

if [ -d "tests" ]; then
    info "Running fast tests (excluding slow, network, audio)..."
    if python -m pytest tests/ -m "not slow and not network and not audio" -q --tb=short 2>&1; then
        success "Quick tests passed"
    else
        warn "Some tests failed. This may be OK for optional features."
        ERRORS=$((ERRORS + 1))
    fi
else
    info "No tests directory found, skipping"
fi

# ── Summary ──────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}────────────────────────────────────────${NC}"

if [ "$ERRORS" -eq 0 ]; then
    echo -e "${GREEN}${BOLD}  Setup completed successfully!${NC}"
else
    echo -e "${YELLOW}${BOLD}  Setup completed with $ERRORS warning(s).${NC}"
fi

echo -e "${BOLD}────────────────────────────────────────${NC}"
echo ""
echo "  Activate the environment:"
echo "    source .venv/bin/activate"
echo ""
echo "  Quick start:"
echo "    scrape https://example.com/blog-post"
echo "    transcribe https://youtube.com/watch?v=..."
echo "    content https://example.com/article"
echo "    crawl rss https://blog.example.com/feed"
echo ""
echo "  Run tests:"
echo "    ./scripts/test.sh          # full suite"
echo "    ./scripts/test_quick.sh    # fast tests only"
echo "    ./scripts/lint.sh          # linting"
echo ""

if [ -n "$GPU_DETECTED" ]; then
    echo "  GPU: $GPU_DETECTED"
    echo ""
fi
