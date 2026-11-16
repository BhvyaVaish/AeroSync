"""
AeroSync Reconstruction Orchestrator

Sequentially executes workspace reconstruction steps on Target B.

Step order:
  0. Snapshot B state   — enumerate what's already running/open on B
  1. Log Stack Replay   — restore OS-logged state (browser tabs, windows,
                          clipboard, apps) using high-fidelity OS data from
                          Host A log stack.
  2. Browser            — open any additional tabs captured via CDP.
  3. Apps/Windows       — smart launch + reposition application windows.
                          Reuses existing windows on B and reorients them.
  4. Clipboard          — restore clipboard text.
  5. Screen Actions     — AI-guided actions for OCR-only content.
  6. Notification       — toast user with what succeeded / failed.

Deduplication & Smart Reuse:
  • Browser tabs already open on B or opened by log replay are skipped.
  • Apps/windows already open on B are reused, not relaunched, and reoriented using coordinates.
  • Items truly not transferable are notified to the user with the full list.
"""

import asyncio
import logging
import os
import subprocess
import time
from typing import Any, Coroutine, Dict, List, Optional, Set, Tuple

import psutil

from shared.types.workspace_types import WorkspaceSnapshot, ReconstructionReport
from services.workspace_reconstructor.browser_restorer import restore_browsers
from services.workspace_reconstructor.window_restorer import restore_windows
from services.workspace_reconstructor.clipboard_restorer import restore_clipboard
from shared.constants import RECONSTRUCTION_STEP_TIMEOUT_SECONDS, RECONSTRUCTION_LAUNCH_SEQUENCE

logger = logging.getLogger(__name__)

# Processes we never try to launch on B
_SKIP_BINARIES: Set[str] = {
    "explorer.exe", "searchhost.exe", "shellexperiencehost.exe",
    "taskhostw.exe", "runtimebroker.exe", "applicationframehost.exe",
    "python.exe", "pythonw.exe", "cmd.exe", "powershell.exe",
    "conhost.exe", "chrome.exe", "msedge.exe", "firefox.exe",
    "aerosync.exe", "system", "registry", "services.exe",
    "svchost.exe", "lsass.exe", "csrss.exe", "wininit.exe",
    "dwm.exe", "winlogon.exe", "fontdrvhost.exe", "spoolsv.exe",
}


async def _safe_execute(coro: Coroutine, name: str, timeout: float) -> Tuple[Any, Optional[str]]:
    """Execute a coroutine with a timeout and catch exceptions."""
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        return result, None
    except asyncio.TimeoutError:
        err = f"Reconstruction step timed out for {name} after {timeout}s"
        logger.warning(err)
        return None, err
    except Exception as e:
        err = f"Reconstruction step failed for {name}: {e}"
        logger.error(err)
        return None, err


def _snapshot_b_state() -> Tuple[Set[str], Dict[str, int]]:
    """
    Enumerate what's currently running/open on Target B before reconstruction.
    
    Returns:
        (running_proc_names_lower, open_window_titles_lower_to_hwnd)
    """
    import ctypes
    import ctypes.wintypes

    user32 = ctypes.windll.user32

    # Running processes
    b_procs: Set[str] = set()
    for p in psutil.process_iter(["name"]):
        try:
            name = p.info.get("name") or ""
            if name:
                b_procs.add(name.lower())
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    # Open windows
    b_windows: Dict[str, int] = {}

    EnumProc = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.wintypes.HWND, ctypes.wintypes.LPARAM)

    def cb(hwnd, _):
        if user32.IsWindowVisible(hwnd):
            length = user32.GetWindowTextLengthW(hwnd)
            if length > 0:
                buf = ctypes.create_unicode_buffer(length + 1)
                user32.GetWindowTextW(hwnd, buf, length + 1)
                title = buf.value.lower()
                if title:
                    b_windows[title] = hwnd
        return True

    user32.EnumWindows(EnumProc(cb), 0)
    return b_procs, b_windows


def _launch_app(process_name: str, exe_path: str, running_procs: Set[str]) -> Tuple[bool, str]:
    """
    Attempt to launch an application on B.
    
    Priority:
      1. Try exe_path directly (most reliable).
      2. Try process_name (if on PATH).
      
    Returns:
        (success, error_message)
    """
    pname_lower = process_name.lower()
    if pname_lower in running_procs:
        return True, ""  # already running

    # Try exe_path first
    if exe_path and os.path.isfile(exe_path):
        try:
            subprocess.Popen([exe_path], shell=False)
            running_procs.add(pname_lower)
            return True, ""
        except Exception as exc:
            logger.debug("[Reconstruct] exe_path launch failed (%s): %s", exe_path, exc)

    # Fallback: process name (hoping it's on PATH)
    if process_name:
        try:
            subprocess.Popen([process_name], shell=False)
            running_procs.add(pname_lower)
            return True, ""
        except Exception as exc:
            return False, f"Could not launch '{process_name}': {exc}"

    return False, f"No launch path available for '{process_name}'"


async def reconstruct_workspace(snapshot: WorkspaceSnapshot, transfer_id: str) -> ReconstructionReport:
    """
    Reconstruct the workspace from a snapshot on Target B.
    
    Args:
        snapshot: The unpacked WorkspaceSnapshot from Host A.
        transfer_id: The ID of the transfer session.
        
    Returns:
        ReconstructionReport detailing success/failures.
    """
    logger.info("Starting workspace reconstruction for snapshot %s", snapshot.snapshot_id)
    start_time = time.monotonic()

    report = ReconstructionReport(transfer_id=transfer_id)

    # ── Step 0: Snapshot Target B current state ───────────────────────────────
    b_running_procs, b_open_windows = _snapshot_b_state()
    already_opened_urls: Set[str] = set()
    logger.info(
        "[B-State] %d running procs, %d open windows",
        len(b_running_procs), len(b_open_windows),
    )

    # ── Step 1: Log Stack Replay ──────────────────────────────────────────────
    if getattr(snapshot, "log_stack_data", None):
        try:
            from services.workspace_logger.log_stack import WorkspaceLogQueue, LogEntryType
            log_queue = WorkspaceLogQueue.from_dict(snapshot.log_stack_data)
            entries = log_queue.snapshot()

            # 1a. Browser tabs from log (Auto-launch normal Chrome)
            tab_urls = [
                e.url for e in entries
                if e.entry_type == LogEntryType.BROWSER_TAB and e.url
            ]
            if tab_urls:
                new_urls = []
                for url in tab_urls:
                    url_norm = url.rstrip("/")
                    if url_norm in already_opened_urls:
                        report.reused_items.append(f"Tab (already open): {url}")
                    else:
                        new_urls.append(url)

                if new_urls:
                    from services.chrome_launcher.chrome_manager import launch_normal_chrome
                    opened_ok = launch_normal_chrome(new_urls, new_window=True)
                    if not opened_ok:
                        import webbrowser
                        for u in new_urls:
                            try:
                                webbrowser.open(u)
                            except Exception as exc:
                                logger.warning("[LogReplay] Failed to open %s: %s", u, exc)
                                report.failed_items.append(f"Browser tab: {u} ({exc})")
                    for u in new_urls:
                        already_opened_urls.add(u.rstrip("/"))
                        report.restored_tabs.append(u)
                        logger.info("[LogReplay] Opened tab: %s", u)
                report.steps_completed.append(f"log_stack_replay ({len(tab_urls)} tabs)")

            # 1b. Clipboard from log
            clip_entries = [
                e.clipboard_text for e in entries
                if e.entry_type == LogEntryType.CLIPBOARD and e.clipboard_text
            ]
            if clip_entries:
                try:
                    import pyperclip
                    pyperclip.copy(clip_entries[-1])
                    logger.info("[LogReplay] Clipboard restored")
                    report.steps_completed.append("log_clipboard_restored")
                except Exception as exc:
                    logger.warning("[LogReplay] Clipboard restore failed: %s", exc)
                    report.warnings.append(f"Clipboard restore from log failed: {exc}")

            # 1c. App launch from log entries
            seen_launch: Set[str] = set()
            for e in entries:
                p_name = (e.process_name or "").strip()
                exe_path = (e.exe_path or "").strip()
                if not p_name:
                    continue
                p_lower = p_name.lower()
                if p_lower in _SKIP_BINARIES or p_lower in seen_launch:
                    continue

                # Check if already running on B
                if p_lower in b_running_procs:
                    report.reused_items.append(f"App already running: {p_name}")
                    seen_launch.add(p_lower)
                    continue

                # Only launch apps that have visible windows in A's log
                if e.entry_type not in (LogEntryType.WINDOW, LogEntryType.FOREGROUND):
                    continue

                ok, err_msg = _launch_app(p_name, exe_path, b_running_procs)
                seen_launch.add(p_lower)
                if ok:
                    report.launched_apps.append(p_name)
                    logger.info("[LogReplay] Launched: %s", p_name)
                else:
                    report.failed_items.append(f"App launch failed: {p_name} — {err_msg}")
                    logger.warning("[LogReplay] %s", err_msg)

            if report.launched_apps:
                report.steps_completed.append(
                    f"log_apps_launched ({len(report.launched_apps)} apps: {', '.join(report.launched_apps)})")

            # Give launched apps a moment to initialize
            if report.launched_apps:
                await asyncio.sleep(2.0)

            logger.info("[LogReplay] Done (%d entries)", log_queue.size)
        except Exception as exc:
            logger.warning("[LogReplay] Log stack replay failed: %s", exc)
            report.warnings.append(f"Log stack replay failed: {exc}")

    # ── Step 2: Browser tabs from WorkspaceSnapshot.browsers ─────────────────
    if "browser" in RECONSTRUCTION_LAUNCH_SEQUENCE and snapshot.browsers:
        res, err = await _safe_execute(
            restore_browsers(snapshot.browsers, already_opened_urls=already_opened_urls),
            "browser",
            RECONSTRUCTION_STEP_TIMEOUT_SECONDS,
        )
        if err:
            report.steps_failed.append("browser")
            report.warnings.append(err)
            report.failed_items.append(f"Browser restore error: {err}")
        else:
            report.steps_completed.append("browser")
            if res:
                successful, failed_tabs, reused = res
                report.restored_tabs.extend(successful)
                report.reused_items.extend([f"Tab (reused): {u}" for u in reused])
                for url in failed_tabs:
                    report.failed_items.append(f"Browser tab failed to open: {url}")
    else:
        report.steps_completed.append("browser (skipped: empty)")

    # ── Step 3: Window reposition (smart reuse & reorient) ─────────────────────
    if "windows" in RECONSTRUCTION_LAUNCH_SEQUENCE and snapshot.windows:
        # Wait a moment for any newly opened windows
        if report.launched_apps or ("browser" in report.steps_completed and not report.steps_completed[-1].endswith("(skipped: empty)")):
            await asyncio.sleep(1.5)
            
        res, err = await _safe_execute(
            restore_windows(snapshot.windows),
            "windows",
            RECONSTRUCTION_STEP_TIMEOUT_SECONDS,
        )
        if err:
            report.steps_failed.append("windows")
            report.warnings.append(err)
            report.failed_items.append(f"Window restorer error: {err}")
        else:
            if res:
                success_count, repositioned, failed_wins = res
                report.repositioned_windows.extend(repositioned)
                for w in failed_wins:
                    report.failed_items.append(f"Window not found on B: {w}")
                report.steps_completed.append(
                    f"windows ({success_count}/{len(snapshot.windows)} repositioned)")
                if success_count < len(snapshot.windows):
                    report.warnings.append(f"Only repositioned {success_count}/{len(snapshot.windows)} windows")
    else:
        report.steps_completed.append("windows (skipped: empty)")

    # ── Step 4: Clipboard ─────────────────────────────────────────────────────
    if "clipboard" in RECONSTRUCTION_LAUNCH_SEQUENCE:
        if snapshot.clipboard and snapshot.clipboard.type != "empty":
            res, err = await _safe_execute(
                restore_clipboard(snapshot.clipboard),
                "clipboard",
                RECONSTRUCTION_STEP_TIMEOUT_SECONDS,
            )
            if err:
                report.steps_failed.append("clipboard")
                report.warnings.append(err)
                report.failed_items.append(f"Clipboard restore failed: {err}")
            elif not res:
                report.steps_failed.append("clipboard")
                report.warnings.append("Clipboard restore returned False")
                report.failed_items.append("Clipboard could not be restored")
            else:
                report.steps_completed.append("clipboard")
        else:
            report.steps_completed.append("clipboard (skipped: empty)")

    # ── Step 5: Screen Actions (AI Reconstruction) ───────────────────────────
    if "screen_actions" in RECONSTRUCTION_LAUNCH_SEQUENCE:
        if snapshot.action_plan and getattr(snapshot.action_plan, "actions", None):
            from services.action_executor.execution_orchestrator import execute_action_plan
            from shared.constants import SCREEN_ACTIONS_TIMEOUT_SECONDS
            timeout = float(SCREEN_ACTIONS_TIMEOUT_SECONDS * max(1, len(snapshot.action_plan.actions)))
            exec_res, err = await _safe_execute(
                execute_action_plan(snapshot.action_plan, transfer_id=transfer_id),
                "screen_actions",
                timeout,
            )
            if err:
                report.steps_failed.append("screen_actions")
                report.warnings.append(err)
                report.failed_items.append(f"AI screen actions failed: {err}")
            else:
                report.steps_completed.append("screen_actions")
                if exec_res and not exec_res.success:
                    report.warnings.append(f"Screen actions partially failed: {exec_res.failed} failed")
        else:
            report.steps_completed.append("screen_actions (skipped: empty)")

    report.duration_ms = int((time.monotonic() - start_time) * 1000)
    fatal_failure = "browser" in report.steps_failed
    report.success = not fatal_failure

    # ── Step 6: User Notification with failed items list ──────────────────────
    try:
        from apps.client.notification import show_failed_transfer_report
        show_failed_transfer_report(
            transfer_id=transfer_id,
            failed_items=report.failed_items,
            reused_items=report.reused_items,
            launched_apps=report.launched_apps,
            restored_tabs=report.restored_tabs,
        )
    except Exception as exc:
        logger.warning("[Reconstruct] Notification failed: %s", exc)

    logger.info(
        "Reconstruction completed in %dms. Success=%s, launched=%d, tabs=%d, failed=%d",
        report.duration_ms, report.success,
        len(report.launched_apps), len(report.restored_tabs), len(report.failed_items),
    )
    return report
