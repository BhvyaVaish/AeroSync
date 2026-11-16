"""
AeroSync Authentication Middleware

Provides the `get_current_user` FastAPI dependency for protecting routes.
Extracts and validates JWT from Authorization header.
"""

from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from apps.relay_server.core.security import validate_access_token
from apps.relay_server.services.auth_service import get_user_profile
from shared.utils.logger import get_logger

logger = get_logger(__name__)

# FastAPI security scheme — extracts Bearer token from Authorization header
_bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> dict:
    """
    FastAPI dependency that validates the JWT access token and returns the current user.
    
    Usage in routes:
        @router.get("/protected")
        async def protected_route(user: dict = Depends(get_current_user)):
            return {"user_id": user["user_id"]}
    
    Args:
        credentials: The Bearer token extracted from Authorization header.
        
    Returns:
        dict: User profile data including user_id, email, display_name, devices.
        
    Raises:
        HTTPException 401: If token is missing, invalid, or expired.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    token = credentials.credentials
    
    # Validate the access token
    user_id = validate_access_token(token)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Fetch user profile
    user = await get_user_profile(user_id)
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user


async def get_current_user_id(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer_scheme),
) -> str:
    """
    Lightweight dependency that returns just the user_id without DB lookup.
    
    Use this for endpoints where you only need the user_id and will
    do your own DB queries.
    
    Args:
        credentials: The Bearer token from Authorization header.
        
    Returns:
        str: The authenticated user's UUID.
        
    Raises:
        HTTPException 401: If token is missing, invalid, or expired.
    """
    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    user_id = validate_access_token(credentials.credentials)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired access token",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return user_id
