# AeroSync

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.11+](https://img.shields.io/badge/Python-3.11+-brightgreen.svg)](https://www.python.org/)
[![React: 18](https://img.shields.io/badge/React-18-blue.svg)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-teal.svg)](https://fastapi.tiangolo.com/)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%2010%2F11-0078D6.svg)](https://www.microsoft.com/windows)

**Instant workspace transfer across devices triggered by vision-based hand gestures.**

AeroSync captures your active workspace state (browser tabs, desktop window geometry, display configuration, and clipboard text) on one device and reconstructs it on another paired device — triggered by hand gestures detected through your webcam.

---

> [!NOTE]
> **Complete Technical Specifications & Living Agent Memory:**
> For in-depth architectural blueprints, database DDL, protocol schemas, full audit reports, and technical boundary analyses, see [knowledge.md](file:///d:/Bhvya%20Vaish%20Documents/Proffesional/Projects/AeroSync/knowledge.md).

---

## How It Works

AeroSync does **not** stream pixels, mirror video, or run high-latency remote desktop protocols (like VNC or RDP). Instead, it captures and transfers structured workspace **metadata**:

```
┌─────────────────┐       ┌────────────────────┐       ┌─────────────────┐
│    Device A     │       │    Relay Server    │       │    Device B     │
│    (Source)     │       │     (FastAPI)      │       │    (Target)     │
├─────────────────┤       ├────────────────────┤       ├─────────────────┤
│ 1. "Throw"      │       │                    │       │                 │
│    Gesture      │       │                    │       │                 │
│ 2. Capture:     │       │                    │       │                 │
│    - Chrome CDP │       │                    │       │                 │
│    - Win32 Rects│       │                    │       │                 │
│    - Clipboard  │       │                    │       │                 │
│ 3. Encrypt      │ HTTP  │                    │  WS   │                 │
│    AES-256-GCM  │──────▶│ - Session State    │──────▶│ 4. Receives     │
│ 4. Upload Blob  │       │ - Ephemeral Blob   │ Push  │    Notification │
│                 │       │ - WS Notifications │       │ 5. Download Blob│
│                 │       │                    │       │ 6. Decrypt &    │
│                 │       │                    │       │    Reconstruct: │
│                 │       │                    │       │    - Launch tabs│
│                 │       │                    │       │    - Move win32 │
│                 │       │                    │       │    - Paste clip │
└─────────────────┘       └────────────────────┘       └─────────────────┘
```

1. **Gesture Trigger & Screen Reader Crop**: The user performs a *"throw"* motion in front of Device A's webcam. A semi-transparent overlay appears allowing the user to optionally drag and crop a specific region of the screen (default is full screen if Enter or Esc is pressed).
2. **Parallel State & Visual Capture**:
   - **Screen Reader & OCR**: Captures the selected screen region via fast Win32 GDI / `mss`, extracts visible text via OCR (Windows native WinRT or pytesseract), and encodes high-res visual context for AI.
   - **AI Context & Action Planner**: Analyzes the screen via Google Gemini Vision (`gemini-1.5-flash`), planning intelligent target reconstruction actions (e.g., search queries in Chrome, creating desktop files for text/docs, or typing directly into open applications via `pyautogui`).
   - **Browser Tabs**: Queries the Chrome DevTools Protocol (`CDP`) on port 9222 to record open URLs and tab titles.
   - **Application Windows**: Uses Windows Win32 APIs (`user32.dll` and `dwmapi.dll`) to capture coordinates `(x, y, width, height)` and window titles.
   - **Monitor Layouts**: Captures display resolutions and primary screen offsets.
   - **System Clipboard**: Captures current clipboard text content (bounded by memory safeguards).
3. **Packaging & Encryption**: Serializes the snapshot and action plan into JSON, compresses it with `zlib`, and encrypts it with **AES-256-GCM**.
4. **Relay Server Transport**: Uploads the encrypted binary to the FastAPI relay server. The server dispatches a real-time WebSocket notification to Device B.
5. **Reconstruction & AI Action Execution**: Device B fetches the payload, decrypts it, reopens browser tabs, repositions matching windows, restores the clipboard, and executes the AI action plan:
   - **Documents / Text**: Generates new `.txt` files on the user's Desktop with the extracted text.
   - **Browser Queries**: Launches Chrome with the exact web search query or active URL visible on the source machine.
   - **Target Applications**: Uses `pyautogui` to focus matching application windows and type in the extracted text.

---

## Constellations (Isolated Multi-Computer Rooms)

AeroSync groups linked computers into **Constellations**:
- **Strict Capacity Cap**: Every constellation links up to a **maximum of 5 computers** (`MAX_CONSTELLATION_DEVICES = 5`).
- **Unique Join Code**: When a constellation is created, it is assigned a unique alphanumeric code formatted as `CST-XXXXX` (e.g. `CST-7K9M2`).
- **Room Isolation**: Computers within a constellation are automatically linked to each other. When a user throws their workspace, transfers are scoped directly to peer computers in that room.
- **Easy Collaboration**: Anyone on another Windows computer can link into the room simply by selecting their device and inputting the 8-character unique join code. Once the room reaches 5 computers, additional join requests are rejected.

---

## Architecture Overview

```
AeroSync/
├── apps/
│   ├── client/                  # Desktop daemon orchestrator
│   │   ├── main.py              # Client entry point
│   │   ├── client_orchestrator.py # Event loop (Camera + WS + Transfer)
│   │   ├── relay_client.py      # HTTP & WebSocket client
│   │   ├── transfer_sender.py   # Outbound transfer coordinator
│   │   ├── transfer_receiver.py # Inbound transfer coordinator
│   │   ├── storage.py           # Local state persistence (tokens, IDs)
│   │   └── notification.py      # Windows native toast notifications
│   ├── relay_server/            # FastAPI central relay server
│   │   ├── main.py              # Application entry point & lifespan
│   │   ├── core/                # DB (aiosqlite), security, WS connection pool
│   │   ├── models/              # SQLite data models & schemas
│   │   ├── routers/             # Endpoints (auth, devices, constellations, sessions, ws)
│   │   └── services/            # Business logic (constellations, session lifecycle, pairing)
│   └── frontend/                # Modern React 18 + Vite management dashboard
│       └── src/
│           ├── pages/           # Dashboard, Constellations, Devices, Sessions, Login
│           ├── components/      # GlassCard, Button, Navbar
│           └── services/        # API client, Auth, WebSocket context
├── services/
│   ├── gesture_engine/          # OpenCV + MediaPipe hand detection
│   │   ├── detector.py          # Background camera loop & thread manager
│   │   ├── hand_tracker.py      # MediaPipe 21-landmark tracking
│   │   ├── node_engine.py       # Biomechanical kinematic nodes & pivots (invisible)
│   │   ├── gesture_classifier.py# Pose, node & velocity gesture recognition
│   │   ├── gesture_state_machine.py # Debounce, confirmation & state transitions
│   │   └── camera_widget.py     # Picture-in-picture corner desktop camera widget
│   ├── workspace_capture/       # Hardware & OS state collectors
│   │   ├── capture_orchestrator.py # Concurrent capture executor
│   │   ├── browser_capture.py   # Chrome CDP tab extractor
│   │   ├── window_capture.py    # Win32 user32 window enumerator
│   │   ├── monitor_capture.py   # Display geometry enumerator
│   │   └── clipboard_capture.py # Bounded clipboard text extractor
│   ├── workspace_packager/      # Compression, serialization & encryption
│   │   └── packager.py          # zlib + AES-256-GCM pack/unpack
│   ├── workspace_reconstructor/ # Target device restoration engine
│   │   ├── reconstruction_orchestrator.py # Sequential restorer
│   │   ├── browser_restorer.py  # CDP tab launcher & CLI fallback
│   │   ├── window_restorer.py   # Win32 SetWindowPos layout restorer
│   │   └── clipboard_restorer.py# Pyperclip clipboard injector
│   ├── screen_reader/           # Screen preview overlay & OCR
│   │   ├── screen_capturer.py   # Fast GDI / mss screen capture
│   │   ├── region_selector.py   # Tkinter interactive crop overlay
│   │   ├── ocr_engine.py        # WinRT / pytesseract dual OCR
│   │   └── screen_reader_orchestrator.py # Screen capture & read coordinator
│   ├── ai_analyzer/             # Vision & LLM action planner
│   │   ├── content_analyzer.py  # Gemini 1.5 Flash vision analysis & heuristics
│   │   └── action_planner.py    # Target action synthesis
│   └── action_executor/         # Target computer reconstruction executor
│       ├── text_creator.py      # Desktop .txt file creator
│       ├── browser_controller.py# Chrome search & URL navigator
│       ├── input_automator.py   # Win32 focus & pyautogui typing
│       └── execution_orchestrator.py # Sequential action plan runner
├── shared/                      # Constants, dataclasses, cryptography & logging
└── config/                      # Pydantic settings & environment templates
```

---

## Prerequisites

- **Operating System**: Windows 10 or Windows 11 (64-bit)
- **Python**: Version 3.11 or higher
- **Node.js**: Version 18.0.0 or higher with `npm`
- **Hardware**: Working webcam (for gesture capture)
- **Web Browser**: Google Chrome or Microsoft Edge (run with `--remote-debugging-port=9222` for CDP tab capture)

---

## Quick Start & Setup Guide

### 1. Repository Setup & Virtual Environment

```powershell
# Clone the repository
git clone <repo-url>
cd AeroSync

# Create and activate virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Copy environment variables
copy config\.env.example .env
```

### 2. Start the Relay Server

From the project root:
```powershell
.\venv\Scripts\python -m uvicorn apps.relay_server.main:app --host 0.0.0.0 --port 8000 --reload
```
The server will initialize `aerosync.db` SQLite storage automatically.
Interactive API documentation will be available at `http://localhost:8000/docs`.

### 3. Start the Web Dashboard

Open a new terminal:
```powershell
cd apps/frontend
npm install
npm run dev
```
Navigate to `http://localhost:5173`. Register an account, log in, and register your primary device.

### 4. Pair Devices

1. In the Web UI, go to **Devices**.
2. Click **Pair Device** on Device A to generate a 6-digit PIN code (valid for 15 minutes).
3. On Device B, log in to the same account and enter the pairing code to establish a trusted bidirectional link.

### 5. Launch the Desktop Client Daemon

On each computer:
```powershell
# Optional: Launch Chrome with debugging port enabled for full tab synchronization
start chrome --remote-debugging-port=9222

# Start the AeroSync daemon
.\venv\Scripts\python -m apps.client.main --server http://127.0.0.1:8000
```
A native Windows toast notification will confirm that the client daemon and camera gesture tracker are active.

---

## REST & WebSocket API Reference

### Authentication (`/api/v1/auth`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Register a new user account |
| `POST` | `/api/v1/auth/login` | Authenticate and obtain JWT access & refresh tokens |
| `POST` | `/api/v1/auth/refresh` | Rotate access token using a valid refresh token |
| `POST` | `/api/v1/auth/logout` | Revoke active refresh token |
| `GET` | `/api/v1/auth/me` | Fetch authenticated user profile |

### Device Management & Pairing (`/api/v1/devices`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/devices/register` | Register or update device hardware fingerprint |
| `GET` | `/api/v1/devices/` | List all registered and paired devices |
| `POST` | `/api/v1/devices/pair/initiate` | Generate a 15-minute 6-digit pairing PIN |
| `POST` | `/api/v1/devices/pair/complete` | Validate PIN and pair two devices |
| `DELETE` | `/api/v1/devices/{device_id}` | Remove device and revoke pairings |

### Session Transfer Lifecycle (`/api/v1/sessions`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/sessions/initiate` | Request transfer session between paired devices |
| `POST` | `/api/v1/sessions/{id}/upload` | Upload raw encrypted AES-GCM binary payload |
| `POST` | `/api/v1/sessions/{id}/uploaded`| Finalize upload and notify target device |
| `POST` | `/api/v1/sessions/{id}/accept` | Accept incoming transfer and retrieve key |
| `GET` | `/api/v1/sessions/{id}/download` | Download encrypted workspace package blob |
| `POST` | `/api/v1/sessions/{id}/complete`| Mark transfer complete or report failure |
| `DELETE`| `/api/v1/sessions/{id}` | Cancel pending transfer session |
| `GET` | `/api/v1/sessions/history` | Paginated transfer audit logs |

### WebSocket Real-Time Signaling
| Protocol | URI | Description |
|---|---|---|
| `WSS` | `/ws/{device_id}?token=<jwt>` | Real-time presence, heartbeat, and transfer notification push |

---

## Technical Security Details

- **Cryptographic Scheme**: Payloads are encrypted locally on the sender using **AES-256-GCM** with a cryptographically secure random 256-bit key (`os.urandom(32)`) and unique 12-byte initialization vector (nonce).
- **Integrity**: SHA-256 checksums verify payload validity upon decompression.
- **Identity & Auth**: Passwords hashed using `bcrypt` (work factor 12). API authorization handled via signed JWT tokens (HMAC-SHA256).

---

## Known Boundaries & Engineering Constraints

For detailed technical analysis of OS boundaries and hardware limits, review [knowledge.md](file:///d:/Bhvya%20Vaish%20Documents/Proffesional/Projects/AeroSync/knowledge.md#7-fundamental-technical-impossibilities--constraints):
1. **Third-Party Application State**: Win32 APIs can reposition windows (`SetWindowPos`), but cannot serialize internal application memory, undo buffers, or unsaved files without per-app integration.
2. **Chrome Tab Discovery**: Requires launching Chrome with `--remote-debugging-port=9222`. Ordinary Chrome instances block external tab inspection by default.
3. **Cross-DPI / Resolution Scaling**: Transferring raw pixel rectangles between different resolution monitors requires normalized relative coordinate transformations.
4. **Spatial Targeting**: Monocular webcams recognize gestures but cannot determine the physical direction of other computers in a room without external spatial tracking (e.g., UWB).

---

## Running Automated Tests

```powershell
# Run the FastAPI test suite
.\venv\Scripts\python -m pytest apps/relay_server/tests/ -v

# Run with full coverage analysis
.\venv\Scripts\python -m pytest --cov=apps --cov=services --cov=shared

# Execute end-to-end pipeline smoke test
.\venv\Scripts\python scripts/test_system.py
```

---

## License

Distributed under the MIT License. See `LICENSE` for details.
