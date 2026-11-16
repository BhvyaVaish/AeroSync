"""
AeroSync Screen Reader Orchestrator

Top-level async function that:
1. (Optionally) shows the region selector overlay so the user can crop
2. Captures the screen (full or cropped region)
3. Runs OCR to extract text
4. Deduplicates OCR output against the OS log exclusion set
5. Encodes screenshot to base64 for AI vision
6. Returns a ScreenContent object ready for AI analysis

Deduplication (Step 5 of the architecture):
  Any OCR text token that is already represented in `log_exclusion_set`
  (provided by capture_orchestrator from the WorkspaceLogQueue) is stripped
  from the OCR output before it reaches the AI analyser.  This guarantees
  that no item is processed by BOTH the OS logger AND the OCR pipeline.

Windows-only. No cross-OS support.
"""

import datetime
import logging
from typing import Optional, Set

from shared.types.screen_types import ScreenContent, ScreenRegion
from services.screen_reader.screen_capturer import capture_screen, image_to_base64_png
from services.screen_reader.ocr_engine import run_ocr

logger = logging.getLogger(__name__)


def _deduplicate_ocr_text(ocr_text: str, exclusion_set: Set[str]) -> str:
    """
    Remove from `ocr_text` any lines / tokens that are already captured by
    the OS logger.

    Strategy:
      For each URL-type or window-title-type content_id in the exclusion set,
      find matching text in the OCR output and strip those lines.  Clip-type
      items are matched by prefix substring.

    Args:
        ocr_text:      Raw OCR text from the screen.
        exclusion_set: Set of content_id strings from WorkspaceLogQueue
                       (format: "url:<url>", "win:<title>", "clip:<snippet>",
                        "proc:<name>").

    Returns:
        Filtered OCR text with duplicate content removed.
    """
    if not exclusion_set:
        return ocr_text

    lines = ocr_text.splitlines()
    kept_lines = []
    skipped = 0

    for line in lines:
        line_stripped = line.strip()
        if not line_stripped:
            kept_lines.append(line)
            continue

        line_lower = line_stripped.lower()
        should_skip = False

        for cid in exclusion_set:
            if cid.startswith("url:"):
                # Match if the URL (or its domain) appears in the line
                url_val = cid[4:].lower()
                # Try domain-only match (e.g. "github.com" from full URL)
                try:
                    from urllib.parse import urlparse
                    domain = urlparse(url_val).netloc or url_val
                except Exception:
                    domain = url_val
                if domain and domain in line_lower:
                    logger.debug("[Dedup] Skipping OCR line (URL match '%s'): %r", domain, line_stripped[:60])
                    should_skip = True
                    break

            elif cid.startswith("win:"):
                # Match if the window title appears verbatim in the line
                win_val = cid[4:].lower()
                if win_val and win_val in line_lower:
                    logger.debug("[Dedup] Skipping OCR line (window match '%s'): %r", win_val[:40], line_stripped[:60])
                    should_skip = True
                    break

            elif cid.startswith("clip:"):
                # Match if OCR line is part of the clipboard text already captured
                clip_val = cid[5:200].lower()  # compare first 200 chars of snippet
                if clip_val and clip_val in line_lower:
                    logger.debug("[Dedup] Skipping OCR line (clipboard match): %r", line_stripped[:60])
                    should_skip = True
                    break

            elif cid.startswith("appcontent:"):
                # Match if the app window title whose content was logged appears in the line
                app_val = cid[11:].lower()
                if app_val and app_val in line_lower:
                    logger.debug("[Dedup] Skipping OCR line (app content match '%s'): %r", app_val[:40], line_stripped[:60])
                    should_skip = True
                    break

        if not should_skip:
            kept_lines.append(line)
        else:
            skipped += 1

    if skipped > 0:
        logger.info("[Dedup] OCR deduplication removed %d lines already in OS log", skipped)

    return "\n".join(kept_lines)


async def capture_and_read_screen(
    region: Optional[ScreenRegion] = None,
    show_selector: bool = True,
    log_exclusion_set: Optional[Set[str]] = None,
) -> ScreenContent:
    """
    Full screen-reading pipeline: region select → capture → OCR → dedup → encode.

    Args:
        region: Pre-defined region to capture. If None AND show_selector=True,
                shows the interactive region selector for the user to crop.
                If None AND show_selector=False, captures the full screen.
        show_selector: Whether to show the interactive crop UI when region is None.
        log_exclusion_set: Set of content_id strings from WorkspaceLogQueue.
                           Lines matching these identifiers are stripped from OCR
                           output to avoid double-processing the same content.

    Returns:
        ScreenContent with deduplicated OCR text, base64 screenshot, and metadata.
    """
    import asyncio

    is_full_screen = False

    # 1. Determine capture region
    if region is None and show_selector:
        try:
            loop = asyncio.get_running_loop()
            from services.screen_reader.region_selector import select_region
            region = await loop.run_in_executor(None, select_region)
            is_full_screen = (region is None)
        except RuntimeError as e:
            if "cancelled" in str(e).lower():
                raise
            logger.warning("Region selector error: %s — using full screen", e)
            is_full_screen = True
    elif region is None:
        is_full_screen = True

    # 2. Capture screenshot
    logger.info("Capturing screen %s", "(full)" if is_full_screen else f"region {region}")
    loop = asyncio.get_running_loop()
    image = await loop.run_in_executor(None, lambda: capture_screen(region))

    # 3. Run OCR
    logger.info("Running OCR on captured image...")
    ocr_result = await loop.run_in_executor(None, lambda: run_ocr(image))
    logger.info(
        "OCR complete: %d words, confidence=%.2f, engine=%s",
        ocr_result.word_count, ocr_result.confidence, ocr_result.engine_used,
    )

    # 4. ── DEDUPLICATION — strip content already in OS log ────────────────────
    raw_text = ocr_result.full_text
    if log_exclusion_set:
        filtered_text = _deduplicate_ocr_text(raw_text, log_exclusion_set)
    else:
        filtered_text = raw_text
    # ──────────────────────────────────────────────────────────────────────────

    # 5. Encode screenshot to base64
    b64 = await loop.run_in_executor(None, lambda: image_to_base64_png(image))

    # 6. Build ScreenContent
    if region is None:
        region = ScreenRegion(x=0, y=0, width=image.width, height=image.height)

    return ScreenContent(
        region=region,
        ocr_text=filtered_text,
        screenshot_base64=b64,
        captured_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),
        ocr_confidence=ocr_result.confidence,
        is_full_screen=is_full_screen,
    )
