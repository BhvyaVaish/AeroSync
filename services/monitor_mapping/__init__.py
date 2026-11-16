"""
AeroSync Monitor Mapping & DPI Normalization Package
"""

from services.monitor_mapping.monitor_mapper import (
    enable_dpi_awareness,
    get_monitor_dpi,
    get_system_dpi,
    get_monitors,
    find_monitor_for_rect,
    compute_divided_coordinates,
    compute_target_window_rect,
)

__all__ = [
    "enable_dpi_awareness",
    "get_monitor_dpi",
    "get_system_dpi",
    "get_monitors",
    "find_monitor_for_rect",
    "compute_divided_coordinates",
    "compute_target_window_rect",
]
