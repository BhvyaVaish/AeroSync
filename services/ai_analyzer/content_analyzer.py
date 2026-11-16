"""
AeroSync AI Content Analyzer

Uses Google Gemini (Vision + text) to analyze captured screen content and
produce a structured ActionPlan — a list of actions to execute on the
target machine to recreate what was visible on the source screen.

Requires: GEMINI_API_KEY environment variable.

Action types produced:
  - open_browser_search  → Open Chrome, search a query
  - open_url             → Open Chrome at a specific URL
  - create_text_file     → Create .txt file on Desktop with content
  - type_in_app          → Focus an app by title, type content into it
"""

import json
import logging
import os
from typing import Optional

from shared.types.screen_types import ScreenContent, ActionItem, ActionPlan

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """\
You are AeroSync, a Windows workspace transfer assistant.

A user has captured their screen on Computer A and wants to recreate the same
context on Computer B (also Windows). Analyze the provided screenshot and OCR
text, then return a JSON object with an "actions" array and a "summary" field.

Each action must have:
  - "type": one of ["open_browser_search", "open_url", "create_text_file", "type_in_app"]
  - "content": main content (search query text, file body, text to type, URL path)
  - "target_app": app window title hint (only for type_in_app, else null)
  - "search_query": the exact search query string (only for open_browser_search, else null)
  - "url": the full URL (only for open_url, else null)
  - "filename_hint": short label for the file name (only for create_text_file, else null)
  - "confidence": float 0.0–1.0 for this action

Rules:
1. If you see a browser with a URL bar, prefer "open_url" for the visible URL.
2. If you see a browser with a search result page, use "open_browser_search" with the query.
3. If you see a text editor or document with text, use "create_text_file".
4. If you see any other application with typed content, use "type_in_app".
5. Return multiple actions if the screen shows multiple relevant things.
6. Keep actions minimal and practical — focus on what matters.
7. The "summary" field must be a single English sentence describing what will be recreated.

Return ONLY valid JSON, no markdown fences, no extra text.
"""


def analyze_screen_content(screen_content: ScreenContent) -> ActionPlan:
    """
    Send the screen content (screenshot + OCR text) to Gemini and get an ActionPlan.

    Args:
        screen_content: ScreenContent with base64 screenshot and OCR text.

    Returns:
        ActionPlan with structured actions. Falls back to rule-based plan if AI fails.
    """
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()

    if api_key:
        try:
            return _analyze_with_gemini(screen_content, api_key)
        except Exception as e:
            logger.warning(f"Gemini analysis failed: {e} — using fallback")

    # Fallback: rule-based heuristics
    return _fallback_plan(screen_content)


def _analyze_with_gemini(screen_content: ScreenContent, api_key: str) -> ActionPlan:
    """Call Gemini Flash with vision + OCR to get a structured ActionPlan."""
    import google.generativeai as genai

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel("gemini-1.5-flash")

    # Build prompt with OCR text as additional context
    user_prompt = (
        f"OCR text extracted from the screen:\n```\n{screen_content.ocr_text[:4000]}\n```\n\n"
        "Now analyze the screenshot and produce the action JSON."
    )

    # Prepare image part
    import base64
    img_bytes = base64.b64decode(screen_content.screenshot_base64)
    image_part = {
        "mime_type": "image/png",
        "data": img_bytes,
    }

    response = model.generate_content(
        [_SYSTEM_PROMPT, user_prompt, image_part],
        generation_config=genai.types.GenerationConfig(
            temperature=0.1,
            max_output_tokens=2048,
        ),
    )

    raw_text = response.text.strip()
    # Strip markdown fences if model added them
    if raw_text.startswith("```"):
        lines = raw_text.splitlines()
        raw_text = "\n".join(
            line for line in lines if not line.startswith("```")
        ).strip()

    parsed = json.loads(raw_text)
    actions = []
    for item in parsed.get("actions", []):
        actions.append(ActionItem(
            type=item.get("type", "create_text_file"),
            content=item.get("content", ""),
            target_app=item.get("target_app"),
            search_query=item.get("search_query"),
            url=item.get("url"),
            filename_hint=item.get("filename_hint"),
            confidence=float(item.get("confidence", 0.9)),
        ))

    overall_conf = (
        sum(a.confidence for a in actions) / len(actions) if actions else 0.0
    )

    return ActionPlan(
        actions=actions,
        summary=parsed.get("summary", "Recreate screen content on target machine."),
        overall_confidence=round(overall_conf, 3),
        fallback_used=False,
    )


def _fallback_plan(screen_content: ScreenContent) -> ActionPlan:
    """
    Rule-based fallback: if AI is unavailable or fails, produce a best-effort plan
    using simple heuristics on the OCR text.
    """
    ocr = screen_content.ocr_text.strip()
    actions = []

    # Heuristic 1: Looks like a URL
    import re
    url_pattern = re.compile(
        r"https?://[^\s]+", re.IGNORECASE
    )
    urls = url_pattern.findall(ocr)
    for url in urls[:3]:  # Max 3 URLs
        actions.append(ActionItem(
            type="open_url",
            content=url,
            url=url,
            confidence=0.7,
        ))

    # Heuristic 2: There's substantial text — save it to a file
    if len(ocr) > 100 and not urls:
        actions.append(ActionItem(
            type="create_text_file",
            content=ocr,
            filename_hint="screen_content",
            confidence=0.6,
        ))
    elif len(ocr) > 20 and not urls:
        # Short text — treat as search query
        query = ocr.replace("\n", " ").strip()[:200]
        actions.append(ActionItem(
            type="open_browser_search",
            content=query,
            search_query=query,
            confidence=0.5,
        ))

    if not actions:
        # Absolute fallback
        actions.append(ActionItem(
            type="create_text_file",
            content=ocr or "(no text detected on screen)",
            filename_hint="aerosync_capture",
            confidence=0.3,
        ))

    overall_conf = (
        sum(a.confidence for a in actions) / len(actions) if actions else 0.0
    )
    return ActionPlan(
        actions=actions,
        summary="Fallback plan: recreating content based on OCR heuristics (AI unavailable).",
        overall_confidence=round(overall_conf, 3),
        fallback_used=True,
    )
