"""
AeroSync Authentication Service

Business logic for user registration, login, token management.
Interfaces with the database layer — no direct SQL here.
"""

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Optional, Tuple

from apps.relay_server.core.database import execute, fetch_one, fetch_all
from apps.relay_server.core.security import (
    create_access_token,
    create_refresh_token,
    hash_password,
    validate_refresh_token,
    verify_password,
)
from shared.utils.crypto import sha256_hash_string
from shared.utils.logger import get_logger
from shared.utils.validators import validate_email, validate_password

logger = get_logger(__name__)


async def register_user(
    email: str, password: str, display_name: Optional[str] = None
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Register a new user.
    
    Args:
        email: User's email address.
        password: User's plaintext password.
        display_name: Optional display name.
        
    Returns:
        Tuple of (user_data_with_tokens, error_message).
        user_data is None if registration failed.
    """
    # Validate email
    valid, error = validate_email(email)
    if not valid:
        return None, error
    
    email = email.strip().lower()
    
    # Validate password
    valid, error = validate_password(password)
    if not valid:
        return None, error
    
    # Check if email already exists
    existing = await fetch_one("SELECT id FROM users WHERE email = ?", (email,))
    if existing:
        return None, "Email already registered"
    
    # Create user
    user_id = str(uuid.uuid4())
    password_hash = hash_password(password)
    now = datetime.now(timezone.utc).isoformat()
    
    await execute(
        """INSERT INTO users (id, email, password_hash, display_name, created_at, updated_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (user_id, email, password_hash, display_name or email.split("@")[0], now, now),
    )
    
    # Generate tokens
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)
    
    # Store refresh token hash
    await _store_refresh_token(user_id, refresh_token)
    
    logger.info(f"User registered: {user_id} ({email})")
    
    return {
        "user_id": user_id,
        "email": email,
        "display_name": display_name or email.split("@")[0],
        "access_token": access_token,
        "refresh_token": refresh_token,
    }, None


async def login_user(
    email: str, password: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Authenticate a user with email and password.
    
    Args:
        email: User's email address.
        password: User's plaintext password.
        
    Returns:
        Tuple of (user_data_with_tokens, error_message).
    """
    email = email.strip().lower()
    
    # Look up user
    user = await fetch_one(
        "SELECT id, email, password_hash, display_name FROM users WHERE email = ?",
        (email,),
    )
    
    if not user:
        logger.debug(f"Login failed: email not found ({email})")
        return None, "Invalid email or password"
    
    # Verify password
    if not verify_password(password, user["password_hash"]):
        logger.debug(f"Login failed: wrong password for {email}")
        return None, "Invalid email or password"
    
    # Generate tokens
    user_id = user["id"]
    access_token = create_access_token(user_id)
    refresh_token = create_refresh_token(user_id)
    
    # Store refresh token hash
    await _store_refresh_token(user_id, refresh_token)
    
    # Update last activity
    now = datetime.now(timezone.utc).isoformat()
    await execute("UPDATE users SET updated_at = ? WHERE id = ?", (now, user_id))
    
    logger.info(f"User logged in: {user_id} ({email})")
    
    return {
        "user_id": user_id,
        "email": user["email"],
        "display_name": user["display_name"],
        "access_token": access_token,
        "refresh_token": refresh_token,
    }, None


async def refresh_access_token(
    refresh_token: str,
) -> Tuple[Optional[Dict[str, str]], Optional[str]]:
    """
    Issue a new access token using a valid refresh token.
    
    Args:
        refresh_token: The refresh token to validate.
        
    Returns:
        Tuple of ({"access_token": "..."}, error_message).
    """
    # Validate the refresh token JWT
    user_id = validate_refresh_token(refresh_token)
    if not user_id:
        return None, "Invalid or expired refresh token"
    
    # Check if refresh token is revoked
    token_hash = sha256_hash_string(refresh_token)
    stored = await fetch_one(
        "SELECT revoked FROM refresh_tokens WHERE token_hash = ? AND user_id = ?",
        (token_hash, user_id),
    )
    
    if not stored:
        return None, "Refresh token not found"
    
    if stored["revoked"]:
        logger.warning(f"Revoked refresh token used for user {user_id}")
        return None, "Refresh token has been revoked"
    
    # Check user still exists
    user = await fetch_one("SELECT id FROM users WHERE id = ?", (user_id,))
    if not user:
        return None, "User not found"
    
    # Issue new access token
    new_access_token = create_access_token(user_id)
    
    logger.info(f"Access token refreshed for user {user_id}")
    
    return {"access_token": new_access_token}, None


async def logout_user(user_id: str, refresh_token: Optional[str] = None) -> bool:
    """
    Logout a user by revoking their refresh token(s).
    
    Args:
        user_id: The user's UUID.
        refresh_token: Optional specific refresh token to revoke.
                       If None, revokes all refresh tokens for the user.
        
    Returns:
        bool: True if logout was successful.
    """
    if refresh_token:
        # Revoke specific token
        token_hash = sha256_hash_string(refresh_token)
        await execute(
            "UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = ? AND user_id = ?",
            (token_hash, user_id),
        )
    else:
        # Revoke all tokens for user
        await execute(
            "UPDATE refresh_tokens SET revoked = 1 WHERE user_id = ?",
            (user_id,),
        )
    
    logger.info(f"User logged out: {user_id}")
    return True


async def get_user_profile(user_id: str) -> Optional[Dict[str, Any]]:
    """
    Get user profile with associated devices.
    
    Args:
        user_id: The user's UUID.
        
    Returns:
        Optional[Dict]: User profile data with devices list, or None.
    """
    user = await fetch_one(
        "SELECT id, email, display_name, created_at FROM users WHERE id = ?",
        (user_id,),
    )
    
    if not user:
        return None
    
    # Get user's devices
    devices = await fetch_all(
        """SELECT id, device_name, platform, is_online, last_seen, created_at
           FROM devices WHERE user_id = ?""",
        (user_id,),
    )
    
    return {
        "user_id": user["id"],
        "email": user["email"],
        "display_name": user["display_name"],
        "created_at": user["created_at"],
        "devices": devices,
    }


# =============================================================================
# Internal Helpers
# =============================================================================

async def _store_refresh_token(user_id: str, refresh_token: str) -> None:
    """Store a hashed refresh token in the database."""
    from config.settings import get_settings
    from datetime import timedelta
    
    token_id = str(uuid.uuid4())
    token_hash = sha256_hash_string(refresh_token)
    
    try:
        settings = get_settings()
        expire_days = settings.jwt.refresh_token_expire_days
    except Exception:
        expire_days = 30
    
    expires_at = (
        datetime.now(timezone.utc) + timedelta(days=expire_days)
    ).isoformat()
    
    await execute(
        """INSERT OR REPLACE INTO refresh_tokens (id, user_id, token_hash, expires_at)
           VALUES (?, ?, ?, ?)""",
        (token_id, user_id, token_hash, expires_at),
    )
