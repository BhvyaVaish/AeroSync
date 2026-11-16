"""
AeroSync Screen Capturer

Captures the full screen or a cropped region as a PIL Image.
Designed specifically for Windows 10/11.

Uses:
1. Windows GDI BitBlt via mss or native ctypes (attaches to Input Desktop if running
   in an isolated window station).
2. PIL.ImageGrab as fallback.
3. Synthetic blank fallback if running in a completely headless/display-less environment.

Windows-only. No cross-OS support.
"""

import base64
import ctypes
import io
import logging
from typing import Optional

from PIL import Image

from shared.types.screen_types import ScreenRegion

logger = logging.getLogger(__name__)


def _attach_input_desktop():
    """
    Ensure the current thread is attached to the active user's input desktop.
    Handles running from service sessions, IDE runners, or isolated worker desktops.
    """
    try:
        user32 = ctypes.windll.user32
        h_input = user32.OpenInputDesktop(0, False, 0x01FF)
        if h_input:
            user32.SetThreadDesktop(h_input)
            return h_input
    except Exception:
        pass
    return None


def _capture_gdi_direct(x: int, y: int, width: int, height: int) -> Optional[Image.Image]:
    """Capture screen pixels directly via Win32 GDI GetDIBits."""
    try:
        user32 = ctypes.windll.user32
        gdi32 = ctypes.windll.gdi32

        hdc = user32.GetDC(0)
        if not hdc:
            return None

        memdc = gdi32.CreateCompatibleDC(hdc)
        bmp = gdi32.CreateCompatibleBitmap(hdc, width, height)
        gdi32.SelectObject(memdc, bmp)

        # BitBlt from screen to memory DC
        # SRCCOPY = 0x00CC0020, CAPTUREBLT = 0x40000000
        ok = gdi32.BitBlt(memdc, 0, 0, width, height, hdc, x, y, 0x00CC0020 | 0x40000000)
        if not ok:
            # Try without CAPTUREBLT
            ok = gdi32.BitBlt(memdc, 0, 0, width, height, hdc, x, y, 0x00CC0020)

        if not ok:
            gdi32.DeleteObject(bmp)
            gdi32.DeleteDC(memdc)
            user32.ReleaseDC(0, hdc)
            return None

        class BITMAPINFOHEADER(ctypes.Structure):
            _fields_ = [
                ("biSize", ctypes.c_uint32),
                ("biWidth", ctypes.c_int32),
                ("biHeight", ctypes.c_int32),
                ("biPlanes", ctypes.c_uint16),
                ("biBitCount", ctypes.c_uint16),
                ("biCompression", ctypes.c_uint32),
                ("biSizeImage", ctypes.c_uint32),
                ("biXPelsPerMeter", ctypes.c_int32),
                ("biYPelsPerMeter", ctypes.c_int32),
                ("biClrUsed", ctypes.c_uint32),
                ("biClrImportant", ctypes.c_uint32),
            ]

        bmi = BITMAPINFOHEADER()
        bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bmi.biWidth = width
        bmi.biHeight = -height  # top-down DIB
        bmi.biPlanes = 1
        bmi.biBitCount = 32
        bmi.biCompression = 0

        buf = ctypes.create_string_buffer(width * height * 4)
        gdi32.GetDIBits(memdc, bmp, 0, height, buf, ctypes.byref(bmi), 0)

        img = Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1).convert("RGB")

        gdi32.DeleteObject(bmp)
        gdi32.DeleteDC(memdc)
        user32.ReleaseDC(0, hdc)
        return img
    except Exception as e:
        logger.debug(f"Direct GDI capture failed: {e}")
        return None


def capture_screen(region: Optional[ScreenRegion] = None) -> Image.Image:
    """
    Capture a screenshot of the full primary monitor or a specific region.

    Args:
        region: If None, captures the full primary monitor.
                If a ScreenRegion, captures only that rectangle.

    Returns:
        A PIL Image (RGB mode).
    """
    h_desktop = _attach_input_desktop()

    try:
        # 1. Try mss first
        try:
            import mss

            with mss.mss() as sct:
                if region is None:
                    monitor = sct.monitors[1]  # primary monitor
                else:
                    monitor = {
                        "top": region.y,
                        "left": region.x,
                        "width": region.width,
                        "height": region.height,
                    }

                sct_img = sct.grab(monitor)
                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")
                logger.debug(f"Captured screen via mss: size={img.size}")
                return img
        except Exception as e_mss:
            logger.debug(f"mss grab failed ({e_mss}), trying direct GDI...")

        # 2. Try direct Win32 GDI
        try:
            user32 = ctypes.windll.user32
            x = region.x if region else 0
            y = region.y if region else 0
            w = region.width if region else user32.GetSystemMetrics(0)
            h = region.height if region else user32.GetSystemMetrics(1)

            img = _capture_gdi_direct(x, y, w, h)
            if img is not None:
                logger.debug(f"Captured screen via direct Win32 GDI: size={img.size}")
                return img
        except Exception as e_gdi:
            logger.debug(f"Direct GDI capture failed ({e_gdi}), trying ImageGrab...")

        # 3. Fallback: PIL.ImageGrab
        try:
            from PIL import ImageGrab

            if region is None:
                img = ImageGrab.grab()
            else:
                img = ImageGrab.grab(bbox=(region.x, region.y, region.right, region.bottom))
            return img.convert("RGB")
        except Exception as e_pil:
            logger.warning(f"PIL.ImageGrab failed: {e_pil}")

        # 4. Fallback for headless test environments
        logger.warning("No screen capture method succeeded. Using fallback blank image.")
        w = region.width if region else 1920
        h = region.height if region else 1080
        return Image.new("RGB", (w, h), color=(30, 30, 30))

    finally:
        if h_desktop:
            try:
                ctypes.windll.user32.CloseDesktop(h_desktop)
            except Exception:
                pass


def image_to_base64_png(image: Image.Image) -> str:
    """
    Encode a PIL Image as a base64 PNG string.

    Args:
        image: PIL Image.

    Returns:
        Base64-encoded PNG string (raw b64, no data: prefix).
    """
    buffer = io.BytesIO()
    if image.width > 1920:
        ratio = 1920 / image.width
        new_size = (1920, int(image.height * ratio))
        image = image.resize(new_size, Image.LANCZOS)
    image.save(buffer, format="PNG", optimize=True)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")
