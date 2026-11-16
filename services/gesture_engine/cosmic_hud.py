"""
AeroSync Cosmic Hand HUD Renderer

Renders an ethereal, space-themed constellation HUD on the camera preview:
- When hands are detected:
  - Renders a glowing "Constellation Core" orbital reticle around the Palm Center Node.
  - Connects the 5 fingertips to the palm pivot with fine celestial constellation lines.
  - Shows an assistive velocity vector when a throw motion begins.
  - If hand is outside the 60% center detection zone: shifts to amber with an
    assistive warning ("Center Hand in Frame") so the user immediately understands
    why gestures aren't triggering.
  - FIST detected → pulsing red/orange "HOST MODE ARMED" badge at top of frame.
  - THROW detected → cyan "TARGET CLAIMING" badge.
- When hand is NOT detected:
  - Completely removed — no clutter! Displays only a faint celestial targeting grid.
- Role Indicator (top-left):
  - NEUTRAL (gray), HOST (red-orange), CANDIDATE (cyan), TARGET (violet), TRANSFERRING (green)
"""

import math
import time
from typing import List, Optional, Tuple
import cv2
import numpy as np

from services.gesture_engine.gesture_types import HandLandmarks
from services.gesture_engine.node_engine import KinematicHandNodes, Vector3D
from shared.constants import GESTURE_FRAME_CENTER_RATIO, RoleState

# Cosmic Colors in BGR format
COLOR_CYAN_GLOW = (255, 230, 0)      # #00E6FF (Cyan starlight)
COLOR_VIOLET_CORE = (250, 120, 160)  # #A078FA (Nebula violet)
COLOR_WHITE_STAR = (255, 255, 255)   # Star apex
COLOR_AMBER_WARN = (0, 165, 255)     # Warning amber
COLOR_GRID_FAINT = (80, 50, 60)      # Very faint cosmic grid

# Role-specific badge colors (BGR)
_ROLE_COLORS = {
    RoleState.NEUTRAL:      (110, 110, 110),   # gray
    RoleState.HOST:         (0,   80,  220),   # red-orange (deep orange in BGR)
    RoleState.CANDIDATE:    (200, 200,   0),   # cyan
    RoleState.TARGET:       (220,  80,  200),  # violet
    RoleState.TRANSFERRING: (60,  200,   40),  # green
}
_ROLE_LABELS = {
    RoleState.NEUTRAL:      "NEUTRAL",
    RoleState.HOST:         "HOST A  ✊ CAPTURING",
    RoleState.CANDIDATE:    "CANDIDATE — THROW TO CLAIM",
    RoleState.TARGET:       "TARGET B  🚀 RECEIVING",
    RoleState.TRANSFERRING: "TRANSFERRING…",
}


def _draw_comet_tail_and_prediction(
    overlay: np.ndarray,
    w: int,
    h: int,
    palm_px: Tuple[int, int],
    past_pts: List[Any],
    pred_pts: List[Any],
    velocity: Optional[Any] = None,
    is_throw: bool = False,
) -> None:
    """
    Renders celestial comet tail with animated particles following the hand's
    velocity vector and predicts the beam trajectory towards the target device.
    """
    # 1. Draw Past Comet Tail (Starlight Ribbon & Particle Dust)
    if past_pts and len(past_pts) >= 2:
        valid_px: List[Tuple[int, int]] = []
        for p in past_pts:
            px = int(p.x * w)
            py = int(p.y * h)
            valid_px.append((px, py))

        # Connect with tapering celestial lines
        n = len(valid_px)
        for i in range(n - 1):
            ratio = (i + 1) / float(n)  # 0.0 near tail start, 1.0 near palm
            b = int(250 * ratio + 180 * (1.0 - ratio))
            g = int(230 * ratio + 80 * (1.0 - ratio))
            r = int(60 * ratio + 180 * (1.0 - ratio))
            color = (b, g, r)
            thickness = max(1, int(3 * ratio))
            cv2.line(overlay, valid_px[i], valid_px[i + 1], color, thickness, cv2.LINE_AA)
            particle_r = max(1, int(3 * ratio))
            cv2.circle(overlay, valid_px[i], particle_r, color, -1, cv2.LINE_AA)

        # Connect last past point to current palm center
        cv2.line(overlay, valid_px[-1], palm_px, COLOR_CYAN_GLOW, 2, cv2.LINE_AA)

    # 2. Draw Forward Predictive Trajectory Vector
    if pred_pts:
        pred_px: List[Tuple[int, int]] = []
        for p in pred_pts:
            px = max(5, min(w - 5, int(p.x * w)))
            py = max(5, min(h - 5, int(p.y * h)))
            pred_px.append((px, py))

        # Draw trajectory prediction arc
        last_pt = palm_px
        for i, pt in enumerate(pred_px):
            if i % 2 == 0:
                cv2.line(overlay, last_pt, pt, (0, 245, 212), 2, cv2.LINE_AA)
            else:
                cv2.line(overlay, last_pt, pt, (255, 200, 50), 1, cv2.LINE_AA)
            cv2.circle(overlay, pt, 2, COLOR_WHITE_STAR, -1, cv2.LINE_AA)
            last_pt = pt

        # Target Aim Reticle at the trajectory head
        lead_pt = pred_px[-1]
        reticle_r = 12 if is_throw else 8
        reticle_color = (0, 255, 255) if is_throw else (0, 245, 212)
        cv2.circle(overlay, lead_pt, reticle_r, reticle_color, 1, cv2.LINE_AA)
        cv2.circle(overlay, lead_pt, 3, COLOR_WHITE_STAR, -1, cv2.LINE_AA)

        # Crosshairs on lead reticle
        ch_len = 5
        cv2.line(overlay, (lead_pt[0] - ch_len, lead_pt[1]), (lead_pt[0] + ch_len, lead_pt[1]), reticle_color, 1, cv2.LINE_AA)
        cv2.line(overlay, (lead_pt[0], lead_pt[1] - ch_len), (lead_pt[0], lead_pt[1] + ch_len), reticle_color, 1, cv2.LINE_AA)

        # Trajectory beam tag
        if is_throw:
            tag = "✦ BEAM AIM: TARGET PC 🚀"
            cv2.putText(
                overlay,
                tag,
                (max(10, min(w - 200, lead_pt[0] - 50)), max(20, lead_pt[1] - 12)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                (0, 255, 255),
                1,
                cv2.LINE_AA,
            )
        elif velocity and getattr(velocity, "magnitude", 0) > 0.2:
            speed_val = round(velocity.magnitude, 1)
            tag = f"✦ VECTOR ({speed_val}m/s)"
            cv2.putText(
                overlay,
                tag,
                (max(10, min(w - 140, lead_pt[0] - 30)), max(20, lead_pt[1] - 10)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.32,
                (0, 245, 212),
                1,
                cv2.LINE_AA,
            )


def draw_cosmic_hud(
    frame: np.ndarray,
    hands: List[HandLandmarks],
    nodes_map: Optional[dict] = None,
    gesture_name: Optional[str] = None,
    role_state: Optional[str] = None,
    calibration_text: Optional[str] = None,
    sensor_alert: Optional[str] = None,
    two_hand_suppressed: bool = False,
    eco_mode: bool = False,
    trajectory_data: Optional[dict] = None,
) -> np.ndarray:
    """
    Apply the celestial constellation HUD to the camera frame.
    Alpha-blends transparent glow layers for a polished sci-fi look.

    Args:
        frame:               Raw BGR camera frame.
        hands:               Detected hand landmark objects.
        nodes_map:           Dict of handedness → KinematicHandNodes (from classifier).
        gesture_name:        Name of the last confirmed gesture for badge display.
        role_state:          Current RoleState value for the role indicator pill.
        calibration_text:    Active 10-second calibration prompt/countdown text.
        sensor_alert:        Low lighting or hardware degradation fallback notification.
        two_hand_suppressed: True if bimanual anti-trigger is suppressing gesture execution.
        eco_mode:            True if running on battery and background operations are throttled.
    """
    h, w, _ = frame.shape
    overlay = frame.copy()

    # 1. Draw Subtle Celestial Sensor Zone (Center 60% Detection Brackets)
    margin_ratio = (1.0 - GESTURE_FRAME_CENTER_RATIO) / 2.0
    x_min = int(w * margin_ratio)
    x_max = int(w * (1.0 - margin_ratio))
    y_min = int(h * margin_ratio)
    y_max = int(h * (1.0 - margin_ratio))

    bracket_len = int(min(w, h) * 0.06)
    bracket_color = (60, 40, 50) if not hands else (100, 70, 90)

    # Top-Left Bracket
    cv2.line(overlay, (x_min, y_min), (x_min + bracket_len, y_min), bracket_color, 1, cv2.LINE_AA)
    cv2.line(overlay, (x_min, y_min), (x_min, y_min + bracket_len), bracket_color, 1, cv2.LINE_AA)
    # Top-Right Bracket
    cv2.line(overlay, (x_max, y_min), (x_max - bracket_len, y_min), bracket_color, 1, cv2.LINE_AA)
    cv2.line(overlay, (x_max, y_min), (x_max, y_min + bracket_len), bracket_color, 1, cv2.LINE_AA)
    # Bottom-Left Bracket
    cv2.line(overlay, (x_min, y_max), (x_min + bracket_len, y_max), bracket_color, 1, cv2.LINE_AA)
    cv2.line(overlay, (x_min, y_max), (x_min, y_max - bracket_len), bracket_color, 1, cv2.LINE_AA)
    # Bottom-Right Bracket
    cv2.line(overlay, (x_max, y_max), (x_max - bracket_len, y_max), bracket_color, 1, cv2.LINE_AA)
    cv2.line(overlay, (x_max, y_max), (x_max, y_max - bracket_len), bracket_color, 1, cv2.LINE_AA)

    # Render 10-Second Calibration Banner if active
    if calibration_text:
        cv2.rectangle(overlay, (20, 10), (w - 20, 44), (25, 15, 35), -1)
        cv2.rectangle(overlay, (20, 10), (w - 20, 44), COLOR_CYAN_GLOW, 1)
        cv2.putText(
            overlay,
            f"✦ {calibration_text}",
            (30, 32),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.46,
            COLOR_CYAN_GLOW,
            1,
            cv2.LINE_AA,
        )

    # If NO hands detected: show minimal assistive radar text
    if not hands:
        cv2.putText(
            overlay,
            "AeroSync Sensor: Show Hand in Center",
            (x_min + 10, y_min + 20),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.4,
            (140, 120, 130),
            1,
            cv2.LINE_AA,
        )
        return cv2.addWeighted(overlay, 0.85, frame, 0.15, 0)

    # 2. When Hands ARE Detected: Draw Space Constellation Overlays
    for hand in hands:
        lms = hand.landmarks
        if len(lms) < 21:
            continue

        # Convert normalized points to pixels
        pts = [(int(lm.x * w), int(lm.y * h)) for lm in lms]

        # Calculate Palm Center Node in pixels
        palm_px = (
            int((pts[0][0] + pts[5][0] + pts[9][0] + pts[13][0] + pts[17][0]) / 5.0),
            int((pts[0][1] + pts[5][1] + pts[9][1] + pts[13][1] + pts[17][1]) / 5.0),
        )

        # Check if palm center is within the 60% center capture zone
        in_zone = (x_min <= palm_px[0] <= x_max) and (y_min <= palm_px[1] <= y_max)
        theme_color = COLOR_CYAN_GLOW if in_zone else COLOR_AMBER_WARN
        core_color = COLOR_VIOLET_CORE if in_zone else COLOR_AMBER_WARN

        # Key Fingertip Node Indices: Thumb(4), Index(8), Middle(12), Ring(16), Pinky(20)
        fingertip_indices = [4, 8, 12, 16, 20]
        fingertips = [pts[i] for i in fingertip_indices]

        # Draw Constellation Starlight Lines (connecting fingertips to Palm Center Pivot)
        for tip in fingertips:
            cv2.line(overlay, palm_px, tip, theme_color, 1, cv2.LINE_AA)
            # Soft glowing halo circle around each fingertip star
            cv2.circle(overlay, tip, 5, theme_color, -1, cv2.LINE_AA)
            cv2.circle(overlay, tip, 2, COLOR_WHITE_STAR, -1, cv2.LINE_AA)

        # Connect fingertips sequentially like a constellation arc
        for i in range(len(fingertips) - 1):
            cv2.line(overlay, fingertips[i], fingertips[i + 1], (180, 140, 240), 1, cv2.LINE_AA)

        # Draw Palm Center "Constellation Core" Orbital Reticle
        core_radius = max(8, int(min(w, h) * 0.035))
        # Outer orbital ring
        cv2.circle(overlay, palm_px, core_radius, theme_color, 1, cv2.LINE_AA)
        # Inner glowing core
        cv2.circle(overlay, palm_px, 4, core_color, -1, cv2.LINE_AA)
        cv2.circle(overlay, palm_px, 2, COLOR_WHITE_STAR, -1, cv2.LINE_AA)

        # Subtle orbital tick marks at 0, 90, 180, 270 deg
        for deg in [0, 90, 180, 270]:
            rad = math.radians(deg)
            p1 = (int(palm_px[0] + (core_radius - 3) * math.cos(rad)), int(palm_px[1] + (core_radius - 3) * math.sin(rad)))
            p2 = (int(palm_px[0] + (core_radius + 4) * math.cos(rad)), int(palm_px[1] + (core_radius + 4) * math.sin(rad)))
            cv2.line(overlay, p1, p2, theme_color, 1, cv2.LINE_AA)

        # 2b. Predictive Trajectory Comet Tail & Beam Aim Reticle
        handedness = getattr(hand, "handedness", "Right")
        if trajectory_data and handedness in trajectory_data:
            t_data = trajectory_data[handedness]
            _draw_comet_tail_and_prediction(
                overlay=overlay,
                w=w,
                h=h,
                palm_px=palm_px,
                past_pts=t_data.get("past", []),
                pred_pts=t_data.get("predicted", []),
                velocity=t_data.get("velocity"),
                is_throw=(gesture_name == "throw"),
            )

        # Assistive Status Tag below the hand
        tag_text = "Constellation Locked" if in_zone else "Move Hand To Center"
        tag_y = min(h - 10, palm_px[1] + core_radius + 18)
        tag_x = max(10, min(w - 180, palm_px[0] - 50))

        # Pill background for text
        (txt_w, txt_h), _ = cv2.getTextSize(tag_text, cv2.FONT_HERSHEY_SIMPLEX, 0.38, 1)
        cv2.rectangle(
            overlay,
            (tag_x - 4, tag_y - txt_h - 4),
            (tag_x + txt_w + 4, tag_y + 4),
            (15, 10, 20),
            -1,
        )
        cv2.putText(
            overlay,
            tag_text,
            (tag_x, tag_y),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.38,
            theme_color,
            1,
            cv2.LINE_AA,
        )

        # If a gesture is being triggered (e.g. Throw or Receive)
        if gesture_name:
            gesture_badge = f"✦ {gesture_name.upper()} TRIGGERED"
            cv2.putText(
                overlay,
                gesture_badge,
                (w // 2 - 80, 30),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 255, 180),
                2,
                cv2.LINE_AA,
            )

    # Two-Hand Anti-Trigger Banner (typing / bimanual gesture suppression)
    if two_hand_suppressed:
        cv2.rectangle(overlay, (15, h - 38), (w - 15, h - 10), (10, 15, 30), -1)
        cv2.rectangle(overlay, (15, h - 38), (w - 15, h - 10), (250, 120, 160), 1)
        cv2.putText(
            overlay,
            "✦ 2 HANDS DETECTED: Anti-trigger active (typing/gesturing) — Triggers paused",
            (25, h - 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.36,
            (250, 120, 160),
            1,
            cv2.LINE_AA,
        )

    # Sensor / Low-Light Fallback Alert Banner
    if sensor_alert:
        cv2.rectangle(overlay, (15, h - 68 if two_hand_suppressed else h - 38), (w - 15, h - 42 if two_hand_suppressed else h - 10), (10, 20, 40), -1)
        cv2.rectangle(overlay, (15, h - 68 if two_hand_suppressed else h - 38), (w - 15, h - 42 if two_hand_suppressed else h - 10), COLOR_AMBER_WARN, 1)
        cv2.putText(
            overlay,
            f"✦ {sensor_alert}",
            (25, h - 52 if two_hand_suppressed else h - 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.36,
            COLOR_AMBER_WARN,
            1,
            cv2.LINE_AA,
        )

    # Eco-Mode Battery Throttling Badge (amber)
    if eco_mode:
        eco_y = 48 if calibration_text else 14
        cv2.rectangle(overlay, (w - 230, eco_y), (w - 15, eco_y + 24), (10, 20, 35), -1)
        cv2.rectangle(overlay, (w - 230, eco_y), (w - 15, eco_y + 24), (0, 165, 255), 1)  # Amber
        cv2.putText(
            overlay,
            "⚡ ECO MODE (Battery Throttled)",
            (w - 222, eco_y + 16),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.36,
            (0, 165, 255),
            1,
            cv2.LINE_AA,
        )

    # Alpha-blend overlay for soft cosmic transparency (65% overlay + 35% original frame)
    blended = cv2.addWeighted(overlay, 0.70, frame, 0.30, 0)
    return blended
