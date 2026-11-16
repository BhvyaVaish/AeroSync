"""
AeroSync Desktop Camera Widget

Floating, unobtrusive picture-in-picture camera widget docked in the bottom-right
corner of the Windows screen.
Displays the live camera view cleanly without cluttering the feed with mathematical
nodes or joint lines (which are computed invisibly by the computer).
"""

import logging
import threading
import time
from typing import Optional

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class DesktopCameraWidget:
    """
    Renders a clean picture-in-picture camera preview window pinned to the
    bottom-right corner of the primary display.
    """

    def __init__(
        self,
        window_title: str = "AeroSync Camera",
        width: int = 280,
        height: int = 210,
        margin: int = 25,
    ):
        self.window_title = window_title
        self.width = width
        self.height = height
        self.margin = margin
        self.is_running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self, get_frame_callback, get_status_callback=None):
        """Start the camera widget display loop in a separate thread."""
        if self.is_running:
            return
        self.is_running = True
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run_widget,
            args=(get_frame_callback, get_status_callback),
            daemon=True,
        )
        self._thread.start()
        logger.info("Desktop Camera Widget started.")

    def stop(self):
        """Stop the camera widget."""
        self.is_running = False
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=1.5)
        try:
            cv2.destroyWindow(self.window_title)
        except Exception:
            pass
        logger.info("Desktop Camera Widget stopped.")

    def _run_widget(self, get_frame_callback, get_status_callback):
        """Widget loop running on thread."""
        try:
            import ctypes
            user32 = ctypes.windll.user32
            screen_w = user32.GetSystemMetrics(0)
            screen_h = user32.GetSystemMetrics(1)
            # Dock in bottom-right corner
            pos_x = max(0, screen_w - self.width - self.margin)
            pos_y = max(0, screen_h - self.height - self.margin - 40) # 40px taskbar buffer

            cv2.namedWindow(self.window_title, cv2.WINDOW_NORMAL)
            cv2.resizeWindow(self.window_title, self.width, self.height)
            cv2.moveWindow(self.window_title, pos_x, pos_y)

            # Keep window on top (HWND_TOPMOST = -1, SWP_NOMOVE = 0x0002, SWP_NOSIZE = 0x0001)
            try:
                hwnd = user32.FindWindowW(None, self.window_title)
                if hwnd:
                    user32.SetWindowPos(hwnd, -1, pos_x, pos_y, self.width, self.height, 0x0040)
            except Exception:
                pass

            while not self._stop_event.is_set():
                frame = get_frame_callback()
                if frame is None:
                    # Black placeholder
                    display = np.zeros((self.height, self.width, 3), dtype=np.uint8)
                    cv2.putText(
                        display,
                        "Camera Starting...",
                        (20, self.height // 2),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.5,
                        (180, 180, 180),
                        1,
                    )
                else:
                    # Clean video frame (NO visible landmark nodes / lines!)
                    display = cv2.resize(frame, (self.width, self.height), interpolation=cv2.INTER_AREA)

                # Add a subtle, sleek status bar at bottom of widget
                status_text = "Tracking: Active"
                status_color = (0, 220, 100) # Green
                if get_status_callback:
                    try:
                        st = get_status_callback()
                        if st.get("hands_detected", 0) > 0:
                            status_text = "Hand Locked • Ready"
                            status_color = (0, 255, 120)
                        else:
                            status_text = "Scanning for Gestures"
                            status_color = (200, 150, 50)
                    except Exception:
                        pass

                # Draw minimal dark overlay strip at bottom
                cv2.rectangle(display, (0, self.height - 24), (self.width, self.height), (15, 15, 25), -1)
                # Status indicator dot
                cv2.circle(display, (12, self.height - 12), 4, status_color, -1)
                cv2.putText(
                    display,
                    status_text,
                    (24, self.height - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.38,
                    (230, 230, 240),
                    1,
                    cv2.LINE_AA,
                )

                cv2.imshow(self.window_title, display)
                key = cv2.waitKey(30)
                if key == 27: # Esc closes widget
                    break

        except Exception as e:
            logger.warning(f"Desktop Camera Widget encountered error: {e}")
        finally:
            try:
                cv2.destroyWindow(self.window_title)
            except Exception:
                pass
            self.is_running = False
