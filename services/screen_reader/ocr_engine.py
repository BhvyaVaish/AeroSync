"""
AeroSync OCR Engine

Extracts text from a PIL Image using:
1. Windows native OCR (winrt Windows.Media.Ocr) — fastest, highest quality
2. pytesseract fallback — requires Tesseract binary on PATH

The engine auto-selects whichever is available, preferring native WinRT.
Returns an OCRResult with full text, confidence score, and word count.

Windows-only. No cross-OS support.
"""

import logging
from typing import Optional

from PIL import Image

from shared.types.screen_types import OCRResult

logger = logging.getLogger(__name__)

# Cache which engine is available
_winrt_available: Optional[bool] = None
_tesseract_available: Optional[bool] = None


def _check_winrt() -> bool:
    global _winrt_available
    if _winrt_available is not None:
        return _winrt_available
    try:
        import winrt.windows.media.ocr as winrt_ocr  # noqa: F401
        import winrt.windows.globalization as globalization  # noqa: F401
        _winrt_available = True
        logger.info("WinRT OCR engine available.")
    except Exception:
        _winrt_available = False
        logger.info("WinRT OCR not available, will use pytesseract.")
    return _winrt_available


def _check_tesseract() -> bool:
    global _tesseract_available
    if _tesseract_available is not None:
        return _tesseract_available
    try:
        import pytesseract
        pytesseract.get_tesseract_version()
        _tesseract_available = True
        logger.info("pytesseract (Tesseract) available.")
    except Exception as e:
        _tesseract_available = False
        logger.warning(f"pytesseract not available: {e}")
    return _tesseract_available


def _run_winrt_ocr(image: Image.Image) -> OCRResult:
    """
    Run Windows native OCR via winrt.
    Requires: pip install winrt  (and Windows 10 1803+)
    """
    import asyncio
    import io
    import winrt.windows.media.ocr as winrt_ocr
    import winrt.windows.globalization as globalization
    import winrt.windows.storage.streams as streams
    import winrt.windows.graphics.imaging as imaging

    # Save image to bytes
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    img_bytes = buf.getvalue()

    async def _do_ocr():
        # Create SoftwareBitmap from bytes
        mem_stream = streams.InMemoryRandomAccessStream()
        writer = streams.DataWriter(mem_stream)
        writer.write_bytes(img_bytes)
        await writer.store_async()
        mem_stream.seek(0)

        decoder = await imaging.BitmapDecoder.create_async(mem_stream)
        soft_bmp = await decoder.get_software_bitmap_async()

        language = globalization.Language("en-US")
        engine = winrt_ocr.OcrEngine.try_create_from_language(language)
        result = await engine.recognize_async(soft_bmp)
        return result

    result = asyncio.run(_do_ocr())
    text = result.text if result else ""
    words = text.split()
    return OCRResult(
        full_text=text,
        confidence=0.95,   # WinRT doesn't expose per-word confidence
        word_count=len(words),
        engine_used="winrt",
    )


def _run_tesseract_ocr(image: Image.Image) -> OCRResult:
    """Run pytesseract OCR and compute average confidence."""
    import pytesseract

    # Get detailed output for confidence scoring
    data = pytesseract.image_to_data(
        image,
        output_type=pytesseract.Output.DICT,
        config="--psm 3 --oem 3",
    )

    words = []
    confidences = []
    for i, word in enumerate(data["text"]):
        word = word.strip()
        conf = data["conf"][i]
        if word and conf > 0:
            words.append(word)
            confidences.append(conf)

    full_text = pytesseract.image_to_string(image, config="--psm 3 --oem 3").strip()
    avg_conf = (sum(confidences) / len(confidences) / 100.0) if confidences else 0.0

    return OCRResult(
        full_text=full_text,
        confidence=round(avg_conf, 3),
        word_count=len(words),
        engine_used="pytesseract",
    )


def run_ocr(image: Image.Image) -> OCRResult:
    """
    Run OCR on a PIL Image, auto-selecting the best available engine.

    Args:
        image: PIL Image (RGB or RGBA).

    Returns:
        OCRResult with extracted text and confidence.
    """
    # Ensure RGB
    if image.mode != "RGB":
        image = image.convert("RGB")

    # Try WinRT first
    if _check_winrt():
        try:
            return _run_winrt_ocr(image)
        except Exception as e:
            logger.warning(f"WinRT OCR failed: {e} — falling back to pytesseract")

    # Fallback: pytesseract
    if _check_tesseract():
        try:
            return _run_tesseract_ocr(image)
        except Exception as e:
            logger.error(f"pytesseract OCR also failed: {e}")

    # Both failed — return empty
    logger.error("All OCR engines failed. Returning empty OCRResult.")
    return OCRResult(
        full_text="",
        confidence=0.0,
        word_count=0,
        engine_used="none",
    )
