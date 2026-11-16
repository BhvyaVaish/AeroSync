"""
AeroSync Constellations Router

Endpoints for creating, joining, listing, and managing Constellations
(isolated rooms of up to 5 linked computers).
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from apps.relay_server.middleware.auth_middleware import get_current_user_id
from apps.relay_server.services.constellation_service import (
    create_constellation,
    join_constellation,
    list_user_constellations,
    get_constellation,
    leave_constellation,
    get_constellation_transfer_targets,
)
from shared.constants import MAX_CONSTELLATION_DEVICES
from shared.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Request / Response Schemas
# =============================================================================

class CreateConstellationRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100, description="Name for the constellation room")
    device_id: Optional[str] = Field(default=None, description="Current computer to immediately link as owner")


class JoinConstellationRequest(BaseModel):
    join_code: str = Field(..., min_length=4, max_length=20, description="Unique constellation room code")
    device_id: str = Field(..., min_length=1, description="Computer being linked to the constellation")


class LeaveConstellationRequest(BaseModel):
    device_id: str = Field(..., min_length=1, description="Computer to remove from the constellation")


class MemberInfo(BaseModel):
    device_id: str
    device_name: str
    platform: str
    is_online: bool
    role: str
    owner_name: Optional[str] = None
    joined_at: Optional[str] = None


class ConstellationResponse(BaseModel):
    id: str
    name: str
    join_code: str
    creator_user_id: str
    max_devices: int = MAX_CONSTELLATION_DEVICES
    device_count: int
    is_full: bool
    created_at: Optional[str] = None
    members: List[MemberInfo] = Field(default_factory=list)


# =============================================================================
# Routes
# =============================================================================

@router.post(
    "/create",
    response_model=ConstellationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new constellation",
)
async def create_new_constellation(
    request: CreateConstellationRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Create an isolated Constellation room.
    Generates a unique join code and links up to 5 computers together.
    """
    result, error = await create_constellation(
        user_id=user_id,
        name=request.name,
        creator_device_id=request.device_id,
    )
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    return result


@router.post(
    "/join",
    response_model=ConstellationResponse,
    summary="Join an existing constellation",
)
async def join_existing_constellation(
    request: JoinConstellationRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Link a computer into an existing Constellation room via its unique code.
    Strictly enforces maximum of 5 computers.
    """
    result, error = await join_constellation(
        user_id=user_id,
        join_code=request.join_code,
        device_id=request.device_id,
    )
    if error:
        if "full" in error.lower():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
        if "not found" in error.lower() or "no constellation" in error.lower():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    return result


@router.get(
    "/",
    summary="List user constellations",
)
async def list_constellations(user_id: str = Depends(get_current_user_id)):
    """List all constellations the current user owns or is linked to."""
    constellations = await list_user_constellations(user_id)
    return {"constellations": constellations}


@router.get(
    "/{constellation_id}",
    response_model=ConstellationResponse,
    summary="Get constellation details",
)
async def get_constellation_details(
    constellation_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get details of a specific constellation including all linked computers."""
    c = await get_constellation(constellation_id)
    if not c:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Constellation not found")
    return c


@router.post(
    "/{constellation_id}/leave",
    summary="Leave a constellation",
)
async def leave_room(
    constellation_id: str,
    request: LeaveConstellationRequest,
    user_id: str = Depends(get_current_user_id),
):
    """Remove a computer from a constellation room."""
    ok, error = await leave_constellation(user_id, constellation_id, request.device_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    return {"success": True, "message": "Left constellation successfully"}


@router.get(
    "/{device_id}/targets",
    summary="Get transfer targets within constellation",
)
async def get_targets(
    device_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """Get peer computers in the same constellation room for workspace transfer."""
    targets = await get_constellation_transfer_targets(device_id)
    return {"targets": targets}
