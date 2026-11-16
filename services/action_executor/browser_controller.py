"""
AeroSync Browser Controller

Opens Chrome (or the system default browser) with a URL or a Google search query.
Uses subprocess + Windows shell to open URLs, so Chrome does not need to be
running with --remote-debugging-port.

Windows-only. No cross-OS support.
"""

import logging
import subprocess
import urllib.parse
from typing import Optional

logger = logging.getLogger(__name__)


def open_url(url: str) -> None:
    """
    Open a URL in Chrome (or the default browser if Chrome isn't found).

    Args:
        url: Full URL to open (e.g. "https://example.com").
    """
    # Ensure URL has a scheme
    if not url.startswith(("http://", "https://")):
        url = "https://" + url

    logger.info(f"Opening URL in browser: {url}")
    _launch_url(url)


def open_browser_search(query: str) -> None:
    """
    Open Chrome with a Google search for the given query.

    Args:
        query: Search query string.
    """
    encoded = urllib.parse.quote(query)
    search_url = f"https://www.google.com/search?q={encoded}"
    logger.info(f"Opening browser search: {query!r}")
    _launch_url(search_url)


def _launch_url(url: str) -> None:
    """
    Try to open the URL with Chrome first, then fall back to system default.
    Uses Windows `start` shell command which is safe and doesn't block.
    """
    chrome_paths = [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    ]

    for chrome_path in chrome_paths:
        try:
            import os
            if os.path.exists(chrome_path):
                subprocess.Popen(
                    [chrome_path, "--new-tab", url],
                    creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
                )
                logger.debug(f"Opened with Chrome: {chrome_path}")
                return
        except Exception as e:
            logger.warning(f"Failed to open with {chrome_path}: {e}")

    # Fall back to Windows shell start command (uses default browser)
    try:
        subprocess.Popen(
            ["cmd", "/c", "start", "", url],
            creationflags=subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP,
            shell=False,
        )
        logger.debug("Opened with Windows default browser via start command.")
    except Exception as e:
        raise RuntimeError(f"All browser open attempts failed for URL: {url}") from e
