"""
AeroSync WebSocket Router

WebSocket endpoint for real-time device communication.
Handles connection authentication, message routing, and heartbeat.
"""

import json
from datetime import datetime, timezone

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from apps.relay_server.core.security import validate_access_token
from apps.relay_server.core.websocket_manager import ws_manager
from apps.relay_server.services.device_service import get_paired_devices
from shared.constants import (
    WS_CLOSE_CODE_AUTH_FAILED,
    WS_CLOSE_CODE_INVALID_DEVICE,
)
from shared.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.websocket("/ws/{device_id}")
async def websocket_endpoint(websocket: WebSocket, device_id: str):
    """
    WebSocket endpoint for real-time device communication.
    
    Connection flow:
    1. Client connects with device_id in path and JWT token in query params
    2. Server validates JWT — rejects with code 4001 if invalid
    3. Server verifies device_id belongs to authenticated user — rejects with 4003 if not
    4. Connection registered in WebSocketManager
    5. Device status updated to online
    6. Initial 'connected' message sent with online paired devices
    7. Message loop processes incoming messages
    8. On disconnect: cleanup, status update, paired device notification
    """
    # --- Step 1: Extract token from query params ---
    token = websocket.query_params.get("token")
    
    if not token:
        await websocket.close(code=WS_CLOSE_CODE_AUTH_FAILED, reason="Token required")
        return
    
    # --- Step 2: Validate JWT ---
    user_id = validate_access_token(token)
    if not user_id:
        await websocket.close(code=WS_CLOSE_CODE_AUTH_FAILED, reason="Invalid or expired token")
        return
    
    # --- Step 3: Verify device belongs to user ---
    from apps.relay_server.core.database import fetch_one
    
    device = await fetch_one(
        "SELECT id, user_id, device_name FROM devices WHERE id = ? AND user_id = ?",
        (device_id, user_id),
    )
    
    if not device:
        await websocket.close(
            code=WS_CLOSE_CODE_INVALID_DEVICE,
            reason="Device not found or does not belong to you",
        )
        return
    
    # --- Step 4: Accept connection and register ---
    await websocket.accept()
    await ws_manager.connect(device_id, user_id, websocket)
    
    try:
        # --- Step 5: Send initial connected message ---
        online_paired = []
        try:
            paired = await get_paired_devices(user_id, device_id)
            online_paired = [
                {"device_id": p["id"], "device_name": p["device_name"]}
                for p in paired
                if ws_manager.is_device_online(p["id"])
            ]
        except Exception as e:
            logger.warning(f"Error fetching paired devices: {e}")
        
        constellation_info = None
        try:
            c_row = await fetch_one(
                """SELECT c.id, c.name, c.join_code FROM constellations c
                   JOIN constellation_members cm ON c.id = cm.constellation_id
                   WHERE cm.device_id = ?""",
                (device_id,),
            )
            if c_row:
                constellation_info = {
                    "id": c_row["id"],
                    "name": c_row["name"],
                    "join_code": c_row["join_code"],
                }
        except Exception as e:
            logger.warning(f"Error fetching constellation for device {device_id}: {e}")

        await ws_manager.send_to_device(device_id, {
            "type": "connected",
            "device_id": device_id,
            "device_name": device["device_name"],
            "online_paired_devices": online_paired,
            "constellation": constellation_info,
        })
        
        # Notify paired devices that this device is now online
        await ws_manager._broadcast_device_status(device_id, user_id, is_online=True)
        
        # --- Step 6: Message loop ---
        while True:
            try:
                raw = await websocket.receive_text()
                message = json.loads(raw)
                await _handle_message(device_id, user_id, message)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON from device {device_id}")
                await ws_manager.send_to_device(device_id, {
                    "type": "error",
                    "message": "Invalid JSON format",
                })
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected normally: device={device_id}")
    except Exception as e:
        logger.error(f"WebSocket error for device {device_id}: {e}")
    finally:
        # --- Step 7: Cleanup ---
        await ws_manager.disconnect(device_id)


async def _handle_message(device_id: str, user_id: str, message: dict) -> None:
    """
    Route incoming WebSocket messages to appropriate handlers.
    
    Args:
        device_id: The sending device's UUID.
        user_id: The authenticated user's UUID.
        message: The parsed JSON message.
    """
    msg_type = message.get("type")
    
    if msg_type == "pong":
        ws_manager.record_pong(device_id)
    
    elif msg_type == "accept_transfer":
        transfer_id = message.get("transfer_id")
        if transfer_id:
            await _handle_accept_transfer(device_id, user_id, transfer_id)
        else:
            logger.warning(f"accept_transfer missing transfer_id from {device_id}")
    
    elif msg_type == "reject_transfer":
        transfer_id = message.get("transfer_id")
        if transfer_id:
            await _handle_reject_transfer(device_id, user_id, transfer_id)
    
    elif msg_type == "transfer_reconstruction_complete":
        transfer_id = message.get("transfer_id")
        if transfer_id:
            await _handle_reconstruction_complete(device_id, user_id, transfer_id)
    
    # ── Constellation Role Negotiation Messages ───────────────────────────────
    elif msg_type == "host_announcing":
        # A PC in the constellation claims Host A role — relay to all peers
        await _handle_host_announcing(device_id, user_id, message)

    elif msg_type == "target_claiming":
        # A candidate PC claims Target B — relay to the host PC
        await _handle_target_claiming(device_id, user_id, message)

    elif msg_type == "constellation_reset":
        # Transfer complete — relay reset to all constellation members
        await _handle_constellation_reset(device_id, user_id, message)

    elif msg_type == "workspace_ready":
        # Host signals payload is ready — relay to target
        await _handle_workspace_ready(device_id, user_id, message)

    elif msg_type == "workspace_transfer":
        # Host is streaming workspace data — relay to target
        await _handle_workspace_transfer(device_id, user_id, message)
    # ─────────────────────────────────────────────────────────────────────────

    else:
        logger.debug(f"Unknown message type '{msg_type}' from device {device_id}")


async def _handle_accept_transfer(
    device_id: str, user_id: str, transfer_id: str
) -> None:
    """Handle transfer acceptance via WebSocket."""
    from apps.relay_server.core.database import fetch_one
    
    session = await fetch_one(
        "SELECT * FROM sessions WHERE transfer_id = ?",
        (transfer_id,),
    )
    
    if not session:
        await ws_manager.send_to_device(device_id, {
            "type": "error",
            "message": f"Transfer {transfer_id} not found",
        })
        return
    
    # Notify source device
    source_device_id = session["source_device_id"]
    await ws_manager.send_to_device(source_device_id, {
        "type": "transfer_accepted",
        "transfer_id": transfer_id,
    })
    
    logger.info(f"Transfer {transfer_id} accepted by device {device_id}")


async def _handle_reject_transfer(
    device_id: str, user_id: str, transfer_id: str
) -> None:
    """Handle transfer rejection via WebSocket."""
    from apps.relay_server.core.database import fetch_one, execute
    from shared.constants import TransferStatus
    
    session = await fetch_one(
        "SELECT source_device_id FROM sessions WHERE transfer_id = ?",
        (transfer_id,),
    )
    
    if not session:
        return
    
    # Update status
    await execute(
        "UPDATE sessions SET status = ? WHERE transfer_id = ?",
        (TransferStatus.FAILED, transfer_id),
    )
    
    # Notify source device
    await ws_manager.send_to_device(session["source_device_id"], {
        "type": "transfer_failed",
        "transfer_id": transfer_id,
        "reason": "Transfer rejected by target device",
    })
    
    logger.info(f"Transfer {transfer_id} rejected by device {device_id}")


async def _handle_reconstruction_complete(
    device_id: str, user_id: str, transfer_id: str
) -> None:
    """Handle reconstruction completion notification via WebSocket."""
    from apps.relay_server.core.database import fetch_one, execute
    from shared.constants import TransferStatus
    
    session = await fetch_one(
        "SELECT source_device_id FROM sessions WHERE transfer_id = ?",
        (transfer_id,),
    )
    
    if not session:
        return
    
    now = datetime.now(timezone.utc).isoformat()
    
    # Update status
    await execute(
        "UPDATE sessions SET status = ?, completed_at = ? WHERE transfer_id = ?",
        (TransferStatus.COMPLETE, now, transfer_id),
    )
    
    # Notify source device
    await ws_manager.send_to_device(session["source_device_id"], {
        "type": "transfer_complete",
        "transfer_id": transfer_id,
    })
    
    logger.info(f"Transfer {transfer_id} reconstruction complete on device {device_id}")

# ──────────────────────────────────────────────────────────────────────────────
# Constellation Role Negotiation Handlers
# ──────────────────────────────────────────────────────────────────────────────

async def _get_constellation_members(constellation_id: str, exclude_device_id: str) -> list:
    """Return device IDs of all OTHER members in a constellation."""
    from apps.relay_server.core.database import fetch_all
    rows = await fetch_all(
        "SELECT device_id FROM constellation_members WHERE constellation_id = ? AND device_id != ?",
        (constellation_id, exclude_device_id),
    )
    return [r["device_id"] for r in rows]


async def _broadcast_to_constellation(
    constellation_id: str, sender_device_id: str, message: dict
) -> None:
    """Fan-out a message to every other member of a constellation."""
    peer_ids = await _get_constellation_members(constellation_id, sender_device_id)
    for peer_id in peer_ids:
        try:
            await ws_manager.send_to_device(peer_id, message)
        except Exception as e:
            logger.debug("Could not send to constellation peer %s: %s", peer_id, e)


async def _handle_host_announcing(device_id: str, user_id: str, message: dict) -> None:
    """
    PC claims Host A role.
    Relay to all OTHER members of its constellation so they switch to CANDIDATE.
    """
    constellation_id = message.get("constellation_id")
    if not constellation_id:
        logger.warning("[Role] host_announcing from %s has no constellation_id", device_id)
        return

    logger.info("[Role] Device %s is HOST A in constellation %s", device_id, constellation_id)
    # Fan out to peers (the sender already knows its own role)
    await _broadcast_to_constellation(constellation_id, device_id, {
        "type": "host_announcing",
        "device_id": device_id,
        "constellation_id": constellation_id,
    })


async def _handle_target_claiming(device_id: str, user_id: str, message: dict) -> None:
    """
    A CANDIDATE PC claims Target B by detecting a THROW gesture.
    Relay directly to the Host A PC so it starts streaming.
    """
    host_device_id = message.get("host_device_id")
    constellation_id = message.get("constellation_id")

    if not host_device_id:
        logger.warning("[Role] target_claiming from %s missing host_device_id", device_id)
        return

    logger.info(
        "[Role] Device %s claims TARGET B, host=%s, constellation=%s",
        device_id, host_device_id, constellation_id,
    )
    # Notify the host
    await ws_manager.send_to_device(host_device_id, {
        "type": "target_claiming",
        "device_id": device_id,
        "host_device_id": host_device_id,
        "constellation_id": constellation_id,
    })


async def _handle_constellation_reset(device_id: str, user_id: str, message: dict) -> None:
    """
    Transfer complete — broadcast NEUTRAL reset to ALL constellation members
    (including the sender, which also needs confirmation).
    """
    constellation_id = message.get("constellation_id")
    if not constellation_id:
        return

    logger.info("[Role] Constellation %s RESET by device %s", constellation_id, device_id)
    # Include the sender in the reset broadcast (all 5 PCs reset)
    from apps.relay_server.core.database import fetch_all
    rows = await fetch_all(
        "SELECT device_id FROM constellation_members WHERE constellation_id = ?",
        (constellation_id,),
    )
    for row in rows:
        peer_id = row["device_id"]
        try:
            await ws_manager.send_to_device(peer_id, {
                "type": "constellation_reset",
                "constellation_id": constellation_id,
                "source_device_id": device_id,
            })
        except Exception as e:
            logger.debug("Reset relay to %s failed: %s", peer_id, e)


async def _handle_workspace_ready(device_id: str, user_id: str, message: dict) -> None:
    """Host A signals workspace snapshot is packaged — relay to Target B."""
    target_device_id = message.get("target_device_id")
    if not target_device_id:
        return
    logger.info("[Role] workspace_ready from %s → target %s", device_id, target_device_id)
    await ws_manager.send_to_device(target_device_id, {
        "type": "workspace_ready",
        "source_device_id": device_id,
        "target_device_id": target_device_id,
        "constellation_id": message.get("constellation_id"),
    })


async def _handle_workspace_transfer(device_id: str, user_id: str, message: dict) -> None:
    """Host A streams workspace data — relay to Target B."""
    target_device_id = message.get("target_device_id")
    if not target_device_id:
        return
    logger.info("[Role] workspace_transfer from %s → target %s", device_id, target_device_id)
    # Relay the full message (including payload) to the target
    await ws_manager.send_to_device(target_device_id, message)
