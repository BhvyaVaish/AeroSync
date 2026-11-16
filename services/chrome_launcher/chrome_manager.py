"""
AeroSync Chrome Manager

Provides automated detection, launching, and tab restoration for normal Google Chrome.
Handles:
  • Auto-detection of standard Google Chrome executable paths on Windows
  • Seamless launching of normal Chrome with URLs in a new or existing window
  • CDP remote debugging readiness check (port 9222)
  • Robust fallback when CDP is unavailable
"""

import logging
import os
import subprocess
from typing import List, Optional

import httpx

from shared.constants import CHROME_CDP_URL_TEMPLATE

logger = logging.getLogger(__name__)

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
