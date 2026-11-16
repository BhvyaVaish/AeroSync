"""
AeroSync Exponential Backoff and Resilient Retry Utility

Provides capped exponential backoff with jitter to prevent server thundering herds,
network congestion, and CPU-spinning retry loops.

Key safety guarantees:
  • Hard retry attempt limits (prevents infinite retry loops).
  • Upper bound delay clamping (max_delay cap).
  • Randomised jitter (±15%) for distributed reconnection.
  • Immediate abort for non-retryable errors (e.g. 401 Auth, 404 Not Found).
  • Stateful ExponentialBackoffTracker for background reconnect loops.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import Any, Callable, Coroutine, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")


def calculate_backoff_delay(
    attempt: int,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    factor: float = 2.0,
    jitter: bool = True,
) -> float:
    """
    Calculate backoff delay for a given attempt index (0-based).

    Formula:
        delay = min(max_delay, base_delay * (factor ** attempt))
        if jitter: delay *= uniform(0.85, 1.15)
    """
    attempt = max(0, attempt)
    raw_delay = min(max_delay, base_delay * (factor ** attempt))
    if jitter:
        # ±15% jitter to prevent synchronized reconnect bursts
        jitter_factor = random.uniform(0.85, 1.15)
        raw_delay *= jitter_factor
    return round(raw_delay, 3)


class ExponentialBackoffTracker:
    """
    Stateful retry tracker for asynchronous long-running connections (e.g. WebSocket).
    Enforces a strict maximum retry cap to prevent infinite unconstrained loops.
    """

    def __init__(
        self,
        max_retries: int = 6,
        base_delay: float = 1.0,
        max_delay: float = 30.0,
        factor: float = 2.0,
    ):
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.factor = factor

        self.current_attempt: int = 0
        self.last_failure_time: float = 0.0
        self.total_retries: int = 0

    @property
    def is_exhausted(self) -> bool:
        """True if the maximum retry threshold has been reached."""
        return self.current_attempt >= self.max_retries

    def next_delay(self) -> Optional[float]:
        """
        Get the next delay duration in seconds, or None if retries are exhausted.
        Increments current_attempt counter.
        """
        if self.is_exhausted:
            logger.warning(
                "[BackoffTracker] Maximum retries (%d) exhausted — halting retry loop to prevent runaway spinning",
                self.max_retries,
            )
            return None

        delay = calculate_backoff_delay(
            attempt=self.current_attempt,
            base_delay=self.base_delay,
            max_delay=self.max_delay,
            factor=self.factor,
            jitter=True,
        )
        self.current_attempt += 1
        self.total_retries += 1
        self.last_failure_time = time.monotonic()
        logger.info(
            "[BackoffTracker] Retry attempt %d/%d scheduled in %.2fs",
            self.current_attempt,
            self.max_retries,
            delay,
        )
        return delay

    def reset(self) -> None:
        """Reset attempt counter upon successful connection or user manual action."""
        if self.current_attempt > 0:
            logger.debug("[BackoffTracker] Connection restored — resetting retry counter")
        self.current_attempt = 0


async def async_retry_with_backoff(
    coro_func: Callable[[], Coroutine[Any, Any, T]],
    max_retries: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 16.0,
    should_retry: Optional[Callable[[Exception], bool]] = None,
    op_name: str = "Operation",
) -> T:
    """
    Execute an asynchronous coroutine with exponential backoff.
    Guaranteed to terminate: raises the final exception if max_retries is reached.
    """
    for attempt in range(max_retries + 1):
        try:
            return await coro_func()
        except Exception as exc:
            if should_retry and not should_retry(exc):
                logger.warning("[%s] Non-retryable exception encountered: %s", op_name, exc)
                raise exc

            if attempt >= max_retries:
                logger.error(
                    "[%s] Failed after %d retry attempts (capped to avoid infinite loop): %s",
                    op_name,
                    max_retries,
                    exc,
                )
                raise exc

            delay = calculate_backoff_delay(
                attempt=attempt,
                base_delay=base_delay,
                max_delay=max_delay,
                jitter=True,
            )
            logger.warning(
                "[%s] Attempt %d/%d failed (%s). Retrying in %.2fs...",
                op_name,
                attempt + 1,
                max_retries,
                exc,
                delay,
            )
            await asyncio.sleep(delay)

    raise RuntimeError(f"[{op_name}] Unexpected termination of retry loop")
