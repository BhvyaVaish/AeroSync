"""
AeroSync Session Service

Business logic for workspace transfer session lifecycle:
initiate → upload → notify → accept → download → complete.
"""

import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from apps.relay_server.core.database import execute, fetch_all, fetch_one
from apps.relay_server.core.websocket_manager import ws_manager
from shared.constants import TransferStatus
from shared.utils.logger import get_logger

logger = get_logger(__name__)

# Local storage directory for session packages (SQLite mode)
_STORAGE_DIR = Path("storage/session-packages")


def _ensure_storage_dir() -> None:
    """Create storage directory if it doesn't exist."""
    _STORAGE_DIR.mkdir(parents=True, exist_ok=True)


async def initiate_session(
    user_id: str, source_device_id: str, target_device_id: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Initiate a new workspace transfer session.
    
    Validates device ownership, pairing, and target online status.
    Creates a session record and returns an upload URL.
    
    Args:
        user_id: The authenticated user's UUID.
        source_device_id: The sending device's UUID.
        target_device_id: The receiving device's UUID.
        
    Returns:
        Tuple of (session_data, error_message).
    """
    # Verify source device belongs to user
    source = await fetch_one(
        "SELECT id, device_name FROM devices WHERE id = ? AND user_id = ?",
        (source_device_id, user_id),
    )
    if not source:
        return None, "Source device not found or does not belong to you"
    
    target = await fetch_one(
        "SELECT id, device_name, user_id FROM devices WHERE id = ?",
        (target_device_id,),
    )
    if not target:
        return None, "Target device not found"
    
    # Verify devices are paired OR linked within the same Constellation
    is_authorized = False
    if target["user_id"] == user_id:
        pairing = await fetch_one(
            """SELECT id FROM paired_devices 
               WHERE user_id = ? AND (
                   (device_a_id = ? AND device_b_id = ?) OR
                   (device_a_id = ? AND device_b_id = ?)
               )""",
            (user_id, source_device_id, target_device_id, target_device_id, source_device_id),
        )
        if pairing:
            is_authorized = True

    if not is_authorized:
        # Check if both devices belong to the same active Constellation
        same_constellation = await fetch_one(
            """SELECT cm1.constellation_id FROM constellation_members cm1
               JOIN constellation_members cm2 ON cm1.constellation_id = cm2.constellation_id
               WHERE cm1.device_id = ? AND cm2.device_id = ?""",
            (source_device_id, target_device_id),
        )
        if same_constellation:
            is_authorized = True

    if not is_authorized:
        return None, "Devices are neither paired nor in the same constellation"
    
    # Check if target device is online
    if not ws_manager.is_device_online(target_device_id):
        return None, "Target device is not online"
    
    # Create session
    session_id = str(uuid.uuid4())
    transfer_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = (now + timedelta(minutes=30)).isoformat()
    
    _ensure_storage_dir()
    
    await execute(
        """INSERT INTO sessions 
           (id, transfer_id, source_device_id, target_device_id, status, expires_at, initiated_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (session_id, transfer_id, source_device_id, target_device_id,
         TransferStatus.PENDING, expires_at, now.isoformat()),
    )
    
    # For local storage mode: upload URL is just the local path endpoint
    upload_url = f"/api/v1/sessions/{transfer_id}/upload"
    
    logger.info(
        f"Session initiated: {transfer_id} "
        f"({source['device_name']} → {target['device_name']})"
    )
    
    return {
        "transfer_id": transfer_id,
        "upload_url": upload_url,
        "upload_expires_at": expires_at,
    }, None


async def mark_uploaded(
    user_id: str, transfer_id: str, package_size_bytes: int, encrypted_key: str
) -> Tuple[bool, Optional[str]]:
    """
    Mark a session as uploaded and notify the target device.
    
    Args:
        user_id: The authenticated user's UUID.
        transfer_id: The transfer's UUID.
        package_size_bytes: Size of the uploaded package.
        encrypted_key: The AES encryption key (base64 encoded).
        
    Returns:
        Tuple of (success, error_message).
    """
    session = await fetch_one(
        "SELECT * FROM sessions WHERE transfer_id = ?", (transfer_id,)
    )
    
    if not session:
        return False, "Transfer not found"
    
    # Verify source device belongs to user
    source = await fetch_one(
        "SELECT user_id FROM devices WHERE id = ?", (session["source_device_id"],)
    )
    if not source or source["user_id"] != user_id:
        return False, "Transfer does not belong to you"
    
    if session["status"] != TransferStatus.PENDING:
        return False, f"Transfer is in '{session['status']}' status, expected 'pending'"
    
    # Update session
    await execute(
        """UPDATE sessions 
           SET status = ?, package_size_bytes = ?, encrypted_key = ?, package_url = ?
           WHERE transfer_id = ?""",
        (TransferStatus.UPLOADED, package_size_bytes, encrypted_key,
         f"storage/session-packages/{transfer_id}.bin", transfer_id),
    )
    
    # Notify target device via WebSocket
    source_device = await fetch_one(
        "SELECT device_name FROM devices WHERE id = ?", (session["source_device_id"],)
    )
    
    sent = await ws_manager.send_to_device(session["target_device_id"], {
        "type": "transfer_incoming",
        "transfer_id": transfer_id,
        "source_device_id": session["source_device_id"],
        "source_device_name": source_device["device_name"] if source_device else "Unknown",
        "package_size_bytes": package_size_bytes,
        "initiated_at": session["initiated_at"],
    })
    
    if sent:
        await execute(
            "UPDATE sessions SET status = ? WHERE transfer_id = ?",
            (TransferStatus.NOTIFIED, transfer_id),
        )
    
    logger.info(f"Session uploaded and target notified: {transfer_id}")
    return True, None


async def accept_session(
    user_id: str, transfer_id: str, target_device_id: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Accept an incoming transfer and get the download URL.
    
    Args:
        user_id: The authenticated user's UUID.
        transfer_id: The transfer's UUID.
        target_device_id: The accepting device's UUID.
        
    Returns:
        Tuple of (download_info, error_message).
    """
    # Verify device belongs to user
    device = await fetch_one(
        "SELECT id FROM devices WHERE id = ? AND user_id = ?",
        (target_device_id, user_id),
    )
    if not device:
        return None, "Device not found or does not belong to you"
    
    session = await fetch_one(
        "SELECT * FROM sessions WHERE transfer_id = ? AND target_device_id = ?",
        (transfer_id, target_device_id),
    )
    
    if not session:
        return None, "Transfer not found"
    
    if session["status"] not in (TransferStatus.UPLOADED, TransferStatus.NOTIFIED):
        return None, f"Transfer is in '{session['status']}' status, cannot accept"
    
    # Update status
    await execute(
        "UPDATE sessions SET status = ? WHERE transfer_id = ?",
        (TransferStatus.ACCEPTED, transfer_id),
    )
    
    # Notify source device
    await ws_manager.send_to_device(session["source_device_id"], {
        "type": "transfer_accepted",
        "transfer_id": transfer_id,
    })
    
    # Return download URL and encryption key
    download_url = f"/api/v1/sessions/{transfer_id}/download"
    
    logger.info(f"Session accepted: {transfer_id} by device {target_device_id}")
    
    return {
        "download_url": download_url,
        "encrypted_key": session["encrypted_key"] or "",
    }, None


async def complete_session(
    user_id: str, transfer_id: str, target_device_id: str,
    success: bool, error_message: Optional[str] = None
) -> Tuple[bool, Optional[str]]:
    """
    Mark a transfer as complete or failed.
    
    Args:
        user_id: The authenticated user's UUID.
        transfer_id: The transfer's UUID.
        target_device_id: The completing device's UUID.
        success: Whether reconstruction succeeded.
        error_message: Optional error description if failed.
        
    Returns:
        Tuple of (success, error_message).
    """
    session = await fetch_one(
        "SELECT * FROM sessions WHERE transfer_id = ? AND target_device_id = ?",
        (transfer_id, target_device_id),
    )
    
    if not session:
        return False, "Transfer not found"
    
    now = datetime.now(timezone.utc).isoformat()
    new_status = TransferStatus.COMPLETE if success else TransferStatus.FAILED
    
    await execute(
        "UPDATE sessions SET status = ?, completed_at = ? WHERE transfer_id = ?",
        (new_status, now, transfer_id),
    )
    
    # Notify source device
    msg_type = "transfer_complete" if success else "transfer_failed"
    msg = {"type": msg_type, "transfer_id": transfer_id}
    if error_message:
        msg["reason"] = error_message
    
    await ws_manager.send_to_device(session["source_device_id"], msg)
    
    # Clean up package file if complete
    if success:
        _cleanup_package(transfer_id)
    
    logger.info(f"Session {new_status}: {transfer_id}")
    return True, None


async def get_session_history(
    user_id: str, device_id: Optional[str] = None, limit: int = 20, offset: int = 0
) -> Dict[str, Any]:
    """
    Get paginated transfer history for a user.
    
    Args:
        user_id: The user's UUID.
        device_id: Optional device filter.
        limit: Max results per page.
        offset: Pagination offset.
        
    Returns:
        Dict with sessions list, total count, limit, and offset.
    """
    # Build query based on whether device_id is specified
    if device_id:
        sessions = await fetch_all(
            """SELECT s.*, 
                      sd.device_name as source_device_name,
                      td.device_name as target_device_name
               FROM sessions s
               LEFT JOIN devices sd ON s.source_device_id = sd.id
               LEFT JOIN devices td ON s.target_device_id = td.id
               WHERE (sd.user_id = ? OR td.user_id = ?)
                 AND (s.source_device_id = ? OR s.target_device_id = ?)
               ORDER BY s.initiated_at DESC
               LIMIT ? OFFSET ?""",
            (user_id, user_id, device_id, device_id, limit, offset),
        )
    else:
        sessions = await fetch_all(
            """SELECT s.*,
                      sd.device_name as source_device_name,
                      td.device_name as target_device_name
               FROM sessions s
               LEFT JOIN devices sd ON s.source_device_id = sd.id
               LEFT JOIN devices td ON s.target_device_id = td.id
               WHERE sd.user_id = ? OR td.user_id = ?
               ORDER BY s.initiated_at DESC
               LIMIT ? OFFSET ?""",
            (user_id, user_id, limit, offset),
        )
    
    return {
        "sessions": sessions,
        "total": len(sessions),
        "limit": limit,
        "offset": offset,
    }


async def cancel_session(
    user_id: str, transfer_id: str
) -> Tuple[bool, Optional[str]]:
    """
    Cancel a pending transfer.
    
    Args:
        user_id: The user's UUID.
        transfer_id: The transfer to cancel.
        
    Returns:
        Tuple of (success, error_message).
    """
    session = await fetch_one(
        "SELECT * FROM sessions WHERE transfer_id = ?", (transfer_id,)
    )
    
    if not session:
        return False, "Transfer not found"
    
    # Verify ownership via source device
    source = await fetch_one(
        "SELECT user_id FROM devices WHERE id = ?", (session["source_device_id"],)
    )
    if not source or source["user_id"] != user_id:
        return False, "Transfer does not belong to you"
    
    # Can only cancel pending/uploaded/notified sessions
    if session["status"] not in TransferStatus.EXPIRABLE:
        return False, f"Cannot cancel transfer in '{session['status']}' status"
    
    await execute(
        "UPDATE sessions SET status = ? WHERE transfer_id = ?",
        (TransferStatus.CANCELLED, transfer_id),
    )
    
    # Clean up package
    _cleanup_package(transfer_id)
    
    # Notify target device if session was notified
    if session["status"] == TransferStatus.NOTIFIED:
        await ws_manager.send_to_device(session["target_device_id"], {
            "type": "transfer_failed",
            "transfer_id": transfer_id,
            "reason": "Transfer cancelled by sender",
        })
    
    logger.info(f"Session cancelled: {transfer_id}")
    return True, None


async def cleanup_expired_sessions() -> int:
    """
    Clean up expired sessions from the database.
    
    Deletes sessions older than the configured expiry time
    that are stuck in pending/uploaded/notified status.
    
    Returns:
        int: Number of sessions cleaned up.
    """
    now = datetime.now(timezone.utc).isoformat()
    
    try:
        expired = await fetch_all(
            """SELECT id, transfer_id FROM sessions 
               WHERE status IN (?, ?, ?) AND expires_at < ?""",
            (TransferStatus.PENDING, TransferStatus.UPLOADED, TransferStatus.NOTIFIED, now),
        )
        
        if not expired:
            return 0
        
        for session in expired:
            await execute(
                "UPDATE sessions SET status = ? WHERE id = ?",
                (TransferStatus.EXPIRED, session["id"]),
            )
            _cleanup_package(session["transfer_id"])
        
        count = len(expired)
        if count > 0:
            logger.info(f"Expired {count} stale sessions")
        
        return count
        
    except Exception as e:
        logger.error(f"Session cleanup error: {e}")
        return 0


def _cleanup_package(transfer_id: str) -> None:
    """Delete a session package file from local storage."""
    try:
        package_path = _STORAGE_DIR / f"{transfer_id}.bin"
        if package_path.exists():
            package_path.unlink()
            logger.debug(f"Deleted package file: {transfer_id}.bin")
    except Exception as e:
        logger.warning(f"Failed to delete package file {transfer_id}: {e}")


async def save_package(transfer_id: str, data: bytes) -> str:
    """
    Save a session package to local storage.
    
    Args:
        transfer_id: The transfer's UUID.
        data: The encrypted package bytes.
        
    Returns:
        str: Path to the saved file.
    """
    _ensure_storage_dir()
    package_path = _STORAGE_DIR / f"{transfer_id}.bin"
    package_path.write_bytes(data)
    logger.debug(f"Saved package: {transfer_id}.bin ({len(data)} bytes)")
    return str(package_path)


async def load_package(transfer_id: str) -> Optional[bytes]:
    """
    Load a session package from local storage.
    
    Args:
        transfer_id: The transfer's UUID.
        
    Returns:
        Optional[bytes]: The package bytes, or None if not found.
    """
    package_path = _STORAGE_DIR / f"{transfer_id}.bin"
    if not package_path.exists():
        return None
    return package_path.read_bytes()
