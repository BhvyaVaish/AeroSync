"""
AeroSync — Constellation Role State Machine

Every PC in a Constellation runs the same application and starts in the
NEUTRAL state.  Roles (Host A / Target B) are assigned dynamically by
gesture:

    NEUTRAL ──(FIST detected)──► HOST
    HOST ────(peers notified)──► AWAITING_TARGET
    NEUTRAL ──(host_announcing arrives)──► CANDIDATE
    CANDIDATE ─(THROW detected)──► TARGET
    TARGET ──(transfer complete)──► NEUTRAL  (all PCs reset together)

State transition diagram:
─────────────────────────────────────────────────────────────────────────
  ┌─────────┐  fist gesture     ┌──────────────────┐
  │ NEUTRAL │──────────────────►│ HOST_CAPTURING   │
  └────┬────┘                   └────────┬─────────┘
       │  host_announcing rcvd           │  capture done
       │                                 ▼
       ▼                        ┌──────────────────┐
  ┌─────────────┐               │ AWAITING_TARGET  │
  │  CANDIDATE  │◄──────────────┤  (broadcast)     │
  └──────┬──────┘  notified     └──────────────────┘
         │  throw gesture
         ▼
  ┌──────────────────┐           ┌──────────────────┐
  │ TARGET_CLAIMING  │──────────►│ RECONSTRUCTING   │
  └──────────────────┘ data rcvd└────────┬─────────┘
                                         │  done
                                         ▼
                                    ← all NEUTRAL →
─────────────────────────────────────────────────────────────────────────

Usage:
    machine = ConstellationRoleMachine(device_id=my_id, send_ws=relay_send_fn)
    machine.on_gesture(GestureType.FIST)
    machine.on_ws_message({"type": "host_announcing", "device_id": "abc"})
    machine.on_gesture(GestureType.THROW)
"""

import asyncio
import logging
import time
from enum import Enum
from typing import Callable, Dict, Any, Optional

from services.gesture_engine.gesture_types import GestureType
from shared.constants import WsMessageType, RoleState

logger = logging.getLogger(__name__)


class RoleStateMachine:
    """
    Tracks the current PC's role in its constellation and drives transitions
    based on gesture events and incoming WebSocket messages.

    Parameters
    ----------
    device_id : str
        This PC's registered device ID.
    send_ws : Callable[[dict], None]
        Coroutine or sync function to send a message to the relay server
        (which then fans it out to all constellation peers).
    on_become_host : Optional[Callable]
        Called when this PC becomes Host A.  Should trigger workspace capture.
    on_become_target : Optional[Callable[[str], None]]
        Called when this PC becomes Target B.  Argument = host device_id.
    on_reset : Optional[Callable]
        Called when constellation resets to NEUTRAL.
    """

    def __init__(
        self,
        device_id: str,
        constellation_id: Optional[str],
        send_ws: Callable[[Dict[str, Any]], None],
        on_become_host: Optional[Callable] = None,
        on_become_target: Optional[Callable[[str], None]] = None,
        on_reset: Optional[Callable] = None,
    ):
        self.device_id = device_id
        self.constellation_id = constellation_id
        self.send_ws = send_ws
        self.on_become_host = on_become_host
        self.on_become_target = on_become_target
        self.on_reset = on_reset

        self._state: str = RoleState.NEUTRAL
        self._host_device_id: Optional[str] = None  # which peer is currently Host A
        self._target_device_id: Optional[str] = None  # which peer is currently Target B
        self._last_fist_time: float = 0.0
        self._last_throw_time: float = 0.0
        self._gesture_cooldown_s: float = 2.5

        # Direct LAN P2P endpoints
        self.lan_endpoint: Optional[Dict[str, Any]] = None
        self.target_lan_endpoint: Optional[Dict[str, Any]] = None

    # ──────────────────────────────────────────────────────────────
    # Public API
    # ──────────────────────────────────────────────────────────────

    @property
    def state(self) -> str:
        return self._state

    @property
    def host_device_id(self) -> Optional[str]:
        return self._host_device_id

    @property
    def target_device_id(self) -> Optional[str]:
        return self._target_device_id

    def on_gesture(self, gesture: GestureType) -> None:
        """
        Called by the gesture classifier when a confirmed gesture fires.
        Only gestures that are valid for the current state are acted upon.
        """
        now = time.monotonic()

        if gesture == GestureType.FIST:
            self._handle_fist(now, is_selective=False)

        elif gesture == GestureType.FIST_LONG:
            self._handle_fist(now, is_selective=True)

        elif gesture == GestureType.THROW:
            self._handle_throw(now)

    def on_ws_message(self, message: Dict[str, Any]) -> None:
        """
        Handle a WebSocket message from a constellation peer (via relay server).
        """
        msg_type = message.get("type")

        if msg_type == WsMessageType.HOST_ANNOUNCING:
            self._handle_host_announcing(message)

        elif msg_type == WsMessageType.TARGET_CLAIMING:
            self._handle_target_claiming(message)

        elif msg_type == WsMessageType.CONSTELLATION_RESET:
            self._handle_reset()

        elif msg_type == WsMessageType.WORKSPACE_READY:
            # Host signals workspace data is packaged and ready to stream
            self._handle_workspace_ready(message)

    def notify_transfer_complete(self) -> None:
        """Call this after the workspace has been fully reconstructed on Target B."""
        logger.info("[RoleSM] Transfer complete — broadcasting constellation reset")
        self._emit({
            "type": WsMessageType.CONSTELLATION_RESET,
            "source_device_id": self.device_id,
            "constellation_id": self.constellation_id,
        })
        self._reset_to_neutral()

    def set_constellation(self, constellation_id: str) -> None:
        """Update the active constellation ID (called after join/create)."""
        self.constellation_id = constellation_id

    # ──────────────────────────────────────────────────────────────
    # Gesture handlers
    # ──────────────────────────────────────────────────────────────

    def _handle_fist(self, now: float, is_selective: bool = False) -> None:
        """FIST gesture → this PC claims Host A role. is_selective=True if long hold."""
        if self._state != RoleState.NEUTRAL:
            logger.debug(
                "[RoleSM] FIST ignored — current state is %s (not NEUTRAL)", self._state
            )
            return

        if now - self._last_fist_time < self._gesture_cooldown_s:
            logger.debug("[RoleSM] FIST ignored — cooldown active")
            return

        if not self.constellation_id:
            logger.warning("[RoleSM] FIST ignored — not in a constellation")
            return

        self._last_fist_time = now
        self._host_device_id = self.device_id
        self._transition(RoleState.HOST)

        logger.info(
            "[RoleSM] 🤜 FIST detected (%s hold) — this PC is now HOST A",
            "LONG" if is_selective else "SHORT"
        )

        # Broadcast to all peers so they switch to CANDIDATE
        self._emit({
            "type": WsMessageType.HOST_ANNOUNCING,
            "device_id": self.device_id,
            "constellation_id": self.constellation_id,
            "is_selective": is_selective,
        })

        # Trigger workspace capture on this PC
        if self.on_become_host:
            try:
                self.on_become_host(is_selective=is_selective)
            except TypeError:
                self.on_become_host()
            except Exception as exc:
                logger.error("[RoleSM] on_become_host callback failed: %s", exc)

    def _handle_throw(self, now: float) -> None:
        """THROW gesture → this PC claims Target B role."""
        if self._state != RoleState.CANDIDATE:
            logger.debug(
                "[RoleSM] THROW ignored — current state is %s (need CANDIDATE)", self._state
            )
            return

        if now - self._last_throw_time < self._gesture_cooldown_s:
            logger.debug("[RoleSM] THROW ignored — cooldown active")
            return

        if not self._host_device_id:
            logger.warning("[RoleSM] THROW ignored — no known Host A")
            return

        self._last_throw_time = now
        self._transition(RoleState.TARGET)

        logger.info(
            "[RoleSM] 🤚→ THROW detected — this PC is now TARGET B (host=%s)",
            self._host_device_id,
        )

        # Notify relay/host that we're claiming Target B
        msg = {
            "type": WsMessageType.TARGET_CLAIMING,
            "device_id": self.device_id,
            "host_device_id": self._host_device_id,
            "constellation_id": self.constellation_id,
        }
        if self.lan_endpoint:
            msg["lan_endpoint"] = self.lan_endpoint
        self._emit(msg)

        # Fire on_become_target callback
        if self.on_become_target:
            try:
                self.on_become_target(self._host_device_id)
            except Exception as exc:
                logger.error("[RoleSM] on_become_target callback failed: %s", exc)

    # ──────────────────────────────────────────────────────────────
    # WS message handlers
    # ──────────────────────────────────────────────────────────────

    def _handle_host_announcing(self, message: Dict[str, Any]) -> None:
        """Another PC in our constellation has become Host A."""
        host_id = message.get("device_id")

        if host_id == self.device_id:
            # Our own broadcast echoed back — ignore
            return

        if self._state not in (RoleState.NEUTRAL,):
            logger.debug(
                "[RoleSM] host_announcing from %s ignored — we are in state %s",
                host_id, self._state,
            )
            return

        self._host_device_id = host_id
        self._transition(RoleState.CANDIDATE)
        logger.info("[RoleSM] ⭐ Peer %s is now Host A — we are CANDIDATE B", host_id)

    def _handle_target_claiming(self, message: Dict[str, Any]) -> None:
        """
        A peer PC has claimed Target B.
        If we are Host A, this triggers us to send the workspace data to them.
        """
        if self._state != RoleState.HOST:
            return

        target_id = message.get("device_id")
        self._target_device_id = target_id
        self.target_lan_endpoint = message.get("lan_endpoint")
        logger.info("[RoleSM] 🎯 Peer %s claimed Target B (LAN endpoint: %s) — sending workspace", target_id, self.target_lan_endpoint)
        self._transition(RoleState.TRANSFERRING)

        # Signal workspace_ready back to the target
        self._emit({
            "type": WsMessageType.WORKSPACE_READY,
            "source_device_id": self.device_id,
            "target_device_id": target_id,
            "constellation_id": self.constellation_id,
        })

    def _handle_workspace_ready(self, message: Dict[str, Any]) -> None:
        """Host A signals that the workspace snapshot is packaged and streaming begins."""
        if self._state != RoleState.TARGET:
            return
        logger.info("[RoleSM] 📦 Workspace ready — reconstructing on this PC")
        self._transition(RoleState.TRANSFERRING)

    def _handle_reset(self) -> None:
        """Constellation-wide reset received — all PCs return to NEUTRAL."""
        logger.info("[RoleSM] 🔄 Constellation reset received — returning to NEUTRAL")
        self._reset_to_neutral()

    # ──────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────

    def _transition(self, new_state: str) -> None:
        logger.debug("[RoleSM] State %s → %s", self._state, new_state)
        self._state = new_state

    def _reset_to_neutral(self) -> None:
        self._state = RoleState.NEUTRAL
        self._host_device_id = None
        self._target_device_id = None
        self.target_lan_endpoint = None
        if self.on_reset:
            try:
                self.on_reset()
            except Exception as exc:
                logger.error("[RoleSM] on_reset callback failed: %s", exc)

    def _emit(self, message: Dict[str, Any]) -> None:
        """Send a message to the relay server (broadcast to constellation peers)."""
        try:
            result = self.send_ws(message)
            # Support both async coroutines and sync callables
            if asyncio.iscoroutine(result):
                asyncio.ensure_future(result)
        except Exception as exc:
            logger.error("[RoleSM] Failed to emit WS message %s: %s", message.get("type"), exc)

    def __repr__(self) -> str:
        return (
            f"<RoleStateMachine device={self.device_id!r} "
            f"state={self._state!r} host={self._host_device_id!r}>"
        )
