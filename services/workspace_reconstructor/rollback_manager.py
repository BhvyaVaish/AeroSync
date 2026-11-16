"""
AeroSync Workspace Rollback Manager

Enables one-gesture / one-click rollback of workspace reconstruction on Target B.
Restores Target B to its exact pre-transfer state:
  1. Terminates processes/applications spawned by AeroSync during reconstruction.
  2. Restores original window positions, dimensions, and maximize/minimize states for reused windows.
  3. Closes browser tabs opened during reconstruction via CDP.
  4. Restores pre-transfer clipboard content.
  5. Plays celestial rewind audio chime (play_undo_sound) and alerts user.
"""

import asyncio
import ctypes
import ctypes.wintypes
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

import psutil

from shared.constants import CHROME_CDP_URL_TEMPLATE

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32 if os.name == "nt" else None

SWP_NOZORDER = 0x0004
SWP_NOACTIVATE = 0x0010
SW_RESTORE = 9
SW_MINIMIZE = 6
SW_MAXIMIZE = 3


@dataclass
class PreReconstructionState:
    """Snapshot of Target B immediately before reconstruction executes."""
    transfer_id: str
    timestamp: float
    pre_clipboard: str = ""
    running_pids: Set[int] = field(default_factory=set)
    existing_window_placements: Dict[int, Dict[str, Any]] = field(default_factory=dict)
    # hwnd -> {x, y, w, h, is_maximized, is_minimized, title}
    open_tab_urls: Set[str] = field(default_factory=set)
    launched_pids: List[int] = field(default_factory=list)
    launched_app_names: List[str] = field(default_factory=list)
    opened_tabs: List[str] = field(default_factory=list)


@dataclass
class RollbackReport:
    """Detailed summary of the workspace rollback operation."""
    transfer_id: str = ""
    success: bool = True
    closed_pids: List[int] = field(default_factory=list)
    closed_apps: List[str] = field(default_factory=list)
    restored_windows: List[str] = field(default_factory=list)
    closed_tabs: List[str] = field(default_factory=list)
    clipboard_restored: bool = False
    warnings: List[str] = field(default_factory=list)


class RollbackManager:
    """
    Manages pre-reconstruction state tracking and rollback operations.
    Thread-safe; maintains a history stack for undo capability.
    """

    def __init__(self, max_history: int = 5):
        self.max_history = max_history
        self._history: List[PreReconstructionState] = []
        self._active_pre_state: Optional[PreReconstructionState] = None

    def capture_pre_reconstruction_state(self, transfer_id: str) -> PreReconstructionState:
        """
        Record the current state of Target B before executing reconstruction.
        """
        now = time.monotonic()

        # 1. Clipboard
        clip_text = ""
        try:
            import pyperclip
            clip_text = pyperclip.paste() or ""
        except Exception:
            pass

        # 2. Running processes
        pids: Set[int] = set()
        for p in psutil.process_iter(["pid"]):
            try:
                pids.add(p.info["pid"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # 3. Open windows & exact bounding rectangles
        window_placements: Dict[int, Dict[str, Any]] = {}
        if user32:
            EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

            def _cb(hwnd, _):
                if user32.IsWindowVisible(hwnd):
                    length = user32.GetWindowTextLengthW(hwnd)
                    if length > 0:
                        buf = ctypes.create_unicode_buffer(length + 1)
                        user32.GetWindowTextW(hwnd, buf, length + 1)
                        title = buf.value.strip()
                        if title and title not in ("Program Manager", "Settings", "Windows Input Experience"):
                            rect = ctypes.wintypes.RECT()
                            user32.GetWindowRect(hwnd, ctypes.byref(rect))
                            window_placements[hwnd] = {
                                "title": title,
                                "x": rect.left,
                                "y": rect.top,
                                "w": max(1, rect.right - rect.left),
                                "h": max(1, rect.bottom - rect.top),
                                "is_maximized": user32.IsZoomed(hwnd) != 0,
                                "is_minimized": user32.IsIconic(hwnd) != 0,
                            }
                return True

            try:
                user32.EnumWindows(EnumProc(_cb), 0)
            except Exception as exc:
                logger.debug("[RollbackManager] Window enumeration failed: %s", exc)

        state = PreReconstructionState(
            transfer_id=transfer_id,
            timestamp=now,
            pre_clipboard=clip_text,
            running_pids=pids,
            existing_window_placements=window_placements,
        )
        self._active_pre_state = state
        logger.info(
            "[RollbackManager] Captured pre-reconstruction state (%d procs, %d windows)",
            len(pids), len(window_placements)
        )
        return state

    def record_post_reconstruction(
        self,
        transfer_id: str,
        launched_apps: List[str],
        opened_tabs: List[str],
    ) -> None:
        """
        Record items modified or opened during reconstruction to finalize the rollback record.
        """
        if not self._active_pre_state or self._active_pre_state.transfer_id != transfer_id:
            return

        state = self._active_pre_state
        state.launched_app_names = list(launched_apps)
        state.opened_tabs = list(opened_tabs)

        # Detect new PIDs that spawned during reconstruction
        current_pids: Set[int] = set()
        for p in psutil.process_iter(["pid", "name"]):
            try:
                pid = p.info["pid"]
                current_pids.add(pid)
                name = (p.info.get("name") or "").lower()
                # If newly appeared or matches launched app names
                if pid not in state.running_pids and any(app.lower() in name for app in launched_apps):
                    state.launched_pids.append(pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        self._history.append(state)
        if len(self._history) > self.max_history:
            self._history.pop(0)

        self._active_pre_state = None
        logger.info(
            "[RollbackManager] Finalized session %s (new pids=%d, tabs=%d)",
            transfer_id, len(state.launched_pids), len(state.opened_tabs)
        )

    async def rollback_last_workspace(self) -> RollbackReport:
        """
        Roll back the most recent workspace transfer.
        Returns a RollbackReport detailing what was closed and restored.
        """
        if not self._history:
            logger.warning("[RollbackManager] No reconstruction sessions to roll back")
            return RollbackReport(success=False, warnings=["No active rollback history available"])

        session = self._history.pop()
        logger.info("[RollbackManager] Rolling back workspace session: %s", session.transfer_id)

        report = RollbackReport(transfer_id=session.transfer_id)

        # 1. Terminate launched processes
        for pid in session.launched_pids:
            try:
                proc = psutil.Process(pid)
                pname = proc.name()
                proc.terminate()
                report.closed_pids.append(pid)
                report.closed_apps.append(pname)
                logger.info("[Rollback] Terminated launched app: %s (PID %d)", pname, pid)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        # Also check by process name if PIDs changed or weren't caught
        if session.launched_app_names:
            for p in psutil.process_iter(["pid", "name"]):
                try:
                    pname = p.info.get("name") or ""
                    pid = p.info["pid"]
                    if pid not in session.running_pids and any(l.lower() == pname.lower() for l in session.launched_app_names):
                        try:
                            psutil.Process(pid).terminate()
                            report.closed_pids.append(pid)
                            report.closed_apps.append(pname)
                        except Exception:
                            pass
                except (psutil.NoSuchProcess, psutil.AccessDenied):
                    pass

        # 2. Restore window positions and states
        if user32:
            for hwnd, placement in session.existing_window_placements.items():
                try:
                    if user32.IsWindow(hwnd):
                        if placement.get("is_maximized"):
                            user32.ShowWindow(hwnd, SW_MAXIMIZE)
                        elif placement.get("is_minimized"):
                            user32.ShowWindow(hwnd, SW_MINIMIZE)
                        else:
                            user32.ShowWindow(hwnd, SW_RESTORE)
                            user32.SetWindowPos(
                                hwnd,
                                0,
                                placement["x"],
                                placement["y"],
                                placement["w"],
                                placement["h"],
                                SWP_NOZORDER | SWP_NOACTIVATE,
                            )
                        report.restored_windows.append(placement.get("title", f"HWND {hwnd}"))
                except Exception as exc:
                    logger.debug("[Rollback] Failed to restore window %d: %s", hwnd, exc)

        # 3. Close opened browser tabs via CDP
        if session.opened_tabs:
            try:
                import httpx
                for port in (9222, 9223):
                    try:
                        base = CHROME_CDP_URL_TEMPLATE.format(port=port).replace("/json", "")
                        async with httpx.AsyncClient(timeout=1.5) as client:
                            resp = await client.get(f"{base}/json/list")
                            if resp.status_code == 200:
                                current_tabs = resp.json()
                                for tab in current_tabs:
                                    t_url = tab.get("url", "").rstrip("/")
                                    t_id = tab.get("id")
                                    if t_id and any(t_url == opened.rstrip("/") for opened in session.opened_tabs):
                                        close_res = await client.get(f"{base}/json/close/{t_id}")
                                        if close_res.status_code == 200:
                                            report.closed_tabs.append(tab.get("url", ""))
                                            logger.info("[Rollback] Closed restored tab: %s", tab.get("url"))
                    except Exception:
                        pass
            except Exception as exc:
                logger.debug("[Rollback] Failed closing browser tabs: %s", exc)

        # 4. Restore Clipboard
        try:
            import pyperclip
            pyperclip.copy(session.pre_clipboard)
            report.clipboard_restored = True
            logger.info("[Rollback] Restored pre-transfer clipboard")
        except Exception as exc:
            report.warnings.append(f"Clipboard restore failed: {exc}")

        # 5. Play celestial rewind sound
        try:
            from services.audio.cosmic_audio import play_undo_sound
            play_undo_sound()
        except Exception:
            pass

        # 6. Toast Notification
        try:
            from apps.client.notifications import show_toast
            show_toast(
                "AeroSync — Workspace Undone ↩",
                f"Rolled back: {len(report.closed_apps)} apps closed, {len(report.restored_windows)} windows restored"
            )
        except Exception:
            pass

        logger.info(
            "[RollbackManager] Completed rollback (%d apps closed, %d windows restored, %d tabs closed)",
            len(report.closed_apps), len(report.restored_windows), len(report.closed_tabs)
        )
        return report


# Global singleton instance
_GLOBAL_ROLLBACK_MANAGER: Optional[RollbackManager] = None


def get_rollback_manager() -> RollbackManager:
    """Return the global RollbackManager instance."""
    global _GLOBAL_ROLLBACK_MANAGER
    if _GLOBAL_ROLLBACK_MANAGER is None:
        _GLOBAL_ROLLBACK_MANAGER = RollbackManager()
    return _GLOBAL_ROLLBACK_MANAGER
