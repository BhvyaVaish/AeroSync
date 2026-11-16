r"""
AeroSync Windows Auto-Start Manager

Configures AeroSync to automatically start on Windows user login
via the Windows Registry Run key:
HKCU\Software\Microsoft\Windows\CurrentVersion\Run
"""

import logging
import os
import sys

logger = logging.getLogger(__name__)

REG_KEY_PATH = r"Software\Microsoft\Windows\CurrentVersion\Run"
REG_VALUE_NAME = "AeroSync"


def _get_autostart_command() -> str:
    """Construct the command line to start AeroSync in background tray mode on login."""
    # Find pythonw or python
    python_exe = sys.executable
    # Prefer pythonw if available (no console window)
    pythonw_candidate = python_exe.replace("python.exe", "pythonw.exe")
    if os.path.isfile(pythonw_candidate):
        launcher = pythonw_candidate
    else:
        launcher = python_exe

    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
    script_path = os.path.join(project_root, "apps", "client", "main.py")

    return f'"{launcher}" "{script_path}" --tray'


def is_autostart_enabled() -> bool:
    """Check if AeroSync is currently registered in Windows Run key."""
    if sys.platform != "win32":
        return False

    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, REG_KEY_PATH, 0, winreg.KEY_READ)
        try:
            val, _ = winreg.QueryValueEx(key, REG_VALUE_NAME)
            return bool(val)
        finally:
            winreg.CloseKey(key)
    except FileNotFoundError:
        return False
    except Exception as exc:
        logger.debug("[AutoStart] Error checking autostart: %s", exc)
        return False


def enable_autostart(custom_cmd: str = None) -> bool:
    """Register AeroSync to start on Windows user login."""
    if sys.platform != "win32":
        logger.warning("[AutoStart] Not supported on non-Windows platforms")
        return False

    cmd = custom_cmd or _get_autostart_command()

    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_KEY_PATH,
            0,
            winreg.KEY_SET_VALUE
        )
        try:
            winreg.SetValueEx(key, REG_VALUE_NAME, 0, winreg.REG_SZ, cmd)
            logger.info("[AutoStart] Registered in Windows startup: %s", cmd)
            return True
        finally:
            winreg.CloseKey(key)
    except Exception as exc:
        logger.error("[AutoStart] Failed to enable startup: %s", exc)
        return False


def disable_autostart() -> bool:
    """Unregister AeroSync from Windows user login."""
    if sys.platform != "win32":
        return False

    try:
        import winreg
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            REG_KEY_PATH,
            0,
            winreg.KEY_SET_VALUE
        )
        try:
            winreg.DeleteValue(key, REG_VALUE_NAME)
            logger.info("[AutoStart] Removed from Windows startup")
            return True
        finally:
            winreg.CloseKey(key)
    except FileNotFoundError:
        return True  # already disabled
    except Exception as exc:
        logger.error("[AutoStart] Failed to disable startup: %s", exc)
        return False


def toggle_autostart() -> bool:
    """Toggle current autostart state and return new state."""
    current = is_autostart_enabled()
    if current:
        disable_autostart()
        return False
    else:
        enable_autostart()
        return True
