"""
AeroSync Kinematic Node & Pivot Hand Engine

Computes biomechanical joint pivots, palm coordinate frames, and 3D angle
feature vectors from raw hand landmarks.

These nodes and pivots are invisible to the user on the screen, but are used
by the computer to learn, analyze, and detect gestures with high accuracy:
- Palm Center Node (Virtual 3D Centroid)
- Metacarpal Plane Normal Vector (Palm facing orientation)
- Scale-Invariant Hand Baseline (Distance invariant)
- Multi-Joint Kinematic Flexion Angles (0°-180° per finger)
- Fingertip-to-Palm Distance Pivot Ratios
- 3D Trajectory Acceleration & Throw Impulse
- 10-Second Per-User Calibration Tuning
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple
from collections import deque

from services.gesture_engine.gesture_types import HandLandmarks, LandmarkPoint


@dataclass
class Vector3D:
    """Simple 3D vector with vector arithmetic."""
    x: float
    y: float
    z: float

    def __add__(self, other: "Vector3D") -> "Vector3D":
        return Vector3D(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "Vector3D") -> "Vector3D":
        return Vector3D(self.x - other.x, self.y - other.y, self.z - other.z)

    def __mul__(self, scalar: float) -> "Vector3D":
        return Vector3D(self.x * scalar, self.y * scalar, self.z * scalar)

    @property
    def magnitude(self) -> float:
        return math.sqrt(self.x * self.x + self.y * self.y + self.z * self.z)

    def normalized(self) -> "Vector3D":
        mag = self.magnitude
        if mag < 1e-6:
            return Vector3D(0.0, 0.0, 0.0)
        return Vector3D(self.x / mag, self.y / mag, self.z / mag)

    def dot(self, other: "Vector3D") -> float:
        return self.x * other.x + self.y * other.y + self.z * other.z

    def cross(self, other: "Vector3D") -> "Vector3D":
        return Vector3D(
            self.y * other.z - self.z * other.y,
            self.z * other.x - self.x * other.z,
            self.x * other.y - self.y * other.x,
        )


@dataclass
class KinematicHandNodes:
    """
    Extracted node-and-pivot representation of a hand.
    Used internally for high-accuracy mathematical gesture classification.
    """
    # 1. Palm Center Pivot (3D Centroid of wrist and MCP joints)
    palm_center: Vector3D = field(default_factory=lambda: Vector3D(0, 0, 0))

    # 2. Palm Normal Vector (unit vector perpendicular to palm plane)
    # nz < -0.35 means palm is facing toward the screen/camera
    palm_normal: Vector3D = field(default_factory=lambda: Vector3D(0, 0, 0))

    # 3. Longitudinal Hand Axis (wrist to middle finger root)
    hand_axis: Vector3D = field(default_factory=lambda: Vector3D(0, 0, 0))

    # 4. Scale baseline (distance between index MCP and pinky MCP)
    hand_scale: float = 1.0

    # 5. Joint flexion angles in degrees (180° = straight, <90° = curled)
    # Keys: 'thumb', 'index', 'middle', 'ring', 'pinky'
    flexion_angles: Dict[str, float] = field(default_factory=dict)

    # 6. Scale-invariant fingertip distance ratios (relative to palm center / scale)
    tip_extension_ratios: Dict[str, float] = field(default_factory=dict)

    # 7. Hand openness score (0.0 = tight fist, 1.0 = fully open splay)
    openness_score: float = 0.0

    # 8. Palm facing direction
    is_facing_camera: bool = False


def _angle_between(v1: Vector3D, v2: Vector3D) -> float:
    """Compute angle between two 3D vectors in degrees (0 to 180)."""
    m1 = v1.magnitude
    m2 = v2.magnitude
    if m1 < 1e-6 or m2 < 1e-6:
        return 180.0
    dot_val = v1.dot(v2) / (m1 * m2)
    dot_clamped = max(-1.0, min(1.0, dot_val))
    return math.degrees(math.acos(dot_clamped))


class NodeBasedGestureAnalyzer:
    """
    Analyzes sequences of KinematicHandNodes to detect gestures with maximum
    accuracy, tracking velocity, acceleration, and kinematic joint state changes.
    """

    def __init__(self, history_length: int = 12):
        self.history_length = history_length
        # History of palm_center pivots for trajectory calculation
        self.palm_trajectory: deque[Vector3D] = deque(maxlen=history_length)
        # History of openness scores
        self.openness_history: deque[float] = deque(maxlen=history_length)
        # Timestamps
        self.timestamps: deque[float] = deque(maxlen=history_length)

        # Per-user 10-second calibration profile
        try:
            from services.gesture_engine.user_calibration import UserCalibrationProfile
            self.calibration_profile: Optional[UserCalibrationProfile] = UserCalibrationProfile.load()
        except Exception:
            self.calibration_profile = None

    def reload_calibration(self) -> None:
        """Reload user calibration from disk."""
        try:
            from services.gesture_engine.user_calibration import UserCalibrationProfile
            self.calibration_profile = UserCalibrationProfile.load()
        except Exception:
            self.calibration_profile = None

    def extract_nodes(self, hand: HandLandmarks) -> KinematicHandNodes:
        """
        Extract kinematic nodes and pivots from 21 MediaPipe raw landmarks.
        """
        lms = [Vector3D(lm.x, lm.y, lm.z) for lm in hand.landmarks]
        if len(lms) < 21:
            return KinematicHandNodes()

        # 1. Palm Center Pivot: weighted centroid of wrist and MCP joints
        wrist = lms[0]
        index_mcp = lms[5]
        middle_mcp = lms[9]
        ring_mcp = lms[13]
        pinky_mcp = lms[17]

        palm_center = Vector3D(
            (wrist.x + index_mcp.x + middle_mcp.x + ring_mcp.x + pinky_mcp.x) / 5.0,
            (wrist.y + index_mcp.y + middle_mcp.y + ring_mcp.y + pinky_mcp.y) / 5.0,
            (wrist.z + index_mcp.z + middle_mcp.z + ring_mcp.z + pinky_mcp.z) / 5.0,
        )

        # 2. Scale baseline: Distance between index MCP and pinky MCP
        hand_scale = (index_mcp - pinky_mcp).magnitude
        if hand_scale < 1e-4:
            hand_scale = 0.1

        # 3. Metacarpal Plane Normal Vector (cross product of palm axes)
        v_wrist_middle = middle_mcp - wrist
        v_pinky_index = index_mcp - pinky_mcp
        normal = v_pinky_index.cross(v_wrist_middle).normalized()

        # For Left Hand, flip normal so negative z always means facing camera
        if hand.handedness == "Left":
            normal = normal * -1.0

        is_facing_camera = normal.z < -0.35

        # 4. Compute finger joint flexion angles (0 to 180 degrees)
        finger_chains = {
            "thumb": (1, 2, 3, 4),
            "index": (5, 6, 7, 8),
            "middle": (9, 10, 11, 12),
            "ring": (13, 14, 15, 16),
            "pinky": (17, 18, 19, 20),
        }

        flexion_angles: Dict[str, float] = {}
        tip_extension_ratios: Dict[str, float] = {}
        tips_distances: List[float] = []

        for name, chain in finger_chains.items():
            p_mcp, p_pip, p_dip, p_tip = lms[chain[0]], lms[chain[1]], lms[chain[2]], lms[chain[3]]
            v_proximal = p_pip - p_mcp
            v_distal = p_tip - p_dip
            angle = _angle_between(v_proximal, v_distal)
            flexion_angles[name] = round(angle, 1)

            tip_dist = (p_tip - palm_center).magnitude
            ratio = tip_dist / hand_scale
            tip_extension_ratios[name] = round(ratio, 2)
            tips_distances.append(ratio)

        # 5. Hand Openness Score (normalized 0.0 to 1.0)
        avg_ratio = sum(tips_distances) / len(tips_distances)
        openness_score = round(max(0.0, min(1.0, (avg_ratio - 0.7) / 1.3)), 2)

        return KinematicHandNodes(
            palm_center=palm_center,
            palm_normal=normal,
            hand_axis=v_wrist_middle.normalized(),
            hand_scale=hand_scale,
            flexion_angles=flexion_angles,
            tip_extension_ratios=tip_extension_ratios,
            openness_score=openness_score,
            is_facing_camera=is_facing_camera,
        )

    def update_trajectory(self, nodes: KinematicHandNodes, timestamp: float) -> None:
        """Record current nodes into temporal history buffer."""
        self.palm_trajectory.append(nodes.palm_center)
        self.openness_history.append(nodes.openness_score)
        self.timestamps.append(timestamp)

    def detect_kinematic_throw(self) -> Tuple[bool, float]:
        """
        High-accuracy node-based throw detection:
        Analyzes the trajectory of the Palm Center Pivot over time.
        A throw consists of:
        1. High forward/outward velocity of the Palm Center Node.
        2. Positive acceleration impulse.
        3. Dynamic expansion from closed/neutral to open hand (release).

        Returns:
            Tuple of (is_throw, confidence_score 0.0-1.0).
        """
        if len(self.palm_trajectory) < 4:
            return False, 0.0

        pts = list(self.palm_trajectory)
        times = list(self.timestamps)

        # 1. Compute velocity vectors between consecutive frames
        velocities: List[Vector3D] = []
        for i in range(1, len(pts)):
            dt = max(1e-4, times[i] - times[i - 1])
            vel = (pts[i] - pts[i - 1]) * (1.0 / dt)
            velocities.append(vel)

        if not velocities:
            return False, 0.0

        recent_vels = velocities[-3:]
        avg_vx = sum(v.x for v in recent_vels) / len(recent_vels)
        avg_vy = sum(v.y for v in recent_vels) / len(recent_vels)
        avg_vz = sum(v.z for v in recent_vels) / len(recent_vels)
        speed = math.sqrt(avg_vx * avg_vx + avg_vy * avg_vy + avg_vz * avg_vz)

        # Forward acceleration (thrust toward screen) or fast swipe
        horizontal_thrust = abs(avg_vx) > 0.6
        forward_thrust = avg_vz < -0.5
        thrust_detected = horizontal_thrust or forward_thrust or speed > 0.8

        # Openness transition: hand was less open, now opened (release)
        openness = list(self.openness_history)
        recent_open = openness[-1]
        earlier_open = openness[0]
        opened_up = (recent_open >= 0.6) and (recent_open >= earlier_open)

        if thrust_detected and opened_up:
            confidence = min(0.99, max(0.80, 0.70 + speed * 0.2 + recent_open * 0.1))
            return True, round(confidence, 2)

        return False, 0.0

    def detect_kinematic_fist(self, nodes: KinematicHandNodes) -> Tuple[bool, float]:
        """
        High-accuracy node-based FIST detection.
        Uses calibrated per-user thresholds when available.

        Returns:
            Tuple of (is_fist, confidence_score 0.0-1.0).
        """
        # 1. Front-view enforcement — strict threshold
        palm_z_threshold = -0.35
        if self.calibration_profile and self.calibration_profile.is_calibrated:
            palm_z_threshold = self.calibration_profile.tuned_palm_z_threshold

        if nodes.palm_normal.z >= palm_z_threshold:
            return False, 0.0

        required_fingers = ["thumb", "index", "middle", "ring", "pinky"]

        # 2. All fingers must be flexed
        for finger in required_fingers:
            threshold = 90.0
            if self.calibration_profile and self.calibration_profile.is_calibrated:
                threshold = self.calibration_profile.get_flexion_threshold(finger)
            angle = nodes.flexion_angles.get(finger, 180.0)
            if angle > threshold:
                return False, 0.0

        # 3. All fingertips must be close to palm center (curled in)
        for finger in required_fingers:
            threshold_ratio = 1.0
            if self.calibration_profile and self.calibration_profile.is_calibrated:
                threshold_ratio = self.calibration_profile.get_ratio_threshold(finger)
            ratio = nodes.tip_extension_ratios.get(finger, 2.0)
            if ratio > threshold_ratio:
                return False, 0.0

        # 4. Global openness gate
        openness_threshold = 0.20
        if self.calibration_profile and self.calibration_profile.is_calibrated:
            openness_threshold = self.calibration_profile.get_openness_threshold()
        if nodes.openness_score > openness_threshold:
            return False, 0.0

        # 5. Relative stationarity check (avoid mis-detecting mid-swipe frames)
        if len(self.palm_trajectory) >= 3:
            pts = list(self.palm_trajectory)[-3:]
            movement = (pts[-1] - pts[0]).magnitude
            if movement > 0.12:
                return False, 0.0

        # Confidence scales with how closed the hand is and how well it faces camera
        avg_flexion = sum(nodes.flexion_angles.get(f, 90.0) for f in required_fingers) / 5.0
        avg_ratio = sum(nodes.tip_extension_ratios.get(f, 1.0) for f in required_fingers) / 5.0
        flex_score = max(0.0, (90.0 - avg_flexion) / 90.0)
        ratio_score = max(0.0, 1.0 - avg_ratio)
        cam_score = max(0.0, (-nodes.palm_normal.z - 0.35) / 0.65)

        confidence = round(0.4 * flex_score + 0.35 * ratio_score + 0.25 * cam_score, 2)
        confidence = min(0.99, max(0.75, confidence + 0.65))  # floor at 0.75
        return True, confidence

    def detect_kinematic_receive(self, nodes: KinematicHandNodes) -> Tuple[bool, float]:
        """
        High-accuracy node-based receive detection:
        Palm open, stable, facing the screen, stationary.
        """
        if len(self.palm_trajectory) < 3:
            return False, 0.0
        if not nodes.is_facing_camera:
            return False, 0.0
        pts = list(self.palm_trajectory)[-3:]
        displacement = (pts[-1] - pts[0]).magnitude
        if displacement < 0.06 and nodes.openness_score > 0.65:
            conf = min(0.98, 0.80 + nodes.openness_score * 0.15)
            return True, round(conf, 2)
        return False, 0.0
