"""
AeroSync Gesture State Machine

Debounces raw gesture classifications and emits confirmed events.
Prevents spurious double-fires and manages cooldown periods.

Supports Short Fist vs Long Fist differentiation:
  • Short Fist Hold (>=600ms, released before 2s): Emits FIST -> Transfer everything automatically
  • Long Fist Hold (>=2000ms continuous hold): Emits FIST_LONG -> Opens selective checklist popup
"""

import time
from typing import Optional, Callable

from services.gesture_engine.gesture_types import (
    GestureType,
    GestureEvent,
    StateMachinePhase,
)
from shared.constants import (
    GESTURE_THROW_COOLDOWN_MS,
    GESTURE_RECEIVE_HOLD_MS,
    GESTURE_FIST_HOLD_MS,
    GESTURE_FIST_CONFIDENCE_THRESHOLD,
)


class GestureStateMachine:
    """
    State machine that manages gesture confirmation, hold durations, and cooldowns.
    """

    def __init__(self, on_event_callback: Callable[[GestureEvent], None]):
        self.phase = StateMachinePhase.IDLE
        self.current_candidate: Optional[GestureType] = None
        self.candidate_start_time: float = 0.0
        self.cooldown_end_time: float = 0.0
        self.on_event_callback = on_event_callback

        # Hold state tracking
        self.fist_short_emitted: bool = False
        self.long_hold_emitted: bool = False
        # Multi-frame gesture confirmation (hold duration tracking)
        self.consecutive_frames: int = 0

    def process(self, classification: Optional[tuple[GestureType, float]], hand: str) -> None:
        """
        Process a new classification from the gesture classifier.

        Args:
            classification: Tuple of (GestureType, confidence) or None.
            hand: Which hand generated the classification ("Left" or "Right").
        """
        now = time.monotonic()

        # 1. Handle Cooldown Phase
        if self.phase == StateMachinePhase.COOLDOWN:
            if now >= self.cooldown_end_time:
                self.phase = StateMachinePhase.IDLE
            return

        # 2. No gesture detected this frame (hand released / missing)
        if classification is None:
            self.consecutive_frames = 0
            if self.phase == StateMachinePhase.DETECTING:
                if self.fist_short_emitted:
                    # Released after short fist confirmation -> enter standard cooldown
                    self.phase = StateMachinePhase.COOLDOWN
                    self.cooldown_end_time = now + 1.5
                else:
                    # Lost before confirmation -> reset to IDLE
                    self.phase = StateMachinePhase.IDLE
                self.current_candidate = None
                self.fist_short_emitted = False
                self.long_hold_emitted = False
            return

        gesture_type, confidence = classification

        # 3. Handle Idle Phase
        if self.phase == StateMachinePhase.IDLE:
            self.phase = StateMachinePhase.DETECTING
            self.current_candidate = gesture_type
            self.candidate_start_time = now
            self.consecutive_frames = 1
            self.fist_short_emitted = False
            self.long_hold_emitted = False

        # 4. Handle Detecting Phase
        elif self.phase == StateMachinePhase.DETECTING:
            if gesture_type != self.current_candidate:
                # Gesture changed before confirmation, reset
                if self.fist_short_emitted:
                    self.phase = StateMachinePhase.COOLDOWN
                    self.cooldown_end_time = now + 1.5
                else:
                    self.current_candidate = gesture_type
                    self.candidate_start_time = now
                self.consecutive_frames = 1
                self.fist_short_emitted = False
                self.long_hold_emitted = False
                return

            self.consecutive_frames += 1

            # Check confirmation requirements based on gesture type (multi-frame hold duration)
            if gesture_type in (GestureType.THROW, GestureType.CANCEL, GestureType.UNDO):
                # Multi-frame confirmation for dynamic gestures (min 2 consecutive frames to prevent single-spike twitch fires)
                hold_time_ms = (now - self.candidate_start_time) * 1000
                if self.consecutive_frames >= 2 or hold_time_ms >= 60.0:
                    self._emit_and_cooldown(gesture_type, confidence, hand, now)

            elif gesture_type == GestureType.FIST:
                hold_time_ms = (now - self.candidate_start_time) * 1000

                # Multi-frame short fist threshold: >= 600ms hold, >= 0.88 confidence, >= 2 frames
                if (
                    hold_time_ms >= GESTURE_FIST_HOLD_MS
                    and confidence >= GESTURE_FIST_CONFIDENCE_THRESHOLD
                    and self.consecutive_frames >= 2
                ):
                    if not self.fist_short_emitted:
                        self.fist_short_emitted = True
                        event = GestureEvent(
                            gesture_type=GestureType.FIST,
                            confidence=confidence,
                            timestamp=now,
                            hand=hand,
                            is_long_hold=False,
                            hold_duration_s=round(hold_time_ms / 1000.0, 2),
                        )
                        self.on_event_callback(event)

                    # Multi-frame long fist threshold (>= 2000ms / 2.0s hold, >= 3 frames) -> Opens Checklist Popup
                    if hold_time_ms >= 2000.0 and self.consecutive_frames >= 3 and not self.long_hold_emitted:
                        self.long_hold_emitted = True
                        event = GestureEvent(
                            gesture_type=GestureType.FIST_LONG,
                            confidence=confidence,
                            timestamp=now,
                            hand=hand,
                            is_long_hold=True,
                            hold_duration_s=round(hold_time_ms / 1000.0, 2),
                        )
                        self.on_event_callback(event)
                        # Complete and cooldown
                        self.phase = StateMachinePhase.COOLDOWN
                        self.cooldown_end_time = now + 1.5
                        self.current_candidate = None
                        self.fist_short_emitted = False
                        self.long_hold_emitted = False
                        self.consecutive_frames = 0

            elif gesture_type == GestureType.RECEIVE:
                hold_time_ms = (now - self.candidate_start_time) * 1000
                if hold_time_ms >= GESTURE_RECEIVE_HOLD_MS:
                    self._emit_and_cooldown(gesture_type, confidence, hand, now)

    def _emit_and_cooldown(
        self,
        gesture_type: GestureType,
        confidence: float,
        hand: str,
        now: float,
        is_long_hold: bool = False,
        hold_duration_s: float = 0.0,
    ) -> None:
        """Emit the confirmed event and enter cooldown."""
        event = GestureEvent(
            gesture_type=gesture_type,
            confidence=confidence,
            timestamp=now,
            hand=hand,
            is_long_hold=is_long_hold,
            hold_duration_s=hold_duration_s,
        )
        self.on_event_callback(event)

        self.phase = StateMachinePhase.COOLDOWN

        cooldown_ms = 1000  # Default 1s
        if gesture_type == GestureType.THROW:
            cooldown_ms = GESTURE_THROW_COOLDOWN_MS
        elif gesture_type in (GestureType.FIST, GestureType.FIST_LONG, GestureType.UNDO):
            cooldown_ms = 1500

        self.cooldown_end_time = now + (cooldown_ms / 1000.0)
        self.current_candidate = None
        self.fist_short_emitted = False
        self.long_hold_emitted = False
