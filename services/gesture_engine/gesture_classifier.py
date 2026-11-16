"""
AeroSync Gesture Classifier

Combines node-based kinematic biomechanical hand tracking with velocity buffers
for high-accuracy gesture detection.

FRONT-VIEW ENFORCEMENT: All gestures require the palm to face the camera
(palm_normal.z < GESTURE_FRONT_VIEW_THRESHOLD). Side-view or tilted hands
are silently ignored — this prevents false triggers from peripheral movement.

Role gestures:
  FIST  → This PC becomes Host A (arms workspace capture)
  THROW → This PC becomes Target B (receives workspace data)
"""

import time
from typing import Dict, Optional, Tuple

from services.gesture_engine.gesture_types import (
    HandLandmarks,
    GestureType,
    VelocityBuffer,
)
from services.gesture_engine.node_engine import (
    NodeBasedGestureAnalyzer,
    KinematicHandNodes,
)
from shared.constants import (
    GESTURE_FRAME_CENTER_RATIO,
    GESTURE_FRONT_VIEW_THRESHOLD,
)


class GestureClassifier:
    """Classifies gestures using invisible kinematic nodes & pivots for high accuracy.

    Front-view gate:
        Before any gesture is emitted, `nodes.is_facing_camera` is checked
        (palm_normal.z < GESTURE_FRONT_VIEW_THRESHOLD = -0.35).  If the palm is
        not squarely facing the camera this PC's webcam is seeing, nothing fires.
    """

    def __init__(self):
        # Velocity buffers for legacy fallback
        self.velocity_buffers: Dict[str, VelocityBuffer] = {
            "Left": VelocityBuffer(),
            "Right": VelocityBuffer(),
        }

        # Node-based kinematic biomechanical analyzers per hand
        self.node_analyzers: Dict[str, NodeBasedGestureAnalyzer] = {
            "Left": NodeBasedGestureAnalyzer(),
            "Right": NodeBasedGestureAnalyzer(),
        }

        # State transition tracking
        self.last_nodes: Dict[str, Optional[KinematicHandNodes]] = {
            "Left": None,
            "Right": None,
        }

    def process_hand(
        self, hand: HandLandmarks, frame_width: int, frame_height: int
    ) -> Optional[Tuple[GestureType, float]]:
        """
        Analyze a hand and return (GestureType, confidence) if a gesture is detected.

        Uses invisible mathematical nodes and pivots for maximum accuracy:
        - Palm Center Node 3D trajectory
        - Joint Flexion Angles
        - Palm Plane Normal Vector (enforced: must face camera before ANY gesture fires)
        """
        # 1. Filter out hands at the extreme perimeter of the camera frame
        if not self._is_in_center(hand.wrist_x, hand.wrist_y):
            return None

        handedness = hand.handedness
        if handedness not in self.node_analyzers:
            handedness = "Right"

        analyzer = self.node_analyzers[handedness]
        now = time.monotonic()

        # 2. Extract invisible kinematic nodes and pivots (not drawn on user screen)
        nodes = analyzer.extract_nodes(hand)
        analyzer.update_trajectory(nodes, now)
        self.last_nodes[handedness] = nodes

        # 3. ─── FRONT-VIEW GATE ──────────────────────────────────────────────
        #    Both FIST and THROW must be detected ONLY when the palm directly
        #    faces the camera (frontal view).  Side-views or tilted palms are
        #    ignored, preventing mis-triggers from peripheral hand movement.
        if not nodes.is_facing_camera:
            return None
        # ─────────────────────────────────────────────────────────────────────

        # 4. Update legacy velocity buffer
        buffer = self.velocity_buffers.get(handedness)
        if buffer:
            buffer.push(hand.wrist_x, hand.wrist_y)

        # 5. ── FIST Detection (Host A role arming) ───────────────────────────
        #    All 5 fingers curled, palm facing camera, hand stationary.
        is_fist, fist_conf = analyzer.detect_kinematic_fist(nodes)
        if is_fist:
            return (GestureType.FIST, fist_conf)

        # 6. ── CANCEL (rapid downward swipe) ────────────────────────────────
        if buffer and buffer.vertical_velocity > 0.15:
            return (GestureType.CANCEL, 0.90)

        # 7. ── THROW Detection (Target B role claiming) ──────────────────────
        #    Palm open, high-velocity forward/horizontal impulse.
        is_throw, throw_conf = analyzer.detect_kinematic_throw()
        if is_throw:
            return (GestureType.THROW, throw_conf)

        # 8. ── RECEIVE Detection (legacy open-palm hold) ─────────────────────
        is_receive, receive_conf = analyzer.detect_kinematic_receive(nodes)
        if is_receive:
            return (GestureType.RECEIVE, receive_conf)

        # 9. Fallback velocity rule — only if palm is facing camera (already gated)
        if buffer:
            vx = buffer.horizontal_velocity
            if abs(vx) > 0.08 and nodes.openness_score >= 0.5:
                return (GestureType.THROW, min(0.95, abs(vx) * 10))

        return None

    def _is_in_center(self, x: float, y: float) -> bool:
        """Check if point is in the center region of the frame."""
        margin = (1.0 - GESTURE_FRAME_CENTER_RATIO) / 2.0
        return (margin <= x <= 1.0 - margin) and (margin <= y <= 1.0 - margin)
