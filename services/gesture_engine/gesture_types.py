"""
AeroSync Gesture Engine — Type Definitions

Data structures for hand tracking, gesture classification,
and engine status reporting.
"""

from dataclasses import dataclass, field
from typing import Deque, List, Optional, Tuple
from collections import deque
from enum import Enum

from shared.constants import (
    GESTURE_THROW,
    GESTURE_RECEIVE,
    GESTURE_FIST,
    GESTURE_CANCEL,
    GESTURE_VELOCITY_BUFFER_FRAMES,
)


class GestureType(str, Enum):
    """Recognised gesture types."""
    THROW = GESTURE_THROW       # Becomes Target B; transfers data to this PC
    RECEIVE = GESTURE_RECEIVE   # (Legacy open-palm receive pose)
    FIST = GESTURE_FIST         # Short hold (<2s): Becomes Host A; transfers everything
    FIST_LONG = "fist_long"     # Long hold (>=2s): Becomes Host A; opens selective checklist
    CANCEL = GESTURE_CANCEL


class EngineState(str, Enum):
    """Gesture engine operational state."""
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"


class StateMachinePhase(str, Enum):
    """Gesture state-machine phase."""
    IDLE = "idle"
    DETECTING = "detecting"
    CONFIRMED = "confirmed"
    COOLDOWN = "cooldown"


@dataclass
class LandmarkPoint:
    """A single 3-D landmark point (normalised 0-1)."""
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass
class HandLandmarks:
    """
    Processed hand-landmark data for a single detected hand.

    `landmarks` contains 21 points following the MediaPipe hand model:
        0: WRIST
        1-4: THUMB (CMC → TIP)
        5-8: INDEX (MCP → TIP)
        9-12: MIDDLE (MCP → TIP)
        13-16: RING (MCP → TIP)
        17-20: PINKY (MCP → TIP)
    """
    landmarks: List[LandmarkPoint] = field(default_factory=list)
    handedness: str = "unknown"        # "Left" | "Right"
    confidence: float = 0.0
    wrist_x: float = 0.0              # convenience — same as landmarks[0].x
    wrist_y: float = 0.0


@dataclass
class VelocityBuffer:
    """
    Ring-buffer that tracks wrist position over N frames
    and computes instantaneous velocity.
    """
    positions: Deque[Tuple[float, float]] = field(
        default_factory=lambda: deque(maxlen=GESTURE_VELOCITY_BUFFER_FRAMES)
    )

    # --- public helpers ---------------------------------------------------

    def push(self, x: float, y: float) -> None:
        """Record a new wrist position."""
        self.positions.append((x, y))

    @property
    def horizontal_velocity(self) -> float:
        """
        Average horizontal velocity (Δx / frame) over the buffer.
        Positive = moving right, negative = moving left.
        """
        if len(self.positions) < 2:
            return 0.0
        total_dx = 0.0
        for i in range(1, len(self.positions)):
            total_dx += self.positions[i][0] - self.positions[i - 1][0]
        return total_dx / (len(self.positions) - 1)

    @property
    def vertical_velocity(self) -> float:
        """Average vertical velocity (Δy / frame)."""
        if len(self.positions) < 2:
            return 0.0
        total_dy = 0.0
        for i in range(1, len(self.positions)):
            total_dy += self.positions[i][1] - self.positions[i - 1][1]
        return total_dy / (len(self.positions) - 1)

    def clear(self) -> None:
        self.positions.clear()


@dataclass
class GestureEvent:
    """A confirmed gesture event emitted by the state machine."""
    gesture_type: GestureType
    confidence: float = 0.0
    timestamp: float = 0.0            # time.monotonic()
    hand: str = "unknown"             # "Left" | "Right"
    is_long_hold: bool = False        # True if fist held >= 2.0s (triggers checklist)
    hold_duration_s: float = 0.0      # Exact hold duration in seconds


@dataclass
class GestureEngineStatus:
    """Snapshot of the gesture engine's current status."""
    state: EngineState = EngineState.STOPPED
    fps: float = 0.0
    hands_detected: int = 0
    last_gesture: Optional[GestureEvent] = None
    error_message: Optional[str] = None
    camera_index: int = 0
