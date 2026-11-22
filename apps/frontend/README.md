# AeroSync Frontend

The official web management cockpit for AeroSync, built with React 19 and Vite.

## Overview

The AeroSync Frontend delivers real-time workspace monitoring, touchless vision sensor feedback, constellation management, and manual beam controls in a cybernetic titanium-and-obsidian theme.

## Key Modules

- **Workspace Overview (`/`)**: Real-time telemetry, memory queue item breakdowns (Windows, Browser Tabs, Clipboard, Processes), role indicators (Host A, Candidate, Target B), and battery-aware Eco-Mode indicator.
- **Kinematic Sensor & Camera HUD (`CameraWidget.jsx`)**: Web-based MediaPipe hand landmark tracking for touchless gesture recognition (Fist, Throw, Peace sign rollback) with multi-vector thumb-invariance and direct cold-start detection.
- **Selective Beam Modal (`SelectiveTransferModal.jsx`)**: Granular filtering interface allowing users to select individual windows, tabs, and clipboard buffers before initiating synchronization.
- **Constellations (`/constellations`)**: Multi-device private rooms capped at 5 computers with join code discovery (`CST-XXXXX`), leave, and deletion lifecycles.
- **Device Pairing (`/devices`)**: Device registration, hardware fingerprinting, and 6-digit PIN pairing.
- **Session History (`/sessions`)**: Audit logs of inbound and outbound workspace transfers with timing metrics and node counts.

## Development Setup

```bash
# Navigate to frontend directory
cd apps/frontend

# Install dependencies
npm install

# Start Vite development server
npm run dev
```

The app will run locally at `http://localhost:5173/`.

## Build for Production

```bash
npm run build
npm run preview
```

## Creator

Developed by **Bhvya Vaish** ([LinkedIn Profile](https://www.linkedin.com/in/bhvya-vaish)).
