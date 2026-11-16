"""
AeroSync Eco-Mode — Throttle Controller

Dynamically adjusts the CPU budget of AeroSync's background services when
the machine transitions from AC power to battery, and restores full
performance when AC power is reconnected.

Throttled services:
  • Gesture Engine  : 15 FPS (normal) → 5 FPS (eco)
  • OS Logger poll  : 1.0 s  (normal) → 4.0 s  (eco)
  • OCR / Screen Reader: enabled (normal) → disabled (eco)

Usage (via ClientOrchestrator):
    ctrl = EcoThrottleController(os_logger=logger, gesture_detector=det)
    ctrl.activate_eco_mode()       # call when battery detected
    ctrl.deactivate_eco_mode()     # call when AC reconnected
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Any, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Eco-Mode state enum
# ---------------------------------------------------------------------------

class EcoMode(Enum):
    NORMAL = auto()   # AC power — full performance
    ECO    = auto()   # Battery — CPU-budget throttled


# ---------------------------------------------------------------------------
# Throttle constants  (mirrors shared/constants.py GESTURE_FPS)
# ---------------------------------------------------------------------------

NORMAL_GESTURE_FPS      = 15
ECO_GESTURE_FPS         = 5

NORMAL_OS_LOGGER_INTERVAL_S = 1.0
ECO_OS_LOGGER_INTERVAL_S    = 4.0

NORMAL_OCR_ENABLED      = True
ECO_OCR_ENABLED         = False


# ---------------------------------------------------------------------------
# EcoThrottleController
# ---------------------------------------------------------------------------

class EcoThrottleController:
    """
    Applies or removes eco-mode throttling on live running AeroSync services.

    Live references to the running service objects must be injected so the
    controller can reach into them and update their operating rates without
    a restart.

    Args:
        os_logger       : OSLogger instance (has `set_interval(s)`)
        gesture_detector: GestureDetector or any object with `set_target_fps(fps)`
                          (optional — gesture engine may not be running in all
                          test/server contexts)
    """

    def __init__(
        self,
        os_logger: Optional[Any] = None,
        gesture_detector: Optional[Any] = None,
    ) -> None:
        self._os_logger = os_logger
        self._gesture_detector = gesture_detector
        self._mode = EcoMode.NORMAL

    # ── Public API ─────────────────────────────────────────────────────────

    @property
    def mode(self) -> EcoMode:
        return self._mode

    @property
    def is_eco_active(self) -> bool:
        return self._mode == EcoMode.ECO

    def activate_eco_mode(self) -> None:
        """Switch to ECO mode — throttle background services for battery life."""
        if self._mode == EcoMode.ECO:
            return   # already throttled; idempotent
        self._mode = EcoMode.ECO
        logger.info("[EcoMode] Activating ECO mode — throttling background services")
        self._apply_gesture_fps(ECO_GESTURE_FPS)
        self._apply_os_logger_interval(ECO_OS_LOGGER_INTERVAL_S)
        self._apply_ocr_enabled(ECO_OCR_ENABLED)
        logger.info(
            "[EcoMode] ECO active — gesture %d fps, logger %.1fs, OCR %s",
            ECO_GESTURE_FPS, ECO_OS_LOGGER_INTERVAL_S, ECO_OCR_ENABLED,
        )

    def deactivate_eco_mode(self) -> None:
        """Switch back to NORMAL mode — restore full performance (AC reconnected)."""
        if self._mode == EcoMode.NORMAL:
            return   # already normal; idempotent
        self._mode = EcoMode.NORMAL
        logger.info("[EcoMode] Deactivating ECO mode — restoring full performance")
        self._apply_gesture_fps(NORMAL_GESTURE_FPS)
        self._apply_os_logger_interval(NORMAL_OS_LOGGER_INTERVAL_S)
        self._apply_ocr_enabled(NORMAL_OCR_ENABLED)
        logger.info(
            "[EcoMode] NORMAL restored — gesture %d fps, logger %.1fs, OCR %s",
            NORMAL_GESTURE_FPS, NORMAL_OS_LOGGER_INTERVAL_S, NORMAL_OCR_ENABLED,
        )

    # ── Internal helpers ───────────────────────────────────────────────────

    def _apply_gesture_fps(self, fps: int) -> None:
        if self._gesture_detector is None:
            logger.debug("[EcoMode] No gesture detector registered — skipping FPS throttle")
            return
        try:
            self._gesture_detector.set_target_fps(fps)
            logger.debug("[EcoMode] Gesture FPS → %d", fps)
        except Exception as exc:
            logger.debug("[EcoMode] Could not set gesture FPS: %s", exc)

    def _apply_os_logger_interval(self, interval_s: float) -> None:
        if self._os_logger is None:
            logger.debug("[EcoMode] No OSLogger registered — skipping interval throttle")
            return
        try:
            self._os_logger.set_interval(interval_s)
            logger.debug("[EcoMode] OSLogger interval → %.1f s", interval_s)
        except Exception as exc:
            logger.debug("[EcoMode] Could not set OSLogger interval: %s", exc)

    def _apply_ocr_enabled(self, enabled: bool) -> None:
        """Toggle the SCREEN_READER_ENABLED flag in shared.constants at runtime."""
        try:
            import shared.constants as _const
            _const.SCREEN_READER_ENABLED = enabled
            logger.debug("[EcoMode] SCREEN_READER_ENABLED → %s", enabled)
        except Exception as exc:
            logger.debug("[EcoMode] Could not toggle OCR flag: %s", exc)
