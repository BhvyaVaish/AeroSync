"""
AeroSync Browser Capture

Captures browser tabs via Chrome DevTools Protocol (CDP).
Requires Chrome to be launched with --remote-debugging-port=9222
"""

import httpx
import logging
from typing import List, Dict

from shared.types.workspace_types import BrowserState, TabInfo
from shared.constants import CHROME_CDP_URL_TEMPLATE

logger = logging.getLogger(__name__)


async def capture_browser_state(port: int = 9222) -> List[BrowserState]:
    """
    Connect to Chrome DevTools Protocol to capture all open tabs.
    
    Groups tabs by their internal window ID (if available, otherwise assumes one window).
    
    Args:
        port: The Chrome DevTools Protocol port.
        
    Returns:
        List of BrowserState objects, representing each open Chrome window.
    """
    url = CHROME_CDP_URL_TEMPLATE.format(port=port)
    
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            tabs_data = response.json()
    except httpx.RequestError as e:
        logger.warning(f"Could not connect to Chrome DevTools Protocol on port {port}: {e}")
        return []
    except Exception as e:
        logger.warning(f"Failed to parse Chrome DevTools Protocol response: {e}")
        return []
        
    # CDP returns a flat list of targets (tabs, extensions, background pages, etc.)
    # We only care about targets of type "page" that are not extensions.
    
    windows: Dict[str, BrowserState] = {}
    
    for item in tabs_data:
        if item.get("type") != "page":
            continue
            
        url_str = item.get("url", "")
        if url_str.startswith("chrome-extension://") or url_str.startswith("devtools://"):
            continue

        ws_url = item.get("webSocketDebuggerUrl")
        scroll_y = 0
        scroll_ratio = 0.0
        if ws_url:
            try:
                from services.chrome_launcher.chrome_manager import async_fetch_tab_scroll
                scroll_y, scroll_ratio = await async_fetch_tab_scroll(ws_url, timeout=0.4)
            except Exception:
                pass

        tab = TabInfo(
            url=url_str,
            title=item.get("title", ""),
            tab_id=item.get("id"),
            favicon_url=item.get("faviconUrl"),
            scroll_y=scroll_y,
            scroll_ratio=scroll_ratio,
        )
        
        # Chrome CDP doesn't directly expose the window ID via the simple /json endpoint
        # To keep it simple and fast without a full WebSocket attachment,
        # we'll group all tabs into a single default window for MVP.
        # In a production app, we would attach via WebSocket to target `Browser.getWindowForTarget`
        window_id = "default_window"
        tab.window_id = window_id
        
        if window_id not in windows:
            windows[window_id] = BrowserState(
                browser_type="chrome",
                window_id=window_id,
                tabs=[]
            )
            
        windows[window_id].tabs.append(tab)
        
    # Mark the first tab as active for now (again, /json doesn't expose active state directly)
    # A robust implementation would use CDP WebSocket.
    for win in windows.values():
        if win.tabs:
            win.tabs[0].is_active = True
            
    return list(windows.values())
