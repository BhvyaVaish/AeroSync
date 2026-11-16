"""
AeroSync Native Windows Global Hotkey Listener

Provides system-wide keyboard fallback shortcuts when camera sensor or lighting is degraded:
  • Ctrl + Alt + C: Force Host A Capture & Workspace Packing (Equivalent to FIST)
  • Ctrl + Alt + L: Force Target B Claim & Launch/Reconstruction (Equivalent to THROW)
  • Ctrl + Alt + T: Alternative Target B Launch shortcut

Uses native Win32 user32 RegisterHotKey with zero third-party dependencies.
"""

from __future__ import annotations

import ctypes
import logging
import sys
import threading
import time
from typing import Callable, Optional

logger = logging.getLogger(__name__)

HOTKEY_ID_CAPTURE = 1001  # Ctrl + Alt + C
HOTKEY_ID_LAUNCH = 1002   # Ctrl + Alt + L
HOTKEY_ID_LAUNCH_T = 1003 # Ctrl + Alt + T

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
PM_REMOVE = 0x0001


class GlobalHotkeyListener:
    """Listens for global Windows shortcuts in a background daemon thread."""

    def __init__(
        self,
        on_capture: Optional[Callable[[], None]] = None,
        on_launch: Optional[Callable[[], None]] = None,
    ):
        self.on_capture = on_capture
        self.on_launch = on_launch
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self.is_active = False

    def start(self) -> bool:
        """Start listening for global hotkeys."""
        if sys.platform != "win32":
            logger.warning("[Hotkeys] Global hotkeys are only supported on Windows")
            return False

        if self.is_active:
            return True

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            name="AeroSyncGlobalHotkeys",
            daemon=True,
        )
        self._thread.start()
        self.is_active = True
        logger.info("[Hotkeys] Global hotkeys started: Ctrl+Alt+C (Capture), Ctrl+Alt+L (Launch)")
        return True

    def stop(self) -> None:
        """Stop listening and unregister hotkeys."""
        self.is_active = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.0)
        logger.info("[Hotkeys] Global hotkeys stopped")

    def _run_loop(self) -> None:
        """Message loop for Win32 hotkey messages."""
        user32 = ctypes.windll.user32
        from ctypes import wintypes

        # Register hotkeys
        # Ctrl + Alt + C (VK 0x43)
        res_c = user32.RegisterHotKey(None, HOTKEY_ID_CAPTURE, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x43)
        # Ctrl + Alt + L (VK 0x4C)
        res_l = user32.RegisterHotKey(None, HOTKEY_ID_LAUNCH, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x4C)
        # Ctrl + Alt + T (VK 0x54)
        res_t = user32.RegisterHotKey(None, HOTKEY_ID_LAUNCH_T, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, 0x54)

        if not (res_c and (res_l or res_t)):
            logger.warning(
                "[Hotkeys] Could not register all hotkeys (C=%s, L=%s, T=%s). Some may be reserved by another app.",
                bool(res_c), bool(res_l), bool(res_t)
            )

        msg = wintypes.MSG()
        try:
            while not self._stop_event.is_set():
                # Non-blocking message check with 50ms sleep
                while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, PM_REMOVE):
                    if msg.message == WM_HOTKEY:
                        hk_id = msg.wParam
                        if hk_id == HOTKEY_ID_CAPTURE:
                            logger.info("[Hotkeys] Shortcut triggered: Ctrl+Alt+C (Capture Workspace)")
                            if self.on_capture:
                                self.on_capture()
                        elif hk_id in (HOTKEY_ID_LAUNCH, HOTKEY_ID_LAUNCH_T):
                            logger.info("[Hotkeys] Shortcut triggered: Ctrl+Alt+L/T (Launch / Claim Target)")
                            if self.on_launch:
                                self.on_launch()

                    user32.TranslateMessage(ctypes.byref(msg))
                    user32.DispatchMessageW(ctypes.byref(msg))

                time.sleep(0.05)
        finally:
            # Cleanly unregister hotkeys on exit
            user32.UnregisterHotKey(None, HOTKEY_ID_CAPTURE)
            user32.UnregisterHotKey(None, HOTKEY_ID_LAUNCH)
            user32.UnregisterHotKey(None, HOTKEY_ID_LAUNCH_T)
            logger.debug("[Hotkeys] Unregistered Win32 hotkeys")
