"""
AeroSync WebSocket Connection Manager

Maintains a registry of connected devices and handles real-time
message routing between paired devices. This is the most critical
backend component for real-time transfer notifications.
"""

import asyncio
from datetime import datetime, timezone
from typing import Dict, List, Optional, Set

from fastapi import WebSocket

from shared.constants import (
    WS_HEARTBEAT_INTERVAL_SECONDS,
    WS_PONG_TIMEOUT_SECONDS,
)
from shared.utils.logger import get_logger

logger = get_logger(__name__)


class WebSocketManager:
    """
    Manages WebSocket connections for all connected devices.
    
    Responsibilities:
    - Track active connections by device_id
    - Track which devices belong to which user
    - Route messages to specific devices or all user devices
    - Broadcast online/offline status changes to paired devices
    - Heartbeat monitoring with ping/pong
    """

    def __init__(self) -> None:
        """Initialize the WebSocket manager."""
        # device_id -> WebSocket connection
        self._connections: Dict[str, WebSocket] = {}
        # user_id -> set of connected device_ids
        self._user_devices: Dict[str, Set[str]] = {}
        # device_id -> user_id (reverse lookup)
        self._device_user: Dict[str, str] = {}
        # device_id -> heartbeat task
        self._heartbeat_tasks: Dict[str, asyncio.Task] = {}
        # device_id -> last pong received
        self._last_pong: Dict[str, datetime] = {}

    async def connect(
        self, device_id: str, user_id: str, websocket: WebSocket
    ) -> None:
        """
        Register a new WebSocket connection for a device.
        
        Args:
            device_id: The connecting device's UUID.
            user_id: The authenticated user's UUID.
            websocket: The WebSocket connection instance.
        """
        # Close existing connection for this device if any
        if device_id in self._connections:
            logger.warning(f"Device {device_id} reconnecting — closing old connection")
            await self.disconnect(device_id)
        
        self._connections[device_id] = websocket
        self._device_user[device_id] = user_id
        
        if user_id not in self._user_devices:
            self._user_devices[user_id] = set()
        self._user_devices[user_id].add(device_id)
        
        # Update device online status in DB
        await self._update_device_status(device_id, is_online=True)
        
        # Start heartbeat monitoring
        self._heartbeat_tasks[device_id] = asyncio.create_task(
            self._heartbeat_loop(device_id)
        )
        
        logger.info(
            f"WebSocket connected: device={device_id}, user={user_id}, "
            f"total_connections={len(self._connections)}"
        )

    async def disconnect(self, device_id: str) -> None:
        """
        Remove a device's WebSocket connection and clean up.
        
        Args:
            device_id: The disconnecting device's UUID.
        """
        # Cancel heartbeat task
        if device_id in self._heartbeat_tasks:
            self._heartbeat_tasks[device_id].cancel()
            try:
                await self._heartbeat_tasks[device_id]
            except asyncio.CancelledError:
                pass
            del self._heartbeat_tasks[device_id]
        
        # Remove from connection registry
        ws = self._connections.pop(device_id, None)
        user_id = self._device_user.pop(device_id, None)
        self._last_pong.pop(device_id, None)
        
        if user_id and user_id in self._user_devices:
            self._user_devices[user_id].discard(device_id)
            if not self._user_devices[user_id]:
                del self._user_devices[user_id]
        
        # Update device offline status in DB
        await self._update_device_status(device_id, is_online=False)
        
        # Close WebSocket if still open
        if ws:
            try:
                await ws.close()
            except Exception:
                pass
        
        # Notify paired devices about offline status
        if user_id:
            await self._broadcast_device_status(device_id, user_id, is_online=False)
        
        logger.info(
            f"WebSocket disconnected: device={device_id}, "
            f"total_connections={len(self._connections)}"
        )

    async def send_to_device(self, device_id: str, message: dict) -> bool:
        """
        Send a JSON message to a specific device.
        
        Args:
            device_id: The target device's UUID.
            message: The message dict to send (will be JSON-serialized).
            
        Returns:
            bool: True if the message was sent successfully.
        """
        ws = self._connections.get(device_id)
        if ws is None:
            logger.debug(f"Cannot send to device {device_id}: not connected")
            return False
        
        try:
            await ws.send_json(message)
            return True
        except Exception as e:
            logger.warning(f"Failed to send to device {device_id}: {e}")
            # Connection is broken — clean up
            await self.disconnect(device_id)
            return False

    async def send_to_user_devices(
        self,
        user_id: str,
        message: dict,
        exclude_device_id: Optional[str] = None,
    ) -> int:
        """
        Send a message to all connected devices of a user.
        
        Args:
            user_id: The user's UUID.
            message: The message dict to send.
            exclude_device_id: Optional device to exclude (e.g., the sender).
            
        Returns:
            int: Number of devices the message was sent to.
        """
        device_ids = self._user_devices.get(user_id, set())
        sent_count = 0
        
        for device_id in list(device_ids):
            if device_id == exclude_device_id:
                continue
            if await self.send_to_device(device_id, message):
                sent_count += 1
        
        return sent_count

    def get_online_devices(self, user_id: str) -> List[str]:
        """
        Get all online device IDs for a user.
        
        Args:
            user_id: The user's UUID.
            
        Returns:
            List[str]: List of connected device IDs.
        """
        return list(self._user_devices.get(user_id, set()))

    def is_device_online(self, device_id: str) -> bool:
        """
        Check if a specific device is currently connected.
        
        Args:
            device_id: The device's UUID.
            
        Returns:
            bool: True if the device has an active WebSocket connection.
        """
        return device_id in self._connections

    def get_user_for_device(self, device_id: str) -> Optional[str]:
        """
        Get the user_id for a connected device.
        
        Args:
            device_id: The device's UUID.
            
        Returns:
            Optional[str]: The user_id, or None if not connected.
        """
        return self._device_user.get(device_id)

    @property
    def total_connections(self) -> int:
        """Total number of active WebSocket connections."""
        return len(self._connections)

    def record_pong(self, device_id: str) -> None:
        """Record that a pong was received from a device."""
        self._last_pong[device_id] = datetime.now(timezone.utc)

    # =========================================================================
    # Internal Methods
    # =========================================================================

    async def _heartbeat_loop(self, device_id: str) -> None:
        """
        Send periodic pings and disconnect if pong is not received.
        
        Runs as an asyncio task for each connected device.
        """
        try:
            while device_id in self._connections:
                await asyncio.sleep(WS_HEARTBEAT_INTERVAL_SECONDS)
                
                if device_id not in self._connections:
                    break
                
                # Send ping
                ping_sent = await self.send_to_device(device_id, {
                    "type": "ping",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
                
                if not ping_sent:
                    break
                
                # Wait for pong
                await asyncio.sleep(WS_PONG_TIMEOUT_SECONDS)
                
                # Check if pong was received
                last_pong = self._last_pong.get(device_id)
                if last_pong is None:
                    logger.warning(f"No pong received from device {device_id} — disconnecting")
                    await self.disconnect(device_id)
                    break
                
                # Check if pong is recent enough
                age = (datetime.now(timezone.utc) - last_pong).total_seconds()
                if age > WS_HEARTBEAT_INTERVAL_SECONDS + WS_PONG_TIMEOUT_SECONDS:
                    logger.warning(
                        f"Stale pong from device {device_id} ({age:.0f}s old) — disconnecting"
                    )
                    await self.disconnect(device_id)
                    break
                    
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Heartbeat error for device {device_id}: {e}")

    async def _update_device_status(self, device_id: str, is_online: bool) -> None:
        """Update device online status and last_seen in the database."""
        try:
            from apps.relay_server.core.database import execute
            
            now = datetime.now(timezone.utc).isoformat()
            await execute(
                "UPDATE devices SET is_online = ?, last_seen = ? WHERE id = ?",
                (1 if is_online else 0, now, device_id),
            )
        except Exception as e:
            logger.error(f"Failed to update device status: {e}")

    async def _broadcast_device_status(
        self, device_id: str, user_id: str, is_online: bool
    ) -> None:
        """Notify all other user devices about a device's status change."""
        try:
            from apps.relay_server.core.database import fetch_one
            
            device = await fetch_one(
                "SELECT device_name FROM devices WHERE id = ?", (device_id,)
            )
            device_name = device["device_name"] if device else "Unknown"
            
            message = {
                "type": "device_online" if is_online else "device_offline",
                "device_id": device_id,
                "device_name": device_name,
            }
            
            await self.send_to_user_devices(
                user_id, message, exclude_device_id=device_id
            )
        except Exception as e:
            logger.error(f"Failed to broadcast device status: {e}")


# Global singleton instance
ws_manager = WebSocketManager()
