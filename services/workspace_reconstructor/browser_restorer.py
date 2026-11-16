"""
AeroSync Browser Restorer

Restores browser tabs on the target device.
Smart deduplication: checks tabs already open on B before opening new ones.
Uses Chrome CDP if available, otherwise falls back to subprocess to launch Chrome.
"""

import httpx
import logging
import subprocess
from typing import List, Optional, Set, Tuple

from shared.types.workspace_types import BrowserState
from shared.constants import CHROME_CDP_URL_TEMPLATE

logger = logging.getLogger(__name__)

_CDP_PORTS = [9222, 9223]


async def _get_existing_tabs(port: int = 9222) -> Set[str]:
    """
    Query CDP for URLs already open in the browser on this machine.
    Returns a set of open URLs (normalized, lowercased without trailing slash).
    """
    existing: Set[str] = set()
    for p in _CDP_PORTS:
        try:
            url = CHROME_CDP_URL_TEMPLATE.format(port=p)
            async with httpx.AsyncClient(timeout=1.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    for tab in resp.json():
                        tab_url = tab.get("url", "")
                        if tab_url and not tab_url.startswith("devtools://") and not tab_url.startswith("chrome://"):
                            existing.add(tab_url.rstrip("/"))
        except Exception:
            pass
    return existing


async def restore_browsers(
    browsers: List[BrowserState],
    already_opened_urls: Optional[Set[str]] = None,
    port: int = 9222,
) -> Tuple[List[str], List[str], List[str]]:
    """
    Restore browser windows and tabs.
    
    Skips tabs that are already open on B (smart dedup).
    
    Args:
        browsers: List of BrowserState objects to restore.
        already_opened_urls: URLs already opened by log stack replay (skip these).
        port: The Chrome DevTools Protocol port.
        
    Returns:
        Tuple of (successful_urls, failed_urls, reused_urls)
        - successful_urls: tabs newly opened
        - failed_urls: tabs that failed to open
        - reused_urls: tabs already present on B (skipped/reused)
    """
    if already_opened_urls is None:
        already_opened_urls = set()

    if not browsers:
        return [], [], []
        
    successful_urls: List[str] = []
    failed_urls: List[str] = []
    reused_urls: List[str] = []

    # Get tabs currently open on B
    existing_on_b = await _get_existing_tabs()
    # Merge with already_opened_urls from log replay
    all_skip = existing_on_b | {u.rstrip("/") for u in already_opened_urls}

    # First check if CDP is available
    cdp_url = CHROME_CDP_URL_TEMPLATE.format(port=port).replace("/json", "/json/version")
    cdp_available = False
    
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            resp = await client.get(cdp_url)
            if resp.status_code == 200:
                cdp_available = True
    except Exception:
        pass
        
    if cdp_available:
        base_url = CHROME_CDP_URL_TEMPLATE.format(port=port).replace("/json", "")
        async with httpx.AsyncClient() as client:
            for browser in browsers:
                for tab in browser.tabs:
                    url_norm = tab.url.rstrip("/")
                    if url_norm in all_skip:
                        reused_urls.append(tab.url)
                        logger.debug("Skipping already-open tab: %s", tab.url)
                        continue
                    try:
                        create_url = f"{base_url}/json/new?{tab.url}"
                        res = await client.put(create_url)
                        res.raise_for_status()
                        successful_urls.append(tab.url)
                        all_skip.add(url_norm)
                    except Exception as e:
                        logger.warning("Failed to open %s via CDP: %s", tab.url, e)
                        failed_urls.append(tab.url)
    else:
        # Fallback: open via normal Chrome auto-launcher
        logger.info("[BrowserRestorer] CDP not running, auto-launching via ChromeManager")
        from services.chrome_launcher.chrome_manager import launch_normal_chrome
        for browser in browsers:
            urls_to_open = []
            for tab in browser.tabs:
                url_norm = tab.url.rstrip("/")
                if url_norm in all_skip:
                    reused_urls.append(tab.url)
                    continue
                urls_to_open.append(tab.url)
            if not urls_to_open:
                continue
            ok = launch_normal_chrome(urls_to_open, new_window=True)
            if ok:
                successful_urls.extend(urls_to_open)
            else:
                logger.error("[BrowserRestorer] Failed to launch Chrome with URLs: %s", urls_to_open)
                failed_urls.extend(urls_to_open)
                
    return successful_urls, failed_urls, reused_urls
