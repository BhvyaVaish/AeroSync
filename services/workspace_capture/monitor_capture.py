"""
AeroSync Monitor Capture

Captures monitor layouts (position, resolution) using ctypes.
"""

import ctypes
import ctypes.wintypes
import logging
from typing import List

from shared.types.workspace_types import MonitorInfo

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32


async def capture_monitors() -> List[MonitorInfo]:
    """
    Enumerate all display monitors and return their layout.
    
    Returns:
        List of MonitorInfo objects.
    """
    monitors: List[MonitorInfo] = []
    
    # Callback type: HMONITOR, HDC, LPRECT, LPARAM
    MonitorEnumProc = ctypes.WINFUNCTYPE(
        ctypes.c_bool, ctypes.c_void_p, ctypes.c_void_p, ctypes.POINTER(ctypes.wintypes.RECT), ctypes.c_void_p
    )
    
    # We'll use a closure to keep track of monitor index
    index_container = [0]
    
    def callback(hmonitor, hdc, lprect, lparam):
        rect = lprect.contents
        x = rect.left
        y = rect.top
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        
        # Primary monitor always has (0,0) as its top-left coordinate in Windows
        is_primary = (x == 0 and y == 0)
        
        monitors.append(MonitorInfo(
            monitor_index=index_container[0],
            x=x,
            y=y,
            width=w,
            height=h,
            is_primary=is_primary
        ))
        
        index_container[0] += 1
        return True

    # Enumerate monitors
    user32.EnumDisplayMonitors(None, None, MonitorEnumProc(callback), 0)
    
    logger.info(f"Captured {len(monitors)} monitors")
    return monitors
