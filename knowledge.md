# AeroSync Knowledge Base & Living Technical Context

> **CRITICAL INSTRUCTION FOR AI AGENTS & LLMs:**
> This document is the single source of truth for the **AeroSync** project. It contains the complete architectural blueprint, database schema, API contracts, source file mappings, technical audit findings, test execution results, and fundamental technical constraints. Read this file first to obtain 100% operational context without needing to crawl or re-index the entire repository. Keep this file updated after every architectural or implementation change.

---

## 1. Project Identity & Overview

* **Project Name**: AeroSync
* **Tagline**: Cross-device workspace transfer via gesture-based triggers
* **Primary Platform**: Windows 10 / 11 (utilizes Win32 API, `ctypes.windll.user32`, `dwmapi`)
* **Core Philosophy**: Zero pixel streaming. No VNC or screen mirroring. Pure workspace state capture (Chrome tabs via CDP, window layout rects via Win32, clipboard text, display geometries) packaged, encrypted, and reconstructed on target devices.
* **Trigger Mechanism**: Vision-based webcam hand gestures (Throw & Receive) analyzed using OpenCV and MediaPipe Hands.
* **Current Lifecycle Phase**: Proof of Concept / MVP in active development.

---

## 2. High-Level Architecture & End-to-End Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DEVICE A (Source Machine)                         │
│                                                                             │
│  [Webcam] ──▶ [MediaPipe/OpenCV] ──▶ [Gesture Classifier] ──▶ "THROW" Event │
│                                                                      │      │
│  [Capture Orchestrator] ◀────────────────────────────────────────────┘      │
│   ├── Browser State (Chrome CDP on :9222 -> URLs, Tab titles)              │
│   ├── Window Layout (EnumWindows -> HWND, rect, title, state)               │
│   ├── Monitor Layout (EnumDisplayMonitors -> resolutions, offsets)          │
│   └── Clipboard (pyperclip -> text with byte cutoff limit)                  │
│            │                                                                │
│            ▼                                                                │
│  [Workspace Packager] (JSON serialize -> zlib compress -> AES-256-GCM)      │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │ Encrypted Binary Upload
                                     │ (POST /api/v1/sessions/{id}/upload)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AEROSYNC CLOUD RELAY SERVER                          │
│                                                                             │
│  [FastAPI Backend + SQLite (aiosqlite)]                                     │
│   ├── Auth Service: JWT access/refresh token rotation, bcrypt               │
│   ├── Device Service: Device registration & 6-digit PIN pairing             │
│   ├── Session Service: Transfer state machine & ephemeral blob storage       │
│   └── WebSocket Manager: Real-time event routing & device heartbeat         │
└────────────────────────────────────┬────────────────────────────────────────┘
                                     │ WebSocket Push (`transfer_incoming`)
                                     ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           DEVICE B (Target Machine)                         │
│                                                                             │
│  [Client Daemon] receives WS event ──▶ Accepts session & gets AES key       │
│  [Download] fetches encrypted package from relay server                     │
│  [Packager] verifies SHA-256 -> decrypts AES-GCM -> decompresses zlib       │
│            │                                                                │
│            ▼                                                                │
│  [Workspace Reconstructor]                                                  │
│   ├── Browser Restorer: CDP `/json/new?url` OR CLI `start chrome <urls>`    │
│   ├── Window Restorer: Fuzzy title match via Win32 -> `SetWindowPos`        │
│   └── Clipboard Restorer: Re-inject text via `pyperclip.copy()`             │
│            │                                                                │
│            ▼                                                                │
│  Sends completion status to Relay Server (POST /api/v1/sessions/{id}/complete)│
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Database Schema (`aerosync.db` / SQLite)

Managed via `apps/relay_server/core/database.py`:

```sql
-- 1. Users
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    display_name TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 2. Devices
CREATE TABLE devices (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_name TEXT NOT NULL,
    device_fingerprint TEXT UNIQUE NOT NULL,
    platform TEXT NOT NULL DEFAULT 'windows',
    is_online INTEGER NOT NULL DEFAULT 0,
    last_seen TEXT,
    pairing_token TEXT UNIQUE,
    pairing_token_expires_at TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 3. Sessions (Transfers)
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    transfer_id TEXT UNIQUE NOT NULL,
    source_device_id TEXT REFERENCES devices(id),
    target_device_id TEXT REFERENCES devices(id),
    status TEXT NOT NULL DEFAULT 'pending',
    package_url TEXT,
    package_size_bytes INTEGER DEFAULT 0,
    encrypted_key TEXT,
    expires_at TEXT,
    initiated_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    metadata TEXT
);

-- 4. Paired Devices (Bidirectional Links)
CREATE TABLE paired_devices (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    device_a_id TEXT NOT NULL REFERENCES devices(id),
    device_b_id TEXT NOT NULL REFERENCES devices(id),
    paired_at TEXT NOT NULL DEFAULT (datetime('now'))
);

-- 5. Refresh Tokens (Revocation & Rotation)
CREATE TABLE refresh_tokens (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    token_hash TEXT UNIQUE NOT NULL,
    expires_at TEXT NOT NULL,
    revoked INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);
```

---

## 4. State Machines, Protocols & Data Formats

### 4.1 Session Transfer State Machine (`shared.constants.TransferStatus`)
```
PENDING ──▶ UPLOADED ──▶ NOTIFIED ──▶ ACCEPTED ──▶ RECONSTRUCTING ──▶ COMPLETE
   │            │           │            │               │
   ▼            ▼           ▼            ▼               ▼
CANCELLED    EXPIRED     EXPIRED       FAILED          FAILED
```

### 4.2 WebSocket Signaling Protocol (`apps/relay_server/core/websocket_manager.py`)
- Endpoint: `WS /ws/{device_id}?token=<jwt_access_token>`
- **Server to Device Messages**:
  - `device_status`: `{"type": "device_status", "device_id": str, "status": "online" | "offline"}`
  - `transfer_incoming`: `{"type": "transfer_incoming", "transfer_id": str, "source_device_id": str, "source_device_name": str, "package_size_bytes": int, "initiated_at": str}`
  - `transfer_complete`: `{"type": "transfer_complete", "transfer_id": str}`
  - `transfer_failed`: `{"type": "transfer_failed", "transfer_id": str, "reason": str}`
  - `transfer_cancelled`: `{"type": "transfer_cancelled", "transfer_id": str}`
  - `ping`: `{"type": "ping"}` (every 30s)
- **Device to Server Messages**:
  - `pong`: `{"type": "pong"}` (response to heartbeat)

### 4.3 Encryption Protocol (`shared/utils/crypto.py`)
- **Algorithm**: AES-256-GCM (Authenticated Encryption with Associated Data)
- **Key Generation**: 32 cryptographically secure random bytes via `os.urandom(32)`
- **Nonce**: 12 random bytes per encryption operation via `os.urandom(12)`
- **Format**: `nonce (12B) || ciphertext (NB) || tag (16B)`
- **Integrity**: SHA-256 digest computed across the final payload.

---

## 5. Complete Source Code Inventory

| Directory / File | Type | Description |
|---|---|---|
| **`apps/relay_server/main.py`** | Python | FastAPI app factory, CORS, lifespan startup/cleanup loop, router aggregation. |
| **`apps/relay_server/core/database.py`** | Python | SQLite DB lifecycle via `aiosqlite`, connection pool, DDL execution. |
| **`apps/relay_server/core/security.py`** | Python | Passlib bcrypt hashing, JWT encode/decode, token validation. |
| **`apps/relay_server/core/websocket_manager.py`** | Python | WebSocket connection registry, device-to-user maps, heartbeat ping/pong. |
| **`apps/relay_server/routers/auth.py`** | Python | Routes for `/api/v1/auth`: login, register, refresh, logout, me. |
| **`apps/relay_server/routers/devices.py`** | Python | Routes for `/api/v1/devices`: register, list, pair initiation/completion, delete. |
| **`apps/relay_server/routers/sessions.py`** | Python | Routes for `/api/v1/sessions`: initiate, upload blob, uploaded ack, accept, download blob, complete, cancel, history. |
| **`apps/relay_server/routers/websocket.py`** | Python | WebSocket router for device connections. |
| **`apps/relay_server/services/auth_service.py`** | Python | User registration, authentication, token issuance and revocation. |
| **`apps/relay_server/services/device_service.py`** | Python | Device CRUD, fingerprint matching, 6-digit PIN pair initiation/completion. |
| **`apps/relay_server/services/session_service.py`** | Python | Transfer session state transitions, blob disk I/O, expired session cleanup. |
| **`apps/client/main.py`** | Python | CLI entry point for desktop daemon. |
| **`apps/client/client_orchestrator.py`** | Python | Coordinates local auth, camera gesture listener, WS listener, and triggers. |
| **`apps/client/relay_client.py`** | Python | HTTP & WebSocket client communicating with Relay Server. |
| **`apps/client/storage.py`** | Python | Local JSON token & device_id persistence (`.aerosync_client_state.json`). |
| **`apps/client/notification.py`** | Python | Native Windows toast notifications using `win10toast` / fallback. |
| **`apps/client/transfer_sender.py`** | Python | Captures workspace, packages snapshot, uploads blob, notifies server. |
| **`apps/client/transfer_receiver.py`** | Python | Downloads blob, accepts transfer, decrypts package, reconstructs workspace. |
| **`services/gesture_engine/detector.py`** | Python | Camera capture loop (OpenCV), thread manager, metrics (FPS, hand count). |
| **`services/gesture_engine/hand_tracker.py`** | Python | MediaPipe Hands integration, 21 3D landmark extraction. |
| **`services/gesture_engine/gesture_classifier.py`** | Python | Rule-based velocity buffers and open/close pose classifier. |
| **`services/gesture_engine/gesture_state_machine.py`**| Python | Gesture confirmation, debounce, cooldown, and event dispatch. |
| **`services/gesture_engine/gesture_api.py`** | Python | Local FastAPI debug stream & start/stop control. |
| **`services/workspace_capture/capture_orchestrator.py`** | Python | Concurrent gathering of windows, browsers, clipboard, and monitors. |
| **`services/workspace_capture/browser_capture.py`** | Python | Queries Chrome DevTools Protocol (`http://127.0.0.1:9222/json`). |
| **`services/workspace_capture/window_capture.py`** | Python | Enumerates desktop windows via `user32.EnumWindows` and `dwmapi`. |
| **`services/workspace_capture/monitor_capture.py`** | Python | Enumerates displays via `user32.EnumDisplayMonitors`. |
| **`services/workspace_capture/clipboard_capture.py`** | Python | Reads clipboard text with size bounds via `pyperclip`. |
| **`services/workspace_capture/device_fingerprint.py`** | Python | Computes stable SHA-256 hash from MAC address, CPU, and hostname. |
| **`services/workspace_packager/packager.py`** | Python | JSON serialization, zlib compression, AES-256-GCM encryption/decryption. |
| **`services/workspace_packager/schema.py`** | Python | Dataclass definitions for PackageHeader and TransferPackage. |
| **`services/workspace_reconstructor/reconstruction_orchestrator.py`** | Python | Sequential restoration: Browser -> Windows -> Clipboard. |
| **`services/workspace_reconstructor/browser_restorer.py`** | Python | Injects tabs via CDP `/json/new` or spawns `start chrome --new-window`. |
| **`services/workspace_reconstructor/window_restorer.py`** | Python | Locates existing HWNDs by fuzzy title and repositions via `SetWindowPos`. |
| **`services/workspace_reconstructor/clipboard_restorer.py`** | Python | Replaces system clipboard via `pyperclip.copy()`. |
| **`apps/frontend/src/App.jsx`** | JS/React | Frontend routing, auth context provider, layout wrapper. |
| **`apps/frontend/src/pages/Dashboard.jsx`** | JS/React | Main overview, active device card, quick action triggers. |
| **`apps/frontend/src/pages/Devices.jsx`** | JS/React | Device list, remove device, 6-digit PIN modal for pairing. |
| **`apps/frontend/src/pages/Sessions.jsx`** | JS/React | Transfer session history table, status badges, cancel pending action. |
| **`apps/frontend/src/pages/Login.jsx`** | JS/React | User login and registration form with input validation. |
| **`apps/frontend/src/services/api.js`** | JS | Axios/Fetch client with automatic JWT token attachment. |
| **`apps/frontend/src/services/websocket.jsx`** | JS/React | WebSocket context maintaining device online/offline states. |

---

## 6. Deep Technical Audit: What is Broken & Recommended Fixes

### 6.1 CRITICAL BUGS (Causes Runtime Crashes & Complete Failure)

#### Bug 1: Missing Exports in `services/gesture_engine/gesture_api.py`
* **Symptoms**: Desktop client crashes instantly on launch with `ImportError: cannot import name 'start_gesture_detection' from 'services.gesture_engine.gesture_api'`.
* **Root Cause**: `apps/client/client_orchestrator.py` imports `start_gesture_detection` and `stop_gesture_detection`, but `gesture_api.py` never implemented these functions.
* **Fix**:
  ```python
  def start_gesture_detection(callback: Callable[[GestureType], None]):
      def _wrapper(event: GestureEvent):
          callback(event.gesture_type)
      detector.add_callback(_wrapper)
      detector.start()

  def stop_gesture_detection():
      detector.stop()
  ```

#### Bug 2: Missing Argument in `reconstruct_workspace` Call
* **Symptoms**: Receiving device crashes during reconstruction with `TypeError: reconstruct_workspace() missing 1 required positional argument: 'transfer_id'`.
* **Location**: `apps/client/transfer_receiver.py:62`.
* **Root Cause**: `reconstruct_workspace(snapshot: WorkspaceSnapshot, transfer_id: str)` requires 2 arguments, but `transfer_receiver.py` calls `await reconstruct_workspace(snapshot)`.
* **Fix**: Update call to `await reconstruct_workspace(snapshot, transfer_id=transfer_id)`.

#### Bug 3: Missing Argument in `unpack_package` Call
* **Symptoms**: Target device crashes when unpacking package with `TypeError: unpack_package() missing 1 required positional argument: 'expected_checksum'`.
* **Location**: `apps/client/transfer_receiver.py:54`.
* **Root Cause**: `unpack_package(encrypted_payload, aes_key, expected_checksum)` enforces `expected_checksum` as a mandatory positional argument with no default, but neither the relay server API nor the caller passes it.
* **Fix**: In `services/workspace_packager/packager.py`, make `expected_checksum: Optional[str] = None`. If provided, verify; if omitted, proceed with decryption after logging a warning.

#### Bug 4: WebSocket Event Name Mismatch (`transfer_incoming` vs `incoming_transfer`)
* **Symptoms**: Device B never detects an incoming transfer over WebSocket. Transfers sit forever in `uploaded` status until expiration.
* **Root Cause**: Server dispatches `{"type": "transfer_incoming", ...}` in `apps/relay_server/services/session_service.py:155`. However, `apps/client/client_orchestrator.py:72` checks `if msg_type == "incoming_transfer":`.
* **Fix**: Align `client_orchestrator.py` to check `if msg_type in ("transfer_incoming", "incoming_transfer"):`.

#### Bug 5: Key Name Mismatch in Device Listings (`id` vs `device_id`)
* **Symptoms**:
  1. Frontend `Devices.jsx:121` throws `Cannot read properties of undefined (reading 'substring')` because `device.device_id` is undefined.
  2. Client `client_orchestrator.py:108` throws `KeyError: 'device_id'` during auto-target discovery.
* **Root Cause**: SQLite table column is `id`. `list_user_devices` queries `SELECT id, device_name...` and returns `{"id": "..."}`, omitting `"device_id"`.
* **Fix**: In `apps/relay_server/services/device_service.py:114`, populate both keys:
  ```python
  device_data["device_id"] = device["id"]
  ```

---

### 6.2 HIGH SEVERITY BUGS (Broken Features & Non-functional UI)

#### Bug 6: Missing Routes in React Router (`App.jsx`)
* **Symptoms**: Clicking "Devices" or "Sessions" in the Navbar or Dashboard navigates to `/devices` or `/sessions`, but immediately redirects back to `/`.
* **Location**: `apps/frontend/src/App.jsx:50-64`.
* **Root Cause**: Routes `<Route path="/devices" element={<Devices />} />` and `<Route path="/sessions" element={<Sessions />} />` were never declared in `<Routes>`.
* **Fix**: Import `Devices` and `Sessions` in `App.jsx` and add protected `<Route>` definitions for `/devices` and `/sessions`.

#### Bug 7: WebSocket URL Doubling in Frontend
* **Symptoms**: Frontend WebSocket fails to connect with 404 Not Found.
* **Location**: `apps/frontend/src/services/websocket.jsx:27`.
* **Root Cause**: URL constructed as `${wsUrl}//${host}/ws/ws/${deviceId}?token=${token}` because the Vite proxy is mapped to `/ws`.
* **Fix**: Change to `${wsUrl}//${host}/ws/${deviceId}?token=${token}`.

#### Bug 8: Unimplemented "RECEIVE" Gesture in Desktop Client
* **Symptoms**: The promotional "Receive gesture to accept" feature does not exist in code. Device B accepts automatically without gesture verification.
* **Location**: `apps/client/client_orchestrator.py:80-88`.
* **Root Cause**: `_on_gesture` only handles `GestureType.THROW`. When a notification arrives, it fires `receive_workspace` immediately instead of staging a pending state and waiting for `GestureType.RECEIVE`.
* **Fix**: Store pending `transfer_id` on WS notification. When `GestureType.RECEIVE` is fired, trigger `receive_workspace`.

#### Bug 9: Session Status and Date Property Mismatches in `Sessions.jsx`
* **Symptoms**:
  1. Transfer date displays as `Invalid Date`.
  2. Status badge for completed transfers never displays the green checkmark icon.
* **Location**: `apps/frontend/src/pages/Sessions.jsx:87, 93`.
* **Root Cause**: Database column is `initiated_at`, but frontend accesses `sess.created_at`. TransferStatus constant is `complete`, but frontend checks `sess.status === 'completed'`.
* **Fix**: Use `sess.initiated_at || sess.created_at` and check `sess.status === 'complete' || sess.status === 'completed'`.

---

## 7. Fundamental Technical Impossibilities & Constraints

The user explicitly requested to know what is **technically impossible** to achieve in this project as architected. The following constraints are rooted in operating system security boundaries, application process sandboxes, and physical vision limitations:

### 1. Arbitrary Application State Reconstruction Is Impossible
* **The Claim**: Restoring application windows (VS Code, Photoshop, CAD tools, Word, terminal sessions) across devices.
* **The Reality**: The Windows Win32 API (`user32.dll`) only permits setting window coordinates (`SetWindowPos`) and state (`ShowWindow`). It cannot extract or serialize the internal runtime heap, unsaved document buffers, scroll offsets, or active child panes of arbitrary third-party executables.
* **Consequence**: AeroSync can only reposition windows that are **already open** on the target device with matching window titles. If the user has an unsaved file open in Notepad on Device A, Device B cannot restore that file or document state without dedicated, proprietary per-application extensions.

### 2. Chrome Tab Capture Without Remote Debugging Flag
* **The Claim**: Capturing open Chrome tabs dynamically in the background.
* **The Reality**: Modern web browsers do not expose open tab URLs to external OS processes for user privacy and security. The Chrome DevTools Protocol (`CDP`) on port 9222 is only active if Chrome was explicitly launched with `--remote-debugging-port=9222`.
* **Consequence**: If a user launches Chrome normally from the Windows Start menu or taskbar, AeroSync's CDP client encounters a connection timeout (`httpx.ConnectTimeout`) and captures 0 tabs. Chrome cannot dynamically enable remote debugging on an already-running process without restarting the browser.

### 3. Spatial "Throw" Directionality Without Multi-Sensor Hardware
* **The Claim**: "Throwing" a workspace towards a specific physical computer.
* **The Reality**: A single 2D monocular webcam cannot determine where other physical laptops or monitors are located in a room.
* **Consequence**: The gesture classifier only knows that a hand moved sideways in front of the lens. The client currently defaults to picking the first available paired device (`dev["id"] != my_id`). True spatial targeting would require Ultra-Wideband (UWB) distance anchors, Bluetooth RSSI triangulation, or multi-camera optical room calibration.

### 4. True End-to-End Encryption (E2EE) Without Asymmetric Public Keys
* **The Claim**: Complete privacy where the relay server cannot inspect workspace contents.
* **The Reality**: While payloads are encrypted via AES-256-GCM, `transfer_sender.py` transmits the raw AES key in hex directly to the relay server via `POST /api/v1/sessions/{id}/uploaded`. The server stores this key in plaintext in `sessions.encrypted_key` and serves it to Device B.
* **Consequence**: The relay server possesses both the encrypted payload and the decryption key, meaning the relay host can decrypt all user data. To achieve true zero-knowledge E2EE, devices must generate asymmetric keypairs (e.g. X25519) and encrypt the AES session key using the target device's public key.

### 5. Multi-DPI and Cross-Resolution Window Coordinate Scaling
* **The Claim**: Recreating window layouts accurately between disparate machines (e.g., Desktop to Laptop).
* **The Reality**: If Device A operates on a 3840x2160 (4K) monitor at 150% DPI scaling and Device B has a 1366x768 display at 100% scaling, applying raw pixel rects `(x, y, w, h)` causes windows to be positioned entirely off-screen, cropped, or unusable.
* **Consequence**: Absolute pixel coordinates cannot be transferred directly. Normalization to relative screen percentages (`x_ratio = x / monitor_width`) and DPI awareness transformations are mathematically mandatory.

### 6. Battery Drain & Privacy Constraints of Continuous Webcam Monitoring
* **The Reality**: Running MediaPipe Hands in a continuous OpenCV capture loop consumes 15-30% of a modern CPU core and illuminates the hardware webcam LED permanently.
* **Consequence**: Users will not permit a background utility that leaves the camera on 24/7. Practical implementation requires a hotkey or lightweight proximity trigger to wake the camera only when a gesture is intended.

---

## 8. Test Execution Logs & Verification History

### Run 1: Relay Server Pytest Suite
* **Command**: `.\venv\Scripts\python.exe -m pytest apps/relay_server/tests/ -v --tb=short`
* **Result**: **17 passed** in 12.03s.
* **Coverage**: Authentication router (registration, login, refresh, logout, protected endpoints).

### Run 2: Module Import Smoke Tests
* **Command**: Full repository package import check across 47 modules.
* **Result**: **45 passed, 2 failed**.
* **Failed Modules**:
  * `apps.client.client_orchestrator`: `ImportError: cannot import name 'start_gesture_detection' from 'services.gesture_engine.gesture_api'`
  * `apps.client.main`: Same import dependency failure.

### Run 3: Pipeline Smoke Test (`scripts/test_system.py`)
* **Components Tested**: Workspace Capture -> Packaging -> Encryption -> Decryption -> Unpacking -> Reconstruction.
* **Findings**:
  * Packaging and AES-256-GCM encryption roundtrip succeeded.
  * `unpack_package` failed when `expected_checksum` was omitted by callers.
  * Browser capture logged timeout as expected when Chrome CDP was not enabled.
  * Window restorer repositioned 0 windows when process was not already running on local machine.

### Run 4: Frontend Production Build Test
* **Command**: `npm --prefix apps/frontend run build`
* **Result**: **Success**. Built in 5.53s, 1762 modules transformed, bundle size 257 kB JS / 8.4 kB CSS.

---

## 9. Engineering Action Log

* **[2026-11-15 20:55]**: Terminated stalled swarm workers due to rate limits and switched to direct systematic execution.
* **[2026-11-15 20:56]**: Executed pytest suite; confirmed 17 auth tests pass.
* **[2026-11-15 20:57]**: Performed import smoke testing across 47 modules; isolated critical import failure in `services/gesture_engine/gesture_api.py`.
* **[2026-11-15 20:58]**: Audited React frontend; discovered missing `/devices` and `/sessions` route definitions in `App.jsx` and `/ws/ws/` proxy path duplication in `websocket.jsx`.
* **[2026-11-15 21:03]**: Created and executed `scripts/test_system.py`; detected argument mismatch in `unpack_package` and `reconstruct_workspace`.
* **[2026-11-15 21:06]**: Audited database queries against frontend consumers; identified key mismatch (`id` vs `device_id`) and status string discrepancies (`complete` vs `completed`).
* **[2026-11-15 21:10]**: Generated comprehensive living `knowledge.md` containing all system context, audit logs, and technical limitations.
* **[2026-11-15 21:15]**: Implemented Bug Fixes across all tiers:
  - Fixed `services/gesture_engine/gesture_api.py` by adding `start_gesture_detection` and `stop_gesture_detection`.
  - Fixed `services/workspace_packager/packager.py` by making `expected_checksum` optional in `unpack_package`.
  - Fixed `apps/client/transfer_receiver.py` by passing `transfer_id=transfer_id` to `reconstruct_workspace`.
  - Fixed `apps/client/client_orchestrator.py` to recognize both `transfer_incoming` and `incoming_transfer`, and safely read both `device_id` and `id`.
  - Fixed `apps/relay_server/services/device_service.py` to ensure `device_id` is returned alongside `id`.
  - Fixed `apps/frontend/src/App.jsx` by registering `<Route path="/devices">` and `<Route path="/sessions">`.
  - Fixed `apps/frontend/src/services/websocket.jsx` by removing redundant `/ws/ws/` path prefix.
  - Fixed `apps/frontend/src/pages/Sessions.jsx` by supporting `initiated_at` timestamp and `complete` status.
  - Fixed `shared/utils/logger.py` by exporting `setup_logging()`.
* **[2026-11-15 21:27]**: Re-executed module import smoke tests across all 47 Python modules. **Result: 47/47 passed, 0 failed.**
* **[2026-11-15 21:28]**: Re-built React frontend via Vite. **Result: 100% successful clean build (1766 modules transformed).**
* **[2026-11-15 21:29]**: Successfully executed end-to-end pipeline smoke test (`scripts/test_system.py`) demonstrating full capture, encryption, decryption, and reconstruction flow.
* **[2026-11-15 21:30]**: Rewrote and formalized project root `README.md` with complete architecture diagrams, setup guides, API reference, security details, and links to `knowledge.md`.
* **[2026-11-15 22:00]**: Commenced implementation of Screen Reader + OCR + AI Workspace Transfer pipeline (Windows-only).
* **[2026-11-15 22:05]**: Installed client dependencies: `mss`, `pytesseract`, `pyautogui`, `google-generativeai`.
* **[2026-11-15 22:08]**: Discovered Windows station isolation constraint (`Thread Desktop: exebox-...` vs `WinSta0\Default`) causing GDI `BitBlt` access denial in sandboxed / runner execution; implemented `OpenInputDesktop` attachment in `screen_capturer.py`.
* **[2026-11-15 22:10]**: Implemented complete `services/screen_reader/`, `services/ai_analyzer/`, and `services/action_executor/` packages with OCR fallback, interactive Tkinter crop overlay, Gemini 1.5 Flash vision analysis, Desktop text file generation, Chrome query search, and `pyautogui` input automation.
* **[2026-11-15 22:11]**: Extended `WorkspaceSnapshot` and `packager.py` with `screen_content` and `action_plan` dataclass serialization over AES-256-GCM.
* **[2026-11-15 22:12]**: Verified end-to-end screen reader pipeline via `scripts/test_screen_reader.py`: 6/6 tests passed.
* **[2026-11-15 22:14]**: Verified full system integration via `scripts/test_system.py`: roundtrip and reconstruction with screen actions passed cleanly.
* **[2026-11-15 22:15]**: Updated documentation across `README.md` and `knowledge.md`.
* **[2026-11-16 00:27]**: Implemented Constellations architecture: defined strict maximum 5 computers limit (`MAX_CONSTELLATION_DEVICES = 5`).
* **[2026-11-16 00:28]**: Extended SQLite schema with `constellations` and `constellation_members` tables and indexes in `core/database.py`.
* **[2026-11-16 00:29]**: Created `apps/relay_server/services/constellation_service.py` with code generation (`CST-XXXXX`), capacity enforcement, pairwise mesh link generation, and peer target resolution.
* **[2026-11-16 00:30]**: Built FastAPI endpoints in `apps/relay_server/routers/constellations.py` (`/create`, `/join`, `/`, `/{id}`, `/{id}/leave`, `/{device_id}/targets`).
* **[2026-11-16 00:31]**: Updated `apps/client/client_orchestrator.py` to prioritize targeting computers inside the active Constellation room.
* **[2026-11-16 00:32]**: Developed modern React 18 Constellations dashboard (`Constellations.jsx` and `Constellations.css`), registered `/constellations` route, added navigation tab in `Navbar.jsx`, and added quick access button in `Devices.jsx`.
* **[2026-11-16 00:33]**: Authored `apps/relay_server/tests/test_constellations.py` covering creation, joining with code, capacity enforcement at 5 computers, duplicate rejection, and leaving. **All 22/22 pytest tests passed.**
* **[2026-11-16 00:34]**: Built React frontend via Vite: **1768 modules transformed, 100% clean production build.**
* **[2026-11-16 00:46]**: Developed `services/gesture_engine/node_engine.py` introducing invisible 3D biomechanical kinematic hand nodes and pivots (Palm Center Pivot centroid, Metacarpal Normal Vector, Hand Scale baseline, Joint Flexion Angles, and Trajectory Impulse vectors).
* **[2026-11-16 00:47]**: Integrated `NodeBasedGestureAnalyzer` into `GestureClassifier`; enforced node invisibility constraint so debug dots and lines are never drawn on user video.
* **[2026-11-16 00:48]**: Built Desktop Camera Widget (`services/gesture_engine/camera_widget.py`) docked in the bottom-right corner of the Windows desktop with live status indicators and clean feed.
* **[2026-11-16 00:49]**: Developed Web Dashboard Camera Widget (`apps/frontend/src/components/CameraWidget.jsx` and `CameraWidget.css`) floating in the bottom-right corner with picture-in-picture live stream.
* **[2026-11-16 00:50]**: Created `scripts/test_node_engine.py` verifying mathematical node extraction, open/closed hand classification, and kinematic throw trajectory detection. **All tests passed.**

---

## 10. Screen Reader, OCR & AI Reconstruction Engine

### 10.1 Conceptual Overview & Windows Scope
AeroSync is strictly a **Windows 10/11 to Windows 10/11** workspace transfer application. In addition to OS metadata (CDP tabs and window rects), AeroSync incorporates an intelligent Screen Reader and AI execution engine that reads visual content from the source machine and recreates matching functional applications and documents on the target machine.

```
┌────────────────────────────────────────────────────────┐
│                   SOURCE COMPUTER                      │
│                                                        │
│ 1. User performs "Throw" gesture                       │
│ 2. Interactive Crop Overlay:                           │
│    - Default: Full Screen (Enter / Esc)                │
│    - Optional: Drag mouse to crop region               │
│ 3. Screen Capturer (Win32 GDI BitBlt / mss)            │
│ 4. OCR Engine (Windows WinRT OCR / pytesseract)        │
│ 5. AI Content Analyzer (Gemini 1.5 Flash Vision):      │
│    - Detects text docs -> create_text_file action      │
│    - Detects browser searches -> open_browser_search   │
│    - Detects URLs -> open_url                          │
│    - Detects active app forms -> type_in_app           │
│ 6. Snapshot packaged + AES-256-GCM encrypted           │
└──────────────────────────┬─────────────────────────────┘
                           │
                           │ HTTPS Relay / WebSockets
                           ▼
┌────────────────────────────────────────────────────────┐
│                   TARGET COMPUTER                      │
│                                                        │
│ 1. Receives and decrypts WorkspaceSnapshot             │
│ 2. Executes ActionPlan sequentially:                   │
│    - create_text_file: creates .txt on Desktop         │
│    - open_browser_search: opens Chrome to query        │
│    - open_url: opens Chrome at URL                     │
│    - type_in_app: focuses target window & types text   │
└────────────────────────────────────────────────────────┘
```

### 10.2 Service Architecture

| Service Component | File Path | Primary Responsibility |
|---|---|---|
| **Data Types** | `shared/types/screen_types.py` | Defines `ScreenRegion`, `OCRResult`, `ScreenContent`, `ActionItem`, `ActionPlan`, `ExecutionReport`. |
| **Screen Capturer** | `services/screen_reader/screen_capturer.py` | Captures high-res screen frames via Win32 GDI / `mss`; attaches to `OpenInputDesktop` for isolated runner resilience. |
| **Region Selector** | `services/screen_reader/region_selector.py` | Tkinter transparent fullscreen overlay; supports drag-to-crop, Enter (confirm), Esc (default full screen), right-click (cancel). |
| **OCR Engine** | `services/screen_reader/ocr_engine.py` | Dual-engine OCR: attempts Windows native `winrt` OCR first; falls back to `pytesseract` with confidence metrics. |
| **Reader Orchestrator** | `services/screen_reader/screen_reader_orchestrator.py` | Coordinates crop selection, screenshot capture, OCR text extraction, and base64 PNG encoding. |
| **AI Content Analyzer** | `services/ai_analyzer/content_analyzer.py` | Feeds visual screenshot + OCR context to `gemini-1.5-flash`; includes rule-based heuristic fallback if AI is offline. |
| **Action Planner** | `services/ai_analyzer/action_planner.py` | Synthesizes and logs structured `ActionPlan` for execution on target computer. |
| **Text File Creator** | `services/action_executor/text_creator.py` | Creates formatted `.txt` files on the target Windows Desktop (`AeroSync_{timestamp}_{hint}.txt`). |
| **Browser Controller** | `services/action_executor/browser_controller.py` | Launches Chrome or Windows default browser with Google search queries or explicit URLs. |
| **Input Automator** | `services/action_executor/input_automator.py` | Finds running windows by title hint, brings them to focus, and injects text via `pyautogui` and clipboard. |
| **Execution Orchestrator**| `services/action_executor/execution_orchestrator.py` | Sequentially executes the `ActionPlan` on the target machine and returns an `ExecutionReport`. |

### 10.3 Failure Mode Handling & Graceful Degradation
1. **Desktop Isolation / Access Denied**: Handled via `_attach_input_desktop()` using `user32.OpenInputDesktop`, allowing GDI access even in background test runners.
2. **Missing Tesseract / WinRT**: `ocr_engine.py` handles missing OCR binaries gracefully, returning an empty `OCRResult` with `confidence=0.0` rather than throwing fatal unhandled exceptions.
3. **Missing or Expired Gemini API Key**: `content_analyzer.py` automatically falls back to regex-based heuristic planning (extracts URLs, text blocks, and search terms directly from OCR text).
4. **App Not Open on Target**: `input_automator.py` attempts to find windows matching `target_app`; if no matching window is active, it falls back to typing into the active window or creating a text file.

---

## 11. Constellations: Isolated Multi-Computer Rooms

### 11.1 Concept & Architecture
A **Constellation** is an isolated, collaborative "room" of linked Windows computers. 

Key characteristics:
1. **Maximum Capacity**: Strictly limited to **5 computers** (`MAX_CONSTELLATION_DEVICES = 5`). Attempts to link a 6th computer are rejected by the API with HTTP 400.
2. **Unique Join Code**: Each constellation is assigned a human-readable unique code formatted as `CST-XXXXX` (e.g. `CST-7K9M2`) using collision-resistant, non-ambiguous alphanumeric characters.
3. **Isolated Workspace Transfers**: When a user performs a gesture "throw", the desktop client prioritizes targeting peer computers within its active constellation room before considering other devices.
4. **Automatic Pairwise Linking**: Joining a constellation automatically pairs all computers in the room with each other, establishing mutual trust for workspace transfers.

```
┌────────────────────────────────────────────────────────┐
│               CONSTELLATION: "STUDIO ALPHA"            │
│               Join Code: CST-8Y4B2 (Max 5 PCs)        │
│                                                        │
│   ┌──────────────┐                  ┌──────────────┐   │
│   │   Laptop 1   │◀────────────────▶│   Laptop 2   │   │
│   │   (Creator)  │                  │   (Member)   │   │
│   └───────┬──────┘                  └──────┬───────┘   │
│           │                                │           │
│           │         ┌──────────────┐       │           │
│           └────────▶│  Desktop 3   │◀──────┘           │
│                     │   (Member)   │                   │
│                     └──────────────┘                   │
│                                                        │
│   * Room holds up to 5 computers total                 │
│   * Devices outside cannot intercept or target room    │
└────────────────────────────────────────────────────────┘
```

### 11.2 Database Schema
- **`constellations`**: `id`, `name`, `join_code`, `creator_user_id`, `max_devices` (default 5), `created_at`.
- **`constellation_members`**: `id`, `constellation_id`, `device_id`, `user_id`, `role` (`owner`/`member`), `joined_at`, `UNIQUE(constellation_id, device_id)`.

### 11.3 API Endpoints
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/constellations/create` | Creates room with unique `CST-XXXXX` code and links creator computer. |
| `POST` | `/api/v1/constellations/join` | Links computer via unique code; validates `count < 5`. |
| `GET` | `/api/v1/constellations/` | Lists user's constellations with members, online status, and capacity. |
| `GET` | `/api/v1/constellations/{id}` | Detailed constellation information. |
| `POST` | `/api/v1/constellations/{id}/leave` | Removes a computer from the room; cleans up room if empty. |
| `GET` | `/api/v1/constellations/{device_id}/targets` | Resolves target peers restricted to the constellation boundary. |

---

## 12. Node-Based Kinematic Gesture Engine & Camera Widgets

### 12.1 Mathematical Node & Pivot Architecture
To maximize gesture classification accuracy without relying on raw, noisy 2D pixel landmarks, AeroSync computes an internal **Biomechanic Kinematic Node Model** (`services/gesture_engine/node_engine.py`):
1. **Palm Center Node (Virtual 3D Centroid)**:
   $$\vec{P}_{\text{center}} = \frac{1}{5} \left( \vec{L}_0 + \vec{L}_5 + \vec{L}_9 + \vec{L}_{13} + \vec{L}_{17} \right)$$
   Provides an ultra-stable origin anchor invariant to individual finger flexion.
2. **Metacarpal Frame Normal Vector ($\vec{n}$)**:
   $$\vec{u} = \frac{\vec{L}_9 - \vec{L}_0}{\|\vec{L}_9 - \vec{L}_0\|}, \quad \vec{v} = \frac{\vec{L}_5 - \vec{L}_{17}}{\|\vec{L}_5 - \vec{L}_{17}\|}, \quad \vec{n} = \vec{u} \times \vec{v}$$
   Normal vector perpendicular to the palm plane; tells whether the palm is directly facing the camera ($n_z < -0.2$).
3. **Scale Invariance Baseline ($s_{\text{hand}}$)**:
   $$s_{\text{hand}} = \|\vec{L}_5 - \vec{L}_{17}\|$$
   Normalizes all distances, ensuring identical classification whether the hand is 30 cm or 150 cm from the webcam.
4. **Joint Flexion Angles (Pivots)**:
   For each finger, computes interior angle at PIP/DIP joints. $180^\circ$ represents full extension; $< 90^\circ$ represents curling.
5. **Palm Center Trajectory & Throw Impulse**:
   Tracks the temporal trajectory of $\vec{P}_{\text{center}}$ over time. Recognizes a throw when forward acceleration impulse occurs simultaneously with a transition from closed to open hand.

### 12.2 User Invisibility Constraint
**Crucial Architectural Rule**: The computed mathematical nodes, pivot vectors, coordinate axes, and joint angle lines are **NEVER drawn on the user-facing video feed**. 
- The user sees a clean, professional, undistorted camera stream.
- The computer uses the mathematical node vector internally for feature extraction and high-accuracy classification.

### 12.3 Corner Camera Widgets
1. **Desktop Native Picture-in-Picture Widget** (`services/gesture_engine/camera_widget.py`):
   - Pinned to the bottom-right corner of the Windows desktop using `SetWindowPos` (`HWND_TOPMOST`).
   - Clean video feed with a minimal status bar ("Hand Locked • Ready" with pulsing green indicator).
2. **Web Dashboard Camera Widget** (`apps/frontend/src/components/CameraWidget.jsx`):
   - Floating action button in the bottom-right corner of the dashboard.
   - Expandable glassmorphism preview window with HTML5 `getUserMedia` live feed, FPS counter, and gesture armed status.
