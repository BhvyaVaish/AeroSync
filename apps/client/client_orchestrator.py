"""
AeroSync Client Orchestrator  (v2 — Unified Role Machine)

Every PC runs the SAME application. Roles (Host A / Target B) are assigned
dynamically by gesture events, coordinated through the Constellation Role
State Machine.

Flow:
  1. App starts → NEUTRAL state
  2. FIST detected → this PC becomes HOST A, all peers become CANDIDATE
  3. A CANDIDATE PC detects THROW → becomes TARGET B, requests data from A
  4. Host A captures workspace (OS log + screen) and streams it to B
  5. Target B reconstructs the workspace
  6. Transfer complete → constellation-wide RESET, all PCs → NEUTRAL

The OS Logger runs continuously in the background (1 Hz) on all PCs so that
when a FIST fires, the log stack is already pre-populated and capture is fast.
"""

import asyncio
import logging
from typing import Dict, Any, Optional

from apps.client import storage
from apps.client.relay_client import RelayClient
from apps.client.notification import show_toast
from apps.client.transfer_sender import send_workspace
from apps.client.transfer_receiver import receive_workspace
from services.gesture_engine.gesture_api import start_gesture_detection, stop_gesture_detection, get_detector
from services.gesture_engine.gesture_types import GestureType
from services.gesture_engine.role_state_machine import RoleStateMachine
from services.workspace_logger.log_stack import WorkspaceLogQueue
from services.workspace_logger.os_logger import OSLogger
from apps.client.tray import AeroSyncTray
from apps.client.hotkeys import GlobalHotkeyListener
from services.lan_transfer.lan_p2p import LanP2PReceiver
from services.eco_mode.power_monitor import PowerMonitor, PowerStatus
from services.eco_mode.eco_throttle import EcoThrottleController

logger = logging.getLogger(__name__)


class ClientOrchestrator:
    def __init__(self):
        self.relay = RelayClient()
        self.is_running = False

        # Pre-populated by OS logger; available instantly when FIST fires
        self._log_queue = WorkspaceLogQueue(max_size=500)
        self._os_logger = OSLogger(queue=self._log_queue, interval_s=1.0)

        # Role state machine (initialised in start() after device_id is known)
        self._role_machine: Optional[RoleStateMachine] = None

        # Active screen region (None = full screen)
        self._screen_region = None

        # Windows system tray
        self._tray = AeroSyncTray(self)

        # Global hotkey fallback listener (Ctrl+Alt+C to Capture, Ctrl+Alt+L to Launch, Ctrl+Alt+Z to Undo)
        self._hotkeys = GlobalHotkeyListener(
            on_capture=self._on_hotkey_capture,
            on_launch=self._on_hotkey_launch,
            on_undo=self._on_hotkey_undo,
        )

        # Direct LAN P2P Socket Receiver (Zero-Cloud Gigabit Transfer)
        self._lan_receiver = LanP2PReceiver(on_payload_received=self._on_lan_p2p_received)

        # ── Eco-Mode Battery Throttling ───────────────────────────────────────
        self._eco_controller = EcoThrottleController(
            os_logger=self._os_logger,
            gesture_detector=get_detector(),
        )
        self._power_monitor = PowerMonitor(on_power_changed=self._on_power_changed)

    # ──────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ──────────────────────────────────────────────────────────────────────────

    async def start(self):
        """Start the orchestrator."""
        self.is_running = True
        logger.info("Starting Client Orchestrator...")

        # 1. Auth check
        if not storage.get_token():
            logger.warning("Not logged in. Please use the frontend UI to login.")
            show_toast("AeroSync", "Please login via the Dashboard.")
            return

        # 2. Device check
        device_id = storage.get_device_id()
        if not device_id:
            logger.warning("Device not registered. Please register via Dashboard.")
            show_toast("AeroSync", "Please register this device via the Dashboard.")
            return

        # 3. Set up Role State Machine
        constellation_id = storage.get_constellation_id() if hasattr(storage, "get_constellation_id") else None
        self._role_machine = RoleStateMachine(
            device_id=device_id,
            constellation_id=constellation_id,
            send_ws=self._send_ws_message,
            on_become_host=self._on_become_host,
            on_become_target=self._on_become_target,
            on_reset=self._on_constellation_reset,
        )

        # 4. Start OS Logger (background, continuous 1 Hz polling)
        self._log_queue.source_device_id = device_id
        self._os_logger.start()
        logger.info("OS Logger started — building workspace log stack...")

        # 5. Start Direct Gigabit LAN P2P Receiver
        try:
            await self._lan_receiver.start()
            if self._role_machine:
                self._role_machine.lan_endpoint = self._lan_receiver.endpoint
        except Exception as e:
            logger.debug("[LanP2P] Could not start LAN receiver: %s", e)

        # 6. Connect WebSocket
        await self.relay.connect_ws(self._on_ws_message)

        # 7. Start Gesture Engine
        try:
            start_gesture_detection(self._on_gesture)
            logger.info("Gesture detection started.")
            show_toast("AeroSync", "Client running. Make a FIST to become Host ✊")
        except Exception as e:
            logger.error("Failed to start gesture engine: %s", e)
            show_toast("AeroSync Error", "Could not start camera.")

        # 8. Start System Tray icon
        try:
            self._tray.start()
        except Exception as e:
            logger.debug("Failed to start system tray icon: %s", e)

        # 9. Start Global Hotkey Fallback Listener (Ctrl+Alt+C, Ctrl+Alt+L)
        try:
            self._hotkeys.start()
        except Exception as e:
            logger.debug("Failed to start global hotkeys: %s", e)

        # 10. Start Eco-Mode Power Monitor (battery throttling daemon)
        try:
            self._power_monitor.start()
            # Apply eco-mode immediately if already on battery at startup
            if self._power_monitor.is_eco_mode_active:
                self._on_power_changed(self._power_monitor.current_status)
            logger.info("[EcoMode] Power monitor started — battery=%s",
                        self._power_monitor.current_status.is_on_battery)
        except Exception as e:
            logger.debug("[EcoMode] Failed to start power monitor: %s", e)

        # Keep running until stopped
        while self.is_running:
            await asyncio.sleep(1)

    async def stop(self):
        """Stop the orchestrator."""
        self.is_running = False
        self._os_logger.stop()
        stop_gesture_detection()
        self._hotkeys.stop()
        try:
            self._power_monitor.stop()
        except Exception:
            pass
        try:
            await self._lan_receiver.stop()
        except Exception:
            pass
        await self.relay.close_ws()
        self._tray.stop()
        logger.info("Client Orchestrator stopped.")

    # ──────────────────────────────────────────────────────────────────────────
    # Gesture & Hotkey handlers
    # ──────────────────────────────────────────────────────────────────────────

    def _on_gesture(self, gesture: GestureType) -> None:
        """
        Called by the gesture engine on a background thread.
        Dispatches to the role state machine (which is thread-safe).
        """
        logger.info("Gesture detected: %s", gesture.value)
        if gesture == GestureType.UNDO:
            self._trigger_workspace_undo()
            return
        if self._role_machine:
            self._role_machine.on_gesture(gesture)

    def _trigger_workspace_undo(self) -> None:
        """Triggered via UNDO gesture (Peace/V-Sign or Left Swipe) or Ctrl+Alt+Z."""
        logger.info("[Undo] Triggering Workspace Rollback")
        from services.workspace_reconstructor.rollback_manager import get_rollback_manager
        mgr = get_rollback_manager()
        asyncio.run_coroutine_threadsafe(mgr.rollback_last_workspace(), self._get_loop())

    def _on_hotkey_capture(self) -> None:
        """Triggered via Ctrl+Alt+C global shortcut (fallback for camera/sensor failure)."""
        logger.info("[Hotkey] Shortcut Ctrl+Alt+C pressed -> Triggering Host A Capture")
        self._on_gesture(GestureType.FIST)

    def _on_hotkey_launch(self) -> None:
        """Triggered via Ctrl+Alt+L/T global shortcut (fallback for camera/sensor failure)."""
        logger.info("[Hotkey] Shortcut Ctrl+Alt+L pressed -> Triggering Target B Claim/Launch")
        self._on_gesture(GestureType.THROW)

    def _on_hotkey_undo(self) -> None:
        """Triggered via Ctrl+Alt+Z global shortcut."""
        logger.info("[Hotkey] Shortcut Ctrl+Alt+Z pressed -> Triggering Workspace Rollback")
        self._trigger_workspace_undo()

    def _on_power_changed(self, status: PowerStatus) -> None:
        """
        Called by PowerMonitor whenever AC/battery status transitions.
        Activates or deactivates eco-mode throttling accordingly.
        """
        if status.is_on_battery:
            logger.info(
                "[EcoMode] Battery detected (pct=%d%%) — activating eco throttle",
                status.battery_pct,
            )
            self._eco_controller.activate_eco_mode()
            self._tray.update_eco_mode(True)
            from apps.client.notification import show_toast
            show_toast(
                "AeroSync ⚡ Eco Mode",
                f"Running on battery ({status.battery_pct}%) — gesture & logger throttled to save power.",
            )
        else:
            logger.info("[EcoMode] AC power restored — deactivating eco throttle")
            self._eco_controller.deactivate_eco_mode()
            self._tray.update_eco_mode(False)
            from apps.client.notification import show_toast
            show_toast("AeroSync ⚡ Eco Mode", "AC power restored — full performance resumed.")

    # ──────────────────────────────────────────────────────────────────────────
    # Role State Machine callbacks
    # ──────────────────────────────────────────────────────────────────────────

    def _on_become_host(self, is_selective: bool = False) -> None:
        """
        This PC just became Host A (FIST gesture confirmed).
        If short hold: captures and transfers everything.
        If long hold: opens checklist popup for selective beam.
        """
        self._tray.update_role("Host A")

        if is_selective:
            logger.info("🤜 Became HOST A (Long Fist Hold) — opening checklist popup")
            try:
                from services.audio.cosmic_audio import play_fist_long_sound
                play_fist_long_sound()
            except Exception:
                pass
            show_toast("AeroSync — Selective Beam", "Long fist held! Opening checklist popup 📋")
            # Open Dashboard checklist popup
            import webbrowser
            webbrowser.open("http://localhost:5173/#checklist")
        else:
            logger.info("🤜 Became HOST A (Short Fist Hold) — transferring everything")
            try:
                from services.audio.cosmic_audio import play_fist_detect_sound
                play_fist_detect_sound()
            except Exception:
                pass
            show_toast("AeroSync", "You are Host A — capturing all workspace ✊")

        # Schedule capture as an asyncio task
        asyncio.run_coroutine_threadsafe(self._capture_host_workspace(), self._get_loop())

    def _on_become_target(self, host_device_id: str) -> None:
        """
        This PC just became Target B (THROW gesture confirmed).
        The relay will stream workspace data from host_device_id.
        """
        logger.info("🎯 Became TARGET B — waiting for workspace from %s", host_device_id)
        show_toast("AeroSync", "You are Target B — workspace arriving 🚀")
        self._tray.update_role("Target B")

    def _on_constellation_reset(self) -> None:
        """All PCs back to NEUTRAL after a completed transfer."""
        logger.info("🔄 Constellation reset — back to NEUTRAL")
        show_toast("AeroSync", "Transfer done! All PCs ready ✅")
        self._tray.update_role("Neutral")

    # ──────────────────────────────────────────────────────────────────────────
    # WebSocket message handling
    # ──────────────────────────────────────────────────────────────────────────

    def _on_ws_message(self, message: Dict[str, Any]) -> None:
        """Handle incoming WebSocket messages (from relay server)."""
        msg_type = message.get("type", "")

        # Delegate constellation role messages to the state machine
        if self._role_machine and msg_type in (
            "host_announcing",
            "target_claiming",
            "constellation_reset",
            "workspace_ready",
        ):
            self._role_machine.on_ws_message(message)
            if msg_type == "host_announcing":
                self._tray.update_role("Candidate B")
            elif msg_type == "constellation_reset":
                self._tray.update_role("Neutral")

        # Incoming transfer notification from relay server
        elif msg_type in ("incoming_transfer", "transfer_incoming"):
            transfer_id = message.get("transfer_id")
            source_name = message.get("source_device_name", "Unknown Device")
            logger.info("Received transfer from %s: %s", source_name, transfer_id)
            asyncio.ensure_future(self._handle_incoming_transfer(transfer_id))

        # workspace_transfer: actual payload delivery for Target B
        elif msg_type == "workspace_transfer":
            transfer_id = message.get("transfer_id")
            if transfer_id:
                asyncio.ensure_future(self._handle_incoming_transfer(transfer_id))

        # Constellation synchronization
        elif msg_type == "constellation_joined":
            c_id = message.get("constellation_id")
            if c_id:
                storage.set_constellation_id(c_id)
                if self._role_machine:
                    self._role_machine.set_constellation(c_id)
                logger.info("Joined constellation via WS: %s", c_id)

        elif msg_type == "constellation_left":
            storage.clear_constellation_id()
            if self._role_machine:
                self._role_machine.set_constellation(None)
            logger.info("Left constellation via WS")

        elif msg_type == "connected":
            # Initial handshake — sync active constellation if server provided it
            c_info = message.get("constellation")
            if c_info and isinstance(c_info, dict):
                c_id = c_info.get("id")
                if c_id:
                    storage.set_constellation_id(c_id)
                    if self._role_machine:
                        self._role_machine.set_constellation(c_id)
                    logger.info("Synchronized constellation: %s (%s)", c_info.get("name"), c_id)

    def _send_ws_message(self, message: Dict[str, Any]) -> None:
        """Send a message to relay (called by RoleStateMachine)."""
        asyncio.run_coroutine_threadsafe(
            self.relay.send_ws(message), self._get_loop()
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Host A — workspace capture and send
    # ──────────────────────────────────────────────────────────────────────────

    async def _capture_host_workspace(self) -> None:
        """
        Triggered when this PC becomes Host A.
        Captures workspace (OS log already warm) + screen, waits for Target B
        to announce, then sends.
        """
        try:
            # Build exclusion set from live log stack (already pre-populated)
            exclusion_set = self._log_queue.exclusion_set
            logger.info("Log stack has %d entries, %d exclusion tokens", self._log_queue.size, len(exclusion_set))

            # Let region selector run (user may crop)
            region = self._screen_region  # Could be pre-set from UI

            # Send workspace — will block until Target B claims and receives
            # The role machine transitions us to AWAITING_TARGET and then
            # TRANSFERRING when target_claiming arrives
            my_id = storage.get_device_id()
            # Wait up to 60s for a target to claim
            for _ in range(60):
                if self._role_machine and self._role_machine.state == "transferring":
                    break
                await asyncio.sleep(1)
            else:
                logger.warning("No Target B claimed within 60s — aborting capture")
                show_toast("AeroSync", "No target claimed — make a THROW on another PC")
                self._role_machine._reset_to_neutral() if self._role_machine else None
                return

            # Retrieve target device ID determined by target_claiming
            target_device_id = self._role_machine.target_device_id if self._role_machine else None
            if not target_device_id:
                logger.error("Target device ID unknown — cannot initiate transfer")
                show_toast("AeroSync Error", "Target device unknown.")
                if self._role_machine:
                    self._role_machine._reset_to_neutral()
                return

            logger.info("Host A sending workspace to Target B (%s)", target_device_id)
            lan_endpoint = self._role_machine.target_lan_endpoint if self._role_machine else None
            await send_workspace(
                relay=self.relay,
                target_device_id=target_device_id,
                region=region,
                log_stack=self._log_queue,
                log_exclusion_set=exclusion_set,
                target_lan_endpoint=lan_endpoint,
            )

        except Exception as exc:
            logger.error("Host workspace capture failed: %s", exc)
            show_toast("AeroSync Error", "Workspace capture failed.")

    async def _on_lan_p2p_received(self, transfer_id: str, aes_key: bytes, payload_bytes: bytes) -> None:
        """Invoked when workspace payload arrives directly over local LAN socket (Zero-Cloud Gigabit)."""
        logger.info("[LanP2P] Received direct LAN payload for %s (%d bytes)", transfer_id, len(payload_bytes))
        try:
            from services.workspace_packager.packager import unpack_package
            from services.workspace_reconstructor.reconstruction_orchestrator import reconstruct_workspace
            from services.audio.cosmic_audio import play_throw_received_sound

            show_toast("AeroSync ⚡", "Direct LAN Gigabit Beam received! Reconstructing…")
            snapshot = unpack_package(payload_bytes, aes_key)
            report = await reconstruct_workspace(snapshot, transfer_id=transfer_id)
            try:
                play_throw_received_sound()
            except Exception:
                pass

            if report.success and self._role_machine:
                self._role_machine.notify_transfer_complete()
        except Exception as exc:
            logger.error("[LanP2P] Failed to reconstruct direct LAN payload: %s", exc)

    async def _handle_incoming_transfer(self, transfer_id: str) -> None:
        """Target B receives and reconstructs a workspace transfer."""
        try:
            success = await receive_workspace(self.relay, transfer_id)
            # After successful reconstruction, signal constellation reset
            if success and self._role_machine:
                self._role_machine.notify_transfer_complete()
        except Exception as exc:
            logger.error("Workspace transfer failed: %s", exc)

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _get_loop(self) -> asyncio.AbstractEventLoop:
        try:
            return asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop
