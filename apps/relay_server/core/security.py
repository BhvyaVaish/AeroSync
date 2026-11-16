"""
AeroSync Security Utilities

JWT token creation/validation and password hashing with bcrypt.
All secrets loaded from environment — nothing hardcoded.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

from shared.constants import (
    BCRYPT_COST_FACTOR,
    TOKEN_TYPE_ACCESS,
    TOKEN_TYPE_REFRESH,
)
from shared.utils.logger import get_logger

logger = get_logger(__name__)

# Password hashing context
_pwd_context = CryptContext(
    schemes=["bcrypt"],
    deprecated="auto",
    bcrypt__rounds=BCRYPT_COST_FACTOR,
)


# =============================================================================
# Password Hashing
# =============================================================================

def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt with configured cost factor.
    
    Args:
        password: The plaintext password to hash.
        
    Returns:
        str: The bcrypt hash string.
    """
    return _pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a plaintext password against a bcrypt hash.
    
    Args:
        plain_password: The plaintext password to verify.
        hashed_password: The stored bcrypt hash.
        
    Returns:
        bool: True if the password matches.
    """
    try:
        return _pwd_context.verify(plain_password, hashed_password)
    except Exception as e:
        logger.warning(f"Password verification error: {e}")
        return False


# =============================================================================
# JWT Token Management
# =============================================================================

def _get_jwt_config() -> Dict[str, Any]:
    """
    Load JWT configuration from settings.
    
    Returns:
        Dict with 'secret', 'algorithm', 'access_expire_minutes', 'refresh_expire_days'.
    """
    import os
    
    try:
        from config.settings import get_settings
        settings = get_settings()
        return {
            "secret": settings.jwt.secret,
            "algorithm": settings.jwt.algorithm,
            "access_expire_minutes": settings.jwt.access_token_expire_minutes,
            "refresh_expire_days": settings.jwt.refresh_token_expire_days,
        }
    except Exception as settings_err:
        # Fallback: read directly from environment
        secret = os.environ.get("JWT_SECRET")
        if secret:
            logger.debug(f"Using JWT_SECRET from os.environ (settings error: {settings_err})")
            return {
                "secret": secret,
                "algorithm": os.environ.get("JWT_ALGORITHM", "HS256"),
                "access_expire_minutes": int(os.environ.get("JWT_ACCESS_TOKEN_EXPIRE_MINUTES", "1440")),
                "refresh_expire_days": int(os.environ.get("JWT_REFRESH_TOKEN_EXPIRE_DAYS", "30")),
            }
        raise RuntimeError(
            f"JWT_SECRET not configured. Set it in .env or environment variables. "
            f"Settings error: {settings_err}"
        )


def create_access_token(user_id: str, extra_claims: Optional[Dict] = None) -> str:
    """
    Create a JWT access token.
    
    Args:
        user_id: The user's UUID to encode as 'sub' claim.
        extra_claims: Optional additional claims to include.
        
    Returns:
        str: The encoded JWT access token.
    """
    config = _get_jwt_config()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(minutes=config["access_expire_minutes"])
    
    payload = {
        "sub": user_id,
        "type": TOKEN_TYPE_ACCESS,
        "iat": now,
        "exp": expire,
    }
    if extra_claims:
        payload.update(extra_claims)
    
    return jwt.encode(payload, config["secret"], algorithm=config["algorithm"])


def create_refresh_token(user_id: str) -> str:
    """
    Create a JWT refresh token with longer expiry.
    
    Args:
        user_id: The user's UUID to encode as 'sub' claim.
        
    Returns:
        str: The encoded JWT refresh token.
    """
    config = _get_jwt_config()
    now = datetime.now(timezone.utc)
    expire = now + timedelta(days=config["refresh_expire_days"])
    
    payload = {
        "sub": user_id,
        "type": TOKEN_TYPE_REFRESH,
        "iat": now,
        "exp": expire,
    }
    
    return jwt.encode(payload, config["secret"], algorithm=config["algorithm"])


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decode and validate a JWT token.
    
    Args:
        token: The JWT token string to decode.
        
    Returns:
        Optional[Dict]: The decoded payload, or None if invalid/expired.
    """
    config = _get_jwt_config()
    try:
        payload = jwt.decode(
            token,
            config["secret"],
            algorithms=[config["algorithm"]],
        )
        return payload
    except JWTError as e:
        logger.debug(f"JWT decode error: {e}")
        return None


def validate_access_token(token: str) -> Optional[str]:
    """
    Validate an access token and return the user_id.
    
    Args:
        token: The JWT access token to validate.
        
    Returns:
        Optional[str]: The user_id (sub claim) if valid, None otherwise.
    """
    payload = decode_token(token)
    if payload is None:
        return None
    
    if payload.get("type") != TOKEN_TYPE_ACCESS:
        logger.debug("Token is not an access token")
        return None
    
    user_id = payload.get("sub")
    if not user_id:
        logger.debug("Token missing 'sub' claim")
        return None
    
    return user_id


def validate_refresh_token(token: str) -> Optional[str]:
    """
    Validate a refresh token and return the user_id.
    
    Args:
        token: The JWT refresh token to validate.
        
    Returns:
        Optional[str]: The user_id (sub claim) if valid, None otherwise.
    """
    payload = decode_token(token)
    if payload is None:
        return None
    
    if payload.get("type") != TOKEN_TYPE_REFRESH:
        logger.debug("Token is not a refresh token")
        return None
    
    user_id = payload.get("sub")
    if not user_id:
        logger.debug("Token missing 'sub' claim")
        return None
    
    return user_id
