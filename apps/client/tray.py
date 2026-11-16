"""
AeroSync Desktop System Tray

Runs in the Windows system tray and provides:
  • Live visual role indicator (Neutral, Host A, Candidate B, Target B)
  • One-click open to the web Dashboard
  • Quick manual triggers for gesture actions (FIST/THROW fallbacks)
  • Clean application shutdown
"""

import logging
import threading
import webbrowser
from typing import Optional, TYPE_CHECKING

from PIL import Image, ImageDraw

if TYPE_CHECKING:
    from apps.client.client_orchestrator import ClientOrchestrator

logger = logging.getLogger(__name__)


def _create_tray_icon_image(color: str = "#00f5d4") -> Image.Image:
    """
    Generate a 64x64 cosmic AeroSync icon with a glowing celestial ring and center node.
    """
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    # Cosmic dark sphere
    draw.ellipse((4, 4, 60, 60), fill=(10, 14, 26, 240), outline=(50, 70, 110, 200), width=2)

    # Glowing orbit ring (ellipse tilted)
    draw.arc((10, 18, 54, 46), start=0, end=360, fill=(0, 245, 212, 220), width=3)

    # Center glowing star node (colored by current state)
    rgb_map = {
        "cyan": (0, 245, 212),     # Neutral / Target
        "gold": (255, 179, 0),     # Host A armed
        "purple": (168, 85, 247),  # Candidate B
        "green": (52, 211, 153),   # Transfer complete
    }
    node_rgb = rgb_map.get(color, (0, 245, 212))

    # Outer glow
    draw.ellipse((26, 26, 38, 38), fill=(*node_rgb, 90))
    # Core node
    draw.ellipse((28, 28, 36, 36), fill=(*node_rgb, 255))

    return image


class AeroSyncTray:
    """
    Manages the Windows System Tray icon for the AeroSync Client.
    """

    def __init__(self, orchestrator: "ClientOrchestrator", dashboard_url: str = "http://localhost:5173"):
        self.orchestrator = orchestrator
        self.dashboard_url = dashboard_url
        self._icon: Optional[object] = None
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the system tray icon in a dedicated daemon thread."""
        try:
            import pystray
        except ImportError:
            logger.warning("[Tray] pystray not installed — running without system tray icon.")
            return

        self._thread = threading.Thread(target=self._run_tray, name="AeroSyncTray", daemon=True)
        self._thread.start()
        logger.info("[Tray] System tray thread started")

    def stop(self) -> None:
        """Stop and remove the tray icon."""
        if self._icon:
            try:
                self._icon.stop()
            except Exception as e:
                logger.debug(f"[Tray] Error stopping icon: {e}")
            self._icon = None

    def update_role(self, state_name: str) -> None:
        """Update icon tooltip and color according to active role state."""
        if not self._icon:
            return

        color_key = "cyan"
        state_lower = (state_name or "").lower()
        if "host" in state_lower:
            color_key = "gold"
        elif "candidate" in state_lower:
            color_key = "purple"
        elif "target" in state_lower or "transferring" in state_lower:
            color_key = "green"

        try:
            self._icon.icon = _create_tray_icon_image(color_key)
            self._icon.title = f"AeroSync — {state_name.upper()}"
        except Exception as e:
            logger.debug(f"[Tray] Could not update icon state: {e}")

    def _run_tray(self) -> None:
        import pystray
        from apps.client.autostart import is_autostart_enabled, toggle_autostart
        from services.chrome_launcher.chrome_manager import launch_normal_chrome
        from apps.client.notification import show_toast

        def on_open_dashboard(icon, item):
            webbrowser.open(self.dashboard_url)

        def on_open_tutorial(icon, item):
            webbrowser.open(f"{self.dashboard_url}/#tutorial")

        def on_launch_chrome(icon, item):
            logger.info("[Tray] Auto-launching normal Chrome")
            launch_normal_chrome([self.dashboard_url], new_window=True)

        def on_toggle_autostart(icon, item):
            new_state = toggle_autostart()
            logger.info("[Tray] Toggle autostart: %s", new_state)
            if new_state:
                show_toast("AeroSync", "Auto-start on Windows login enabled.")
            else:
                show_toast("AeroSync", "Auto-start on Windows login disabled.")

        def on_arm_host(icon, item):
            from services.gesture_engine.gesture_types import GestureType
            logger.info("[Tray] Manual trigger: FIST (Arm Host)")
            self.orchestrator._on_gesture(GestureType.FIST)

        def on_claim_target(icon, item):
            from services.gesture_engine.gesture_types import GestureType
            logger.info("[Tray] Manual trigger: THROW (Claim Target)")
            self.orchestrator._on_gesture(GestureType.THROW)

        def on_reset(icon, item):
            logger.info("[Tray] Manual trigger: Reset Constellation")
            if self.orchestrator._role_machine:
                self.orchestrator._role_machine.notify_transfer_complete()

        def on_exit(icon, item):
            logger.info("[Tray] User selected Exit from system tray")
            icon.stop()
            # Signal orchestrator to stop
            import asyncio
            loop = self.orchestrator._get_loop() if hasattr(self.orchestrator, "_get_loop") else None
            if loop:
                asyncio.run_coroutine_threadsafe(self.orchestrator.stop(), loop)
            else:
                self.orchestrator.is_running = False

        menu = pystray.Menu(
            pystray.MenuItem("AeroSync Constellation", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Open Dashboard", on_open_dashboard, default=True),
            pystray.MenuItem("Walkthrough Tutorial 📖", on_open_tutorial),
            pystray.MenuItem("Launch Normal Chrome 🌐", on_launch_chrome),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem(
                "Start at Windows Login",
                on_toggle_autostart,
                checked=lambda item: is_autostart_enabled(),
            ),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Arm Host Mode (Fist ✊)", on_arm_host),
            pystray.MenuItem("Claim Target Mode (Throw 🚀)", on_claim_target),
            pystray.MenuItem("Reset to Neutral 🔄", on_reset),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Exit AeroSync", on_exit),
        )

        self._icon = pystray.Icon(
            name="AeroSync",
            icon=_create_tray_icon_image("cyan"),
            title="AeroSync — Ready",
            menu=menu,
        )

        self._icon.run()
