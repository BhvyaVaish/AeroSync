"""
AeroSync Device Service

Business logic for device registration, listing, pairing, and removal.
"""

import random
import string
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

from apps.relay_server.core.database import execute, fetch_all, fetch_one
from shared.constants import PAIRING_CODE_EXPIRY_MINUTES, PAIRING_CODE_LENGTH
from shared.utils.logger import get_logger

logger = get_logger(__name__)


def _generate_pairing_code() -> str:
    """Generate a random 6-digit pairing code."""
    return "".join(random.choices(string.digits, k=PAIRING_CODE_LENGTH))


async def register_device(
    user_id: str,
    device_name: str,
    device_fingerprint: str,
    platform: str = "windows",
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Register a new device or update an existing one.
    
    If a device with the same fingerprint exists for this user,
    updates the device name and last_seen timestamp.
    
    Args:
        user_id: The authenticated user's UUID.
        device_name: Human-readable device name.
        device_fingerprint: SHA-256 fingerprint from device_fingerprint.py.
        platform: Operating system platform.
        
    Returns:
        Tuple of (device_data, error_message).
    """
    now = datetime.now(timezone.utc).isoformat()
    
    # Check if fingerprint already exists for this user
    existing = await fetch_one(
        "SELECT id, device_name FROM devices WHERE device_fingerprint = ? AND user_id = ?",
        (device_fingerprint, user_id),
    )
    
    if existing:
        # Update existing device
        await execute(
            "UPDATE devices SET device_name = ?, last_seen = ? WHERE id = ?",
            (device_name, now, existing["id"]),
        )
        logger.info(f"Device updated: {existing['id']} for user {user_id}")
        return {
            "device_id": existing["id"],
            "device_name": device_name,
            "platform": platform,
            "is_new": False,
        }, None
    
    # Check if fingerprint exists for another user
    other_user = await fetch_one(
        "SELECT id FROM devices WHERE device_fingerprint = ?",
        (device_fingerprint,),
    )
    if other_user:
        return None, "This device is already registered to another account"
    
    # Create new device
    device_id = str(uuid.uuid4())
    await execute(
        """INSERT INTO devices (id, user_id, device_name, device_fingerprint, platform, last_seen, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        (device_id, user_id, device_name, device_fingerprint, platform, now, now),
    )
    
    logger.info(f"Device registered: {device_id} ({device_name}) for user {user_id}")
    return {
        "device_id": device_id,
        "device_name": device_name,
        "platform": platform,
        "is_new": True,
    }, None


async def list_user_devices(user_id: str) -> List[Dict[str, Any]]:
    """
    List all devices belonging to a user, with paired device info.
    
    Args:
        user_id: The user's UUID.
        
    Returns:
        List of device dicts with paired_with info.
    """
    devices = await fetch_all(
        """SELECT id, device_name, platform, is_online, last_seen, created_at
           FROM devices WHERE user_id = ? ORDER BY created_at DESC""",
        (user_id,),
    )
    
    # Enrich each device with its paired devices
    result = []
    for device in devices:
        paired = await get_paired_devices(user_id, device["id"])
        device_data = dict(device)
        device_data["device_id"] = device["id"]
        device_data["paired_with"] = paired
        result.append(device_data)
    
    return result


async def get_device(user_id: str, device_id: str) -> Optional[Dict[str, Any]]:
    """
    Get a specific device, verifying it belongs to the user.
    
    Args:
        user_id: The user's UUID.
        device_id: The device UUID.
        
    Returns:
        Device dict or None if not found / not owned by user.
    """
    return await fetch_one(
        "SELECT * FROM devices WHERE id = ? AND user_id = ?",
        (device_id, user_id),
    )


async def initiate_pairing(
    user_id: str, device_id: str
) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """
    Generate a 6-digit pairing code for a device.
    
    Args:
        user_id: The user's UUID.
        device_id: The device to generate a code for.
        
    Returns:
        Tuple of ({"pairing_code", "expires_at"}, error_message).
    """
    # Verify device belongs to user
    device = await get_device(user_id, device_id)
    if not device:
        return None, "Device not found or does not belong to you"
    
    # Generate code and expiry
    code = _generate_pairing_code()
    expires_at = (
        datetime.now(timezone.utc) + timedelta(minutes=PAIRING_CODE_EXPIRY_MINUTES)
    ).isoformat()
    
    # Store on device record
    await execute(
        "UPDATE devices SET pairing_token = ?, pairing_token_expires_at = ? WHERE id = ?",
        (code, expires_at, device_id),
    )
    
    logger.info(f"Pairing code generated for device {device_id}")
    return {"pairing_code": code, "expires_at": expires_at}, None


async def complete_pairing(
    user_id: str, pairing_code: str, target_device_id: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Complete device pairing using a 6-digit code.
    
    Args:
        user_id: The user's UUID.
        pairing_code: The 6-digit pairing code.
        target_device_id: The device that is accepting the pairing.
        
    Returns:
        Tuple of (paired_device_info, error_message).
    """
    # Verify target device belongs to user
    target = await get_device(user_id, target_device_id)
    if not target:
        return None, "Target device not found or does not belong to you"
    
    # Find the device with this pairing code
    source = await fetch_one(
        """SELECT id, user_id, device_name FROM devices 
           WHERE pairing_token = ? AND user_id = ?""",
        (pairing_code, user_id),
    )
    
    if not source:
        return None, "Invalid pairing code"
    
    # Check expiry
    source_full = await fetch_one(
        "SELECT pairing_token_expires_at FROM devices WHERE id = ?",
        (source["id"],),
    )
    
    if source_full and source_full["pairing_token_expires_at"]:
        expires_at = datetime.fromisoformat(source_full["pairing_token_expires_at"])
        if datetime.now(timezone.utc) > expires_at:
            # Clear expired token
            await execute(
                "UPDATE devices SET pairing_token = NULL, pairing_token_expires_at = NULL WHERE id = ?",
                (source["id"],),
            )
            return None, "Pairing code has expired"
    
    # Cannot pair a device with itself
    if source["id"] == target_device_id:
        return None, "Cannot pair a device with itself"
    
    # Check if already paired
    existing = await fetch_one(
        """SELECT id FROM paired_devices 
           WHERE user_id = ? AND (
               (device_a_id = ? AND device_b_id = ?) OR
               (device_a_id = ? AND device_b_id = ?)
           )""",
        (user_id, source["id"], target_device_id, target_device_id, source["id"]),
    )
    
    if existing:
        return None, "These devices are already paired"
    
    # Create pairing record
    pairing_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    
    await execute(
        """INSERT INTO paired_devices (id, user_id, device_a_id, device_b_id, paired_at)
           VALUES (?, ?, ?, ?, ?)""",
        (pairing_id, user_id, source["id"], target_device_id, now),
    )
    
    # Clear pairing token
    await execute(
        "UPDATE devices SET pairing_token = NULL, pairing_token_expires_at = NULL WHERE id = ?",
        (source["id"],),
    )
    
    logger.info(f"Devices paired: {source['id']} <-> {target_device_id}")
    
    return {
        "success": True,
        "paired_device": {
            "id": source["id"],
            "name": source["device_name"],
        },
    }, None


async def get_paired_devices(
    user_id: str, device_id: str
) -> List[Dict[str, Any]]:
    """
    Get all devices paired with a given device.
    
    Args:
        user_id: The user's UUID.
        device_id: The device to find pairings for.
        
    Returns:
        List of paired device info dicts.
    """
    # Get pairings where this device is either A or B
    pairings = await fetch_all(
        """SELECT device_a_id, device_b_id FROM paired_devices
           WHERE user_id = ? AND (device_a_id = ? OR device_b_id = ?)""",
        (user_id, device_id, device_id),
    )
    
    paired = []
    for pairing in pairings:
        # Get the other device's ID
        other_id = (
            pairing["device_b_id"]
            if pairing["device_a_id"] == device_id
            else pairing["device_a_id"]
        )
        
        device = await fetch_one(
            "SELECT id, device_name, platform, is_online, last_seen FROM devices WHERE id = ?",
            (other_id,),
        )
        if device:
            paired.append(dict(device))
    
    return paired


async def delete_device(
    user_id: str, device_id: str
) -> Tuple[bool, Optional[str]]:
    """
    Delete a device and all its pairings.
    
    Args:
        user_id: The user's UUID.
        device_id: The device to delete.
        
    Returns:
        Tuple of (success, error_message).
    """
    # Verify ownership
    device = await get_device(user_id, device_id)
    if not device:
        return False, "Device not found or does not belong to you"
    
    # Delete pairings first
    await execute(
        "DELETE FROM paired_devices WHERE device_a_id = ? OR device_b_id = ?",
        (device_id, device_id),
    )
    
    # Delete device
    await execute("DELETE FROM devices WHERE id = ?", (device_id,))
    
    logger.info(f"Device deleted: {device_id} for user {user_id}")
    return True, None
