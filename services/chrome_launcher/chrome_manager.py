"""
AeroSync Chrome Manager

Provides automated detection, launching, and tab restoration for normal Google Chrome.
Handles:
  • Auto-detection of standard Google Chrome executable paths on Windows
  • Seamless launching of normal Chrome with URLs in a new or existing window
  • CDP remote debugging readiness check (port 9222)
  • Robust fallback when CDP is unavailable
"""

import asyncio
import json
import logging
import os
import subprocess
from typing import Any, Dict, List, Optional, Tuple

import httpx

from shared.constants import CHROME_CDP_URL_TEMPLATE

logger = logging.getLogger(__name__)

try:
    import websockets
    from websockets.sync.client import connect as ws_sync_connect
except ImportError:
    websockets = None
    ws_sync_connect = None

# Standard Google Chrome install locations on Windows
_STANDARD_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%PROGRAMFILES%\Google\Chrome\Application\chrome.exe"),
    os.path.expandvars(r"%PROGRAMFILES(X86)%\Google\Chrome\Application\chrome.exe"),
]


def find_chrome_executable() -> Optional[str]:
    """
    Locate the normal Google Chrome executable on this Windows machine.
    Checks standard paths and the Windows Registry.
    """
    for path in _STANDARD_CHROME_PATHS:
        if path and os.path.isfile(path):
            return path

    # Check Windows Registry App Paths
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths\chrome.exe"
        )
        val, _ = winreg.QueryValueEx(key, "")
        winreg.CloseKey(key)
        if val and os.path.isfile(val):
            return val
    except Exception:
        pass

    return None


async def is_cdp_available(port: int = 9222) -> bool:
    """Check if Chrome is actively running with CDP debugging port."""
    url = CHROME_CDP_URL_TEMPLATE.format(port=port).replace("/json", "/json/version")
    try:
        async with httpx.AsyncClient(timeout=1.5) as client:
            resp = await client.get(url)
            return resp.status_code == 200
    except Exception:
        return False


def launch_normal_chrome(
    urls: Optional[List[str]] = None,
    new_window: bool = True,
    debug_port: Optional[int] = None,
) -> bool:
    """
    Launch normal Google Chrome automatically and smoothly.
    
    Args:
        urls: Optional list of URLs to open.
        new_window: Whether to group these URLs in a fresh new window.
        debug_port: If provided, attempts to add --remote-debugging-port=<port>.
        
    Returns:
        True if successfully spawned, False otherwise.
    """
    chrome_exe = find_chrome_executable()
    urls = [u for u in (urls or []) if u and u.strip()]

    cmd = []
    if chrome_exe:
        cmd.append(chrome_exe)
    else:
        # Fallback to standard start command
        cmd.extend(["cmd", "/c", "start", "chrome"])

    if new_window:
        cmd.append("--new-window")

    if debug_port:
        cmd.append(f"--remote-debugging-port={debug_port}")

    if urls:
        cmd.extend(urls)

    try:
        logger.info("[ChromeManager] Auto-launching Chrome: %s", " ".join(cmd[:4]))
        subprocess.Popen(
            cmd,
            shell=False if chrome_exe else True,
            creationflags=subprocess.DETACHED_PROCESS if os.name == "nt" else 0,
        )
        return True
    except Exception as exc:
        logger.error("[ChromeManager] Failed to launch Chrome: %s", exc)
        return False


# ──────────────────────────────────────────────────────────────────────────────
# Browser Scroll Depth & Reading Position Preservation (CDP)
# ──────────────────────────────────────────────────────────────────────────────

_SCROLL_CAPTURE_JS = (
    "(() => {"
    "  try {"
    "    const top = window.scrollY || window.pageYOffset || (document.documentElement ? document.documentElement.scrollTop : 0) || 0;"
    "    const docH = Math.max("
    "      document.documentElement ? document.documentElement.scrollHeight : 0,"
    "      document.body ? document.body.scrollHeight : 0,"
    "      1"
    "    );"
    "    const winH = window.innerHeight || 1;"
    "    const maxScroll = Math.max(1, docH - winH);"
    "    const ratio = Math.min(1.0, Math.max(0.0, top / maxScroll));"
    "    return JSON.stringify({"
    "      scroll_y: Math.round(top),"
    "      scroll_ratio: Number(ratio.toFixed(4))"
    "    });"
    "  } catch (e) {"
    "    return JSON.stringify({ scroll_y: 0, scroll_ratio: 0.0 });"
    "  }"
    "})()"
)


def _build_scroll_restore_js(scroll_y: int, scroll_ratio: float) -> str:
    return f"""
    (() => {{
        const targetY = {int(scroll_y)};
        const targetRatio = {float(scroll_ratio)};
        function applyScroll() {{
            try {{
                const docH = Math.max(
                    document.documentElement ? document.documentElement.scrollHeight : 0,
                    document.body ? document.body.scrollHeight : 0,
                    1
                );
                const winH = window.innerHeight || 1;
                const maxScroll = Math.max(1, docH - winH);
                let y = targetY;
                if (targetRatio > 0 && maxScroll > 0) {{
                    const scaledY = Math.round(targetRatio * maxScroll);
                    y = Math.max(targetY, scaledY);
                }}
                window.scrollTo({{ top: y, behavior: 'instant' }});
            }} catch (e) {{}}
        }}
        if (document.readyState === 'complete') {{
            applyScroll();
        }} else {{
            window.addEventListener('DOMContentLoaded', applyScroll);
            window.addEventListener('load', applyScroll);
        }}
        setTimeout(applyScroll, 200);
        setTimeout(applyScroll, 750);
        setTimeout(applyScroll, 1600);
    }})();
    """


def fetch_tab_scroll(ws_url: Optional[str], timeout: float = 0.4) -> Tuple[int, float]:
    """
    Synchronously query Chrome DevTools Protocol via WebSocket to fetch:
    (scroll_y: int, scroll_ratio: float)
    Returns (0, 0.0) on any failure or if ws_sync_connect is unavailable.
    """
    if not ws_url or ws_sync_connect is None:
        return 0, 0.0

    cmd = {
        "id": 101,
        "method": "Runtime.evaluate",
        "params": {
            "expression": _SCROLL_CAPTURE_JS,
            "returnByValue": True,
        },
    }
    try:
        with ws_sync_connect(ws_url, open_timeout=timeout, close_timeout=timeout) as ws:
            ws.send(json.dumps(cmd))
            resp_raw = ws.recv(timeout=timeout)
            resp = json.loads(resp_raw)
            val = resp.get("result", {}).get("result", {}).get("value")
            if isinstance(val, str):
                parsed = json.loads(val)
                return int(parsed.get("scroll_y", 0)), float(parsed.get("scroll_ratio", 0.0))
            elif isinstance(val, dict):
                return int(val.get("scroll_y", 0)), float(val.get("scroll_ratio", 0.0))
    except Exception as exc:
        logger.debug("[ChromeManager] fetch_tab_scroll exception (%s): %s", ws_url, exc)
    return 0, 0.0


async def async_fetch_tab_scroll(ws_url: Optional[str], timeout: float = 0.5) -> Tuple[int, float]:
    """
    Asynchronously query Chrome DevTools Protocol via WebSocket to fetch:
    (scroll_y: int, scroll_ratio: float)
    """
    if not ws_url or websockets is None:
        return 0, 0.0

    cmd = {
        "id": 101,
        "method": "Runtime.evaluate",
        "params": {
            "expression": _SCROLL_CAPTURE_JS,
            "returnByValue": True,
        },
    }
    try:
        async with websockets.connect(ws_url, open_timeout=timeout, close_timeout=timeout) as ws:
            await ws.send(json.dumps(cmd))
            resp_raw = await asyncio.wait_for(ws.recv(), timeout=timeout)
            resp = json.loads(resp_raw)
            val = resp.get("result", {}).get("result", {}).get("value")
            if isinstance(val, str):
                parsed = json.loads(val)
                return int(parsed.get("scroll_y", 0)), float(parsed.get("scroll_ratio", 0.0))
            elif isinstance(val, dict):
                return int(val.get("scroll_y", 0)), float(val.get("scroll_ratio", 0.0))
    except Exception as exc:
        logger.debug("[ChromeManager] async_fetch_tab_scroll exception (%s): %s", ws_url, exc)
    return 0, 0.0


def restore_tab_scroll(
    ws_url: str,
    scroll_y: int,
    scroll_ratio: float = 0.0,
    timeout: float = 1.0,
) -> bool:
    """
    Synchronously inject scroll restoration scripts into the target tab via CDP.
    Uses Page.addScriptToEvaluateOnNewDocument and Runtime.evaluate.
    """
    if not ws_url or ws_sync_connect is None:
        return False
    if scroll_y <= 0 and scroll_ratio <= 0.0:
        return True

    js_code = _build_scroll_restore_js(scroll_y, scroll_ratio)
    preload_cmd = {
        "id": 201,
        "method": "Page.addScriptToEvaluateOnNewDocument",
        "params": {"source": js_code},
    }
    eval_cmd = {
        "id": 202,
        "method": "Runtime.evaluate",
        "params": {"expression": js_code, "returnByValue": False},
    }
    try:
        with ws_sync_connect(ws_url, open_timeout=timeout, close_timeout=timeout) as ws:
            ws.send(json.dumps(preload_cmd))
            ws.send(json.dumps(eval_cmd))
            return True
    except Exception as exc:
        logger.debug("[ChromeManager] restore_tab_scroll failed (%s): %s", ws_url, exc)
        return False


async def async_restore_tab_scroll(
    ws_url: str,
    scroll_y: int,
    scroll_ratio: float = 0.0,
    timeout: float = 1.2,
) -> bool:
    """
    Asynchronously inject scroll restoration scripts into the target tab via CDP.
    """
    if not ws_url or websockets is None:
        return False
    if scroll_y <= 0 and scroll_ratio <= 0.0:
        return True

    js_code = _build_scroll_restore_js(scroll_y, scroll_ratio)
    preload_cmd = {
        "id": 201,
        "method": "Page.addScriptToEvaluateOnNewDocument",
        "params": {"source": js_code},
    }
    eval_cmd = {
        "id": 202,
        "method": "Runtime.evaluate",
        "params": {"expression": js_code, "returnByValue": False},
    }
    try:
        async with websockets.connect(ws_url, open_timeout=timeout, close_timeout=timeout) as ws:
            await ws.send(json.dumps(preload_cmd))
            await ws.send(json.dumps(eval_cmd))
            return True
    except Exception as exc:
        logger.debug("[ChromeManager] async_restore_tab_scroll failed (%s): %s", ws_url, exc)
        return False


def open_tab_with_scroll(
    url: str,
    scroll_y: int = 0,
    scroll_ratio: float = 0.0,
    port: int = 9222,
) -> bool:
    """
    Open a single URL in Chrome with reading scroll depth restored.
    Tries CDP on `port` first. If CDP is inactive, falls back to normal launch.
    """
    if not url or not url.strip():
        return False

    cdp_base = CHROME_CDP_URL_TEMPLATE.format(port=port).replace("/json", "")
    try:
        resp = httpx.put(f"{cdp_base}/json/new?{url}", timeout=2.0)
        if resp.status_code in (200, 201):
            tab_data = resp.json()
            ws_url = tab_data.get("webSocketDebuggerUrl")
            if ws_url and (scroll_y > 0 or scroll_ratio > 0.0):
                restore_tab_scroll(ws_url, scroll_y, scroll_ratio)
            return True
    except Exception:
        pass

    # Fallback to standard launch
    return launch_normal_chrome([url], new_window=False)


async def open_tabs_with_scroll(
    tabs_data: List[Dict[str, Any]],
    port: int = 9222,
) -> Tuple[List[str], List[str]]:
    """
    Open multiple tabs and restore their reading positions on Target B.
    
    Args:
        tabs_data: List of dicts with keys: 'url', optional 'scroll_y', optional 'scroll_ratio'.
        port: CDP port to attempt.
        
    Returns:
        (opened_urls, failed_urls)
    """
    if not tabs_data:
        return [], []

    opened_urls: List[str] = []
    failed_urls: List[str] = []

    cdp_available = await is_cdp_available(port)
    if cdp_available:
        cdp_base = CHROME_CDP_URL_TEMPLATE.format(port=port).replace("/json", "")
        async with httpx.AsyncClient(timeout=2.5) as client:
            for item in tabs_data:
                url = item.get("url", "").strip()
                if not url:
                    continue
                scroll_y = int(item.get("scroll_y", 0))
                scroll_ratio = float(item.get("scroll_ratio", 0.0))
                try:
                    res = await client.put(f"{cdp_base}/json/new?{url}")
                    if res.status_code in (200, 201):
                        tab_info = res.json()
                        ws_url = tab_info.get("webSocketDebuggerUrl")
                        if ws_url and (scroll_y > 0 or scroll_ratio > 0.0):
                            await async_restore_tab_scroll(ws_url, scroll_y, scroll_ratio)
                        opened_urls.append(url)
                    else:
                        failed_urls.append(url)
                except Exception as exc:
                    logger.warning("[ChromeManager] Failed to open tab via CDP: %s (%s)", url, exc)
                    failed_urls.append(url)
    else:
        # Fallback to normal Chrome auto-launcher
        urls = [item.get("url", "").strip() for item in tabs_data if item.get("url", "").strip()]
        if urls:
            ok = launch_normal_chrome(urls, new_window=True)
            if ok:
                opened_urls.extend(urls)
            else:
                failed_urls.extend(urls)

    return opened_urls, failed_urls
