"""
AeroSync Workspace Capture Orchestrator

Runs browser, window, monitor, clipboard, and (optionally) screen reader
captures in parallel. Produces the final WorkspaceSnapshot.

Deduplication contract (Step 5 of the architecture):
  1. OSLogger populates the WorkspaceLogQueue FIRST.
  2. This orchestrator reads the stack's `exclusion_set`.
  3. Screen-reader / OCR receives the exclusion_set and MUST NOT re-capture
     any content whose identifier is already present in the log.

Windows-only. No cross-OS support.
"""

import asyncio
import datetime
import logging
import time
import uuid
from typing import List, Any, Coroutine, Optional, Set, Tuple

from shared.types.workspace_types import WorkspaceSnapshot
from services.workspace_capture.browser_capture import capture_browser_state
from services.workspace_capture.window_capture import capture_windows
from services.workspace_capture.monitor_capture import capture_monitors
from services.workspace_capture.clipboard_capture import capture_clipboard
from services.workspace_capture.device_fingerprint import generate_device_fingerprint
from shared.constants import (
    CAPTURE_TIMEOUT_SECONDS,
    PLATFORM_WINDOWS,
    SCREEN_READER_ENABLED,
    SCREEN_READER_TIMEOUT_SECONDS,
)

logger = logging.getLogger(__name__)


async def _safe_execute(coro: Coroutine, name: str, timeout: float) -> Tuple[Any, Optional[str]]:
    """Execute a coroutine with a timeout and catch exceptions."""
    try:
        result = await asyncio.wait_for(coro, timeout=timeout)
        return result, None
    except asyncio.TimeoutError:
        err = f"Capture timed out for {name} after {timeout}s"
        logger.warning(err)
        return None, err
    except Exception as e:
        err = f"Capture failed for {name}: {e}"
        logger.error(err)
        return None, err


async def capture_workspace(
    screen_region=None,
    enable_screen_reader: Optional[bool] = None,
    log_exclusion_set: Optional[Set[str]] = None,
) -> WorkspaceSnapshot:
    """
    Capture the entire workspace in parallel.

    Args:
        screen_region:       Optional ScreenRegion to restrict OCR/AI capture.
                             None = full primary monitor.
        enable_screen_reader: Override the SCREEN_READER_ENABLED constant.
                              None = use constant value.
        log_exclusion_set:   Set of content_id strings from WorkspaceLogQueue.
                             OCR will skip any item whose text matches an entry
                             in this set.  Pass None to disable deduplication.
    Returns:
        WorkspaceSnapshot object.
    """
    start_time = time.monotonic()
    snapshot_id = str(uuid.uuid4())
    logger.info("Starting workspace capture %s", snapshot_id)

    # Determine if screen reading is active
    should_read_screen = (
        enable_screen_reader if enable_screen_reader is not None else SCREEN_READER_ENABLED
    )

    # Build exclusion set for OCR deduplication
    exclusion: Set[str] = log_exclusion_set or set()
    if exclusion:
        logger.info(
            "[Dedup] OCR exclusion set has %d entries from OS log — duplicates will be skipped",
            len(exclusion),
        )

    async def _capture_screen_task():
        from services.screen_reader.screen_reader_orchestrator import capture_and_read_screen
        from services.ai_analyzer.action_planner import plan_actions

        content = await capture_and_read_screen(
            region=screen_region,
            show_selector=False,
            log_exclusion_set=exclusion,  # pass dedup set to OCR engine
        )
        loop = asyncio.get_running_loop()
        plan = await loop.run_in_executor(None, lambda: plan_actions(content))
        return content, plan

    # Fire off all captures concurrently
    tasks = [
        _safe_execute(capture_browser_state(), "browser", CAPTURE_TIMEOUT_SECONDS),
        _safe_execute(capture_windows(), "windows", CAPTURE_TIMEOUT_SECONDS),
        _safe_execute(capture_monitors(), "monitors", CAPTURE_TIMEOUT_SECONDS),
        _safe_execute(capture_clipboard(), "clipboard", CAPTURE_TIMEOUT_SECONDS),
    ]

    if should_read_screen:
        tasks.append(
            _safe_execute(_capture_screen_task(), "screen_reader", SCREEN_READER_TIMEOUT_SECONDS)
        )

    results = await asyncio.gather(*tasks)

    # Process results
    warnings = []
    browser_res, browser_err = results[0]
    windows_res, windows_err = results[1]
    monitors_res, monitors_err = results[2]
    clipboard_res, clipboard_err = results[3]

    if browser_err:
        warnings.append(browser_err)
    if windows_err:
        warnings.append(windows_err)
    if monitors_err:
        warnings.append(monitors_err)
    if clipboard_err:
        warnings.append(clipboard_err)

    screen_content = None
    action_plan = None
    if should_read_screen and len(results) > 4:
        screen_res, screen_err = results[4]
        if screen_err:
            warnings.append(screen_err)
        elif screen_res:
            screen_content, action_plan = screen_res

    # Create snapshot
    device_id = generate_device_fingerprint()
    now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
    duration_ms = int((time.monotonic() - start_time) * 1000)

    snapshot = WorkspaceSnapshot(
        snapshot_id=snapshot_id,
        captured_at=now_iso,
        source_device_id=device_id,
        source_platform=PLATFORM_WINDOWS,
        browsers=browser_res if browser_res else [],
        windows=windows_res if windows_res else [],
        monitors=monitors_res if monitors_res else [],
        clipboard=clipboard_res if clipboard_res is not None else None,
        capture_duration_ms=duration_ms,
        capture_warnings=warnings,
        screen_content=screen_content,
        action_plan=action_plan,
    )

    # If clipboard completely failed and returned None, fix it
    if snapshot.clipboard is None:
        from shared.types.workspace_types import ClipboardContent
        snapshot.clipboard = ClipboardContent(type="empty")

    logger.info("Completed workspace capture in %dms with %d warnings", duration_ms, len(warnings))
    return snapshot


# Simple test block
if __name__ == "__main__":
    async def run_test():
        snapshot = await capture_workspace()
        print(f"Captured {len(snapshot.windows)} windows")
        print(f"Captured {len(snapshot.browsers)} browsers")
        print(f"Captured {len(snapshot.monitors)} monitors")
        print(f"Clipboard type: {snapshot.clipboard.type}")
        print(f"Warnings: {snapshot.capture_warnings}")

    asyncio.run(run_test())
