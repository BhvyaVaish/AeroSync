"""
AeroSync Device Management Router

Endpoints for device registration, listing, pairing, and removal.
"""


from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from apps.relay_server.middleware.auth_middleware import get_current_user_id
from apps.relay_server.services.device_service import (
    complete_pairing,
    delete_device,
    get_paired_devices,
    initiate_pairing,
    list_user_devices,
    register_device,
)
from shared.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class DeviceRegisterRequest(BaseModel):
    """Device registration request."""
    device_name: str = Field(..., min_length=1, max_length=100)
    device_fingerprint: str = Field(..., min_length=1)
    platform: str = Field(default="windows")


class DeviceResponse(BaseModel):
    """Device registration response."""
    device_id: str
    device_name: str
    platform: str
    is_new: bool = True


class PairInitiateRequest(BaseModel):
    """Pairing initiation request."""
    source_device_id: str


class PairCompleteRequest(BaseModel):
    """Pairing completion request."""
    pairing_code: str = Field(..., min_length=6, max_length=6)
    target_device_id: str


class PairInitiateResponse(BaseModel):
    """Pairing code response."""
    pairing_code: str
    expires_at: str


class MessageResponse(BaseModel):
    """Simple message response."""
    success: bool
    message: str = ""


# =============================================================================
# Routes
# =============================================================================

@router.post(
    "/register",
    response_model=DeviceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a device",
)
async def register(
    request: DeviceRegisterRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Register a new device or update an existing one.
    
    If a device with the same fingerprint exists for this user,
    updates the device name and last_seen timestamp.
    """
    result, error = await register_device(
        user_id=user_id,
        device_name=request.device_name,
        device_fingerprint=request.device_fingerprint,
        platform=request.platform,
    )
    
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    
    return result


@router.get(
    "/",
    summary="List user devices",
)
async def list_devices(user_id: str = Depends(get_current_user_id)):
    """List all devices belonging to the authenticated user with pairing info."""
    devices = await list_user_devices(user_id)
    return {"devices": devices}


@router.post(
    "/pair/initiate",
    response_model=PairInitiateResponse,
    summary="Initiate device pairing",
)
async def pair_initiate(
    request: PairInitiateRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Generate a 6-digit pairing code for a device.
    
    The code expires after 15 minutes. Share this code with
    the target device to complete pairing.
    """
    result, error = await initiate_pairing(user_id, request.source_device_id)
    
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    
    return result


@router.post(
    "/pair/complete",
    summary="Complete device pairing",
)
async def pair_complete(
    request: PairCompleteRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Complete device pairing using a 6-digit code.
    
    Validates the pairing code, checks expiry, and creates
    a bidirectional pairing record.
    """
    result, error = await complete_pairing(
        user_id=user_id,
        pairing_code=request.pairing_code,
        target_device_id=request.target_device_id,
    )
    
    if error:
        if "expired" in error.lower():
            raise HTTPException(status_code=status.HTTP_410_GONE, detail=error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    
    return result


@router.delete(
    "/{device_id}",
    response_model=MessageResponse,
    summary="Delete a device",
)
async def remove_device(
    device_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Delete a device and all its pairings.
    
    Verifies the device belongs to the authenticated user.
    """
    success, error = await delete_device(user_id, device_id)
    
    if error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error)
    
    return MessageResponse(success=True, message="Device deleted")


@router.get(
    "/{device_id}/paired",
    summary="Get paired devices",
)
async def get_device_pairings(
    device_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Return all devices paired with the given device."""
    paired = await get_paired_devices(user_id, device_id)
    return {"paired_devices": paired}
