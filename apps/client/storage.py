"""
AeroSync Client Storage

Simple local JSON persistence for client state (tokens, device ID).
"""

import json
import os
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)

# Save in the user's home directory or app data
# For development, we'll just save it in the project root
STORAGE_PATH = Path(os.getcwd()) / ".aerosync_client_state.json"


def load_state() -> Dict[str, Any]:
    """Load client state from local JSON file."""
    if not STORAGE_PATH.exists():
        return {}
        
    try:
        with open(STORAGE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        logger.warning(f"Failed to load client state: {e}")
        return {}


def save_state(state: Dict[str, Any]) -> None:
    """Save client state to local JSON file."""
    try:
        # Merge with existing
        current = load_state()
        current.update(state)
        
        with open(STORAGE_PATH, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
    except Exception as e:
        logger.error(f"Failed to save client state: {e}")


def get_token() -> Optional[str]:
    return load_state().get("access_token")

def set_tokens(access: str, refresh: str) -> None:
    save_state({"access_token": access, "refresh_token": refresh})

def get_device_id() -> Optional[str]:
    return load_state().get("device_id")

def set_device_id(device_id: str) -> None:
    save_state({"device_id": device_id})

def get_server_url() -> str:
    return load_state().get("server_url", "http://127.0.0.1:8000")

def set_server_url(url: str) -> None:
    save_state({"server_url": url})

def get_constellation_id() -> Optional[str]:
    """Return the constellation ID this device is currently a member of."""
    return load_state().get("constellation_id")

def set_constellation_id(constellation_id: str) -> None:
    """Persist the active constellation ID after create/join."""
    save_state({"constellation_id": constellation_id})

def clear_constellation_id() -> None:
    """Clear constellation membership (after leaving/resetting)."""
    state = load_state()
    state.pop("constellation_id", None)
    # Rewrite the entire file without that key
    try:
        with open(STORAGE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        logger.error("Failed to clear constellation_id: %s", e)
