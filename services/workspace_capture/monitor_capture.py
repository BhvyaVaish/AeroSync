"""
AeroSync Monitor Capture

Captures monitor layouts (position, resolution, DPI scaling) using ctypes and Shcore.
"""

import logging
from typing import List

from shared.types.workspace_types import MonitorInfo
from services.monitor_mapping.monitor_mapper import get_monitors

logger = logging.getLogger(__name__)


def capture_monitors_sync() -> List[MonitorInfo]:
    """Synchronously enumerate all display monitors with DPI and layout."""
    monitors = get_monitors()
    logger.info("Captured %d monitors with DPI mapping", len(monitors))
    return monitors


async def capture_monitors() -> List[MonitorInfo]:
    """
    Asynchronously enumerate all display monitors and return their layout with DPI.
    
    Returns:
        List of MonitorInfo objects.
    """
    return capture_monitors_sync()
