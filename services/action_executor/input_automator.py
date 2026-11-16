"""
AeroSync Input Automator

Types text into the active window or finds a window by title and types into it.
Uses pyautogui for keystrokes and ctypes/win32 to find and focus windows.

Windows-only. No cross-OS support.
"""

import logging
import time
from typing import Optional

import ctypes
import ctypes.wintypes

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32


def _find_window_by_title(title_hint: str) -> Optional[int]:
    """
    Find a window whose title contains title_hint (case-insensitive).

    Returns:
        HWND (int) if found, None otherwise.
    """
    title_hint_lower = title_hint.lower()
    found_hwnd = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def enum_callback(hwnd, lParam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buf = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buf, length + 1)
            if title_hint_lower in buf.value.lower():
                found_hwnd.append(hwnd)
        return True

    user32.EnumWindows(enum_callback, 0)
    return found_hwnd[0] if found_hwnd else None


def _focus_window(hwnd: int) -> bool:
    """Bring a window to foreground and focus it."""
    try:
        # Restore if minimised
        user32.ShowWindow(hwnd, 9)   # SW_RESTORE = 9
        time.sleep(0.3)
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        time.sleep(0.3)
        return True
    except Exception as e:
        logger.warning(f"Failed to focus window {hwnd}: {e}")
        return False


def type_into_active_window(text: str, interval: float = 0.02) -> bool:
    """
    Type text into whichever window is currently focused.

    Args:
        text:     Text to type.
        interval: Delay between keystrokes in seconds.

    Returns:
        True on success, False on failure.
    """
    try:
        import pyautogui
        pyautogui.FAILSAFE = False
        # Click the current window to ensure focus
        pyautogui.click()
        time.sleep(0.2)

        # pyautogui.typewrite doesn't handle Unicode well — use write() for ASCII
        # and pyperclip + paste for Unicode/special chars
        import pyperclip
        pyperclip.copy(text)
        pyautogui.hotkey("ctrl", "v")
        logger.info(f"Pasted {len(text)} chars into active window via clipboard.")
        return True
    except Exception as e:
        logger.error(f"Failed to type into active window: {e}")
        return False


def open_app_and_type(app_title_hint: str, content: str) -> bool:
    """
    Find a running window matching app_title_hint, focus it, then type content.

    Args:
        app_title_hint: Part of the window title to search for.
        content:        Text to type into the focused window.

    Returns:
        True on success, False on failure.
    """
    hwnd = _find_window_by_title(app_title_hint)
    if not hwnd:
        logger.warning(
            f"No window found matching '{app_title_hint}'. "
            "Typing into currently active window instead."
        )
        return type_into_active_window(content)

    if not _focus_window(hwnd):
        logger.warning("Could not focus target window.")
        return False

    return type_into_active_window(content)
