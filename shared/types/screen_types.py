"""
AeroSync Screen Transfer Type Definitions

Data structures for screen capture, OCR, AI analysis, and action execution.
These types are shared between the screen_reader, ai_analyzer, and action_executor services.

Windows-only: These types are designed exclusively for Windows 10/11.
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class ScreenRegion:
    """A rectangular region of the screen, in screen coordinates (pixels)."""
    x: int = 0
    y: int = 0
    width: int = 0
    height: int = 0

    @property
    def as_tuple(self):
        """Return as (left, top, width, height) tuple for mss."""
        return {"top": self.y, "left": self.x, "width": self.width, "height": self.height}

    @property
    def right(self) -> int:
        return self.x + self.width

    @property
    def bottom(self) -> int:
        return self.y + self.height


@dataclass
class OCRResult:
    """Result of OCR text extraction from an image."""
    full_text: str = ""
    confidence: float = 0.0        # 0.0–1.0 average confidence
    word_count: int = 0
    engine_used: str = "pytesseract"  # "winrt" | "pytesseract"


@dataclass
class ScreenContent:
    """
    Full screen content captured at a point in time.
    Contains both raw OCR text and a base64-encoded screenshot for AI vision.
    """
    region: ScreenRegion = field(default_factory=ScreenRegion)
    ocr_text: str = ""
    screenshot_base64: str = ""    # PNG encoded as base64 string
    captured_at: str = ""          # ISO 8601 datetime
    ocr_confidence: float = 0.0
    is_full_screen: bool = True


@dataclass
class ActionItem:
    """
    A single executable action to be performed on the target machine.

    Types:
        open_browser_search  — Open Chrome and search a query
        open_url             — Open Chrome at a specific URL
        create_text_file     — Create a .txt file on Desktop with content
        type_in_app          — Focus an app and type text into it
    """
    type: str = "create_text_file"
    content: str = ""
    target_app: Optional[str] = None      # App window title hint (for type_in_app)
    search_query: Optional[str] = None    # For open_browser_search
    url: Optional[str] = None            # For open_url
    filename_hint: Optional[str] = None  # For create_text_file
    confidence: float = 1.0              # AI confidence in this action


@dataclass
class ActionPlan:
    """
    AI-generated plan of actions to execute on the target machine.
    Built by the ai_analyzer from screen OCR + vision data.
    """
    actions: List[ActionItem] = field(default_factory=list)
    summary: str = ""
    overall_confidence: float = 0.0
    fallback_used: bool = False   # True if AI failed and rule-based fallback was used


@dataclass
class ExecutionResult:
    """Result of executing a single ActionItem."""
    action_type: str = ""
    success: bool = False
    output: Optional[str] = None   # E.g., file path created, URL opened
    error: Optional[str] = None


@dataclass
class ExecutionReport:
    """Full report after executing an ActionPlan on the target machine."""
    transfer_id: str = ""
    results: List[ExecutionResult] = field(default_factory=list)
    succeeded: int = 0
    failed: int = 0
    duration_ms: int = 0
    success: bool = False
