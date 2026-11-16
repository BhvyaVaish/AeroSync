"""
AeroSync Workspace Logger – Log Queue

A thread-safe, deque-based FIFO queue that records the live OS state of
Computer A as a sequence of LogEntry items.

WHY QUEUE (FIFO) instead of a stack:
  Order matters during reconstruction on Computer B. Events should be
  replayed in the same chronological order they occurred on Computer A –
  first tab opened first, first window launched first, clipboard state at
  the time it was set.  A queue (FIFO – First In First Out) preserves
  that order exactly:  enqueue() adds to the tail, dequeue() removes from
  the head, so the oldest item is always processed first.

Each entry captures exactly ONE identifiable OS artefact (a window, a
browser tab, a clipboard value, a running process).  The queue is
serialisable to JSON for packaging and transfer to Computer B, which
dequeues (pops from the front) each entry in the original capture order.

Deduplication contract:
  Items that appear in this queue MUST NOT be sent to the OCR pipeline.
  The `exclusion_set` property exposes the content identifiers (titles,
  URLs, text values) that the OCR engine must skip.
"""

from __future__ import annotations

import dataclasses
import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field, asdict
from typing import Any, Deque, Dict, List, Optional, Set


# ────────────────────────────────────────────────────────────────────────────────
# Log Entry Types
# ────────────────────────────────────────────────────────────────────────────────

class LogEntryType:
    """Enumerated string constants for log entry types."""
    WINDOW        = "window"        # An open application window
    BROWSER_TAB   = "browser_tab"   # A Chrome/Edge browser tab
    CLIPBOARD     = "clipboard"     # Clipboard text snapshot
    PROCESS       = "process"       # Running process (name + pid)
    FOREGROUND    = "foreground"    # Foreground window at capture time
    APP_CONTENT   = "app_content"   # Text content extracted from an app window
    WINDOW_ZORDER = "window_zorder" # Z-order snapshot of all visible windows


@dataclass
class LogEntry:
    """
    A single captured OS artefact enqueued into the workspace log queue.

    Fields are intentionally optional to handle heterogeneous artefact types
    without subclassing.
    """
    # Unique identifier for this entry (never duplicated on target)
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    # Type tag – one of LogEntryType constants
    entry_type: str = ""

    # Wall-clock ISO-8601 timestamp at capture
    captured_at: str = ""

    # Process / Application
    process_name: str = ""
    pid: int = 0

    # Window
    window_title: str = ""
    window_rect: Optional[Dict[str, int]] = None   # {left, top, right, bottom}
    is_minimised: bool = False

    # Browser
    url: str = ""
    page_title: str = ""
    browser: str = ""   # "chrome" | "edge" | "firefox"

    # Clipboard
    clipboard_text: str = ""

    # Enhanced fields for maximum fidelity transfer
    exe_path: str = ""          # Full path to executable e.g. C:\Windows\notepad.exe
    window_class: str = ""      # Win32 window class name e.g. "Notepad", "Chrome_WidgetWin_1"
    z_order: int = 0            # Window z-order index (0 = topmost)
    is_foreground: bool = False # Whether this window was the foreground window at capture
    app_text_content: str = ""  # Text extracted from window (WM_GETTEXT / accessibility)

    # Extra metadata (open for future extension)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "LogEntry":
        """Deserialise a LogEntry, ignoring unknown keys for forward-compat."""
        known = {f.name for f in dataclasses.fields(LogEntry)}
        filtered = {k: v for k, v in d.items() if k in known}
        return LogEntry(**filtered)

    # ── Deduplication identity ────────────────────────────────────────────────
    @property
    def content_id(self) -> str:
        """
        A string that uniquely identifies the content of this entry for
        deduplication purposes.  The OCR pipeline uses this to skip
        content already captured by the OS logger.
        """
        if self.entry_type == LogEntryType.BROWSER_TAB:
            return f"url:{self.url}"
        if self.entry_type in (LogEntryType.WINDOW, LogEntryType.FOREGROUND):
            return f"win:{self.window_title}"
        if self.entry_type == LogEntryType.CLIPBOARD:
            return f"clip:{self.clipboard_text[:200]}"
        if self.entry_type == LogEntryType.PROCESS:
            return f"proc:{self.process_name}"
        if self.entry_type == LogEntryType.APP_CONTENT:
            return f"appcontent:{self.window_title}"
        return f"entry:{self.entry_id}"


# ────────────────────────────────────────────────────────────────────────────────
# WorkspaceLogQueue
# ────────────────────────────────────────────────────────────────────────────────

class WorkspaceLogQueue:
    """
    Thread-safe FIFO queue of LogEntry objects.

    enqueue() – add to tail (newest end)
    dequeue() – remove from head (oldest end) → FIFO order preserved
    snapshot() – stable ordered list (oldest → newest) for serialisation
    """

    def __init__(self, max_size: int = 500):
        self.max_size = max_size
        self._entries: Deque[LogEntry] = deque(maxlen=max_size)
        self._lock = threading.Lock()
        self.source_device_id: str = ""
        self.captured_at: str = ""

    # ── Mutation ──────────────────────────────────────────────────────────────

    def enqueue(self, entry: LogEntry) -> None:
        """Add a new entry to the tail of the queue (most-recent end)."""
        with self._lock:
            self._entries.append(entry)

    # Alias for backward compatibility with code that calls .push()
    def push(self, entry: LogEntry) -> None:
        self.enqueue(entry)

    def dequeue(self) -> Optional[LogEntry]:
        """
        Remove and return the oldest entry from the head of the queue (FIFO).
        Returns None if the queue is empty.
        """
        with self._lock:
            if not self._entries:
                return None
            return self._entries.popleft()   # ← FIFO: oldest first

    # Alias kept for any old code that calls .pop() – now FIFO-corrected
    def pop(self) -> Optional[LogEntry]:
        return self.dequeue()

    def clear(self) -> None:
        """Empty the queue."""
        with self._lock:
            self._entries.clear()

    # ── Inspection ────────────────────────────────────────────────────────────

    def snapshot(self) -> List[LogEntry]:
        """Return a stable ordered list (oldest → newest) for serialisation."""
        with self._lock:
            return list(self._entries)

    @property
    def size(self) -> int:
        with self._lock:
            return len(self._entries)

    @property
    def exclusion_set(self) -> Set[str]:
        """
        Set of content_id strings representing all items already captured by
        the OS logger.  The OCR pipeline MUST exclude any text that matches
        a prefix of one of these identifiers to avoid double-processing.
        """
        with self._lock:
            return {e.content_id for e in self._entries}

    def get_telemetry(self) -> Dict[str, Any]:
        """Return real-time queue telemetry for space-themed QueueMonitorWidget."""
        with self._lock:
            entries = list(self._entries)

        windows = sum(1 for e in entries if e.entry_type == LogEntryType.WINDOW)
        tabs = sum(1 for e in entries if e.entry_type == LogEntryType.BROWSER_TAB)
        clipboard = sum(1 for e in entries if e.entry_type == LogEntryType.CLIPBOARD)
        processes = sum(1 for e in entries if e.entry_type == LogEntryType.PROCESS)

        size = len(entries)
        cap = self.max_size
        return {
            "size": size,
            "capacity": cap,
            "max_size": cap,
            "capacity_pct": round(size / max(1, cap), 3),
            "windows": windows,
            "tabs": tabs,
            "clipboard": clipboard,
            "clipboards": clipboard,
            "processes": processes,
            "mode": "FIFO Chronological",
        }

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> Dict[str, Any]:
        """Serialise the entire queue to a plain dict (for JSON / AES packing)."""
        return {
            "source_device_id": self.source_device_id,
            "captured_at": self.captured_at or time.strftime(
                "%Y-%m-%dT%H:%M:%SZ", time.gmtime()
            ),
            "entry_count": self.size,
            "entries": [e.to_dict() for e in self.snapshot()],  # oldest→newest
        }

    @staticmethod
    def from_dict(d: Dict[str, Any]) -> "WorkspaceLogQueue":
        queue = WorkspaceLogQueue()
        queue.source_device_id = d.get("source_device_id", "")
        queue.captured_at = d.get("captured_at", "")
        for entry_dict in d.get("entries", []):
            queue.enqueue(LogEntry.from_dict(entry_dict))
        return queue


# ── Backward-compat alias ──────────────────────────────────────────────────────
# Old code that imports WorkspaceLogStack still works; it now refers to the
# FIFO queue.  Remove this alias once all call-sites are updated.
WorkspaceLogStack = WorkspaceLogQueue
