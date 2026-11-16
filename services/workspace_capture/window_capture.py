"""
AeroSync Window Capture

Captures open window layouts and metadata using ctypes.windll.user32 and psutil.
Avoids the pywin32 dependency for easier installation.
"""

import ctypes
import ctypes.wintypes
import logging
from typing import List

import psutil

from shared.types.workspace_types import WindowState

logger = logging.getLogger(__name__)

# User32 Constants
GW_OWNER = 4
DWMWA_CLOAKED = 14

user32 = ctypes.windll.user32
dwmapi = ctypes.windll.dwmapi


def _is_window_visible(hwnd: int) -> bool:
    """Check if window is visible and not cloaked (Windows 10/11 invisible apps)."""
    if not user32.IsWindowVisible(hwnd):
        return False
        
    # Check if cloaked (e.g., on another virtual desktop or suspended)
    cloaked = ctypes.c_int(0)
    res = dwmapi.DwmGetWindowAttribute(
        hwnd, DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
    )
    if res == 0 and cloaked.value != 0:
        return False
        
    return True


def _get_window_text(hwnd: int) -> str:
    """Get the window title."""
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
        
    buff = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buff, length + 1)
    return buff.value


def _get_window_rect(hwnd: int) -> tuple:
    """Get the window bounding rectangle."""
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top)


def _get_process_id(hwnd: int) -> int:
    """Get the process ID owning the window."""
    pid = ctypes.c_ulong()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    return pid.value


def _get_window_class(hwnd: int) -> str:
    """Get the Win32 window class name."""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


async def capture_windows() -> List[WindowState]:
    """
    Enumerate all top-level windows and return their state.
    
    Returns:
        List of WindowState objects for all visible application windows.
    """
    windows: List[WindowState] = []
    z_order_counter = [0]  # mutable counter for enumeration order
    screen_w = user32.GetSystemMetrics(0) or 1920
    screen_h = user32.GetSystemMetrics(1) or 1080
    
    # Define the EnumWindows callback
    EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
    )
    
    def callback(hwnd, lparam):
        if not _is_window_visible(hwnd):
            return True
            
        # Ignore tool windows and child windows
        if user32.GetWindow(hwnd, GW_OWNER) != 0:
            return True
            
        title = _get_window_text(hwnd)
        if not title:
            return True
            
        # Ignore common system windows
        if title in ("Program Manager", "Settings", "Microsoft Text Input Application", "Windows Input Experience"):
            return True
            
        x, y, w, h = _get_window_rect(hwnd)
        if w == 0 or h == 0:
            return True
            
        pid = _get_process_id(hwnd)
        win_class = _get_window_class(hwnd)
        
        # Resolve process name and exe path using psutil
        proc_name = ""
        exe_path = ""
        try:
            proc = psutil.Process(pid)
            proc_name = proc.name()
            exe_path = proc.exe()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            proc_name = f"pid_{pid}"  # fallback if psutil fails
        
        # Screen division coordinates
        rel_x = round(x / screen_w, 4)
        rel_y = round(y / screen_h, 4)
        rel_w = round(w / screen_w, 4)
        rel_h = round(h / screen_h, 4)

        mid_x = x + w / 2
        mid_y = y + h / 2
        if rel_w >= 0.9 and rel_h >= 0.9:
            quadrant = "full"
        elif mid_x < screen_w / 2 and mid_y < screen_h / 2:
            quadrant = "top-left"
        elif mid_x >= screen_w / 2 and mid_y < screen_h / 2:
            quadrant = "top-right"
        elif mid_x < screen_w / 2 and mid_y >= screen_h / 2:
            quadrant = "bottom-left"
        else:
            quadrant = "bottom-right"

        state = WindowState(
            hwnd=hwnd,
            title=title,
            process_name=proc_name,
            exe_path=exe_path,
            window_class=win_class,
            z_order=z_order_counter[0],
            x=x,
            y=y,
            width=w,
            height=h,
            rel_x=rel_x,
            rel_y=rel_y,
            rel_width=rel_w,
            rel_height=rel_h,
            screen_width=screen_w,
            screen_height=screen_h,
            quadrant=quadrant,
            is_minimized=user32.IsIconic(hwnd) != 0,
            is_maximized=user32.IsZoomed(hwnd) != 0
        )
        windows.append(state)
        z_order_counter[0] += 1
        return True
        
    # Execute enumeration
    user32.EnumWindows(EnumWindowsProc(callback), 0)
    
    # Mark focused window
    fg_hwnd = user32.GetForegroundWindow()
    for win in windows:
        if win.hwnd == fg_hwnd:
            win.is_focused = True
            break
            
    logger.info(f"Captured {len(windows)} visible windows")
    return windows
