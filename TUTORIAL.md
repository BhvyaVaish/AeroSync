# AeroSync — Full Walkthrough & User Guide

Welcome to **AeroSync**, the celestial, gesture-powered workspace synchronization platform. AeroSync allows you to seamlessly beam your live workspace — open applications, exact window coordinates, browser tabs, clipboard, and screen text — from any computer to any other computer in your Constellation using natural, front-facing hand gestures.

---

## 🚀 Quick Start (One-Time Setup)

### Automated Setup
1. **Double-click `setup.bat`** (or in PowerShell run `.\setup.ps1`).
2. The setup script will:
   - Check Python 3.10+
   - Configure the virtual environment (`.\venv`)
   - Install dependencies (`requirements.txt`)
   - Configure Google Chrome auto-launcher
   - Ask if you'd like AeroSync to **auto-start on Windows login**
   - Create a desktop shortcut named **AeroSync**
   - Launch the background System Tray icon and Dashboard.

### Manual Launch
- **Double-click `start_aerosync.bat`** anytime to launch the relay server, frontend dashboard, and system tray app.

---

## ✋ Hand Gestures Cheatsheet

AeroSync uses a node-based kinematic hand analyzer. For precision and privacy, hand skeleton lines are never drawn over your camera. Gestures must be performed facing the camera (`palm_normal.z < -0.35`).

| Gesture | Icon | Trigger Condition | Role Action |
|---|---|---|---|
| **Fist** | ✊ | Hold closed fist facing camera for **≥ 600ms** | **Computer A becomes HOST A** (captures OS log stack & screen) |
| **Throw** | 🚀 | Open hand thrust outward towards camera from a Candidate PC | **Computer B becomes TARGET B** (claims and reconstructs workspace) |
| **Reset** | 🔄 | Automatic upon transfer completion (or via tray menu) | **All PCs revert to NEUTRAL** |

> **Single-App Rule**: Every computer runs the exact same AeroSync app. Any PC can become Host A, and any peer can become Target B. Once the transfer completes, both PCs return to Neutral.

---

## 📐 Screen Orientation & Window Coordinates Division

AeroSync divides your screen into a normalized coordinate grid:
- **Normalized Coordinates**: Window positions and dimensions are logged relative to screen resolution:
  - `rel_x = x / screen_width`
  - `rel_y = y / screen_height`
  - `rel_width = width / screen_width`
  - `rel_height = height / screen_height`
- **Visual Parity across Monitors**:
  - If Computer B has a different resolution or aspect ratio (e.g. 4K vs 1080p), windows land in the exact same quadrant (top-left, top-right, bottom-half, centered, etc.) proportionally.
  - If resolutions match, pixel-perfect coordinates are preserved.
- **Smart Window Reuse**:
  - If a transferred application or window is **already open on Computer B**, AeroSync **does not restart or duplicate it**. It reuses the window and reorients/moves it to match Computer A's coordinates.

---

## 🌐 Google Chrome Auto-Launcher & Tab Restoration

AeroSync includes an automated Chrome Manager (`services/chrome_launcher/chrome_manager.py`):
- **Automatic Detection**: Finds your standard Google Chrome executable across Program Files, LocalAppData, and the Windows Registry.
- **Auto-Launch**: When restoring tabs, it automatically opens normal Chrome with your default profile, grouping all transferred tabs into a clean window without requiring manual command-line flags.
- **Tab Deduplication**: Tabs already open in Computer B are reused and not duplicated.

---

## 💻 Windows System Tray & Auto-Start at Login

AeroSync resides in your Windows System Tray (notification area at the bottom-right taskbar):
- **Live Visual Indicator**:
  - 🔵 **Cyan Star**: Ready / Neutral
  - 🟠 **Gold Star**: Host A Armed & Capturing
  - 🟣 **Purple Star**: Candidate B (Peer has armed Host)
  - 🟢 **Green Star**: Target B / Transferring Complete
- **Tray Menu Options**:
  - **Open Dashboard**: Opens the web control center
  - **Walkthrough Tutorial**: Opens this interactive guide
  - **Launch Normal Chrome**: One-click Chrome launcher
  - **Start at Windows Login**: Checkbox toggle to automatically start AeroSync on boot
  - **Arm Host Mode (Fist ✊)**: Manual trigger fallback
  - **Claim Target Mode (Throw 🚀)**: Manual trigger fallback
  - **Reset to Neutral 🔄**: Reset constellation
  - **Exit AeroSync**: Clean shutdown

---

## ⚠️ Notifications & Unachieved Items Reporting

If an application transferred from Computer A is not installed on Computer B:
- AeroSync will automatically re-launch and reorient all compatible apps and browser tabs.
- Any items that cannot be reconstructed (e.g. proprietary software missing on B) are reported via a native Windows toast notification.
- If more than 3 items fail, a detailed failure report is saved to `~/AeroSync_failed_<transfer_id>_<timestamp>.txt`.
