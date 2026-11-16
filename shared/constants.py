"""
AeroSync Application Constants

All application-wide constants. No magic numbers in application code —
everything is defined here or in environment variables.
"""

# --- Application ---
APP_NAME = "AeroSync"
APP_VERSION = "0.1.0"
APP_DESCRIPTION = "Workspace transfer across devices via gesture-based triggers"

# --- API ---
API_V1_PREFIX = "/api/v1"

# --- Authentication ---
BCRYPT_COST_FACTOR = 12
TOKEN_TYPE_ACCESS = "access"
TOKEN_TYPE_REFRESH = "refresh"
MIN_PASSWORD_LENGTH = 8

# --- Device Pairing ---
PAIRING_CODE_LENGTH = 6
PAIRING_CODE_EXPIRY_MINUTES = 15

# --- Constellations (Isolated Multi-Computer Rooms) ---
MAX_CONSTELLATION_DEVICES = 5  # Maximum number of computers that can be linked in one constellation
CONSTELLATION_CODE_LENGTH = 8  # Format: CST-XXXXX (e.g., CST-7K9M)

# --- Session Transfer Status ---
class TransferStatus:
    """Session transfer status state machine values."""
    PENDING = "pending"
    UPLOADED = "uploaded"
    NOTIFIED = "notified"
    ACCEPTED = "accepted"
    RECONSTRUCTING = "reconstructing"
    COMPLETE = "complete"
    FAILED = "failed"
    EXPIRED = "expired"
    CANCELLED = "cancelled"

    ALL = [
        PENDING, UPLOADED, NOTIFIED, ACCEPTED,
        RECONSTRUCTING, COMPLETE, FAILED, EXPIRED, CANCELLED,
    ]

    # States that can be expired by cleanup
    EXPIRABLE = [PENDING, UPLOADED, NOTIFIED]

# --- WebSocket ---
WS_HEARTBEAT_INTERVAL_SECONDS = 30
WS_PONG_TIMEOUT_SECONDS = 10
WS_CLOSE_CODE_AUTH_FAILED = 4001
WS_CLOSE_CODE_INVALID_DEVICE = 4003
WS_CLOSE_CODE_PONG_TIMEOUT = 4002

# --- Gesture Engine ---
GESTURE_THROW = "throw"
GESTURE_RECEIVE = "receive"
GESTURE_FIST = "fist"       # Triggers Host/A role
GESTURE_GRAB = "grab"
GESTURE_CANCEL = "cancel"
GESTURE_UNDO = "undo"

GESTURE_FPS = 15
GESTURE_THROW_COOLDOWN_MS = 2000
GESTURE_RECEIVE_HOLD_MS = 800
GESTURE_FIST_HOLD_MS = 600          # Minimum hold time before fist is confirmed
GESTURE_THROW_CONFIDENCE_THRESHOLD = 0.85
GESTURE_RECEIVE_CONFIDENCE_THRESHOLD = 0.80
GESTURE_FIST_CONFIDENCE_THRESHOLD = 0.88    # High bar: fist arms Host mode
GESTURE_FRONT_VIEW_THRESHOLD = -0.35        # Palm normal z < this = facing camera
GESTURE_FRAME_CENTER_RATIO = 0.6  # Only process hands in center 60% of frame
GESTURE_VELOCITY_BUFFER_FRAMES = 10

# --- Workspace Capture ---
CAPTURE_TIMEOUT_SECONDS = 3
CLIPBOARD_MAX_TEXT_BYTES = 50 * 1024  # 50KB
CHROME_CDP_URL_TEMPLATE = "http://127.0.0.1:{port}/json"

# --- Workspace Reconstruction ---
RECONSTRUCTION_STEP_TIMEOUT_SECONDS = 10
RECONSTRUCTION_LAUNCH_SEQUENCE = ["browser", "windows", "clipboard", "screen_actions"]

# --- Package ---
PACKAGE_VERSION = "1.0"
COMPRESSION_LEVEL = 6  # zlib compression level (0-9)
AES_KEY_SIZE_BYTES = 32  # AES-256
AES_NONCE_SIZE_BYTES = 12  # GCM nonce

# --- Platform ---
PLATFORM_WINDOWS = "windows"
SUPPORTED_PLATFORMS = [PLATFORM_WINDOWS]

# --- Screen Reader / OCR / AI ---
# Feature flag: set SCREEN_READER_ENABLED=True to enable screen capture on throw.
SCREEN_READER_ENABLED = True
# Timeout for the full screen capture + OCR + AI analysis pipeline (seconds)
SCREEN_READER_TIMEOUT_SECONDS = 30
# Timeout for executing each screen action on the receiver (seconds)
SCREEN_ACTIONS_TIMEOUT_SECONDS = 20

# --- Role State Machine (Constellation-level peer roles) ---
class RoleState:
    """Dynamic role that each PC holds at any point in a Constellation session."""
    NEUTRAL = "neutral"               # No active role; candidate for A
    HOST = "host"                     # Computer A — capturing workspace
    CANDIDATE = "candidate"           # Waiting to be claimed as B
    TARGET = "target"                 # Computer B — reconstructing workspace
    TRANSFERRING = "transferring"     # In the middle of data transfer

class WsMessageType:
    """WebSocket message types for constellation role negotiation."""
    # Role announcements (broadcast within constellation)
    HOST_ANNOUNCING = "host_announcing"       # PC claims Host A role (fist gesture)
    TARGET_CLAIMING = "target_claiming"       # PC claims Target B role (throw gesture)
    CONSTELLATION_RESET = "constellation_reset"  # All PCs return to NEUTRAL

    # Workspace data transfer
    WORKSPACE_READY = "workspace_ready"       # Host signals payload is ready
    WORKSPACE_TRANSFER = "workspace_transfer" # Actual payload delivery

    # Standard relay types
    INCOMING_TRANSFER = "incoming_transfer"
    DEVICE_ONLINE = "device_online"
    DEVICE_OFFLINE = "device_offline"
    HEARTBEAT = "heartbeat"
    PONG = "pong"
