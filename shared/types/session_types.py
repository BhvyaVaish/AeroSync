"""
AeroSync Session Type Definitions

Data structures for workspace transfer sessions.
"""

from dataclasses import dataclass
from typing import Any, Dict, Optional


@dataclass
class SessionInfo:
    """Information about a workspace transfer session."""
    session_id: str = ""
    transfer_id: str = ""
    source_device_id: str = ""
    target_device_id: str = ""
    status: str = "pending"
    package_url: Optional[str] = None
    package_size_bytes: int = 0
    encrypted_key: Optional[str] = None
    expires_at: Optional[str] = None
    initiated_at: Optional[str] = None
    completed_at: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None


@dataclass
class TransferResult:
    """Result of a transfer operation."""
    transfer_id: str = ""
    success: bool = False
    error_message: Optional[str] = None
    duration_ms: int = 0
    package_size_bytes: int = 0


@dataclass
class TransferProgress:
    """Progress update during a transfer."""
    transfer_id: str = ""
    stage: str = ""  # capturing | packaging | uploading | waiting | downloading | reconstructing
    progress_percent: float = 0.0
    message: str = ""
