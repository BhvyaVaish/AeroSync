"""
AeroSync Input Validators

Validation utilities for emails, passwords, device names, and other user input.
Used across routers and services for consistent input validation.
"""

import re
from typing import Optional, Tuple


# Pre-compiled regex patterns
_EMAIL_PATTERN = re.compile(
    r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
)
_UUID_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    re.IGNORECASE,
)


def validate_email(email: str) -> Tuple[bool, Optional[str]]:
    """
    Validate email format.
    
    Args:
        email: Email address to validate.
        
    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    if not email or not email.strip():
        return False, "Email is required"
    
    email = email.strip().lower()
    
    if len(email) > 254:
        return False, "Email is too long (max 254 characters)"
    
    if not _EMAIL_PATTERN.match(email):
        return False, "Invalid email format"
    
    return True, None


def validate_password(password: str) -> Tuple[bool, Optional[str]]:
    """
    Validate password strength.
    
    Requirements:
    - Minimum 8 characters
    - At least 1 number
    - At least 1 special character
    
    Args:
        password: Password to validate.
        
    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    if not password:
        return False, "Password is required"
    
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    
    if not re.search(r"\d", password):
        return False, "Password must contain at least 1 number"
    
    if not re.search(r"[!@#$%^&*()_+\-=\[\]{};':\"\\|,.<>/?`~]", password):
        return False, "Password must contain at least 1 special character"
    
    return True, None


def validate_device_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate device name.
    
    Args:
        name: Device name to validate.
        
    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    if not name or not name.strip():
        return False, "Device name is required"
    
    name = name.strip()
    
    if len(name) < 1:
        return False, "Device name is too short"
    
    if len(name) > 100:
        return False, "Device name is too long (max 100 characters)"
    
    return True, None


def validate_uuid(value: str) -> Tuple[bool, Optional[str]]:
    """
    Validate UUID format.
    
    Args:
        value: String to validate as UUID.
        
    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    if not value:
        return False, "UUID is required"
    
    if not _UUID_PATTERN.match(value):
        return False, "Invalid UUID format"
    
    return True, None


def validate_pairing_code(code: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a 6-digit pairing code.
    
    Args:
        code: Pairing code to validate.
        
    Returns:
        Tuple of (is_valid, error_message). error_message is None if valid.
    """
    if not code:
        return False, "Pairing code is required"
    
    code = code.strip()
    
    if not code.isdigit():
        return False, "Pairing code must contain only digits"
    
    if len(code) != 6:
        return False, "Pairing code must be exactly 6 digits"
    
    return True, None


def sanitize_string(value: str, max_length: int = 500) -> str:
    """
    Sanitize a string input by stripping whitespace and truncating.
    
    Args:
        value: String to sanitize.
        max_length: Maximum allowed length.
        
    Returns:
        str: Sanitized string.
    """
    if not value:
        return ""
    return value.strip()[:max_length]
