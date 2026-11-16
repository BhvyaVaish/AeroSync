"""Session model — Pydantic schemas for session API requests/responses."""

from typing import List, Optional
from pydantic import BaseModel, Field


class SessionInitiateRequest(BaseModel):
    """Session transfer initiation request."""
    source_device_id: str
    target_device_id: str


class SessionInitiateResponse(BaseModel):
    """Session initiation response."""
    transfer_id: str
    upload_url: str
    upload_expires_at: str


class SessionUploadedRequest(BaseModel):
    """Notification that package was uploaded."""
    package_size_bytes: int
    encrypted_key: str


class SessionAcceptRequest(BaseModel):
    """Session acceptance request."""
    target_device_id: str


class SessionAcceptResponse(BaseModel):
    """Session acceptance response with download URL."""
    download_url: str
    encrypted_key: str


class SessionCompleteRequest(BaseModel):
    """Session completion notification."""
    target_device_id: str
    success: bool
    error_message: Optional[str] = None


class SessionHistoryItem(BaseModel):
    """Single item in transfer history."""
    transfer_id: str
    status: str
    source_device_name: Optional[str] = None
    target_device_name: Optional[str] = None
    initiated_at: Optional[str] = None
    completed_at: Optional[str] = None
    package_size_bytes: int = 0


class SessionHistoryResponse(BaseModel):
    """Paginated transfer history response."""
    sessions: List[SessionHistoryItem] = Field(default_factory=list)
    total: int = 0
    limit: int = 20
    offset: int = 0
