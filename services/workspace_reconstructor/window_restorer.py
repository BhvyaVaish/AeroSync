"""
AeroSync Window Restorer

Repositions and resizes windows on the target device to match
the source device's layout as closely as possible.

Smart reuse: if a window is already open on B, reposition it
instead of trying to launch a new instance.
"""

import ctypes
import ctypes.wintypes
import logging
from typing import Dict, List, Optional, Tuple

from shared.types.workspace_types import WindowState

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32

# Constants for SetWindowPos / ShowWindow
SWP_NOZORDER   = 0x0004
SWP_NOACTIVATE = 0x0010
SW_RESTORE     = 9
SW_MINIMIZE    = 6
SW_MAXIMIZE    = 3


def _find_window_smart(
    title: str,
    process_name: str = "",
    window_class: str = "",
) -> Tuple[int, bool]:
    """
    Find a window on the current machine matching the given attributes.
    
    Matching priority:
      1. Exact title match
      2. Partial title match (len > 5)
      3. Window-class match (if provided)
      
    Returns:
        (hwnd, was_found) — hwnd=0 if not found.
    """
    candidates: Dict[int, int] = {}

    EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
    )

    def callback(hwnd, lparam):
        length = user32.GetWindowTextLengthW(hwnd)
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            window_title = buff.value

            score = 0
            if title and title == window_title:
                score = 100  # exact title match
            elif title and len(title) > 5 and title in window_title:
                score = 60   # partial title match
            elif title and len(window_title) > 5 and window_title in title:
                score = 40   # reverse partial match

            if window_class:
                cls_buf = ctypes.create_unicode_buffer(256)
                user32.GetClassNameW(hwnd, cls_buf, 256)
                if cls_buf.value == window_class:
                    score += 20  # bonus for class match

            if score > 0:
                candidates[hwnd] = max(candidates.get(hwnd, 0), score)
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)

    if not candidates:
        return 0, False

    best_hwnd = max(candidates, key=lambda h: candidates[h])
    return best_hwnd, True


def _find_window_by_process(process_name: str, exe_path: str = "") -> int:
    """
    Find any visible window belonging to the given process.
    Used as a fallback when title matching fails.
    """
    import psutil
    target_pids: set = set()
    pname_lower = process_name.lower()
    exe_lower = exe_path.lower() if exe_path else ""

    for proc in psutil.process_iter(["pid", "name", "exe"]):
        try:
            name = (proc.info.get("name") or "").lower()
            exe = (proc.info.get("exe") or "").lower()
            if name == pname_lower or (exe_lower and exe == exe_lower):
                target_pids.add(proc.info["pid"])
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    if not target_pids:
        return 0

    found_hwnd = [0]

    EnumWindowsProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM
    )

    def callback(hwnd, lparam):
        if found_hwnd[0]:
            return False
        pid_buf = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_buf))
        if pid_buf.value in target_pids and user32.IsWindowVisible(hwnd):
            found_hwnd[0] = hwnd
            return False
        return True

    user32.EnumWindows(EnumWindowsProc(callback), 0)
    return found_hwnd[0]


def _reposition_window(hwnd: int, win: WindowState) -> bool:
    """
    Apply position/state from WindowState to the given hwnd.
    Smart coordinate mapping:
      If Target B has a different screen resolution from Host A,
      maps proportional divided screen coordinates (rel_x, rel_y, rel_width, rel_height)
      so the window is placed at the exact corresponding relative position & quadrant.
      If resolutions match, uses exact pixel coordinates.
    """
    try:
        if win.is_maximized:
            user32.ShowWindow(hwnd, SW_MAXIMIZE)
            return True
        elif win.is_minimized:
            user32.ShowWindow(hwnd, SW_MINIMIZE)
            return True

        user32.ShowWindow(hwnd, SW_RESTORE)

        target_screen_w = user32.GetSystemMetrics(0) or 1920
        target_screen_h = user32.GetSystemMetrics(1) or 1080

        # Check if proportional mapping is appropriate
        has_proportional = (
            getattr(win, "rel_width", 0.0) > 0 and getattr(win, "rel_height", 0.0) > 0
        )
        has_diff_res = (
            getattr(win, "screen_width", 0) > 0
            and getattr(win, "screen_height", 0) > 0
            and (win.screen_width != target_screen_w or win.screen_height != target_screen_h)
        )

        if has_proportional and has_diff_res:
            dest_w = max(150, int(win.rel_width * target_screen_w))
            dest_h = max(100, int(win.rel_height * target_screen_h))
            dest_x = int(win.rel_x * target_screen_w)
            dest_y = int(win.rel_y * target_screen_h)
            dest_x = max(0, min(dest_x, target_screen_w - dest_w))
            dest_y = max(0, min(dest_y, target_screen_h - dest_h))
        else:
            dest_x = win.x
            dest_y = win.y
            dest_w = win.width
            dest_h = win.height

        user32.SetWindowPos(
            hwnd,
            0,  # HWND_TOP placeholder, ignored by SWP_NOZORDER
            dest_x,
            dest_y,
            dest_w,
            dest_h,
            SWP_NOZORDER | SWP_NOACTIVATE,
        )
        return True
    except Exception as exc:
        logger.warning("Failed to reposition window '%s': %s", win.title, exc)
        return False


async def restore_windows(
    windows: List[WindowState],
) -> Tuple[int, List[str], List[str]]:
    """
    Restore window positions on Target B.

    For each WindowState from Host A:
      1. Find matching window on B using smart matching.
      2. If found → reposition/reorient it (reuse existing window).
      3. If not found → record as failed.

    Args:
        windows: List of WindowState objects from Host A snapshot.

    Returns:
        (success_count, repositioned_titles, failed_titles)
    """
    repositioned: List[str] = []
    failed: List[str] = []

    for win in windows:
        hwnd, found = _find_window_smart(
            title=win.title,
            process_name=win.process_name,
            window_class=win.window_class,
        )

        if not found:
            # Fallback: search by process name
            hwnd = _find_window_by_process(win.process_name, win.exe_path or "")
            found = hwnd != 0

        if found and hwnd:
            ok = _reposition_window(hwnd, win)
            if ok:
                repositioned.append(win.title)
                logger.debug("Repositioned window: %s", win.title)
            else:
                failed.append(win.title)
        else:
            logger.debug("Could not find window on B: %s", win.title)
            failed.append(win.title)

    logger.info(
        "Window restore: %d repositioned, %d not found",
        len(repositioned), len(failed),
    )
    return len(repositioned), repositioned, failed
