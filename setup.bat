@echo off
REM setup.bat — mediakit installer for Windows
REM Usage: setup.bat
setlocal enabledelayedexpansion

echo.
echo   +---------------------------------+
echo   ^|       mediakit setup            ^|
echo   ^|  Composable CLI media toolkit   ^|
echo   +---------------------------------+
echo.

set "ERRORS=0"

REM ── Navigate to project root ───────────────────────────────────────
cd /d "%~dp0"

REM ── 1. Check Python version ────────────────────────────────────────
echo [1/10] Checking Python version...

set "PYTHON="
where python >nul 2>&1
if %ERRORLEVEL% equ 0 (
    set "PYTHON=python"
) else (
    where python3 >nul 2>&1
    if %ERRORLEVEL% equ 0 (
        set "PYTHON=python3"
    )
)

if "%PYTHON%"=="" (
    echo [ERR]  Python not found. Install Python 3.10+ from https://python.org
    exit /b 1
)

for /f "tokens=*" %%i in ('%PYTHON% -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"') do set PY_VERSION=%%i
for /f "tokens=*" %%i in ('%PYTHON% -c "import sys; print(sys.version_info.major)"') do set PY_MAJOR=%%i
for /f "tokens=*" %%i in ('%PYTHON% -c "import sys; print(sys.version_info.minor)"') do set PY_MINOR=%%i

if %PY_MAJOR% lss 3 (
    echo [ERR]  Python ^>= 3.10 required ^(found %PY_VERSION%^)
    echo [ERR]  Download from https://python.org
    exit /b 1
)
if %PY_MAJOR% equ 3 if %PY_MINOR% lss 10 (
    echo [ERR]  Python ^>= 3.10 required ^(found %PY_VERSION%^)
    echo [ERR]  Download from https://python.org
    exit /b 1
)

echo [OK]   Python %PY_VERSION%

REM ── 2. Create virtual environment ──────────────────────────────────
echo.
echo [2/10] Creating virtual environment...

if exist ".venv\Scripts\python.exe" (
    echo [OK]   Reusing existing .venv\
) else (
    if exist ".venv" (
        echo [WARN] Existing .venv\ appears broken, recreating...
        rmdir /s /q .venv
    )
    %PYTHON% -m venv .venv
    if %ERRORLEVEL% neq 0 (
        echo [ERR]  Failed to create virtual environment
        exit /b 1
    )
    echo [OK]   Created .venv\
)

REM Activate
call .venv\Scripts\activate.bat

REM Upgrade pip
echo [INFO] Upgrading pip...
pip install --upgrade pip --quiet
echo [OK]   pip upgraded

REM ── 3. Install Python dependencies ────────────────────────────────
echo.
echo [3/10] Installing Python dependencies...

echo [INFO] Installing mediakit with all extras...
pip install -e ".[all,dev]" --quiet
if %ERRORLEVEL% equ 0 (
    echo [OK]   All Python dependencies installed
) else (
    echo [ERR]  Failed to install dependencies
    set /a ERRORS+=1
)

REM ── 4. Install Playwright browser ─────────────────────────────────
echo.
echo [4/10] Installing Playwright Chromium browser...

where playwright >nul 2>&1
if %ERRORLEVEL% equ 0 (
    playwright install chromium
    if %ERRORLEVEL% equ 0 (
        echo [OK]   Playwright Chromium installed
    ) else (
        echo [WARN] Playwright Chromium install failed
        set /a ERRORS+=1
    )
) else (
    if exist ".venv\Scripts\playwright.exe" (
        .venv\Scripts\playwright.exe install chromium
        if %ERRORLEVEL% equ 0 (
            echo [OK]   Playwright Chromium installed
        ) else (
            echo [WARN] Playwright Chromium install failed
            set /a ERRORS+=1
        )
    ) else (
        echo [WARN] Playwright CLI not found. Skipping browser install.
        set /a ERRORS+=1
    )
)

REM ── 5. Check ffmpeg ────────────────────────────────────────────────
echo.
echo [5/10] Checking ffmpeg...

where ffmpeg >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [OK]   ffmpeg found
) else (
    echo [WARN] ffmpeg not found. Audio transcription will not work.
    echo [WARN] Install with:  winget install ffmpeg
    echo [WARN]   or download from https://ffmpeg.org/download.html
    set /a ERRORS+=1
)

REM ── 6. Check Ollama ───────────────────────────────────────────────
echo.
echo [6/10] Checking Ollama...

where ollama >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [OK]   Ollama found
) else (
    echo [WARN] Ollama not found. Local LLM summarization will not work.
    echo [WARN] Download from https://ollama.com/download
    set /a ERRORS+=1
)

REM ── 7. Pull default Ollama model ──────────────────────────────────
echo.
echo [7/10] Pulling default Ollama model...

where ollama >nul 2>&1
if %ERRORLEVEL% equ 0 (
    echo [INFO] Pulling llama3.2...
    ollama pull llama3.2
    if %ERRORLEVEL% equ 0 (
        echo [OK]   llama3.2 model ready
    ) else (
        echo [WARN] Could not pull llama3.2. Is Ollama running?
        set /a ERRORS+=1
    )
) else (
    echo [INFO] Skipping model pull ^(Ollama not installed^)
)

REM ── 8. Detect GPU ─────────────────────────────────────────────────
echo.
echo [8/10] Detecting GPU...

where nvidia-smi >nul 2>&1
if %ERRORLEVEL% equ 0 (
    for /f "tokens=*" %%i in ('nvidia-smi --query-gpu=name --format^=csv^,noheader 2^>nul') do (
        echo [OK]   NVIDIA GPU detected: %%i
    )
) else (
    echo [INFO] No NVIDIA GPU detected. Whisper will run on CPU.
)

REM ── 9. Generate config file ───────────────────────────────────────
echo.
echo [9/10] Generating config file...

set "CONFIG_FILE=%USERPROFILE%\.mediakit\config.toml"

if exist "%CONFIG_FILE%" (
    echo [INFO] Config already exists at %CONFIG_FILE% -- skipping
) else (
    echo [INFO] Running mediakit init...
    mediakit init
    if %ERRORLEVEL% equ 0 (
        echo [OK]   Config written
    ) else (
        echo [WARN] Could not generate config. Run 'mediakit init' manually.
        set /a ERRORS+=1
    )
)

REM ── 10. Run quick tests ───────────────────────────────────────────
echo.
echo [10/10] Running quick test suite...

if exist "tests" (
    echo [INFO] Running fast tests...
    python -m pytest tests/ -m "not slow and not network and not audio" -q --tb=short
    if %ERRORLEVEL% equ 0 (
        echo [OK]   Quick tests passed
    ) else (
        echo [WARN] Some tests failed
        set /a ERRORS+=1
    )
) else (
    echo [INFO] No tests directory found, skipping
)

REM ── Summary ────────────────────────────────────────────────────────
echo.
echo ----------------------------------------

if %ERRORS% equ 0 (
    echo   Setup completed successfully!
) else (
    echo   Setup completed with %ERRORS% warning^(s^).
)

echo ----------------------------------------
echo.
echo   Activate the environment:
echo     .venv\Scripts\activate
echo.
echo   Quick start:
echo     scrape https://example.com/blog-post
echo     transcribe https://youtube.com/watch?v=...
echo     summarize input.md
echo     crawl rss https://blog.example.com/feed
echo.
echo   Run tests:
echo     scripts\test.sh
echo.

endlocal
