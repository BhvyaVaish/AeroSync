"""
AeroSync Clipboard Capture

Captures clipboard content (text only for MVP).
Truncates content that exceeds the maximum size to prevent huge payload transfers.
"""

import logging
import pyperclip

from shared.types.workspace_types import ClipboardContent
from shared.constants import CLIPBOARD_MAX_TEXT_BYTES

logger = logging.getLogger(__name__)


async def capture_clipboard() -> ClipboardContent:
    """
    Capture the current clipboard content.
    
    Returns:
        ClipboardContent object.
    """
    result = ClipboardContent(type="empty")
    
    try:
        # Try getting text content
        text = pyperclip.paste()
        
        if not text:
            return result
            
        text_bytes = text.encode('utf-8')
        
        if len(text_bytes) > CLIPBOARD_MAX_TEXT_BYTES:
            # Truncate to max bytes (careful not to split unicode characters)
            truncated_bytes = text_bytes[:CLIPBOARD_MAX_TEXT_BYTES]
            # Decode with ignore to drop any partial character at the end
            text = truncated_bytes.decode('utf-8', errors='ignore')
            result.truncated = True
            logger.info(f"Clipboard text truncated from {len(text_bytes)} to {len(truncated_bytes)} bytes")
            
        result.type = "text"
        result.content = text
        
    except Exception as e:
        logger.error(f"Failed to capture clipboard: {e}")
        
    return result
