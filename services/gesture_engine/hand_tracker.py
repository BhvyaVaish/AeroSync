"""
AeroSync Hand Tracker (MediaPipe wrapper)

Provides a clean interface for hand landmark detection.
Gracefully falls back to a mock implementation if MediaPipe
is unavailable (e.g., incompatible Python versions).
"""

import logging
from typing import List

from services.gesture_engine.gesture_types import HandLandmarks, LandmarkPoint

logger = logging.getLogger(__name__)

# Try importing MediaPipe
try:
    import mediapipe as mp
    import cv2
    MEDIAPIPE_AVAILABLE = True
except ImportError:
    logger.warning("MediaPipe or cv2 not available. Falling back to mock hand tracker.")
    MEDIAPIPE_AVAILABLE = False


class HandTracker:
    """
    Wrapper around MediaPipe Hands solution.
    Detects hands in an image and extracts 21 landmarks per hand.
    """

    def __init__(self, max_hands: int = 2, min_confidence: float = 0.7):
        self.max_hands = max_hands
        self.min_confidence = min_confidence
        self._hands = None
        
        if MEDIAPIPE_AVAILABLE:
            self._mp_hands = mp.solutions.hands
            self._hands = self._mp_hands.Hands(
                static_image_mode=False,
                max_num_hands=max_hands,
                min_detection_confidence=min_confidence,
                min_tracking_confidence=min_confidence
            )

    def process_frame(self, frame) -> List[HandLandmarks]:
        """
        Process a BGR image frame and return a list of detected hands.
        
        Args:
            frame: A BGR numpy array (OpenCV format)
            
        Returns:
            List[HandLandmarks]: One object per detected hand
        """
        if not MEDIAPIPE_AVAILABLE:
            return self._mock_process(frame)
            
        if self._hands is None:
            return []

        # Convert BGR to RGB for MediaPipe
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        # To improve performance, optionally mark image as not writeable
        frame_rgb.flags.writeable = False
        results = self._hands.process(frame_rgb)
        
        detected_hands = []
        if results.multi_hand_landmarks and results.multi_handedness:
            for hand_landmarks, handedness in zip(results.multi_hand_landmarks, results.multi_handedness):
                # Extract classification info (Left/Right, Score)
                label = handedness.classification[0].label
                score = handedness.classification[0].score
                
                # Convert landmarks to our data structure
                points = []
                for lm in hand_landmarks.landmark:
                    points.append(LandmarkPoint(x=lm.x, y=lm.y, z=lm.z))
                
                hl = HandLandmarks(
                    landmarks=points,
                    handedness=label,
                    confidence=score,
                    wrist_x=points[0].x,
                    wrist_y=points[0].y
                )
                detected_hands.append(hl)
                
        return detected_hands

    def _mock_process(self, frame) -> List[HandLandmarks]:
        """Mock processor when MediaPipe is unavailable."""
        # For mock, we return no hands by default.
        # In a test environment, you could inject synthetic data here.
        return []

    def close(self):
        """Clean up MediaPipe resources."""
        if self._hands is not None:
            self._hands.close()
