"""
AeroSync Gesture API

Local FastAPI server that exposes the gesture detection engine.
Provides endpoints to start/stop the engine and a WebSocket
to stream gesture events to the main orchestrator.
"""

import asyncio
from typing import List

import cv2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import Response

from services.gesture_engine.detector import GestureDetector
from services.gesture_engine.gesture_types import EngineState, GestureEvent, GestureType
from shared.utils.logger import get_logger

logger = get_logger(__name__)

# Global instances
detector = GestureDetector()
app = FastAPI(title="AeroSync Gesture Engine API")

# Store connected websockets
active_connections: List[WebSocket] = []


def start_gesture_detection(callback=None, show_widget: bool = True):
    """Start local gesture detection thread with optional callback(GestureType) and corner camera widget."""
    detector.show_camera_widget = show_widget
    if callback:
        def _cb(event: GestureEvent):
            try:
                callback(event.gesture_type)
            except Exception as e:
                logger.error(f"Error invoking gesture callback: {e}")
        detector.add_callback(_cb)
    detector.start()


def stop_gesture_detection():
    """Stop local gesture detection thread."""
    detector.stop()


def _broadcast_event(event: GestureEvent):
    """Callback fired by the detector to broadcast events to WS clients."""
    if not active_connections:
        return
        
    event_dict = {
        "type": "gesture",
        "data": {
            "gesture_type": event.gesture_type.value,
            "confidence": event.confidence,
            "timestamp": event.timestamp,
            "hand": event.hand
        }
    }
    
    # Fire and forget broadcasting to all connected clients
    for ws in active_connections:
        asyncio.create_task(ws.send_json(event_dict))

# Register callback
detector.add_callback(_broadcast_event)


@app.on_event("shutdown")
def shutdown_event():
    """Ensure detector stops on shutdown."""
    detector.stop()


@app.get("/status")
def get_status():
    """Get the current status of the gesture engine."""
    status = detector.get_status()
    # Serialize dataclass
    return {
        "state": status.state.value,
        "fps": status.fps,
        "hands_detected": status.hands_detected,
        "error_message": status.error_message,
        "camera_index": status.camera_index,
        "last_gesture": {
            "gesture_type": status.last_gesture.gesture_type.value,
            "confidence": status.last_gesture.confidence,
            "timestamp": status.last_gesture.timestamp,
            "hand": status.last_gesture.hand
        } if status.last_gesture else None
    }


@app.post("/start")
def start_engine():
    """Start the gesture detection engine."""
    if detector.get_status().state == EngineState.RUNNING:
        return {"status": "already running"}
    detector.start()
    return {"status": "started"}


@app.post("/stop")
def stop_engine():
    """Stop the gesture detection engine."""
    detector.stop()
    return {"status": "stopped"}


@app.post("/calibrate/start")
def start_calibration(user_id: str = "default_user"):
    """Trigger 10-second per-user biomechanical gesture calibration."""
    detector.start_calibration(user_id=user_id)
    return {"status": "started", "user_id": user_id, "duration_s": 10.0}


@app.get("/calibrate/status")
def get_calibration_status():
    """Get active 10-second calibration progress and instructions."""
    return detector.get_calibration_status()


@app.get("/frame")
def get_frame():
    """Get the latest processed frame as a JPEG image (for debugging)."""
    with detector.frame_lock:
        frame = detector.last_frame
        
    if frame is None:
        return Response(status_code=404, content="No frame available")
        
    ret, jpeg = cv2.imencode(".jpg", frame)
    if not ret:
        return Response(status_code=500, content="Failed to encode frame")
        
    return Response(content=jpeg.tobytes(), media_type="image/jpeg")


@app.websocket("/events")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time gesture events.
    The main orchestrator connects here.
    """
    await websocket.accept()
    active_connections.append(websocket)
    logger.info(f"Client connected to gesture events. Total: {len(active_connections)}")
    
    try:
        while True:
            # We don't expect data from the client, just keep connection open
            await websocket.receive_text()
    except WebSocketDisconnect:
        active_connections.remove(websocket)
        logger.info(f"Client disconnected. Total: {len(active_connections)}")


# If run directly for testing
if __name__ == "__main__":
    import uvicorn
    # Make sure detector is running for standalone tests
    detector.start()
    uvicorn.run(app, host="127.0.0.1", port=7878)
