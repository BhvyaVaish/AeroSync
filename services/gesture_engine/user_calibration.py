"""
AeroSync 10-Second Per-User Gesture Calibration Engine

Calibrates individual user biomechanics, finger joint mobilities,
camera distance, and natural resting flexion angles over a 10-second guided cycle:
  • Phase 1 (0.0s – 5.0s): Open Hand Calibration (resting splay, extension ratios, palm normal)
  • Phase 2 (5.0s – 10.0s): Fist Pose Calibration (fist curl flexion, closed ratios, fist openness)

Saves a persistent UserCalibrationProfile that tunes the Kinematic Node Engine
for personalized accuracy.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

CALIBRATION_FILE_DEFAULT = os.path.join(
    os.path.expanduser("~"), ".aerosync", "user_calibration.json"
)


@dataclass
class UserCalibrationProfile:
    """Personalized kinematic thresholds computed from 10-second calibration."""
    user_id: str = "default_user"
    is_calibrated: bool = False
    calibrated_at: str = ""

    # Phase 1: Open Hand Baselines
    open_flexion_angles: Dict[str, float] = field(default_factory=dict)
    open_tip_extension_ratios: Dict[str, float] = field(default_factory=dict)
    open_openness_score: float = 0.85
    open_hand_scale: float = 0.15

    # Phase 2: Fist Pose Baselines
    fist_flexion_angles: Dict[str, float] = field(default_factory=dict)
    fist_tip_extension_ratios: Dict[str, float] = field(default_factory=dict)
    fist_openness_score: float = 0.12
    palm_normal_z_baseline: float = -0.55

    # Tuned Thresholds (Personalized)
    tuned_flexion_thresholds: Dict[str, float] = field(default_factory=dict)
    tuned_ratio_thresholds: Dict[str, float] = field(default_factory=dict)
    tuned_openness_threshold: float = 0.22
    tuned_palm_z_threshold: float = -0.35

    def get_flexion_threshold(self, finger: str) -> float:
        """Personalized flexion threshold (degrees); angle must be below this for fist."""
        if not self.is_calibrated:
            return 90.0
        return self.tuned_flexion_thresholds.get(finger, 90.0)

    def get_ratio_threshold(self, finger: str) -> float:
        """Personalized tip extension ratio threshold; ratio must be below this for fist."""
        if not self.is_calibrated:
            return 1.0
        return self.tuned_ratio_thresholds.get(finger, 1.0)

    def get_openness_threshold(self) -> float:
        """Personalized openness score threshold; score must be below this for fist."""
        if not self.is_calibrated:
            return 0.20
        return self.tuned_openness_threshold

    def save(self, filepath: str = CALIBRATION_FILE_DEFAULT) -> bool:
        """Persist calibration profile to disk."""
        try:
            os.makedirs(os.path.dirname(filepath), exist_ok=True)
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(asdict(self), f, indent=2)
            logger.info("[Calibration] Saved user profile to %s", filepath)
            return True
        except Exception as exc:
            logger.error("[Calibration] Failed to save profile: %s", exc)
            return False

    @staticmethod
    def load(filepath: str = CALIBRATION_FILE_DEFAULT) -> "UserCalibrationProfile":
        """Load user calibration profile from disk, or return default uncalibrated."""
        if not os.path.isfile(filepath):
            return UserCalibrationProfile()
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                data = json.load(f)
            profile = UserCalibrationProfile(**data)
            logger.info("[Calibration] Loaded calibrated user profile from %s", filepath)
            return profile
        except Exception as exc:
            logger.debug("[Calibration] Could not load profile: %s", exc)
            return UserCalibrationProfile()


class TenSecondCalibrator:
    """
    Coordinates the 10-second calibration routine.
    Takes frame nodes, computes running statistics, and generates profile.
    """

    def __init__(self, user_id: str = "default_user"):
        self.user_id = user_id
        self.start_time: Optional[float] = None
        self.is_active = False

        # Samples collected during Phase 1 (0s - 5s)
        self.open_samples: List[dict] = []
        # Samples collected during Phase 2 (5s - 10s)
        self.fist_samples: List[dict] = []

    def start(self) -> None:
        """Begin 10-second calibration session."""
        self.start_time = time.monotonic()
        self.is_active = True
        self.open_samples.clear()
        self.fist_samples.clear()
        logger.info("[Calibration] Started 10-second user calibration")

    def feed_nodes(self, nodes: object) -> Tuple[bool, float, str]:
        """
        Feed a frame's KinematicHandNodes into the calibrator.

        Returns:
            (is_complete, elapsed_seconds, current_instruction)
        """
        if not self.is_active or self.start_time is None:
            return False, 0.0, "Inactive"

        elapsed = time.monotonic() - self.start_time

        if elapsed < 5.0:
            # Phase 1: Open Hand
            instruction = f"Show OPEN hand facing camera ({5.0 - elapsed:.1f}s)"
            if getattr(nodes, "is_facing_camera", False) or getattr(nodes, "openness_score", 0) > 0.4:
                self.open_samples.append({
                    "flexion": getattr(nodes, "flexion_angles", {}),
                    "ratios": getattr(nodes, "tip_extension_ratios", {}),
                    "openness": getattr(nodes, "openness_score", 0.8),
                    "scale": getattr(nodes, "hand_scale", 0.15),
                    "palm_z": getattr(nodes, "palm_normal", None).z if getattr(nodes, "palm_normal", None) else -0.5,
                })
            return False, elapsed, instruction

        elif elapsed < 10.0:
            # Phase 2: Fist Pose
            instruction = f"Form a natural FIST facing camera ({10.0 - elapsed:.1f}s)"
            self.fist_samples.append({
                "flexion": getattr(nodes, "flexion_angles", {}),
                "ratios": getattr(nodes, "tip_extension_ratios", {}),
                "openness": getattr(nodes, "openness_score", 0.1),
                "palm_z": getattr(nodes, "palm_normal", None).z if getattr(nodes, "palm_normal", None) else -0.5,
            })
            return False, elapsed, instruction

        else:
            # Calibration complete!
            self.is_active = False
            return True, 10.0, "Calibration Complete!"

    def compute_profile(self) -> UserCalibrationProfile:
        """Compile sampled frames into a finalized UserCalibrationProfile."""
        profile = UserCalibrationProfile(
            user_id=self.user_id,
            is_calibrated=True,
            calibrated_at=time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        )

        fingers = ["thumb", "index", "middle", "ring", "pinky"]

        # Average Phase 1 (Open Hand)
        if self.open_samples:
            for f in fingers:
                angles = [s["flexion"].get(f, 150.0) for s in self.open_samples if f in s["flexion"]]
                ratios = [s["ratios"].get(f, 1.5) for s in self.open_samples if f in s["ratios"]]
                profile.open_flexion_angles[f] = round(sum(angles) / len(angles), 1) if angles else 150.0
                profile.open_tip_extension_ratios[f] = round(sum(ratios) / len(ratios), 2) if ratios else 1.5
            profile.open_openness_score = round(sum(s["openness"] for s in self.open_samples) / len(self.open_samples), 2)

        # Average Phase 2 (Fist)
        if self.fist_samples:
            for f in fingers:
                angles = [s["flexion"].get(f, 60.0) for s in self.fist_samples if f in s["flexion"]]
                ratios = [s["ratios"].get(f, 0.7) for s in self.fist_samples if f in s["ratios"]]
                profile.fist_flexion_angles[f] = round(sum(angles) / len(angles), 1) if angles else 60.0
                profile.fist_tip_extension_ratios[f] = round(sum(ratios) / len(ratios), 2) if ratios else 0.7
            profile.fist_openness_score = round(sum(s["openness"] for s in self.fist_samples) / len(self.fist_samples), 2)
            z_vals = [s["palm_z"] for s in self.fist_samples]
            profile.palm_normal_z_baseline = round(sum(z_vals) / len(z_vals), 2) if z_vals else -0.55

        # Compute tuned personalized thresholds (midpoint with safety margins)
        for f in fingers:
            open_a = profile.open_flexion_angles.get(f, 150.0)
            fist_a = profile.fist_flexion_angles.get(f, 60.0)
            # Threshold halfway between open and closed, clamped reasonably
            tuned_a = max(70.0, min(105.0, (open_a + fist_a) * 0.5))
            profile.tuned_flexion_thresholds[f] = round(tuned_a, 1)

            fist_r = profile.fist_tip_extension_ratios.get(f, 0.7)
            profile.tuned_ratio_thresholds[f] = round(fist_r + 0.25, 2)

        profile.tuned_openness_threshold = round(max(0.18, min(0.30, profile.fist_openness_score + 0.10)), 2)
        profile.tuned_palm_z_threshold = -0.35

        logger.info("[Calibration] Finalized profile for user %s: %s", self.user_id, profile.tuned_flexion_thresholds)
        return profile
