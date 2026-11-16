"""
AeroSync Region Selector

Displays a fullscreen semi-transparent Tkinter overlay that lets the user
draw a rectangular crop region with mouse drag. The selected region is used
to restrict screen capture and OCR to only what the user cares about.

Controls:
  - Click + Drag  → Draw selection rectangle
  - Enter / Space → Confirm selection
  - Escape        → Use full screen (no crop)
  - Right-Click   → Cancel transfer entirely

Windows-only. Must be called from the main thread (or its own thread).
"""

import logging
import threading
from typing import Optional

from shared.types.screen_types import ScreenRegion

logger = logging.getLogger(__name__)


def select_region() -> Optional[ScreenRegion]:
    """
    Open an interactive fullscreen overlay for the user to draw a crop region.

    Blocks until the user confirms, presses Escape (full screen), or cancels.

    Returns:
        ScreenRegion if the user drew a selection.
        None if the user pressed Escape → full screen will be used.
        Raises RuntimeError if the user cancelled (right-click).
    """
    import tkinter as tk
    from tkinter import font as tkfont

    result_holder = {"region": None, "cancelled": False}

    def run_ui():
        root = tk.Tk()
        root.withdraw()

        win = tk.Toplevel(root)
        win.attributes("-fullscreen", True)
        win.attributes("-alpha", 0.35)
        win.attributes("-topmost", True)
        win.configure(bg="black")
        win.overrideredirect(True)

        # Instruction label
        label_font = tkfont.Font(family="Segoe UI", size=14, weight="bold")
        label = tk.Label(
            win,
            text="✦ AeroSync Screen Selector\n"
                 "Drag to select region  •  Enter = confirm  •  Esc = full screen  •  Right-click = cancel",
            fg="white",
            bg="#1a1a2e",
            font=label_font,
            padx=20,
            pady=10,
        )
        label.pack(side="top", fill="x")

        canvas = tk.Canvas(win, bg="black", highlightthickness=0, cursor="crosshair")
        canvas.pack(fill="both", expand=True)
        # Make canvas transparent
        win.attributes("-alpha", 0.4)

        state = {
            "start_x": 0,
            "start_y": 0,
            "rect_id": None,
            "confirmed": False,
        }

        def on_press(event):
            state["start_x"] = event.x_root
            state["start_y"] = event.y_root
            if state["rect_id"]:
                canvas.delete(state["rect_id"])
                state["rect_id"] = None

        def on_drag(event):
            x0 = state["start_x"] - win.winfo_rootx()
            y0 = state["start_y"] - win.winfo_rooty()
            x1 = event.x
            y1 = event.y
            if state["rect_id"]:
                canvas.delete(state["rect_id"])
            state["rect_id"] = canvas.create_rectangle(
                x0, y0, x1, y1,
                outline="#ff4444",
                width=3,
                dash=(8, 4),
            )

        def on_release(event):
            x0 = min(state["start_x"], event.x_root)
            y0 = min(state["start_y"], event.y_root)
            x1 = max(state["start_x"], event.x_root)
            y1 = max(state["start_y"], event.y_root)
            w = x1 - x0
            h = y1 - y0
            if w > 10 and h > 10:
                result_holder["region"] = ScreenRegion(x=x0, y=y0, width=w, height=h)

        def on_confirm(event=None):
            state["confirmed"] = True
            win.destroy()
            root.quit()

        def on_escape(event=None):
            # Full screen — region stays None
            result_holder["region"] = None
            win.destroy()
            root.quit()

        def on_cancel(event=None):
            result_holder["cancelled"] = True
            win.destroy()
            root.quit()

        canvas.bind("<ButtonPress-1>", on_press)
        canvas.bind("<B1-Motion>", on_drag)
        canvas.bind("<ButtonRelease-1>", on_release)
        canvas.bind("<Button-3>", on_cancel)
        win.bind("<Return>", on_confirm)
        win.bind("<space>", on_confirm)
        win.bind("<Escape>", on_escape)
        win.focus_force()

        root.mainloop()
        try:
            root.destroy()
        except Exception:
            pass

    # Run in the calling thread (must be main thread on Windows for Tkinter)
    run_ui()

    if result_holder["cancelled"]:
        raise RuntimeError("User cancelled screen region selection.")

    region = result_holder["region"]
    if region:
        logger.info(f"User selected region: {region}")
    else:
        logger.info("User chose full-screen capture (Escape pressed).")
    return region
