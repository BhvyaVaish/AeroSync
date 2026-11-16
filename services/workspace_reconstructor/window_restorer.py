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


def _reposition_window(
    hwnd: int,
    win: WindowState,
    target_monitors: Optional[List[Any]] = None,
) -> bool:
    """
    Apply position/state from WindowState to the given hwnd.
    Smart Multi-Monitor & DPI mapping:
      • Uses compute_target_window_rect to map across multi-to-single or multi-to-multi monitor setups
      • Handles per-monitor DPI scaling without distortion
      • Clamps strictly within target monitor boundaries
    """
    try:
        if win.is_maximized:
            user32.ShowWindow(hwnd, SW_MAXIMIZE)
            return True
        elif win.is_minimized:
            user32.ShowWindow(hwnd, SW_MINIMIZE)
            return True

        user32.ShowWindow(hwnd, SW_RESTORE)

        if target_monitors is None:
            target_screen_w = user32.GetSystemMetrics(0) or 1920
            target_screen_h = user32.GetSystemMetrics(1) or 1080
            from services.monitor_mapping.monitor_mapper import get_monitors
            from shared.types.workspace_types import MonitorInfo
            real_mons = get_monitors()
            if real_mons and (real_mons[0].width != target_screen_w or real_mons[0].height != target_screen_h):
                target_monitors = [
                    MonitorInfo(
                        monitor_index=0,
                        x=0,
                        y=0,
                        width=target_screen_w,
                        height=target_screen_h,
                        is_primary=True,
                        dpi=real_mons[0].dpi,
                        dpi_scale=real_mons[0].dpi_scale,
                    )
                ]
            else:
                target_monitors = real_mons

        from services.monitor_mapping.monitor_mapper import compute_target_window_rect
        dest_x, dest_y, dest_w, dest_h = compute_target_window_rect(win, target_monitors=target_monitors)

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
    target_monitors: Optional[List[Any]] = None,
) -> Tuple[int, List[str], List[str]]:
    """
    Restore window positions on Target B.

    For each WindowState from Host A:
      1. Find matching window on B using smart matching.
      2. If found → reposition/reorient it using multi-monitor & DPI mapping (reuse existing window).
      3. If not found → record as failed.

    Args:
        windows: List of WindowState objects from Host A snapshot.
        target_monitors: Optional list of target MonitorInfo objects (defaults to local monitors).

    Returns:
        (success_count, repositioned_titles, failed_titles)
    """
    repositioned: List[str] = []
    failed: List[str] = []

    if target_monitors is None:
        from services.monitor_mapping.monitor_mapper import get_monitors
        target_monitors = get_monitors()

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
            ok = _reposition_window(hwnd, win, target_monitors=target_monitors)
            if ok:
                repositioned.append(win.title)
                logger.debug("Repositioned window with multi-monitor mapping: %s", win.title)
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
