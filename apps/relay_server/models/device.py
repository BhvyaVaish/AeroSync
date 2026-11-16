"""Device model — Pydantic schemas for device API requests/responses."""

from typing import List, Optional
from pydantic import BaseModel, Field


class DeviceRegisterRequest(BaseModel):
    """Device registration request."""
    device_name: str = Field(..., min_length=1, max_length=100)
    device_fingerprint: str = Field(..., min_length=1)
    platform: str = Field(default="windows")


class DeviceResponse(BaseModel):
    """Device response."""
    device_id: str
    device_name: str
    platform: str
    is_online: bool = False
    last_seen: Optional[str] = None
    created_at: Optional[str] = None


class DeviceWithPairings(DeviceResponse):
    """Device with paired device list."""
    paired_devices: List[DeviceResponse] = Field(default_factory=list)


class PairInitiateRequest(BaseModel):
    """Pairing initiation request."""
    source_device_id: str


class PairCompleteRequest(BaseModel):
    """Pairing completion request."""
    pairing_code: str = Field(..., min_length=6, max_length=6)
    target_device_id: str


class PairResponse(BaseModel):
    """Pairing code response."""
    pairing_code: str
    expires_at: str
