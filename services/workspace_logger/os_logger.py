"""
AeroSync Workspace Logger — OS Logger

Polls the Windows OS at ~1 Hz and pushes live-state artefacts onto a
WorkspaceLogQueue.  Uses only APIs the OS allows; OCR handles the rest.

Captured by this module (do NOT also capture via OCR):
  • Running desktop application windows (title + geometry + exe_path + class)
  • Active Chrome / Edge browser tabs via CDP (port 9222 / 9223)
  • Clipboard text snapshot
  • Foreground window identity + app text content (WM_GETTEXT, capped 10 KB)
  • Process list (name + PID + exe path) — incremental every cycle
  • Window z-order (enumeration index = topmost-first)

Deduplication:
  Each item is diffed against the previous snapshot so only *changes* are
  pushed (new windows, new tabs, clipboard change).  Unchanged items stay
  on the queue from the previous cycle.
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import threading
import time
from typing import Dict, List, Optional, Set

import httpx
import pyperclip
import psutil

from services.workspace_logger.log_stack import (
    LogEntry,
    LogEntryType,
    WorkspaceLogQueue,
)
from shared.constants import CHROME_CDP_URL_TEMPLATE

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────────────────────
# Win32 helpers
# ──────────────────────────────────────────────────────────────────────────────

user32 = ctypes.windll.user32  # type: ignore[attr-defined]

WM_GETTEXT       = 0x000D
WM_GETTEXTLENGTH = 0x000E
_APP_TEXT_CAP    = 10_240  # 10 KB max per window


def _get_window_title(hwnd: int) -> str:
    length = user32.GetWindowTextLengthW(hwnd)
    if length == 0:
        return ""
    buf = ctypes.create_unicode_buffer(length + 1)
    user32.GetWindowTextW(hwnd, buf, length + 1)
    return buf.value


def _get_window_rect(hwnd: int) -> Optional[Dict[str, int]]:
    rect = ctypes.wintypes.RECT()
    if user32.GetWindowRect(hwnd, ctypes.byref(rect)):
        return {"left": rect.left, "top": rect.top, "right": rect.right, "bottom": rect.bottom}
    return None


def _get_window_class(hwnd: int) -> str:
    """Return the Win32 class name of a window (e.g. 'Notepad', 'Chrome_WidgetWin_1')."""
    buf = ctypes.create_unicode_buffer(256)
    user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def _get_exe_path(pid: int) -> str:
    """Return full path to the executable owning this PID, or '' on failure."""
    try:
        return psutil.Process(pid).exe()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return ""


def _get_app_text_content(hwnd: int) -> str:
    """
    Attempt to extract text content from a window via WM_GETTEXT.
    Works well for simple editors (Notepad, WordPad).
    Caps at _APP_TEXT_CAP characters.
    Returns empty string on any failure.
    """
    try:
        length = user32.SendMessageW(hwnd, WM_GETTEXTLENGTH, 0, 0)
        if not length or length <= 0:
            return ""
        cap = min(length + 1, _APP_TEXT_CAP + 1)
        buf = ctypes.create_unicode_buffer(cap)
        copied = user32.SendMessageW(hwnd, WM_GETTEXT, cap, buf)
        if copied > 0:
            return buf.value[:_APP_TEXT_CAP]
    except Exception:
        pass
    return ""


def _is_visible_window(hwnd: int) -> bool:
    if not user32.IsWindowVisible(hwnd):
        return False
    title = _get_window_title(hwnd)
    if not title or title.strip() == "":
        return False
    skip = {"Program Manager", "Windows Input Experience", "Microsoft Text Input Application"}
    return title not in skip


def _enum_visible_windows() -> List[Dict]:
    """Return list of dicts for every visible top-level window, with z-order index and divided screen coordinates."""
    results: List[Dict] = []
    fg_hwnd = user32.GetForegroundWindow()
    from services.monitor_mapping.monitor_mapper import (
        get_monitors,
        find_monitor_for_rect,
        compute_divided_coordinates,
    )
    monitors = get_monitors()

    @ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)
    def _callback(hwnd: int, _: int) -> bool:
        if _is_visible_window(hwnd):
            title = _get_window_title(hwnd)
            rect = _get_window_rect(hwnd)
            pid_buf = ctypes.wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_buf))
            pid = pid_buf.value
            proc_name = ""
            exe_path = ""
            try:
                proc = psutil.Process(pid)
                proc_name = proc.name()
                exe_path = proc.exe()
            except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                pass
            win_class = _get_window_class(hwnd)
            z_order = len(results)  # enumeration order = z-order (topmost first)
            is_fg = (hwnd == fg_hwnd)

            # Enhanced multi-monitor & DPI normalized coordinates
            enriched_rect = None
            mon_idx = 0
            win_dpi = 96
            if rect:
                w = max(1, rect["right"] - rect["left"])
                h = max(1, rect["bottom"] - rect["top"])
                mon_idx, mon = find_monitor_for_rect(rect["left"], rect["top"], w, h, monitors)
                div = compute_divided_coordinates(rect["left"], rect["top"], w, h, mon)
                win_dpi = mon.dpi
                enriched_rect = {
                    **rect,
                    "width": w,
                    "height": h,
                    "rel_x": div["rel_x"],
                    "rel_y": div["rel_y"],
                    "rel_width": div["rel_width"],
                    "rel_height": div["rel_height"],
                    "screen_width": div["screen_width"],
                    "screen_height": div["screen_height"],
                    "quadrant": div["quadrant"],
                    "monitor_index": mon_idx,
                    "dpi": win_dpi,
                }

            results.append({
                "title": title,
                "rect": enriched_rect,
                "pid": pid,
                "proc_name": proc_name,
                "exe_path": exe_path,
                "window_class": win_class,
                "z_order": z_order,
                "is_foreground": is_fg,
                "hwnd": hwnd,
                "monitor_index": mon_idx,
                "dpi": win_dpi,
            })
        return True  # continue enumeration

    user32.EnumWindows(_callback, 0)
    return results


def _get_foreground_hwnd() -> int:
    return user32.GetForegroundWindow()


# ──────────────────────────────────────────────────────────────────────────────
# Chrome / Edge CDP browser-tab reader
# ──────────────────────────────────────────────────────────────────────────────

_CDP_PORTS = [9222, 9223]  # Chrome=9222, Edge=9223


def _fetch_browser_tabs() -> List[Dict[str, Any]]:
    """
    Query Chrome / Edge DevTools Protocol (CDP) for open tabs.
    Returns list of {url, title, browser, scroll_y, scroll_ratio}.
    """
    tabs: List[Dict[str, Any]] = []
    for port in _CDP_PORTS:
        try:
            url = CHROME_CDP_URL_TEMPLATE.format(port=port)
            resp = httpx.get(url, timeout=1.0)
            if resp.status_code != 200:
                continue
            browser = "edge" if port == 9223 else "chrome"
            raw_tabs = resp.json()
            page_tabs = [
                t for t in raw_tabs
                if t.get("type") == "page" and not t.get("url", "").startswith("devtools://")
            ]
            for tab in page_tabs:
                tab_url = tab.get("url", "")
                tab_title = tab.get("title", "")
                ws_url = tab.get("webSocketDebuggerUrl")
                scroll_y = 0
                scroll_ratio = 0.0
                if ws_url:
                    try:
                        from services.chrome_launcher.chrome_manager import fetch_tab_scroll
                        scroll_y, scroll_ratio = fetch_tab_scroll(ws_url, timeout=0.3)
                    except Exception:
                        pass
                if tab_url:
                    tabs.append({
                        "url": tab_url,
                        "title": tab_title,
                        "browser": browser,
                        "scroll_y": scroll_y,
                        "scroll_ratio": scroll_ratio,
                    })
        except Exception:
            pass  # CDP not available on this port
    return tabs


# ──────────────────────────────────────────────────────────────────────────────
# OS Logger
# ──────────────────────────────────────────────────────────────────────────────

class OSLogger:
    """
    Polls Windows OS state every `interval_s` seconds and maintains a
    WorkspaceLogQueue with the latest artefacts.

    Thread-safe; runs in a background daemon thread.
    """

    def __init__(self, queue: WorkspaceLogQueue, interval_s: float = 1.0):
        self.queue = queue
        self.interval_s = interval_s

        self._running = False
        self._thread: Optional[threading.Thread] = None

        # Tracking sets for deduplication between polling cycles
        self._known_window_titles: Set[str] = set()
        self._known_tab_urls: Set[str] = set()
        self._last_clipboard: str = ""
        self._known_procs: Set[str] = set()   # incremental process tracking

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self) -> None:
        """Start background polling thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop, name="OSLogger", daemon=True
        )
        self._thread.start()
        logger.info("[OSLogger] Started (interval=%.1fs)", self.interval_s)

    def stop(self) -> None:
        """Stop the polling thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        logger.info("[OSLogger] Stopped")

    def set_interval(self, interval_s: float) -> None:
        """
        Thread-safe update of the polling interval.

        Takes effect on the *next* sleep boundary (up to the previous interval_s).
        Called by EcoThrottleController to throttle/restore OS Logger polling rate.
        """
        old = self.interval_s
        self.interval_s = max(0.1, float(interval_s))
        logger.info("[OSLogger] Polling interval changed %.1f s → %.1f s", old, self.interval_s)

    def capture_snapshot(self) -> WorkspaceLogQueue:
        """
        Perform a single synchronous full capture and return the queue.
        Useful for one-shot capture at gesture time (not continuous).
        """
        self._poll_once(force_all=True)
        return self.queue

    # ── Internal ──────────────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        while self._running:
            try:
                self._poll_once(force_all=False)
            except Exception as exc:
                logger.error("[OSLogger] Poll error: %s", exc)
            time.sleep(self.interval_s)

    def _poll_once(self, *, force_all: bool = False) -> None:
        now_str = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        # 1. ── Foreground window ──────────────────────────────────────────────
        fg_hwnd = _get_foreground_hwnd()
        fg_title = _get_window_title(fg_hwnd) if fg_hwnd else ""
        if fg_title and (force_all or fg_title not in self._known_window_titles):
            fg_pid = self._get_pid(fg_hwnd)
            fg_exe = _get_exe_path(fg_pid)
            fg_class = _get_window_class(fg_hwnd) if fg_hwnd else ""
            self.queue.enqueue(LogEntry(
                entry_type=LogEntryType.FOREGROUND,
                captured_at=now_str,
                window_title=fg_title,
                exe_path=fg_exe,
                window_class=fg_class,
                is_foreground=True,
            ))

        # 2. ── All visible windows ────────────────────────────────────────────
        windows = _enum_visible_windows()
        current_titles: Set[str] = set()
        for w in windows:
            title = w["title"]
            current_titles.add(title)
            if force_all or title not in self._known_window_titles:
                self.queue.enqueue(LogEntry(
                    entry_type=LogEntryType.WINDOW,
                    captured_at=now_str,
                    window_title=title,
                    window_rect=w.get("rect"),
                    pid=w.get("pid", 0),
                    process_name=w.get("proc_name", ""),
                    exe_path=w.get("exe_path", ""),
                    window_class=w.get("window_class", ""),
                    z_order=w.get("z_order", 0),
                    is_foreground=w.get("is_foreground", False),
                    monitor_index=w.get("monitor_index", 0),
                    dpi=w.get("dpi", 96),
                    is_minimised=False,
                ))
        self._known_window_titles = current_titles

        # 3. ── App text content (foreground window, every cycle) ──────────────
        if fg_hwnd and fg_title:
            fg_text = _get_app_text_content(fg_hwnd)
            if fg_text:
                self.queue.enqueue(LogEntry(
                    entry_type=LogEntryType.APP_CONTENT,
                    captured_at=now_str,
                    window_title=fg_title,
                    app_text_content=fg_text,
                    is_foreground=True,
                ))

        # 4. ── Browser tabs (Chrome/Edge via CDP) ─────────────────────────────
        tabs = _fetch_browser_tabs()
        current_urls: Set[str] = set()
        for tab in tabs:
            url = tab["url"]
            current_urls.add(url)
            if force_all or url not in self._known_tab_urls:
                self.queue.enqueue(LogEntry(
                    entry_type=LogEntryType.BROWSER_TAB,
                    captured_at=now_str,
                    url=url,
                    page_title=tab["title"],
                    browser=tab["browser"],
                    scroll_y=tab.get("scroll_y", 0),
                    scroll_ratio=tab.get("scroll_ratio", 0.0),
                ))
        self._known_tab_urls = current_urls

        # 5. ── Clipboard ──────────────────────────────────────────────────────
        try:
            clip = pyperclip.paste() or ""
            if clip and (force_all or clip != self._last_clipboard):
                self.queue.enqueue(LogEntry(
                    entry_type=LogEntryType.CLIPBOARD,
                    captured_at=now_str,
                    clipboard_text=clip[:50_000],  # cap at 50 KB
                ))
                self._last_clipboard = clip
        except Exception as exc:
            logger.debug("[OSLogger] Clipboard read failed: %s", exc)

        # 6. ── Running processes (incremental every cycle) ────────────────────
        try:
            new_procs: Set[str] = set()
            for proc in psutil.process_iter(["name", "pid", "username"]):
                try:
                    name = proc.info["name"] or ""
                    pid  = proc.info["pid"]
                    user = proc.info.get("username") or ""
                    if name and "SYSTEM" not in user.upper():
                        new_procs.add(name)
                        if force_all or name not in self._known_procs:
                            exe_path = ""
                            try:
                                exe_path = proc.exe()
                            except (psutil.NoSuchProcess, psutil.AccessDenied):
                                pass
                            self.queue.enqueue(LogEntry(
                                entry_type=LogEntryType.PROCESS,
                                captured_at=now_str,
                                process_name=name,
                                pid=pid,
                                exe_path=exe_path,
                            ))
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass
            self._known_procs = new_procs
        except Exception as exc:
            logger.debug("[OSLogger] Process scan failed: %s", exc)

        logger.debug(
            "[OSLogger] Snapshot: %d windows, %d tabs, clipboard=%s",
            len(windows), len(tabs), bool(self._last_clipboard),
        )

    @staticmethod
    def _get_pid(hwnd: int) -> int:
        """Get PID for a window handle."""
        pid_buf = ctypes.wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid_buf))
        return pid_buf.value
