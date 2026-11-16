"""
AeroSync Eco-Mode — Power Monitor

Polls the Windows SYSTEM_POWER_STATUS struct via GetSystemPowerStatus every
10 seconds and emits on_power_changed callbacks when AC/battery status changes.

PowerStatus:
  is_on_battery  : True if running on battery (ACLineStatus == 0)
  battery_pct    : 0-100% (255 = unknown / desktop)
  is_charging    : True if BatteryFlag has charging bit (8) set

Usage:
    mon = PowerMonitor(on_power_changed=my_callback)
    mon.start()   # background daemon thread
    ...
    mon.stop()
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import logging
import sys
import threading
import time
from dataclasses import dataclass
from typing import Callable, List, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Win32 SYSTEM_POWER_STATUS struct
# ---------------------------------------------------------------------------

class _SYSTEM_POWER_STATUS(ctypes.Structure):
    """Win32 SYSTEM_POWER_STATUS structure (Windows.h)."""
    _fields_ = [
        ("ACLineStatus",        ctypes.c_byte),    # 0=battery, 1=AC, 255=unknown
        ("BatteryFlag",         ctypes.c_byte),    # bit flags (8=charging, 128=no battery)
        ("BatteryLifePercent",  ctypes.c_byte),    # 0-100, 255=unknown
        ("SystemStatusFlag",    ctypes.c_byte),    # Windows 10+: power-saver mode
        ("BatteryLifeTime",     ctypes.wintypes.DWORD),  # seconds remaining, -1=unknown
        ("BatteryFullLifeTime", ctypes.wintypes.DWORD),  # full charge life, -1=unknown
    ]


def _query_power_status() -> Optional["_SYSTEM_POWER_STATUS"]:
    """Call GetSystemPowerStatus; return struct or None on failure."""
    if sys.platform != "win32":
        return None
    try:
        status = _SYSTEM_POWER_STATUS()
        ok = ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(status))
        if ok:
            return status
    except Exception as exc:
        logger.debug("[PowerMonitor] GetSystemPowerStatus failed: %s", exc)
    return None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

@dataclass
class PowerStatus:
    """Snapshot of the current machine power state."""
    is_on_battery: bool    # True → running on battery; False → plugged in
    battery_pct: int       # 0–100 %; 255 means unknown (desktop with no battery)
    is_charging: bool      # True if battery is actively charging


def _build_power_status(raw: Optional[_SYSTEM_POWER_STATUS]) -> PowerStatus:
    """Convert a raw Win32 struct into a PowerStatus dataclass."""
    if raw is None:
        # Fallback: assume AC power (safe default — no throttling)
        return PowerStatus(is_on_battery=False, battery_pct=255, is_charging=False)

    ac_line      = raw.ACLineStatus           # 0=battery, 1=AC, 255=unknown
    batt_flag    = raw.BatteryFlag            # 8=charging, 128=no battery
    batt_pct     = raw.BatteryLifePercent     # 0–100 or 255

    is_on_battery = (ac_line == 0)
    is_charging   = bool(batt_flag & 0x08)   # Charging bit

    return PowerStatus(
        is_on_battery=is_on_battery,
        battery_pct=int(batt_pct),
        is_charging=is_charging,
    )


class PowerMonitor:
    """
    Background daemon that polls GetSystemPowerStatus every `poll_interval_s`
    seconds and fires registered callbacks when the power state changes.

    Thread-safe. Can be started and stopped multiple times.
    """

    def __init__(
        self,
        on_power_changed: Optional[Callable[[PowerStatus], None]] = None,
        poll_interval_s: float = 10.0,
    ) -> None:
        self._callbacks: List[Callable[[PowerStatus], None]] = []
        if on_power_changed:
            self._callbacks.append(on_power_changed)

        self._poll_interval_s = poll_interval_s
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._last_status: Optional[PowerStatus] = None

    # ── Public API ─────────────────────────────────────────────────────────

    def register_callback(self, cb: Callable[[PowerStatus], None]) -> None:
        """Add a callback to be notified on power state transitions."""
        if cb not in self._callbacks:
            self._callbacks.append(cb)

    def start(self) -> None:
        """Start background polling thread (idempotent)."""
        if self._running:
            return
        self._running = True
        # Capture initial status immediately so callers can read current_status
        self._last_status = _build_power_status(_query_power_status())
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="AeroSyncPowerMonitor",
            daemon=True,
        )
        self._thread.start()
        logger.info(
            "[PowerMonitor] Started — battery=%s, pct=%d%%, charging=%s",
            self._last_status.is_on_battery,
            self._last_status.battery_pct,
            self._last_status.is_charging,
        )

    def stop(self) -> None:
        """Stop the background polling thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
        logger.info("[PowerMonitor] Stopped")

    @property
    def current_status(self) -> PowerStatus:
        """Return the most recently polled power status (never None after start)."""
        if self._last_status is None:
            # Lazily initialize if read before start()
            self._last_status = _build_power_status(_query_power_status())
        return self._last_status

    @property
    def is_eco_mode_active(self) -> bool:
        """True when the machine is on battery power (eco-mode should be on)."""
        return self.current_status.is_on_battery

    # ── Internal ───────────────────────────────────────────────────────────

    def _poll_loop(self) -> None:
        while self._running:
            time.sleep(self._poll_interval_s)
            if not self._running:
                break
            try:
                raw = _query_power_status()
                new_status = _build_power_status(raw)
                prev = self._last_status
                if prev is None or new_status.is_on_battery != prev.is_on_battery:
                    logger.info(
                        "[PowerMonitor] Power state changed: battery=%s → battery=%s",
                        prev.is_on_battery if prev else "?",
                        new_status.is_on_battery,
                    )
                    self._last_status = new_status
                    self._fire_callbacks(new_status)
                else:
                    self._last_status = new_status
            except Exception as exc:
                logger.debug("[PowerMonitor] Poll error: %s", exc)

    def _fire_callbacks(self, status: PowerStatus) -> None:
        for cb in list(self._callbacks):
            try:
                cb(status)
            except Exception as exc:
                logger.debug("[PowerMonitor] Callback error: %s", exc)
