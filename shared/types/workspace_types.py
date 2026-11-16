"""
AeroSync Workspace Type Definitions

Data structures for workspace capture, packaging, and reconstruction.
These types are shared between the capture engine, packager, and reconstructor.
"""

from dataclasses import dataclass, field
from typing import List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from shared.types.screen_types import ScreenContent, ActionPlan


@dataclass
class TabInfo:
    """Information about a single browser tab."""
    url: str
    title: str
    tab_id: Optional[str] = None
    window_id: Optional[str] = None
    is_active: bool = False
    favicon_url: Optional[str] = None
    index: int = 0


@dataclass
class BrowserState:
    """State of a browser instance (one window)."""
    browser_type: str = "chrome"  # chrome | edge | firefox (only chrome for MVP)
    window_id: Optional[str] = None
    tabs: List[TabInfo] = field(default_factory=list)
    active_tab_index: int = 0
    is_focused: bool = False
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0


@dataclass
class WindowState:
    """State of a single application window."""
    hwnd: Optional[int] = None
    title: str = ""
    process_name: str = ""
    exe_path: Optional[str] = None
    window_class: str = ""   # Win32 class name e.g. "Notepad", "Chrome_WidgetWin_1"
    z_order: int = 0          # Enumeration order (0 = topmost)
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    monitor_index: int = 0
    is_minimized: bool = False
    is_maximized: bool = False
    is_focused: bool = False
    app_text_content: str = ""  # Text content extracted via WM_GETTEXT/accessibility

    # Screen orientation & coordinate division
    rel_x: float = 0.0          # Normalized [0.0 - 1.0] relative to screen width
    rel_y: float = 0.0          # Normalized [0.0 - 1.0] relative to screen height
    rel_width: float = 0.0      # Normalized [0.0 - 1.0] relative to screen width
    rel_height: float = 0.0     # Normalized [0.0 - 1.0] relative to screen height
    screen_width: int = 1920    # Host screen resolution width at capture
    screen_height: int = 1080   # Host screen resolution height at capture
    quadrant: str = ""          # e.g. "top-left", "top-right", "bottom-left", "bottom-right", "full", "center"


@dataclass
class MonitorInfo:
    """Information about a display monitor."""
    monitor_index: int = 0
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    is_primary: bool = False


@dataclass
class ClipboardContent:
    """Captured clipboard content."""
    type: str = "empty"  # text | image | file_paths | empty
    content: Optional[str] = None
    truncated: bool = False


@dataclass
class WindowPlacement:
    """Target placement for a window during reconstruction."""
    process_name: str = ""
    title_pattern: Optional[str] = None
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0
    monitor_index: int = 0
    is_minimized: bool = False
    is_maximized: bool = False


@dataclass
class ReconstructionPlan:
    """Instructions for reconstructing a workspace on the target device."""
    open_chrome_urls: List[str] = field(default_factory=list)
    active_tab_url: Optional[str] = None
    window_layout: List[WindowPlacement] = field(default_factory=list)
    clipboard_restore: Optional[ClipboardContent] = None
    launch_sequence: List[str] = field(
        default_factory=lambda: ["browser", "windows", "clipboard"]
    )


@dataclass
class WorkspaceSnapshot:
    """
    Complete snapshot of a user's workspace at a point in time.

    This is the core data structure captured by the workspace capture engine
    and used to reconstruct the workspace on another device.
    """
    snapshot_id: str = ""
    captured_at: str = ""  # ISO 8601 datetime
    source_device_id: str = ""
    source_platform: str = "windows"

    browsers: List[BrowserState] = field(default_factory=list)
    windows: List[WindowState] = field(default_factory=list)
    monitors: List[MonitorInfo] = field(default_factory=list)
    clipboard: ClipboardContent = field(default_factory=ClipboardContent)

    capture_duration_ms: int = 0
    capture_warnings: List[str] = field(default_factory=list)

    # --- Screen Reader / AI fields (optional) ---
    # Set during capture on the sender machine; executed during reconstruction on receiver.
    screen_content: Optional[object] = None   # ScreenContent (avoid circular import)
    action_plan: Optional[object] = None      # ActionPlan (avoid circular import)

    # --- OS Log Stack (optional) ---
    # Serialised WorkspaceLogQueue dict produced by the OS Logger on Host A.
    # Present only when the gesture-triggered capture path is used.
    log_stack_data: Optional[dict] = None   # WorkspaceLogQueue.to_dict()


@dataclass
class ReconstructionReport:
    """Report generated after workspace reconstruction attempt."""
    transfer_id: str = ""
    steps_completed: List[str] = field(default_factory=list)
    steps_failed: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    duration_ms: int = 0
    success: bool = False
    error_message: Optional[str] = None

    # Detailed tracking for user notification
    failed_items: List[str] = field(default_factory=list)         # human-readable failures
    reused_items: List[str] = field(default_factory=list)         # already present on B, reused
    launched_apps: List[str] = field(default_factory=list)        # apps successfully launched
    repositioned_windows: List[str] = field(default_factory=list) # windows repositioned
    restored_tabs: List[str] = field(default_factory=list)        # browser tabs opened
