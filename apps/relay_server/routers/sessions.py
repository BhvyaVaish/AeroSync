"""
AeroSync Session Transfer Router

Endpoints for workspace transfer session lifecycle.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from apps.relay_server.middleware.auth_middleware import get_current_user_id
from apps.relay_server.services.session_service import (
    accept_session,
    cancel_session,
    complete_session,
    get_session_history,
    initiate_session,
    load_package,
    mark_uploaded,
    save_package,
)
from shared.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class InitiateRequest(BaseModel):
    """Session initiation request."""
    source_device_id: str
    target_device_id: str


class InitiateResponse(BaseModel):
    """Session initiation response."""
    transfer_id: str
    upload_url: str
    upload_expires_at: str


class UploadedRequest(BaseModel):
    """Package uploaded notification."""
    package_size_bytes: int
    encrypted_key: str


class AcceptRequest(BaseModel):
    """Session acceptance request."""
    target_device_id: str


class AcceptResponse(BaseModel):
    """Session acceptance response."""
    download_url: str
    encrypted_key: str


class CompleteRequest(BaseModel):
    """Session completion request."""
    target_device_id: str
    success: bool
    error_message: Optional[str] = None


class MessageResponse(BaseModel):
    """Simple response."""
    success: bool
    message: str = ""


# =============================================================================
# Routes
# =============================================================================

@router.post(
    "/initiate",
    response_model=InitiateResponse,
    summary="Initiate a workspace transfer",
)
async def initiate(
    request: InitiateRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Start a new workspace transfer between two paired devices.
    
    Validates device ownership, pairing, and target online status.
    Returns a transfer_id and upload URL.
    """
    result, error = await initiate_session(
        user_id=user_id,
        source_device_id=request.source_device_id,
        target_device_id=request.target_device_id,
    )
    
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    
    return result


@router.post(
    "/{transfer_id}/upload",
    summary="Upload session package",
)
async def upload_package(
    transfer_id: str,
    request: Request,
    user_id: str = Depends(get_current_user_id),
):
    """
    Upload the encrypted session package for a transfer.
    
    Accepts raw bytes in the request body.
    """
    body = await request.body()
    
    if not body:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty request body",
        )
    
    # Save the package
    await save_package(transfer_id, body)
    
    return {"success": True, "size_bytes": len(body)}


@router.post(
    "/{transfer_id}/uploaded",
    response_model=MessageResponse,
    summary="Mark package as uploaded",
)
async def mark_as_uploaded(
    transfer_id: str,
    request: UploadedRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Notify the server that the package has been uploaded.
    
    Triggers a WebSocket notification to the target device.
    """
    success, error = await mark_uploaded(
        user_id=user_id,
        transfer_id=transfer_id,
        package_size_bytes=request.package_size_bytes,
        encrypted_key=request.encrypted_key,
    )
    
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    
    return MessageResponse(success=True, message="Target device notified")


@router.post(
    "/{transfer_id}/accept",
    response_model=AcceptResponse,
    summary="Accept an incoming transfer",
)
async def accept(
    transfer_id: str,
    request: AcceptRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Accept a pending incoming transfer and get the download URL.
    """
    result, error = await accept_session(
        user_id=user_id,
        transfer_id=transfer_id,
        target_device_id=request.target_device_id,
    )
    
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    
    return result


@router.get(
    "/{transfer_id}/download",
    summary="Download session package",
)
async def download_package(
    transfer_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Download the encrypted session package for a transfer.
    
    Returns raw bytes of the encrypted package.
    """
    data = await load_package(transfer_id)
    
    if data is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Package not found",
        )
    
    return Response(
        content=data,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={transfer_id}.bin"},
    )


@router.post(
    "/{transfer_id}/complete",
    response_model=MessageResponse,
    summary="Mark transfer as complete",
)
async def complete(
    transfer_id: str,
    request: CompleteRequest,
    user_id: str = Depends(get_current_user_id),
):
    """
    Mark a transfer as complete (or failed) after reconstruction.
    
    Notifies the source device of the result.
    """
    success, error = await complete_session(
        user_id=user_id,
        transfer_id=transfer_id,
        target_device_id=request.target_device_id,
        success=request.success,
        error_message=request.error_message,
    )
    
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    
    return MessageResponse(success=True, message="Transfer completed")


@router.get(
    "/history",
    summary="Get transfer history",
)
async def history(
    device_id: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
    user_id: str = Depends(get_current_user_id),
):
    """Get paginated transfer history for the authenticated user."""
    return await get_session_history(
        user_id=user_id,
        device_id=device_id,
        limit=min(limit, 100),
        offset=offset,
    )


@router.delete(
    "/{transfer_id}",
    response_model=MessageResponse,
    summary="Cancel a transfer",
)
async def cancel(
    transfer_id: str,
    user_id: str = Depends(get_current_user_id),
):
    """
    Cancel a pending transfer.
    
    Deletes the package from storage and notifies the target device.
    """
    success, error = await cancel_session(user_id=user_id, transfer_id=transfer_id)
    
    if error:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    
    return MessageResponse(success=True, message="Transfer cancelled")
