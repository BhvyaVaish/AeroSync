# AeroSync

<div align="center">

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.11+](https://img.shields.io/badge/Python-3.11+-3776AB.svg?logo=python&logoColor=white)](https://www.python.org/)
[![React: 19](https://img.shields.io/badge/React-19-61DAFB.svg?logo=react&logoColor=black)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Vite](https://img.shields.io/badge/Vite-8.0+-646CFF.svg?logo=vite&logoColor=white)](https://vitejs.dev/)
[![MediaPipe](https://img.shields.io/badge/MediaPipe-Hands%20Kinematics-0097A7.svg?logo=google&logoColor=white)](https://developers.google.com/mediapipe)
[![Platform: Windows](https://img.shields.io/badge/Platform-Windows%2010%20%7C%2011-0078D6.svg?logo=windows&logoColor=white)](https://www.microsoft.com/windows)
[![Security: AES--256--GCM](https://img.shields.io/badge/Security-AES--256--GCM-green.svg)](https://en.wikipedia.org/wiki/Galois/Counter_Mode)
[![Author: Bhvya Vaish](https://img.shields.io/badge/Author-Bhvya%20Vaish-0A66C2.svg?logo=linkedin&logoColor=white)](https://www.linkedin.com/in/bhvya-vaish)

<p align="center">
  <strong>Instant, touchless workspace synchronization across multiple computers triggered by vision-based hand gestures.</strong>
</p>

<p align="center">
  AeroSync captures active desktop window geometry, Chrome DevTools browser tabs, system clipboard buffers, and display topology on one machine and reconstructs it on a target machine in milliseconds — triggered by computer vision hand gestures detected through any standard webcam.
</p>

[Key Features](#key-features) • [How It Works](#how-it-works) • [Kinematic Gestures](#touchless-kinematic-sensor--gesture-engine) • [Constellations](#constellations-isolated-multi-computer-rooms) • [Architecture](#architecture-overview) • [Quick Start](#quick-start--installation) • [API Reference](#rest--websocket-api-reference) • [Author](#developed-by)

</div>

---

## ⚡ Core Philosophy: Zero Pixel Streaming

Traditional screen-sharing and remote desktop solutions (such as VNC, RDP, or AnyDesk) continuously stream compressed video frames over the network, suffering from high bandwidth consumption, noticeable latency, and host-dependent input lag.

**AeroSync re-imagines multi-device productivity**:
- **Zero Pixel Streaming**: Transmits structured workspace **state metadata** rather than video frames.
- **Micro-Payloads**: Transports lightweight, compressed, and encrypted payloads (~10 KB to 50 KB) instead of gigabytes of streaming video.
- **Native Reconstruction**: Target machines launch apps, arrange windows via Win32 APIs, restore tabs via Chrome DevTools Protocol (`CDP`), and inject clipboard buffers natively.
- **Touchless Kinematic Control**: Intuitive hand gestures (Fist, Throw, Peace) execute instant state capture and synchronization.

---

## 🚀 Key Features

* **🖐️ Touchless Kinematic Sensor & Vision Engine**
  - Integrated in-browser & desktop MediaPipe hand landmark tracking (21 3D points).
  - **Instant Cold-Start Fist Detection**: Multi-vector geometric analysis ($\text{avgTipToPalm} \le 0.90$) allows direct fist recognition from cold entry without needing to open the palm first.
  - **Thumb-Invariant Tracking**: 100% invariant to thumb position (thumb folded over fingers, tucked under, on the side, or across knuckles).
  - **Throw Gesture Sync & Peace Sign Rollback**: Fast forward-thrust detection to claim/beam, and two-finger peace sign for instant undo rollback.
* **📦 Selective Workspace Beam**
  - Interactive granular modal allowing users to selectively choose which application windows, Chrome tabs, and clipboard items to transmit.
* **🌌 Constellations (Isolated Multi-Computer Rooms)**
  - Group linked computers into private rooms capped at **5 computers** (`MAX_CONSTELLATION_DEVICES = 5`).
  - Shareable alphanumeric join codes (`CST-XXXXX`) for instant pairing across home, office, or studio networks.
  - Full room management: join, leave, and delete constellation rooms.
* **🧠 AI Vision Context & Action Planner (Google Gemini 1.5 Flash)**
  - Fast Win32 GDI / `mss` screen capture with dual OCR (Windows native WinRT + pytesseract).
  - Gemini 1.5 Flash analyzes active screen regions to synthesize smart action plans (generating desktop files for text/docs, automated browser searches, or typing into target applications).
* **🔒 Enterprise Cryptography (AES-256-GCM)**
  - Workspace state serialized to JSON, compressed with `zlib`, and encrypted with a cryptographically secure 256-bit key (`AES-256-GCM` with a 12-byte initialization vector).
  - Ephemeral blob storage with automated expiration and memory cleanup.
* **💎 Obsidian & Titanium Cybernetic UI**
  - Frosted capsule pill navigation bar with **active-tab spotlight glow** and frosted glassmorphism (`backdrop-filter: blur(24px)`).
  - High-contrast pure white pill CTA buttons (`Selective Beam`, `Push Workspace`).
  - Minimalist matte telemetry badges with pure white hover glow.
  - Obsidian liquid chrome canvas background with specular caustic glints.
* **⌨️ Low-Light & Accessibility Fallbacks**
  - Instant global keyboard shortcuts when gestures are degraded by low lighting:
    - `Ctrl + Alt + C`: Armed Host A capture
    - `Ctrl + Alt + L`: Beam to Target B
    - `Ctrl + Alt + Z`: Undo Rollback

---

## 🔄 How It Works

```
┌───────────────────────────────┐       ┌───────────────────────────────┐       ┌───────────────────────────────┐
│           DEVICE A            │       │      AEROSYNC RELAY HUB       │       │           DEVICE B            │
│        (Source Host)          │       │       (FastAPI + SQLite)      │       │        (Target Device)        │
├───────────────────────────────┤       ├───────────────────────────────┤       ├───────────────────────────────┤
│  1. Gesture Trigger           │       │                               │       │                               │
│     - Form Fist (Host A)      │       │                               │       │                               │
│     - Or Ctrl+Alt+C / Click   │       │                               │       │                               │
│                               │       │                               │       │                               │
│  2. Parallel State Capture    │       │                               │       │                               │
│     - Chrome CDP (:9222)      │       │                               │       │                               │
│     - Win32 Rectangles        │       │                               │       │                               │
│     - Clipboard Buffer        │       │                               │       │                               │
│     - Optional OCR / AI Vision│       │                               │       │                               │
│                               │       │                               │       │                               │
│  3. Compression & Encryption  │ HTTP  │                               │  WS   │                               │
│     - JSON -> zlib            │──────▶│  - Session State Machine      │──────▶│  5. Real-Time Push Notification│
│     - AES-256-GCM Encryption  │       │  - Ephemeral Encrypted Blob   │ Push  │     - WebSocket Event         │
│     - Upload Binary Blob      │       │  - WebSocket Connection Pool  │       │                               │
│                               │       │  - Constellation Router       │       │  6. Inbound Retrieval & Exec  │
│  4. Throw Gesture             │       │                               │       │     - Download Blob           │
│     - Beams payload to room   │       │                               │       │     - Decrypt AES-256-GCM     │
│                               │       │                               │       │     - Decompress zlib         │
│                               │       │                               │       │     - Open Chrome URLs        │
│                               │       │                               │       │     - Restore Win32 Layouts   │
│                               │       │                               │       │     - Inject Clipboard Text   │
│                               │       │                               │       │     - Run AI Action Plan      │
└───────────────────────────────┘       └───────────────────────────────┘       └───────────────────────────────┘
```

---

## 🖐️ Touchless Kinematic Sensor & Gesture Engine

AeroSync features a dual-layer kinematic engine that operates both in the browser (`CameraWidget.jsx`) and through the background desktop daemon (`services/gesture_engine`):

| Gesture | Biomechanical Metric | Trigger Time | Action | Visual HUD Feedback | Keyboard Fallback |
|---|---|---|---|---|---|
| **Closed Fist** | $\text{avgTipToPalm} \le 0.90$ (all thumb placements) | **250 ms** | **Host A Mode**: Captures workspace state and arms payload | Radial charge reticle + `FIST ARMED: HOST A` | `Ctrl + Alt + C` |
| **Long Fist** | Continuous fist hold | **1400 ms** | **Selective Beam**: Opens granular item selection checklist | Dual charge ring + `LONG FIST: SELECTIVE BEAM` | Modal button |
| **Throw / Open Hand** | Forward velocity impulse + $\text{avgTipToPalm} > 1.35$ | **250 ms** | **Target B Claim**: Beams and reconstructs workspace on target | Concentric pulse + `THROW: CLAIM TARGET B` | `Ctrl + Alt + L` |
| **Peace Sign (V)** | Index & Middle extended, Ring & Pinky curled | **250 ms** | **Undo Rollback**: Reverts target machine to prior standby state | Purple halo + `PEACE SIGN: ROLLBACK` | `Ctrl + Alt + Z` |

> [!TIP]
> **Cold-Start Sensitivity**: The sensor is tuned with `minDetectionConfidence: 0.12` and a `400ms` jitter grace window, allowing direct fist recognition the moment your hand enters the camera view without requiring you to open your palm first.

---

## 🌌 Constellations (Isolated Multi-Computer Rooms)

AeroSync groups paired computers into collaborative rooms called **Constellations**:

* **5-Device Hard Cap**: Each constellation accommodates up to **5 computers** (`MAX_CONSTELLATION_DEVICES = 5`) for ultra-low latency peer discovery.
* **Join Codes**: Every constellation generates a unique alphanumeric code formatted as `CST-XXXXX` (e.g., `CST-9K2M4`).
* **Instant Collaboration**: Any computer can join a room by entering the join code. Once joined, throwing a workspace automatically synchronizes with active constellation peers.
* **Full Lifecycle**: Users can create, join, leave, or permanently delete constellations directly from the dashboard.

---

## 🏗️ Architecture Overview

```
AeroSync/
├── apps/
│   ├── client/                  # Desktop background daemon orchestrator
│   │   ├── main.py              # Client entry point
│   │   ├── client_orchestrator.py # Core event loop (Camera + WS + Transfer)
│   │   ├── relay_client.py      # HTTP & WebSocket asynchronous client
│   │   ├── transfer_sender.py   # Outbound capture & packaging coordinator
│   │   ├── transfer_receiver.py # Inbound download, decrypt & restoration runner
│   │   ├── storage.py           # Local persistence (hardware ID, JWT tokens)
│   │   └── notification.py      # Native Windows toast notification dispatcher
│   ├── relay_server/            # Central FastAPI relay & coordination hub
│   │   ├── main.py              # Application entry point & lifespan events
│   │   ├── core/                # DB engine (aiosqlite), security, WS connection pool
│   │   ├── models/              # SQLite ORM models & Pydantic schemas
│   │   ├── routers/             # API routes (auth, devices, constellations, sessions, ws)
│   │   └── services/            # Session lifecycle, PIN pairing, constellation service
│   └── frontend/                # Modern React 19 + Vite titanium dashboard
│       └── src/
│           ├── pages/           # Dashboard, Constellations, Devices, Sessions, Login
│           ├── components/      # Navbar, GlassCard, Button, CameraWidget, SpaceBackground, Footer
│           └── services/        # API client, WebSocket provider, Sound effects
├── services/
│   ├── gesture_engine/          # Computer vision kinematic engine (OpenCV + MediaPipe)
│   │   ├── detector.py          # Background video capture thread
│   │   ├── hand_tracker.py      # MediaPipe 21-landmark tracking
│   │   ├── node_engine.py       # Biomechanical joint pivots & angle feature vectors
│   │   ├── gesture_classifier.py# Pose, node & velocity gesture recognition
│   │   └── camera_widget.py     # Desktop picture-in-picture camera HUD
│   ├── workspace_capture/       # OS state collectors
│   │   ├── capture_orchestrator.py # Concurrent capture executor
│   │   ├── browser_capture.py   # Chrome CDP tab extractor (port 9222)
│   │   ├── window_capture.py    # Win32 user32 & dwmapi window geometry collector
│   │   ├── monitor_capture.py   # Display resolution & offset collector
│   │   └── clipboard_capture.py # Bounded clipboard text extractor
│   ├── workspace_packager/      # Compression & encryption engine
│   │   └── packager.py          # JSON serialization -> zlib -> AES-256-GCM
│   ├── workspace_reconstructor/ # Target device restoration engine
│   │   ├── reconstruction_orchestrator.py # Sequential restorer
│   │   ├── browser_restorer.py  # CDP `/json/new` launcher & CLI fallback
│   │   ├── window_restorer.py   # Fuzzy title matching -> Win32 SetWindowPos
│   │   └── clipboard_restorer.py# Pyperclip clipboard injector
│   ├── screen_reader/           # Visual preview & OCR engine
│   │   ├── screen_capturer.py   # High-speed GDI / mss screen capture
│   │   ├── region_selector.py   # Interactive drag-and-crop overlay
│   │   ├── ocr_engine.py        # WinRT / pytesseract dual OCR
│   │   └── screen_reader_orchestrator.py # Screen capture & read coordinator
│   ├── ai_analyzer/             # Vision & LLM action planner
│   │   ├── content_analyzer.py  # Gemini 1.5 Flash vision analysis & heuristics
│   │   └── action_planner.py    # Target action synthesis
│   └── action_executor/         # Target execution automator
│       ├── text_creator.py      # Desktop .txt file creator
│       ├── browser_controller.py# Chrome search & URL navigator
│       ├── input_automator.py   # Win32 focus & pyautogui typing
│       └── execution_orchestrator.py # Sequential action plan runner
├── shared/                      # Constants, dataclasses, cryptography & logging
├── config/                      # Pydantic settings & environment templates
└── aerosync-video/              # 45-second launch film (HyperFrames composition & MP4)
```

---

## 🛠️ Tech Stack Breakdown

| Layer | Technologies |
|---|---|
| **Frontend Dashboard** | React 19, Vite 8, Lucide React, MediaPipe Hands (WASM/SIMD), WebSockets |
| **Relay Backend** | FastAPI 0.115+, Uvicorn, SQLite (`aiosqlite`), Pydantic v2, Python 3.11+ |
| **Desktop Daemon** | Python 3.11+, PyWin32 (`ctypes`, `win32gui`, `win32con`, `dwmapi`), PyAutoGUI |
| **Vision & Gestures** | MediaPipe Hands, OpenCV (`cv2`), Biomechanical Kinematic Node Engine |
| **AI & OCR** | Google Gemini 1.5 Flash, Windows WinRT OCR, Pytesseract, `mss` |
| **Security & Crypto** | AES-256-GCM (PyCryptodome), SHA-256, bcrypt, JWT (HMAC-SHA256) |
| **Motion & Video** | HyperFrames Engine, GSAP, FFmpeg 9.0.2 |

---

## ⚡ Quick Start & Installation

### Prerequisites
- **Operating System**: Windows 10 or Windows 11 (64-bit)
- **Python**: Version 3.11 or higher
- **Node.js**: Version 18.0.0 or higher with `npm`
- **Hardware**: Any standard webcam (integrated or USB)
- **Web Browser**: Google Chrome or Microsoft Edge (run with `--remote-debugging-port=9222` for Chrome DevTools tab sync)

---

### Step 1: Clone & Configure

```powershell
# Clone the repository
git clone https://github.com/bhvya-vaish/AeroSync.git
cd AeroSync

# Automated One-Click Setup (Installs Python venv + Frontend modules)
.\setup.bat
```

*Or manual setup:*
```powershell
# Create & activate Python virtual environment
python -m venv venv
.\venv\Scripts\activate

# Install backend dependencies
pip install -r requirements.txt
pip install -r requirements-dev.txt

# Copy environment template
copy config\.env.example .env
```

---

### Step 2: Start the Relay Server

```powershell
.\venv\Scripts\python -m uvicorn apps.relay_server.main:app --host 127.0.0.1 --port 8000 --reload
```
* Interactive Swagger API docs: `http://localhost:8000/docs`
* Local SQLite database `aerosync.db` will initialize automatically.

---

### Step 3: Start the Web Dashboard

Open a second terminal window:
```powershell
cd apps/frontend
npm install
npm run dev
```
Open `http://localhost:5173` in your browser. Register an account, log in, and your device will connect automatically.

---

### Step 4: Launch the Desktop Client Daemon

Open a third terminal on each computer you wish to synchronize:
```powershell
# Optional: Launch Chrome with CDP port enabled for tab sync
start chrome --remote-debugging-port=9222

# Start the AeroSync desktop daemon
.\venv\Scripts\python -m apps.client.main --server http://127.0.0.1:8000
```
A Windows native toast notification will confirm that the daemon and camera gesture tracker are online.

---

## 📡 REST & WebSocket API Reference

### Authentication (`/api/v1/auth`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/auth/register` | Register a new user account |
| `POST` | `/api/v1/auth/login` | Authenticate and obtain JWT access & refresh tokens |
| `POST` | `/api/v1/auth/refresh` | Rotate access token using valid refresh token |
| `POST` | `/api/v1/auth/logout` | Revoke active refresh token |
| `GET` | `/api/v1/auth/me` | Fetch authenticated profile |

### Device Management (`/api/v1/devices`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/devices/register` | Register or update device hardware fingerprint |
| `GET` | `/api/v1/devices/` | List all registered and paired devices |
| `POST` | `/api/v1/devices/pair/initiate` | Generate a 15-minute 6-digit pairing PIN |
| `POST` | `/api/v1/devices/pair/complete` | Validate PIN and pair two devices |
| `DELETE` | `/api/v1/devices/{device_id}` | Remove device and revoke pairings |

### Constellations (`/api/v1/constellations`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/constellations/` | Create a new constellation room (max 5 devices) |
| `GET` | `/api/v1/constellations/` | List constellations linked to user |
| `POST` | `/api/v1/constellations/join` | Join constellation using `CST-XXXXX` join code |
| `POST` | `/api/v1/constellations/{id}/leave` | Leave a constellation room |
| `DELETE` | `/api/v1/constellations/{id}` | Permanently delete constellation and unlink peers |

### Session Transfer (`/api/v1/sessions`)
| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/v1/sessions/initiate` | Request transfer session between devices |
| `POST` | `/api/v1/sessions/{id}/upload` | Upload encrypted AES-256-GCM binary payload |
| `POST` | `/api/v1/sessions/{id}/uploaded`| Finalize upload and notify target device |
| `POST` | `/api/v1/sessions/{id}/accept` | Accept incoming transfer and retrieve key |
| `GET` | `/api/v1/sessions/{id}/download` | Download encrypted workspace blob |
| `POST` | `/api/v1/sessions/{id}/complete`| Mark transfer complete or report failure |
| `DELETE`| `/api/v1/sessions/{id}` | Cancel pending transfer session |
| `GET` | `/api/v1/sessions/history` | Paginated transfer audit logs |

### WebSocket Real-Time Signaling
| Protocol | URI | Description |
|---|---|---|
| `WSS` | `/ws/{device_id}?token=<jwt>` | Real-time presence, heartbeat, and transfer notification push |

---

## 🔒 Security Architecture

* **End-to-End Encryption**: Every workspace package is encrypted locally using **AES-256-GCM** with a single-use 256-bit key (`os.urandom(32)`) and a unique 12-byte initialization vector (IV).
* **Integrity Validation**: Payloads include a **SHA-256 checksum** verified prior to decompression to prevent tampering or corruption.
* **Ephemeral Storage**: Uploaded binary blobs are stored with time-to-live (`TTL`) bounds and purged automatically once retrieved or upon session expiration.
* **Zero Host-Memory Leakage**: Relay server acts as a blind broker and never holds encryption keys in plaintext.
* **Authentication**: Password storage uses `bcrypt` with salt rounds = 12. API communication is authorized via signed JWT access tokens with short-lived expiration.

---

## 🎬 Product Launch Video

AeroSync includes a complete 45-second product launch video built using the **HyperFrames** motion engine:
* **Output Render**: `aerosync-video/renders/aerosync_launch_45s.mp4`
* **Resolution**: 1920×1080 (1080p Full HD) @ 30.0 fps
* **Soundtrack**: Custom cyberpunk synth score with synchronized spatial sound effects (whoosh, click, kinematic lock, beam hum).
* **Narrative Arc**:
  - *Act 1 (0s–11s)*: The problem of fragmented workspace sessions and lost buffers across devices.
  - *Act 2 (11s–34s)*: Touchless kinematic sensor demo — Fist capture, Selective Beam, Memory Deque, Throw sync, and Peace rollback.
  - *Act 3 (34s–45s)*: Constellations network topology, developer attribution, and call-to-action.

---

## 🧪 Testing Suite

```powershell
# Run backend FastAPI unit & integration tests
.\venv\Scripts\python -m pytest apps/relay_server/tests/ -v

# Run with test coverage analysis
.\venv\Scripts\python -m pytest --cov=apps --cov=services --cov=shared

# Run end-to-end smoke test
.\venv\Scripts\python scripts/test_system.py
```

---

## 👨‍💻 Developed By

<div align="center">

### **Bhvya Vaish**

[![LinkedIn](https://img.shields.io/badge/LinkedIn-Bhvya%20Vaish-0A66C2?style=for-the-badge&logo=linkedin&logoColor=white)](https://www.linkedin.com/in/bhvya-vaish)
[![GitHub](https://img.shields.io/badge/GitHub-Profile-181717?style=for-the-badge&logo=github&logoColor=white)](https://github.com/bhvya-vaish)

*Connect on [LinkedIn (linkedin.com/in/bhvya-vaish)](https://www.linkedin.com/in/bhvya-vaish) for collaborations, inquiries, or tech discussions.*

</div>

---

## 📄 License

This project is open-source and distributed under the **[MIT License](LICENSE)**.

Copyright © 2026 **Bhvya Vaish**. All rights reserved.
