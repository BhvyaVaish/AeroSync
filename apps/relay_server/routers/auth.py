"""
AeroSync Authentication Router

Endpoints for user registration, login, token refresh, logout, and profile.
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from apps.relay_server.middleware.auth_middleware import get_current_user, get_current_user_id
from apps.relay_server.services.auth_service import (
    login_user,
    logout_user,
    refresh_access_token,
    register_user,
)
from shared.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter()


# =============================================================================
# Request/Response Models
# =============================================================================

class RegisterRequest(BaseModel):
    """Registration request body."""
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password (min 8 chars, 1 number, 1 special)")
    display_name: Optional[str] = Field(None, description="Optional display name")


class LoginRequest(BaseModel):
    """Login request body."""
    email: str = Field(..., description="User email address")
    password: str = Field(..., description="User password")


class RefreshRequest(BaseModel):
    """Token refresh request body."""
    refresh_token: str = Field(..., description="Valid refresh token")


class AuthResponse(BaseModel):
    """Authentication response with tokens."""
    user_id: str
    email: str
    display_name: str
    access_token: str
    refresh_token: str


class TokenResponse(BaseModel):
    """Token-only response for refresh endpoint."""
    access_token: str


class MessageResponse(BaseModel):
    """Simple message response."""
    success: bool
    message: str = ""


# =============================================================================
# Routes
# =============================================================================

@router.post(
    "/register",
    response_model=AuthResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user",
)
async def register(request: RegisterRequest):
    """
    Register a new user account.
    
    Validates email format and password strength, creates the user,
    and returns access and refresh tokens.
    """
    result, error = await register_user(
        email=request.email,
        password=request.password,
        display_name=request.display_name,
    )
    
    if error:
        if "already registered" in error.lower():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=error)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=error)
    
    return result


@router.post(
    "/login",
    response_model=AuthResponse,
    summary="Login with email and password",
)
async def login(request: LoginRequest):
    """
    Authenticate with email and password.
    
    Returns access and refresh tokens on success.
    """
    result, error = await login_user(
        email=request.email,
        password=request.password,
    )
    
    if error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error,
        )
    
    return result


@router.post(
    "/refresh",
    response_model=TokenResponse,
    summary="Refresh access token",
)
async def refresh(request: RefreshRequest):
    """
    Get a new access token using a valid refresh token.
    """
    result, error = await refresh_access_token(request.refresh_token)
    
    if error:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=error,
        )
    
    return result


@router.post(
    "/logout",
    response_model=MessageResponse,
    summary="Logout and revoke tokens",
)
async def logout(user_id: str = Depends(get_current_user_id)):
    """
    Logout the current user by revoking all refresh tokens.
    
    Requires a valid access token in the Authorization header.
    """
    await logout_user(user_id)
    return MessageResponse(success=True, message="Logged out successfully")


@router.get(
    "/me",
    summary="Get current user profile",
)
async def get_me(user: dict = Depends(get_current_user)):
    """
    Get the authenticated user's profile including registered devices.
    
    Requires a valid access token in the Authorization header.
    """
    return user
