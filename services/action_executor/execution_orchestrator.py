"""
AeroSync Action Execution Orchestrator

Iterates through all actions in an ActionPlan and routes each to the
appropriate executor (browser_controller, text_creator, input_automator).
Collects results and returns an ExecutionReport.

Windows-only. No cross-OS support.
"""

import asyncio
import logging
import time
from typing import Optional

from shared.types.screen_types import ActionPlan, ExecutionReport, ExecutionResult

logger = logging.getLogger(__name__)


async def execute_action_plan(
    plan: ActionPlan,
    transfer_id: str = "",
) -> ExecutionReport:
    """
    Execute all actions in an ActionPlan sequentially.

    Args:
        plan:        The ActionPlan produced by the AI analyzer.
        transfer_id: ID of the parent transfer session (for logging).

    Returns:
        ExecutionReport with per-action results and overall success flag.
    """
    start_time = time.monotonic()
    report = ExecutionReport(transfer_id=transfer_id)

    if not plan.actions:
        logger.warning("ActionPlan has no actions — nothing to execute.")
        report.success = True
        return report

    logger.info(
        f"Executing {len(plan.actions)} screen action(s) for transfer {transfer_id}"
    )

    loop = asyncio.get_running_loop()

    for i, action in enumerate(plan.actions):
        result = await loop.run_in_executor(
            None, lambda a=action: _execute_single(a)
        )
        report.results.append(result)
        if result.success:
            report.succeeded += 1
        else:
            report.failed += 1

        # Small delay between actions to avoid racing UI
        await asyncio.sleep(0.5)

    report.duration_ms = int((time.monotonic() - start_time) * 1000)
    report.success = report.failed == 0 or report.succeeded > 0

    logger.info(
        f"Screen actions complete: {report.succeeded} succeeded, "
        f"{report.failed} failed, {report.duration_ms}ms"
    )
    return report


def _execute_single(action) -> ExecutionResult:
    """Route a single ActionItem to the correct executor."""
    result = ExecutionResult(action_type=action.type)

    try:
        if action.type == "open_url":
            from services.action_executor.browser_controller import open_url
            open_url(action.url or action.content)
            result.success = True
            result.output = action.url or action.content

        elif action.type == "open_browser_search":
            from services.action_executor.browser_controller import open_browser_search
            open_browser_search(action.search_query or action.content)
            result.success = True
            result.output = action.search_query or action.content

        elif action.type == "create_text_file":
            from services.action_executor.text_creator import create_text_file
            path = create_text_file(
                content=action.content,
                filename_hint=action.filename_hint or "",
            )
            result.success = True
            result.output = path

        elif action.type == "type_in_app":
            from services.action_executor.input_automator import open_app_and_type, type_into_active_window
            if action.target_app:
                ok = open_app_and_type(action.target_app, action.content)
            else:
                ok = type_into_active_window(action.content)
            result.success = ok

        else:
            result.error = f"Unknown action type: {action.type}"
            logger.warning(result.error)

    except Exception as e:
        result.error = str(e)
        logger.error(f"Action {action.type} failed: {e}")

    return result
