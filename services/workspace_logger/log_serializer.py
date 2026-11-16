"""
AeroSync Workspace Logger — Log Queue Serialiser

Converts a WorkspaceLogQueue to/from bytes for AES-256-GCM packaging
and transmission to Target B.

The serialised form preserves FIFO order (oldest entry first in the JSON
array), so Target B reconstructs events in the same chronological sequence
they occurred on Host A.
"""

from __future__ import annotations

import json
import zlib
from typing import Tuple

from services.workspace_logger.log_stack import WorkspaceLogQueue


def serialise_queue(queue: WorkspaceLogQueue) -> bytes:
    """
    Serialise a WorkspaceLogQueue to compressed JSON bytes.

    Entry order in the JSON array is oldest → newest (FIFO-preserved).

    Returns:
        zlib-compressed UTF-8 JSON bytes.
    """
    raw_dict = queue.to_dict()
    json_bytes = json.dumps(raw_dict, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return zlib.compress(json_bytes, level=6)


def deserialise_queue(data: bytes) -> WorkspaceLogQueue:
    """
    Deserialise a WorkspaceLogQueue from compressed JSON bytes.

    Args:
        data: zlib-compressed UTF-8 JSON bytes as produced by `serialise_queue`.

    Returns:
        WorkspaceLogQueue with all entries loaded in original FIFO order.
    """
    json_bytes = zlib.decompress(data)
    raw_dict = json.loads(json_bytes.decode("utf-8"))
    return WorkspaceLogQueue.from_dict(raw_dict)


def roundtrip_check(queue: WorkspaceLogQueue) -> Tuple[bool, str]:
    """
    Verify that a queue serialises and deserialises without data loss,
    and that FIFO order is maintained across the roundtrip.

    Returns:
        (ok, message)
    """
    try:
        compressed = serialise_queue(queue)
        restored = deserialise_queue(compressed)

        original_ids = [e.entry_id for e in queue.snapshot()]
        restored_ids = [e.entry_id for e in restored.snapshot()]

        if original_ids == restored_ids:
            return True, f"OK — {len(original_ids)} entries, {len(compressed)} bytes, FIFO order preserved"

        set_missing = set(original_ids) - set(restored_ids)
        set_extra = set(restored_ids) - set(original_ids)
        return False, f"Mismatch: missing={set_missing}, extra={set_extra}"
    except Exception as exc:
        return False, f"Error: {exc}"


# ── Backward-compat aliases ───────────────────────────────────────────────────
serialise_stack   = serialise_queue
deserialise_stack = deserialise_queue
