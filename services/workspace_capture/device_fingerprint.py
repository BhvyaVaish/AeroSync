"""
AeroSync Device Fingerprint Generator

Generates a stable, unique device identifier from Windows system properties.
The fingerprint is consistent across reboots and application restarts.
"""

import hashlib
import platform
import uuid
from typing import Optional

from shared.utils.logger import get_logger

logger = get_logger(__name__)


def get_machine_guid() -> Optional[str]:
    """
    Read the Windows MachineGuid from the registry.
    
    Location: HKLM\\SOFTWARE\\Microsoft\\Cryptography\\MachineGuid
    
    Returns:
        Optional[str]: The MachineGuid string, or None if not available.
    """
    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Microsoft\Cryptography",
            0,
            winreg.KEY_READ | winreg.KEY_WOW64_64KEY,
        )
        value, _ = winreg.QueryValueEx(key, "MachineGuid")
        winreg.CloseKey(key)
        return str(value)
    except Exception as e:
        logger.warning(f"Could not read MachineGuid from registry: {e}")
        return None


def get_hostname() -> str:
    """
    Get the system hostname.
    
    Returns:
        str: The hostname string.
    """
    return platform.node()


def get_mac_address() -> str:
    """
    Get the primary MAC address of the system.
    
    Returns:
        str: The MAC address as a hex string.
    """
    mac = uuid.getnode()
    return f"{mac:012x}"


def generate_device_fingerprint() -> str:
    """
    Generate a stable device fingerprint by hashing system properties.
    
    Combines:
    - Windows MachineGuid (from registry)
    - Hostname
    - Primary MAC address
    
    The result is a SHA-256 hash that remains consistent across reboots.
    
    Returns:
        str: A 64-character hex SHA-256 hash uniquely identifying this device.
    """
    machine_guid = get_machine_guid() or "unknown-guid"
    hostname = get_hostname()
    mac_address = get_mac_address()
    
    # Combine all identifiers
    fingerprint_input = f"{machine_guid}:{hostname}:{mac_address}"
    
    # Hash to produce a consistent fingerprint
    fingerprint = hashlib.sha256(fingerprint_input.encode("utf-8")).hexdigest()
    
    logger.debug(f"Generated device fingerprint: {fingerprint[:16]}...")
    return fingerprint
