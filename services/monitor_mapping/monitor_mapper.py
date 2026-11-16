"""
AeroSync Multi-Monitor & DPI Mapping Engine

Provides:
  • Per-Monitor V2 DPI awareness initialization (SetProcessDpiAwarenessContext)
  • Real-time enumeration of physical monitor layouts, coordinates, and DPIs
  • Window-to-monitor intersection & quadrant assignment
  • Cross-device multi-monitor mapping:
      - Multi-to-single monitor folding (prevents off-screen window loss)
      - Single-to-multi monitor index preservation
      - Multi-to-multi monitor geometry alignment
      - Per-monitor DPI scaling ratio adjustments
      - Mathematical on-screen boundary clamping
"""

import ctypes
import ctypes.wintypes
import logging
import os
from typing import Any, Dict, List, Optional, Tuple

from shared.types.workspace_types import MonitorInfo

logger = logging.getLogger(__name__)

# Cache active DPI awareness state
_DPI_AWARENESS_INITIALIZED = False
_DPI_MODE: str = "Uninitialized"


def enable_dpi_awareness() -> str:
    """
    Set Windows process DPI awareness to Per-Monitor V2.
    Ensures Windows reports true physical pixels instead of virtualized scaled coordinates.
    """
    global _DPI_AWARENESS_INITIALIZED, _DPI_MODE
    if _DPI_AWARENESS_INITIALIZED:
        return _DPI_MODE

    if os.name != "nt":
        _DPI_MODE = "NonWindows"
        _DPI_AWARENESS_INITIALIZED = True
        return _DPI_MODE

    # Try Windows 10/11 PerMonitorV2 (-4)
    try:
        user32 = ctypes.windll.user32
        res = user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        if res:
            _DPI_MODE = "PerMonitorV2"
            _DPI_AWARENESS_INITIALIZED = True
            logger.info("[DpiMapper] Enabled PerMonitorV2 DPI awareness")
            return _DPI_MODE
    except Exception:
        pass

    # Try Windows 8.1 Shcore PROCESS_PER_MONITOR_DPI_AWARE (2)
    try:
        shcore = ctypes.windll.shcore
        res = shcore.SetProcessDpiAwareness(2)
        if res == 0:
            _DPI_MODE = "ShcorePerMonitor"
            _DPI_AWARENESS_INITIALIZED = True
            logger.info("[DpiMapper] Enabled ShcorePerMonitor DPI awareness")
            return _DPI_MODE
    except Exception:
        pass

    # Fallback to system-wide DPI awareness
    try:
        user32 = ctypes.windll.user32
        res = user32.SetProcessDPIAware()
        if res:
            _DPI_MODE = "SystemAware"
            _DPI_AWARENESS_INITIALIZED = True
            logger.info("[DpiMapper] Enabled SystemAware DPI awareness")
            return _DPI_MODE
    except Exception:
        pass

    _DPI_MODE = "Failed"
    _DPI_AWARENESS_INITIALIZED = True
    return _DPI_MODE


def get_monitor_dpi(hmonitor: Any) -> Tuple[int, float]:
    """
    Query DPI and scaling factor for a specific monitor handle.
    Returns (dpi: int, dpi_scale: float). E.g. (96, 1.0) or (144, 1.5).
    """
    if os.name != "nt" or not hmonitor:
        return 96, 1.0

    try:
        shcore = ctypes.windll.shcore
        dpi_x = ctypes.c_uint()
        dpi_y = ctypes.c_uint()
        # MDT_EFFECTIVE_DPI = 0
        hr = shcore.GetDpiForMonitor(hmonitor, 0, ctypes.byref(dpi_x), ctypes.byref(dpi_y))
        if hr == 0 and dpi_x.value > 0:
            dpi = dpi_x.value
            return dpi, round(dpi / 96.0, 2)
    except Exception:
        pass

    return get_system_dpi()


def get_system_dpi() -> Tuple[int, float]:
    """Return primary system DPI and scaling factor."""
    if os.name != "nt":
        return 96, 1.0

    try:
        user32 = ctypes.windll.user32
        if hasattr(user32, "GetDpiForSystem"):
            dpi = user32.GetDpiForSystem()
            if dpi > 0:
                return dpi, round(dpi / 96.0, 2)
    except Exception:
        pass

    return 96, 1.0


def get_monitors() -> List[MonitorInfo]:
    """
    Enumerate all physical display monitors on this machine with exact positions and DPIs.
    """
    enable_dpi_awareness()

    if os.name != "nt":
        return [MonitorInfo(monitor_index=0, x=0, y=0, width=1920, height=1080, is_primary=True, dpi=96, dpi_scale=1.0)]

    monitors: List[MonitorInfo] = []
    user32 = ctypes.windll.user32

    MonitorEnumProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.wintypes.RECT),
        ctypes.c_void_p,
    )

    idx_box = [0]

    def _enum_cb(hmon, hdc, lprect, lparam):
        rect = lprect.contents
        x = rect.left
        y = rect.top
        w = max(1, rect.right - rect.left)
        h = max(1, rect.bottom - rect.top)

        is_primary = (x == 0 and y == 0)
        dpi, scale = get_monitor_dpi(hmon)

        monitors.append(
            MonitorInfo(
                monitor_index=idx_box[0],
                x=x,
                y=y,
                width=w,
                height=h,
                is_primary=is_primary,
                dpi=dpi,
                dpi_scale=scale,
            )
        )
        idx_box[0] += 1
        return True

    try:
        user32.EnumDisplayMonitors(None, None, MonitorEnumProc(_enum_cb), 0)
    except Exception as exc:
        logger.debug("[DpiMapper] Monitor enumeration failed: %s", exc)

    if not monitors:
        # Fallback to system metrics
        w = user32.GetSystemMetrics(0) or 1920
        h = user32.GetSystemMetrics(1) or 1080
        dpi, scale = get_system_dpi()
        monitors.append(
            MonitorInfo(
                monitor_index=0,
                x=0,
                y=0,
                width=w,
                height=h,
                is_primary=True,
                dpi=dpi,
                dpi_scale=scale,
            )
        )

    # Sort primary first, then left-to-right
    monitors.sort(key=lambda m: (0 if m.is_primary else 1, m.x))
    for i, m in enumerate(monitors):
        m.monitor_index = i

    return monitors


def find_monitor_for_rect(
    x: int,
    y: int,
    width: int,
    height: int,
    monitors: List[MonitorInfo],
) -> Tuple[int, MonitorInfo]:
    """
    Determine which monitor contains the majority or center of the given rectangle.
    Returns (monitor_index, MonitorInfo).
    """
    if not monitors:
        fallback = MonitorInfo(monitor_index=0, x=0, y=0, width=1920, height=1080, is_primary=True, dpi=96, dpi_scale=1.0)
        return 0, fallback

    cx = x + width / 2.0
    cy = y + height / 2.0

    # 1. Point containment test
    for m in monitors:
        if m.x <= cx <= m.x + m.width and m.y <= cy <= m.y + m.height:
            return m.monitor_index, m

    # 2. Overlap area test
    best_overlap = -1
    best_mon = monitors[0]
    for m in monitors:
        ox1 = max(x, m.x)
        oy1 = max(y, m.y)
        ox2 = min(x + width, m.x + m.width)
        oy2 = min(y + height, m.y + m.height)
        if ox2 > ox1 and oy2 > oy1:
            area = (ox2 - ox1) * (oy2 - oy1)
            if area > best_overlap:
                best_overlap = area
                best_mon = m

    return best_mon.monitor_index, best_mon


def compute_divided_coordinates(
    x: int,
    y: int,
    width: int,
    height: int,
    mon: MonitorInfo,
) -> Dict[str, Any]:
    """
    Compute proportional coordinates and visual quadrant relative to a specific monitor.
    """
    mw = max(1, mon.width)
    mh = max(1, mon.height)

    # Normalized relative to monitor origin
    rel_x = round((x - mon.x) / mw, 4)
    rel_y = round((y - mon.y) / mh, 4)
    rel_w = round(width / mw, 4)
    rel_h = round(height / mh, 4)

    # Midpoint relative to monitor
    mid_x = (x - mon.x) + width / 2.0
    mid_y = (y - mon.y) + height / 2.0

    if rel_w >= 0.88 and rel_h >= 0.88:
        quadrant = "full"
    elif mid_x < mw / 2.0 and mid_y < mh / 2.0:
        quadrant = "top-left"
    elif mid_x >= mw / 2.0 and mid_y < mh / 2.0:
        quadrant = "top-right"
    elif mid_x < mw / 2.0 and mid_y >= mh / 2.0:
        quadrant = "bottom-left"
    elif mid_x >= mw / 2.0 and mid_y >= mh / 2.0:
        quadrant = "bottom-right"
    else:
        quadrant = "center"

    return {
        "rel_x": rel_x,
        "rel_y": rel_y,
        "rel_width": rel_w,
        "rel_height": rel_h,
        "screen_width": mw,
        "screen_height": mh,
        "quadrant": quadrant,
        "monitor_index": mon.monitor_index,
        "dpi": mon.dpi,
    }


def compute_target_window_rect(
    win: Any,
    target_monitors: Optional[List[MonitorInfo]] = None,
) -> Tuple[int, int, int, int]:
    """
    Calculate (dest_x, dest_y, dest_w, dest_h) on Target B.
    
    Handles:
      • Multi-to-single monitor folding (clamps safely within primary monitor without going off-screen)
      • Single-to-multi monitor placement (preserves monitor index)
      • Multi-to-multi monitor index alignment
      • DPI scaling ratio adjustments
      • Quadrant & proportional boundary scaling
      • Strict on-screen clamping guarantee
    """
    if not target_monitors:
        target_monitors = get_monitors()

    # Determine target monitor
    source_mon_idx = getattr(win, "monitor_index", 0) or 0
    if 0 <= source_mon_idx < len(target_monitors):
        target_mon = target_monitors[source_mon_idx]
    else:
        # Multi-to-single folding: secondary monitor window folded safely onto primary monitor
        target_mon = next((m for m in target_monitors if m.is_primary), target_monitors[0])

    # DPI Scaling
    source_dpi = getattr(win, "dpi", 0) or 96
    target_dpi = target_mon.dpi or 96
    dpi_ratio = target_dpi / source_dpi if source_dpi > 0 else 1.0

    # Proportional coordinates
    rel_w = getattr(win, "rel_width", 0.0) or 0.0
    rel_h = getattr(win, "rel_height", 0.0) or 0.0
    rel_x = getattr(win, "rel_x", 0.0) or 0.0
    rel_y = getattr(win, "rel_y", 0.0) or 0.0

    has_proportional = (rel_w > 0.0 and rel_h > 0.0)

    # Check differences in resolution or DPI
    screen_w = getattr(win, "screen_width", 0) or target_mon.width
    screen_h = getattr(win, "screen_height", 0) or target_mon.height
    diff_res = (screen_w != target_mon.width or screen_h != target_mon.height)
    diff_dpi = abs(dpi_ratio - 1.0) > 0.05
    was_folded = (source_mon_idx >= len(target_monitors))

    if has_proportional and (diff_res or diff_dpi or was_folded):
        dest_w = max(150, int(rel_w * target_mon.width))
        dest_h = max(100, int(rel_h * target_mon.height))
        # Ensure folded windows don't wrap to negative
        norm_x = max(0.0, min(1.0 - rel_w, rel_x)) if was_folded else rel_x
        norm_y = max(0.0, min(1.0 - rel_h, rel_y)) if was_folded else rel_y
        dest_x = target_mon.x + int(norm_x * target_mon.width)
        dest_y = target_mon.y + int(norm_y * target_mon.height)
    else:
        # Fallback using pixel dimensions with DPI scaling
        w_val = getattr(win, "width", 800) or 800
        h_val = getattr(win, "height", 600) or 600
        x_val = getattr(win, "x", 0) or 0
        y_val = getattr(win, "y", 0) or 0

        dest_w = max(150, int(w_val * dpi_ratio))
        dest_h = max(100, int(h_val * dpi_ratio))

        if not was_folded:
            # If coordinates are global, offset by difference
            if x_val >= target_mon.x and x_val < target_mon.x + target_mon.width:
                dest_x = target_mon.x + int((x_val - target_mon.x) * dpi_ratio)
            else:
                dest_x = target_mon.x + int(x_val * dpi_ratio)
            if y_val >= target_mon.y and y_val < target_mon.y + target_mon.height:
                dest_y = target_mon.y + int((y_val - target_mon.y) * dpi_ratio)
            else:
                dest_y = target_mon.y + int(y_val * dpi_ratio)
        else:
            # Window folded from disconnected monitor onto primary
            dest_x = target_mon.x + int(rel_x * target_mon.width) if has_proportional else target_mon.x + 80
            dest_y = target_mon.y + int(rel_y * target_mon.height) if has_proportional else target_mon.y + 80

    # Strict Safety Clamping (Guaranteed 100% On-Screen)
    dest_w = min(dest_w, target_mon.width)
    dest_h = min(dest_h, target_mon.height)
    dest_x = max(target_mon.x, min(target_mon.x + target_mon.width - dest_w, dest_x))
    dest_y = max(target_mon.y, min(target_mon.y + target_mon.height - dest_h, dest_y))

    return int(dest_x), int(dest_y), int(dest_w), int(dest_h)
