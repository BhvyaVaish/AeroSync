"""
AeroSync Clipboard Restorer

Restores clipboard content (text only for MVP).
"""

import logging
import pyperclip

from shared.types.workspace_types import ClipboardContent

logger = logging.getLogger(__name__)


async def restore_clipboard(clipboard: ClipboardContent) -> bool:
    """
    Restore clipboard text content.
    
    Args:
        clipboard: ClipboardContent object to restore.
        
    Returns:
        True if successful, False otherwise.
    """
    if not clipboard or clipboard.type != "text" or not clipboard.content:
        return False
        
    try:
        pyperclip.copy(clipboard.content)
        logger.info("Restored clipboard text")
        return True
    except Exception as e:
        logger.error(f"Failed to restore clipboard: {e}")
        return False
