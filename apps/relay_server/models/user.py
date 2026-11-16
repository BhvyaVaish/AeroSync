"""User model — Pydantic schemas for user API requests/responses."""

from typing import List, Optional
from pydantic import BaseModel, Field


class UserBase(BaseModel):
    """Base user fields."""
    email: str
    display_name: Optional[str] = None


class UserCreate(UserBase):
    """User creation request."""
    password: str = Field(..., min_length=8)


class UserResponse(UserBase):
    """User response (no password)."""
    user_id: str
    created_at: Optional[str] = None


class UserWithDevices(UserResponse):
    """User response with device list."""
    devices: List[dict] = Field(default_factory=list)
