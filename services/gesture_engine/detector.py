"""
AeroSync Gesture Detector Service

Runs the camera capture loop, integrates MediaPipe tracker,
classifier, and state machine, and exposes gesture events via callbacks.
"""

import threading
import time
import logging
from typing import Callable, List, Optional
import traceback

import cv2
import numpy as np

from services.gesture_engine.gesture_types import EngineState, GestureEngineStatus, GestureEvent
from services.gesture_engine.hand_tracker import HandTracker, MEDIAPIPE_AVAILABLE
from services.gesture_engine.gesture_classifier import GestureClassifier
from services.gesture_engine.gesture_state_machine import GestureStateMachine
from services.gesture_engine.camera_widget import DesktopCameraWidget
from services.gesture_engine.cosmic_hud import draw_cosmic_hud
from services.gesture_engine.user_calibration import TenSecondCalibrator
from shared.constants import GESTURE_FPS

logger = logging.getLogger(__name__)


class GestureDetector:
    """
    Main controller for gesture detection.
    Runs camera capture and processing in a background thread.
    """
    
    def __init__(self, camera_index: int = 0, show_camera_widget: bool = True):
        self.camera_index = camera_index
        self.show_camera_widget = show_camera_widget
        self._state = EngineState.STOPPED
        self._error_msg: Optional[str] = None
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        
        # Components
        self.tracker: Optional[HandTracker] = None
        self.classifier = GestureClassifier()
        self.camera_widget = DesktopCameraWidget()

        # 10-Second Per-User Calibration
        self.calibrator = TenSecondCalibrator()
        self._calibration_instruction: str = ""

        # Two-hand anti-trigger & sensor health
        self._two_hand_suppressed: bool = False
        self._last_degraded_toast: float = 0.0
        self._current_sensor_alert: Optional[str] = None
        
        # State machine and callbacks
        self.event_callbacks: List[Callable[[GestureEvent], None]] = []
        self.state_machine = GestureStateMachine(on_event_callback=self._handle_event)
        
        # Metrics
        self._fps = 0.0
        self._hands_detected = 0
        self._last_event: Optional[GestureEvent] = None
        
        # For debugging / API
        self.last_frame: Optional[np.ndarray] = None
        self.frame_lock = threading.Lock()

    def add_callback(self, callback: Callable[[GestureEvent], None]):
        """Register a callback for confirmed gesture events."""
        self.event_callbacks.append(callback)
        
    def _handle_event(self, event: GestureEvent):
        """Internal handler called by State Machine."""
        logger.info(f"GESTURE CONFIRMED: {event.gesture_type.value} ({event.confidence:.2f})")
        self._last_event = event
        for cb in self.event_callbacks:
            try:
                cb(event)
            except Exception as e:
                logger.error(f"Error in gesture callback: {e}")

    def get_status(self) -> GestureEngineStatus:
        """Get a snapshot of the current engine status."""
        return GestureEngineStatus(
            state=self._state,
            fps=self._fps,
            hands_detected=self._hands_detected,
            last_gesture=self._last_event,
            error_message=self._error_msg,
            camera_index=self.camera_index
        )

    def get_latest_frame(self) -> Optional[np.ndarray]:
        """Safely fetch a copy of the latest clean camera frame."""
        with self.frame_lock:
            return self.last_frame.copy() if self.last_frame is not None else None

    def start_calibration(self, user_id: str = "default_user") -> None:
        """Start a 10-second per-user calibration routine."""
        self.calibrator.user_id = user_id
        self.calibrator.start()
        self._calibration_instruction = "Show OPEN hand facing camera (5.0s)"
        try:
            from services.audio.cosmic_audio import play_calibration_step_sound
            play_calibration_step_sound(1)
        except Exception:
            pass

    def get_calibration_status(self) -> dict:
        """Get live calibration status."""
        elapsed = 0.0
        if self.calibrator.is_active and self.calibrator.start_time:
            elapsed = round(time.monotonic() - self.calibrator.start_time, 1)
        return {
            "is_active": self.calibrator.is_active,
            "instruction": self._calibration_instruction,
            "elapsed": elapsed,
            "progress_pct": min(100, int((elapsed / 10.0) * 100)),
        }

    def start(self):
        """Start the detection thread and bottom-corner camera widget."""
        if self._state == EngineState.RUNNING:
            return
            
        logger.info("Starting gesture detection engine...")
        self._state = EngineState.STARTING
        self._error_msg = None
        self._stop_event.clear()
        
        self.tracker = HandTracker()
        
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()

        # Start picture-in-picture camera widget in bottom corner if enabled
        if self.show_camera_widget:
            self.camera_widget.start(
                get_frame_callback=self.get_latest_frame,
                get_status_callback=lambda: {
                    "hands_detected": self._hands_detected,
                    "fps": self._fps,
                },
            )

    def stop(self):
        """Stop the detection thread and camera widget."""
        if self._state == EngineState.STOPPED:
            return
            
        logger.info("Stopping gesture detection engine...")
        self.camera_widget.stop()
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3.0)
            
        if self.tracker:
            self.tracker.close()
            self.tracker = None
            
        self._state = EngineState.STOPPED
        logger.info("Gesture detection engine stopped.")

    def _run_loop(self):
        """Main camera and processing loop."""
        cap = None
        try:
            if MEDIAPIPE_AVAILABLE:
                # Only try to open camera if we're not using the mock
                cap = cv2.VideoCapture(self.camera_index)
                if not cap.isOpened():
                    raise RuntimeError(f"Could not open camera {self.camera_index}")
                    
                # Set lower resolution for performance
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
            
            self._state = EngineState.RUNNING
            
            frame_time = 1.0 / GESTURE_FPS
            last_time = time.monotonic()
            frames_processed = 0
            fps_last_calc = time.monotonic()
            
            while not self._stop_event.is_set():
                now = time.monotonic()
                elapsed = now - last_time
                
                # Enforce target FPS
                if elapsed < frame_time:
                    time.sleep(frame_time - elapsed)
                    now = time.monotonic()
                    
                last_time = now
                
                frame = None
                if MEDIAPIPE_AVAILABLE and cap:
                    ret, frame = cap.read()
                    if not ret:
                        logger.warning("Failed to read from camera. Retrying...")
                        time.sleep(1.0)
                        continue
                        
                    # Flip horizontally for selfie-view
                    frame = cv2.flip(frame, 1)
                else:
                    # Mock frame (blank)
                    frame = np.zeros((480, 640, 3), dtype=np.uint8)
                    cv2.putText(frame, "MOCK MODE (MediaPipe missing)", (50, 240), 
                               cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
                    time.sleep(frame_time) # Simulate camera delay
                
                # Process Frame (Node & Pivot analysis is performed invisibly without drawing on user screen)
                h, w, _ = frame.shape
                hands = self.tracker.process_frame(frame)
                self._hands_detected = len(hands)
                
                # Classify hands using kinematic nodes
                for hand in hands:
                    classification = self.classifier.process_hand(hand, w, h)
                    self.state_machine.process(classification, hand.handedness)
                    
                # If no hands, still tick the state machine to handle resets/cooldowns
                if not hands:
                    self.state_machine.process(None, "unknown")
                    
                # 10-Second Per-User Calibration processing
                if self.calibrator.is_active:
                    primary_nodes = None
                    if hands:
                        h0 = hands[0]
                        primary_nodes = self.classifier.last_nodes.get(h0.handedness)
                    is_complete, elapsed, instruction = self.calibrator.feed_nodes(primary_nodes)
                    self._calibration_instruction = instruction
                    if is_complete:
                        profile = self.calibrator.compute_profile()
                        profile.save()
                        for analyzer in self.classifier.node_analyzers.values():
                            analyzer.reload_calibration()
                        try:
                            from services.audio.cosmic_audio import play_calibration_step_sound
                            play_calibration_step_sound(3)
                        except Exception:
                            pass

                # Render the space-themed Cosmic Constellation HUD onto frame
                active_gesture = (
                    self._last_event.gesture_type.value
                    if (self._last_event and now - getattr(self._last_event, "timestamp", 0) < 1.5)
                    else None
                )
                cal_text = self._calibration_instruction if self.calibrator.is_active else None
                hud_frame = draw_cosmic_hud(frame, hands, gesture_name=active_gesture, calibration_text=cal_text)

                # Store latest frame safely for the corner camera widget
                with self.frame_lock:
                    self.last_frame = hud_frame
                    
                # Calculate FPS
                frames_processed += 1
                if now - fps_last_calc >= 2.0:
                    self._fps = frames_processed / (now - fps_last_calc)
                    frames_processed = 0
                    fps_last_calc = now
                    
        except Exception as e:
            self._state = EngineState.ERROR
            self._error_msg = str(e)
            logger.error(f"Gesture detection engine crashed: {e}")
            logger.error(traceback.format_exc())
        finally:
            if cap:
                cap.release()
