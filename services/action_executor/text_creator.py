"""
AeroSync Text File Creator

Creates a plain-text .txt file on the user's Desktop with the given content.
File name: AeroSync_{timestamp}_{hint}.txt

Windows-only. No cross-OS support.
"""

import datetime
import logging
import os
import re
from pathlib import Path

logger = logging.getLogger(__name__)


def create_text_file(content: str, filename_hint: str = "") -> str:
    """
    Write content to a new .txt file on the Windows Desktop.

    Args:
        content:       Text to write.
        filename_hint: Short label to embed in the filename.

    Returns:
        Absolute path of the created file.

    Raises:
        RuntimeError: If file creation fails.
    """
    desktop = Path(os.path.expanduser("~/Desktop"))
    desktop.mkdir(parents=True, exist_ok=True)

    # Sanitize hint
    hint = re.sub(r"[^\w\-]", "_", filename_hint.strip())[:30] if filename_hint else "content"
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"AeroSync_{timestamp}_{hint}.txt"
    filepath = desktop / filename

    try:
        filepath.write_text(content, encoding="utf-8")
        logger.info(f"Created text file: {filepath}")
        return str(filepath)
    except Exception as e:
        raise RuntimeError(f"Failed to create text file: {e}") from e
