"""
AeroSync Action Planner

Thin wrapper around content_analyzer that adds error handling, logging,
and optional override of the action plan before execution.
"""

import logging

from shared.types.screen_types import ScreenContent, ActionPlan
from services.ai_analyzer.content_analyzer import analyze_screen_content

logger = logging.getLogger(__name__)


def plan_actions(screen_content: ScreenContent) -> ActionPlan:
    """
    Analyze screen content and produce an ActionPlan.

    Args:
        screen_content: Captured screen data (OCR text + base64 screenshot).

    Returns:
        ActionPlan ready for execution on the target machine.
    """
    logger.info("Building action plan from screen content...")
    plan = analyze_screen_content(screen_content)

    logger.info(
        f"Action plan built: {len(plan.actions)} action(s), "
        f"confidence={plan.overall_confidence:.2f}, "
        f"fallback={'yes' if plan.fallback_used else 'no'}\n"
        f"Summary: {plan.summary}"
    )

    for i, action in enumerate(plan.actions):
        logger.debug(
            f"  Action {i+1}: type={action.type}, "
            f"confidence={action.confidence:.2f}, "
            f"content_preview={repr(action.content[:80])}"
        )

    return plan
