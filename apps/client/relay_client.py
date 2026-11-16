"""
AeroSync Relay API Client

Wrapper around HTTP and WebSocket calls to the Relay Server.
"""

import asyncio
import json
import logging
from typing import Dict, Any, Optional, Callable, Tuple

import httpx
import websockets
from websockets.exceptions import ConnectionClosed

from apps.client import storage
from shared.utils.retry import ExponentialBackoffTracker, async_retry_with_backoff

logger = logging.getLogger(__name__)

class RelayClient:
    """Client for interacting with the AeroSync Relay Server."""
    
    def __init__(self):
        self._ws: Optional[websockets.WebSocketClientProtocol] = None
        self._ws_task: Optional[asyncio.Task] = None
        self._on_message_cb: Optional[Callable[[Dict[str, Any]], None]] = None
        self._should_reconnect: bool = True
        self.backoff_tracker = ExponentialBackoffTracker(max_retries=6, base_delay=1.0, max_delay=30.0)
        
    @property
    def base_url(self) -> str:
        return storage.get_server_url()
        
    @property
    def api_url(self) -> str:
        return f"{self.base_url}/api/v1"
        
    @property
    def ws_url(self) -> str:
        # Convert http(s) to ws(s)
        base = self.base_url
        if base.startswith("http://"):
            return base.replace("http://", "ws://")
        elif base.startswith("https://"):
            return base.replace("https://", "wss://")
        return base
        
    def _get_headers(self) -> Dict[str, str]:
        token = storage.get_token()
        if not token:
            return {}
        return {"Authorization": f"Bearer {token}"}
        
    # --- Auth & Registration ---
    
    async def login(self, email: str, password: str) -> Tuple[bool, str]:
        """Login and save tokens."""
        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(
                    f"{self.api_url}/auth/login",
                    json={"email": email, "password": password}
                )
                
                if res.status_code == 200:
                    data = res.json()
                    storage.set_tokens(data["access_token"], data["refresh_token"])
                    return True, ""
                return False, res.text
            except Exception as e:
                return False, str(e)
                
    async def register_device(self, name: str, fingerprint: str) -> Tuple[Optional[str], str]:
        """Register this device with the server."""
        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(
                    f"{self.api_url}/devices/register",
                    headers=self._get_headers(),
                    json={
                        "device_name": name,
                        "device_fingerprint": fingerprint,
                        "platform": "windows"
                    }
                )
                
                if res.status_code == 201:
                    data = res.json()
                    device_id = data["device_id"]
                    storage.set_device_id(device_id)
                    return device_id, ""
                return None, res.text
            except Exception as e:
                return None, str(e)
                
    # --- Session Transfer ---
    
    async def initiate_session(self, target_device_id: str) -> Tuple[Optional[str], str]:
        """Start a transfer to a target device."""
        source_id = storage.get_device_id()
        if not source_id:
            return None, "Device not registered locally"
            
        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(
                    f"{self.api_url}/sessions/initiate",
                    headers=self._get_headers(),
                    json={
                        "source_device_id": source_id,
                        "target_device_id": target_device_id
                    }
                )
                
                if res.status_code == 200:
                    data = res.json()
                    return data["transfer_id"], ""
                return None, res.text
            except Exception as e:
                return None, str(e)
                
    async def upload_package(self, transfer_id: str, data: bytes) -> Tuple[bool, str]:
        """Upload the encrypted package binary."""
        async with httpx.AsyncClient() as client:
            try:
                # Custom timeout for large uploads
                res = await client.post(
                    f"{self.api_url}/sessions/{transfer_id}/upload",
                    headers=self._get_headers(),
                    content=data,
                    timeout=30.0
                )
                
                if res.status_code == 200:
                    return True, ""
                return False, res.text
            except Exception as e:
                return False, str(e)
                
    async def mark_uploaded(self, transfer_id: str, size: int, encrypted_key: str) -> Tuple[bool, str]:
        """Notify server that upload is complete."""
        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(
                    f"{self.api_url}/sessions/{transfer_id}/uploaded",
                    headers=self._get_headers(),
                    json={
                        "package_size_bytes": size,
                        "encrypted_key": encrypted_key
                    }
                )
                
                if res.status_code == 200:
                    return True, ""
                return False, res.text
            except Exception as e:
                return False, str(e)
                
    async def accept_session(self, transfer_id: str) -> Tuple[Optional[str], str]:
        """Accept an incoming transfer."""
        target_id = storage.get_device_id()
        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(
                    f"{self.api_url}/sessions/{transfer_id}/accept",
                    headers=self._get_headers(),
                    json={"target_device_id": target_id}
                )
                
                if res.status_code == 200:
                    return res.json()["encrypted_key"], ""
                return None, res.text
            except Exception as e:
                return None, str(e)
                
    async def download_package(self, transfer_id: str) -> Tuple[Optional[bytes], str]:
        """Download the encrypted package using capped exponential backoff."""
        async def _download():
            async with httpx.AsyncClient() as client:
                res = await client.get(
                    f"{self.api_url}/sessions/{transfer_id}/download",
                    headers=self._get_headers(),
                    timeout=30.0
                )
                if res.status_code == 200:
                    return res.content
                elif res.status_code in (401, 403, 404):
                    raise ValueError(f"HTTP {res.status_code}: {res.text}")
                else:
                    raise IOError(f"HTTP {res.status_code}: {res.text}")

        try:
            content = await async_retry_with_backoff(
                _download,
                max_retries=3,
                base_delay=1.0,
                should_retry=lambda e: not isinstance(e, ValueError),
                op_name=f"Download-{transfer_id}"
            )
            return content, ""
        except Exception as e:
            logger.error("Download package %s failed after retries: %s", transfer_id, e)
            return None, str(e)
                
    async def complete_session(self, transfer_id: str, success: bool, error_msg: str = "") -> Tuple[bool, str]:
        """Mark reconstruction as complete or failed."""
        target_id = storage.get_device_id()
        async with httpx.AsyncClient() as client:
            try:
                res = await client.post(
                    f"{self.api_url}/sessions/{transfer_id}/complete",
                    headers=self._get_headers(),
                    json={
                        "target_device_id": target_id,
                        "success": success,
                        "error_message": error_msg
                    }
                )
                
                if res.status_code == 200:
                    return True, ""
                return False, res.text
            except Exception as e:
                return False, str(e)
                
    # --- WebSocket with Capped Exponential Backoff ---
    
    async def connect_ws(self, on_message: Callable[[Dict[str, Any]], None]):
        """Connect to WebSocket and start resilient backoff-monitored lifecycle loop."""
        self._on_message_cb = on_message
        self._should_reconnect = True
        self.backoff_tracker.reset()
        if not self._ws_task or self._ws_task.done():
            self._ws_task = asyncio.create_task(self._ws_lifecycle_loop())

    async def _ws_lifecycle_loop(self):
        """Resilient WebSocket lifecycle loop with capped exponential backoff."""
        while self._should_reconnect:
            device_id = storage.get_device_id()
            token = storage.get_token()

            if not device_id or not token:
                logger.debug("Cannot connect WS: Missing device_id or token — waiting")
                await asyncio.sleep(2.0)
                continue

            url = f"{self.ws_url}/ws/{device_id}?token={token}"
            try:
                logger.info("Connecting to Relay WebSocket: %s", url)
                async with websockets.connect(url) as ws:
                    self._ws = ws
                    self.backoff_tracker.reset()
                    logger.info("Connected to Relay WebSocket ✅")

                    async for message in ws:
                        try:
                            data = json.loads(message)
                            if self._on_message_cb:
                                self._on_message_cb(data)
                        except json.JSONDecodeError:
                            logger.warning("Received invalid JSON over WS")
            except ConnectionClosed:
                logger.warning("WebSocket connection closed")
            except Exception as e:
                logger.warning("WebSocket connection attempt failed: %s", e)
            finally:
                self._ws = None

            if not self._should_reconnect:
                break

            # Exponential backoff delay (capped; returns None if retries exhausted to avoid infinite loops)
            delay = self.backoff_tracker.next_delay()
            if delay is None:
                logger.warning(
                    "[RelayClient] Max connection retries reached (%d). Halting infinite loop. Call reset_and_reconnect() to resume.",
                    self.backoff_tracker.max_retries
                )
                try:
                    from apps.client.notification import show_toast
                    show_toast("AeroSync Offline", "Relay disconnected. Auto-retries paused — click Tray to reconnect.")
                except Exception:
                    pass
                break

            await asyncio.sleep(delay)

    def reset_and_reconnect(self):
        """Manual trigger from tray or UI to reset backoff and resume reconnection."""
        self.backoff_tracker.reset()
        if self._on_message_cb:
            asyncio.create_task(self.connect_ws(self._on_message_cb))
            
    async def send_ws_message(self, data: Dict[str, Any]):
        """Send a JSON message over WebSocket."""
        if self._ws:
            try:
                await self._ws.send(json.dumps(data))
            except Exception as e:
                logger.error(f"Failed to send WS message: {e}")
                
    async def close_ws(self):
        """Close WebSocket connection."""
        self._should_reconnect = False
        if self._ws:
            try:
                await self._ws.close()
            except Exception:
                pass
        if self._ws_task:
            self._ws_task.cancel()
