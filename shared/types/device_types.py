"""
AeroSync Device Type Definitions

Data structures for device registration, fingerprinting, and pairing.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class DeviceInfo:
    """Information about a registered device."""
    device_id: str = ""
    user_id: str = ""
    device_name: str = ""
    device_fingerprint: str = ""
    platform: str = "windows"
    is_online: bool = False
    last_seen: Optional[str] = None  # ISO 8601 datetime
    created_at: Optional[str] = None


@dataclass
class PairedDevice:
    """Information about a device pairing."""
    pairing_id: str = ""
    device_a_id: str = ""
    device_b_id: str = ""
    user_id: str = ""
    paired_at: Optional[str] = None


@dataclass
class DeviceWithPairings:
    """Device info enriched with its paired devices."""
    device: DeviceInfo = field(default_factory=DeviceInfo)
    paired_devices: List[DeviceInfo] = field(default_factory=list)


@dataclass
class PairingRequest:
    """A pending pairing request with its code."""
    device_id: str = ""
    pairing_code: str = ""
    expires_at: str = ""  # ISO 8601 datetime
