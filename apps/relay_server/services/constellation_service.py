"""
AeroSync Constellation Service

Manages isolated rooms (Constellations) of linked computers.
A constellation connects up to 5 computers together with a unique join code.
"""

import random
import string
import uuid
from typing import Dict, List, Optional, Tuple, Any

from apps.relay_server.core.database import get_db
from shared.constants import MAX_CONSTELLATION_DEVICES
from shared.utils.logger import get_logger

logger = get_logger(__name__)

# Safe characters for human-readable codes (excluding ambiguous characters: 0, O, 1, I, L)
CODE_CHARS = "23456789ABCDEFGHJKMNPQRSTUVWXYZ"


def _generate_join_code() -> str:
    """Generate a friendly unique join code formatted as CST-XXXXX."""
    suffix = "".join(random.choices(CODE_CHARS, k=5))
    return f"CST-{suffix}"


async def create_constellation(
    user_id: str,
    name: str,
    creator_device_id: Optional[str] = None,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Create a new isolated constellation room.

    Args:
        user_id: ID of the creating user.
        name: Human-friendly name for the constellation (e.g., 'Design Studio').
        creator_device_id: Optional device ID to immediately link into the room.

    Returns:
        Tuple of (constellation_dict, error_string).
    """
    db = await get_db()
    name = name.strip()
    if not name:
        name = "My Constellation"

    # Verify creator device if provided
    if creator_device_id:
        cursor = await db.execute(
            "SELECT id, device_name, platform, is_online FROM devices WHERE id = ? AND user_id = ?",
            (creator_device_id, user_id),
        )
        creator_device = await cursor.fetchone()
        if not creator_device:
            return None, "Selected creator device not found or does not belong to you."

    constellation_id = str(uuid.uuid4())

    # Generate unique join code with retry on collision
    join_code = ""
    for _ in range(10):
        candidate = _generate_join_code()
        cursor = await db.execute("SELECT id FROM constellations WHERE join_code = ?", (candidate,))
        if not await cursor.fetchone():
            join_code = candidate
            break

    if not join_code:
        return None, "Failed to generate unique constellation code. Please try again."

    # Insert constellation
    await db.execute(
        """
        INSERT INTO constellations (id, name, join_code, creator_user_id, max_devices)
        VALUES (?, ?, ?, ?, ?)
        """,
        (constellation_id, name, join_code, user_id, MAX_CONSTELLATION_DEVICES),
    )

    members = []
    # If creator device specified, add as owner member
    if creator_device_id:
        member_id = str(uuid.uuid4())
        await db.execute(
            """
            INSERT INTO constellation_members (id, constellation_id, device_id, user_id, role)
            VALUES (?, ?, ?, ?, 'owner')
            """,
            (member_id, constellation_id, creator_device_id, user_id),
        )
        members.append({
            "device_id": creator_device_id,
            "device_name": creator_device["device_name"],
            "platform": creator_device["platform"],
            "is_online": bool(creator_device["is_online"]),
            "role": "owner",
        })

    await db.commit()
    logger.info(f"Created constellation '{name}' ({constellation_id}) with code {join_code}")

    if creator_device_id:
        try:
            from apps.relay_server.core.websocket_manager import ws_manager
            await ws_manager.send_to_device(creator_device_id, {
                "type": "constellation_joined",
                "constellation_id": constellation_id,
                "constellation_name": name,
                "join_code": join_code,
            })
        except Exception as exc:
            logger.debug(f"WS notification for create constellation failed: {exc}")

    return {
        "id": constellation_id,
        "name": name,
        "join_code": join_code,
        "creator_user_id": user_id,
        "max_devices": MAX_CONSTELLATION_DEVICES,
        "device_count": len(members),
        "is_full": len(members) >= MAX_CONSTELLATION_DEVICES,
        "members": members,
    }, None


async def join_constellation(
    user_id: str,
    join_code: str,
    device_id: str,
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Link a computer into an existing constellation room using its unique code.

    Enforces the strict MAX_CONSTELLATION_DEVICES (5) limit.

    Args:
        user_id: ID of the user requesting to join.
        join_code: The constellation's unique join code (case-insensitive).
        device_id: ID of the device being linked into the room.

    Returns:
        Tuple of (constellation_dict, error_string).
    """
    db = await get_db()
    clean_code = join_code.strip().upper()

    # 1. Verify device exists and belongs to user
    cursor = await db.execute(
        "SELECT id, device_name, platform, is_online FROM devices WHERE id = ? AND user_id = ?",
        (device_id, user_id),
    )
    device = await cursor.fetchone()
    if not device:
        return None, "Device not found or not registered to your account."

    # 2. Look up constellation by join_code
    cursor = await db.execute(
        "SELECT id, name, join_code, creator_user_id, max_devices, created_at FROM constellations WHERE UPPER(join_code) = ?",
        (clean_code,),
    )
    constellation = await cursor.fetchone()
    if not constellation:
        return None, f"No constellation found with code '{clean_code}'."

    constellation_id = constellation["id"]
    max_devices = constellation["max_devices"] or MAX_CONSTELLATION_DEVICES

    # 3. Check if device is already in this constellation
    cursor = await db.execute(
        "SELECT id FROM constellation_members WHERE constellation_id = ? AND device_id = ?",
        (constellation_id, device_id),
    )
    if await cursor.fetchone():
        return None, "This computer is already linked to this constellation."

    # 4. Enforce strict maximum capacity (5 computers)
    cursor = await db.execute(
        "SELECT COUNT(*) as count FROM constellation_members WHERE constellation_id = ?",
        (constellation_id,),
    )
    count_row = await cursor.fetchone()
    current_count = count_row["count"] if count_row else 0

    if current_count >= max_devices:
        return None, f"Constellation is full (maximum {max_devices} computers allowed)."

    # 5. Add device to constellation members
    member_id = str(uuid.uuid4())
    await db.execute(
        """
        INSERT INTO constellation_members (id, constellation_id, device_id, user_id, role)
        VALUES (?, ?, ?, ?, 'member')
        """,
        (member_id, constellation_id, device_id, user_id),
    )

    # 6. Pair this device pairwise with all existing devices in the constellation
    cursor = await db.execute(
        "SELECT device_id FROM constellation_members WHERE constellation_id = ? AND device_id != ?",
        (constellation_id, device_id),
    )
    existing_members = await cursor.fetchall()
    for row in existing_members:
        peer_device_id = row["device_id"]
        # Check if already paired
        cursor_p = await db.execute(
            """
            SELECT id FROM paired_devices 
            WHERE (device_a_id = ? AND device_b_id = ?) OR (device_a_id = ? AND device_b_id = ?)
            """,
            (device_id, peer_device_id, peer_device_id, device_id),
        )
        if not await cursor_p.fetchone():
            await db.execute(
                """
                INSERT INTO paired_devices (id, user_id, device_a_id, device_b_id)
                VALUES (?, ?, ?, ?)
                """,
                (str(uuid.uuid4()), user_id, device_id, peer_device_id),
            )

    await db.commit()
    logger.info(f"Device {device_id} joined constellation {constellation_id} ({current_count + 1}/{max_devices})")

    try:
        from apps.relay_server.core.websocket_manager import ws_manager
        await ws_manager.send_to_device(device_id, {
            "type": "constellation_joined",
            "constellation_id": constellation_id,
            "constellation_name": constellation["name"],
            "join_code": constellation["join_code"],
        })
    except Exception as exc:
        logger.debug(f"WS notification for join constellation failed: {exc}")

    # Fetch updated members
    updated = await get_constellation(constellation_id)
    return updated, None


async def get_constellation(constellation_id: str) -> Optional[Dict[str, Any]]:
    """Get complete details for a constellation including all member computers."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, name, join_code, creator_user_id, max_devices, created_at FROM constellations WHERE id = ?",
        (constellation_id,),
    )
    constellation = await cursor.fetchone()
    if not constellation:
        return None

    # Fetch member computers with details
    cursor = await db.execute(
        """
        SELECT 
            cm.id as membership_id,
            cm.role,
            cm.joined_at,
            d.id as device_id,
            d.device_name,
            d.platform,
            d.is_online,
            d.last_seen,
            u.display_name as owner_name
        FROM constellation_members cm
        JOIN devices d ON cm.device_id = d.id
        JOIN users u ON cm.user_id = u.id
        WHERE cm.constellation_id = ?
        ORDER BY cm.joined_at ASC
        """,
        (constellation_id,),
    )
    members_raw = await cursor.fetchall()
    members = []
    for m in members_raw:
        members.append({
            "membership_id": m["membership_id"],
            "device_id": m["device_id"],
            "device_name": m["device_name"],
            "platform": m["platform"],
            "is_online": bool(m["is_online"]),
            "last_seen": m["last_seen"],
            "role": m["role"],
            "owner_name": m["owner_name"],
            "joined_at": m["joined_at"],
        })

    max_devices = constellation["max_devices"] or MAX_CONSTELLATION_DEVICES
    return {
        "id": constellation["id"],
        "name": constellation["name"],
        "join_code": constellation["join_code"],
        "creator_user_id": constellation["creator_user_id"],
        "max_devices": max_devices,
        "device_count": len(members),
        "is_full": len(members) >= max_devices,
        "created_at": constellation["created_at"],
        "members": members,
    }


async def list_user_constellations(user_id: str) -> List[Dict[str, Any]]:
    """List all constellations that the user owns or has devices in."""
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT DISTINCT c.id
        FROM constellations c
        LEFT JOIN constellation_members cm ON c.id = cm.constellation_id
        WHERE c.creator_user_id = ? OR cm.user_id = ?
        ORDER BY c.created_at DESC
        """,
        (user_id, user_id),
    )
    rows = await cursor.fetchall()
    results = []
    for r in rows:
        c_info = await get_constellation(r["id"])
        if c_info:
            results.append(c_info)
    return results


async def leave_constellation(
    user_id: str,
    constellation_id: str,
    device_id: str,
) -> Tuple[bool, Optional[str]]:
    """
    Remove a computer from a constellation room.
    If no computers remain, deletes the room.
    """
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT id FROM constellation_members 
        WHERE constellation_id = ? AND device_id = ? AND user_id = ?
        """,
        (constellation_id, device_id, user_id),
    )
    member = await cursor.fetchone()
    if not member:
        return False, "Device is not a member of this constellation."

    await db.execute(
        "DELETE FROM constellation_members WHERE id = ?",
        (member["id"],),
    )

    # Check remaining members
    cursor = await db.execute(
        "SELECT COUNT(*) as count FROM constellation_members WHERE constellation_id = ?",
        (constellation_id,),
    )
    count = (await cursor.fetchone())["count"]
    if count == 0:
        await db.execute("DELETE FROM constellations WHERE id = ?", (constellation_id,))
        logger.info(f"Constellation {constellation_id} deleted as it has 0 members.")

    await db.commit()
    logger.info(f"Device {device_id} removed from constellation {constellation_id}")

    try:
        from apps.relay_server.core.websocket_manager import ws_manager
        await ws_manager.send_to_device(device_id, {
            "type": "constellation_left",
            "constellation_id": constellation_id,
        })
    except Exception as exc:
        logger.debug(f"WS notification for leave constellation failed: {exc}")

    return True, None


async def delete_constellation(
    user_id: str,
    constellation_id: str,
) -> Tuple[bool, Optional[str]]:
    """
    Delete a constellation owned by the user, removing all member associations.
    """
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, creator_user_id FROM constellations WHERE id = ?",
        (constellation_id,)
    )
    constellation = await cursor.fetchone()
    if not constellation:
        return False, "Constellation not found."
    if constellation["creator_user_id"] != user_id:
        return False, "Only the creator can delete this constellation."

    await db.execute("DELETE FROM constellation_members WHERE constellation_id = ?", (constellation_id,))
    await db.execute("DELETE FROM constellations WHERE id = ?", (constellation_id,))
    await db.commit()
    logger.info(f"Constellation {constellation_id} deleted by creator user {user_id}")
    return True, None


async def get_constellation_transfer_targets(device_id: str) -> List[Dict[str, Any]]:
    """
    Find all peer computers that share an isolated constellation room with device_id.
    Ensures transfers remain strictly within the constellation boundary.
    """
    db = await get_db()
    cursor = await db.execute(
        """
        SELECT DISTINCT 
            d.id as device_id,
            d.device_name,
            d.platform,
            d.is_online,
            c.id as constellation_id,
            c.name as constellation_name
        FROM constellation_members my_m
        JOIN constellation_members peer_m ON my_m.constellation_id = peer_m.constellation_id
        JOIN devices d ON peer_m.device_id = d.id
        JOIN constellations c ON my_m.constellation_id = c.id
        WHERE my_m.device_id = ? AND peer_m.device_id != ?
        """,
        (device_id, device_id),
    )
    rows = await cursor.fetchall()
    return [
        {
            "device_id": r["device_id"],
            "device_name": r["device_name"],
            "platform": r["platform"],
            "is_online": bool(r["is_online"]),
            "constellation_id": r["constellation_id"],
            "constellation_name": r["constellation_name"],
        }
        for r in rows
    ]
