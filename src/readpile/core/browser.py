"""Browser dependency helpers."""

from __future__ import annotations

from playwright.async_api import Error as PlaywrightError


async def launch_chromium(pw, **kwargs):
    """Launch Chromium, raising a clear error if the browser binary is missing."""
    try:
        args = list(kwargs.pop("args", []))
        args.append("--disable-gpu")
        return await pw.chromium.launch(args=args, **kwargs)
    except PlaywrightError as exc:
        if "Executable doesn't exist" in str(exc):
            raise SystemExit(
                "Chromium browser binary not found.\n"
                "Run this command to install it:\n\n"
                "  python -m playwright install chromium\n"
            ) from exc
        raise


async def launch_persistent_chromium(pw, user_data_dir: str, **kwargs):
    """Launch a persistent Chromium context, raising a clear error if the browser binary is missing."""
    try:
        args = list(kwargs.pop("args", []))
        args.append("--disable-gpu")
        return await pw.chromium.launch_persistent_context(
            user_data_dir=user_data_dir, args=args, **kwargs
        )
    except PlaywrightError as exc:
        if "Executable doesn't exist" in str(exc):
            raise SystemExit(
                "Chromium browser binary not found.\n"
                "Run this command to install it:\n\n"
                "  python -m playwright install chromium\n"
            ) from exc
        raise
