"""Playwright browser helpers for JS-rendered career pages."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_PLAYWRIGHT_AVAILABLE = False
try:
    from playwright.sync_api import sync_playwright  # noqa: F401

    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    pass


def is_browser_available() -> bool:
    return _PLAYWRIGHT_AVAILABLE


def fetch_rendered_html(
    url: str,
    wait_selector: str | None = None,
    timeout_ms: int = 15000,
) -> str:
    """Launch a headless browser, navigate to URL, and return rendered HTML.

    Each call creates its own browser instance for thread safety.
    Returns empty string if playwright is not installed or rendering fails.
    """
    if not _PLAYWRIGHT_AVAILABLE:
        return ""

    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                context = browser.new_context(
                    user_agent=(
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    ),
                    viewport={"width": 1280, "height": 800},
                )
                page = context.new_page()
                try:
                    page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)

                    if wait_selector:
                        try:
                            page.wait_for_selector(wait_selector, timeout=timeout_ms)
                        except Exception:
                            pass
                    else:
                        try:
                            page.wait_for_load_state("networkidle", timeout=timeout_ms)
                        except Exception:
                            pass

                    return page.content()
                finally:
                    page.close()
                    context.close()
            finally:
                browser.close()
    except Exception as exc:
        logger.info("Browser rendering failed for %s: %s", url, exc)
        return ""
