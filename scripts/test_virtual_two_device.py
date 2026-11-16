"""
AeroSync — Virtual Two-Device E2E Test (Single Machine)

Simulates Computer A (Host) and Computer B (Target) on the same machine
using two in-process instances of the Role State Machine, talking via a
shared in-memory message bus instead of a real relay server.

What is tested:
  1. FIST gesture on "PC-A" → A becomes HOST, B becomes CANDIDATE
  2. THROW gesture on "PC-B" → B becomes TARGET, A enters TRANSFERRING
  3. Workspace capture (mocked, non-blocking) on A
  4. Transfer complete signal → all PCs return to NEUTRAL
  5. Second round: roles can flip — B makes FIST, A becomes CANDIDATE
  6. Log stack embed in snapshot + log stack replay on target side
  7. OCR dedup: items in log stack are not in OCR output

Usage:
    .\\venv\\Scripts\\python scripts\\test_virtual_two_device.py
"""

import sys
import os
import time
import threading
from typing import Dict, Any, List, Callable

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.gesture_engine.role_state_machine import RoleStateMachine
from services.gesture_engine.gesture_types import GestureType
from services.workspace_logger.log_stack import WorkspaceLogQueue, LogEntry, LogEntryType
from shared.constants import RoleState


# ──────────────────────────────────────────────────────────────────────────────
# In-memory message bus (simulates relay server fan-out)
# ──────────────────────────────────────────────────────────────────────────────

class InMemoryBus:
    """
    Simulates the relay server WebSocket fan-out within a single process.
    Messages sent by one machine are delivered to all other machines in the
    same 'constellation'.
    """
    def __init__(self):
        self._handlers: Dict[str, Callable] = {}
        self._lock = threading.Lock()

    def register(self, device_id: str, handler: Callable[[Dict[str, Any]], None]):
        with self._lock:
            self._handlers[device_id] = handler

    def broadcast(self, sender_id: str, message: Dict[str, Any]):
        """Fan-out to all OTHER registered devices."""
        with self._lock:
            handlers = {k: v for k, v in self._handlers.items() if k != sender_id}
        for device_id, handler in handlers.items():
            try:
                handler(message)
            except Exception as exc:
                print(f"  [Bus] Error delivering to {device_id}: {exc}")

    def send_to(self, target_id: str, message: Dict[str, Any]):
        """Direct message to one device."""
        with self._lock:
            handler = self._handlers.get(target_id)
        if handler:
            try:
                handler(message)
            except Exception as exc:
                print(f"  [Bus] Error delivering to {target_id}: {exc}")


bus = InMemoryBus()


def make_send_fn(device_id: str, constellation_id: str) -> Callable:
    """
    Create a send_ws function for a device that routes through the in-memory bus,
    simulating what the relay server WebSocket router does.
    """
    def send(message: Dict[str, Any]):
        msg_type = message.get("type", "")
        # Simulate relay routing logic
        if msg_type in ("host_announcing", "constellation_reset"):
            # broadcast to all peers
            bus.broadcast(device_id, message)
        elif msg_type in ("target_claiming", "workspace_ready", "workspace_transfer"):
            target = message.get("host_device_id") or message.get("target_device_id")
            if target:
                bus.send_to(target, message)
            else:
                bus.broadcast(device_id, message)
        else:
            bus.broadcast(device_id, message)
    return send


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _separator(label: str):
    print(f"\n{'─'*60}")
    print(f"  {label}")
    print('─'*60)


def _assert_state(machine: RoleStateMachine, expected: str, context: str):
    actual = machine.state
    if actual != expected:
        raise AssertionError(f"[{context}] Expected state {expected!r}, got {actual!r}")
    print(f"  ✓ {context}: state = {actual!r}")


# ──────────────────────────────────────────────────────────────────────────────
# Test
# ──────────────────────────────────────────────────────────────────────────────

def test_virtual_two_device():
    CONSTELLATION_ID = "CST-VTEST"

    # Events captured during the test
    events = {"host_a": [], "host_b": [], "target_a": [], "target_b": [], "resets": 0}

    # ── Create Machine A ─────────────────────────────────────────────────────
    machine_a = RoleStateMachine(
        device_id="PC-A",
        constellation_id=CONSTELLATION_ID,
        send_ws=make_send_fn("PC-A", CONSTELLATION_ID),
        on_become_host=lambda: events["host_a"].append(time.monotonic()),
        on_become_target=lambda h: events["target_a"].append(h),
        on_reset=lambda: events.__setitem__("resets", events["resets"] + 1),
    )

    # ── Create Machine B ─────────────────────────────────────────────────────
    machine_b = RoleStateMachine(
        device_id="PC-B",
        constellation_id=CONSTELLATION_ID,
        send_ws=make_send_fn("PC-B", CONSTELLATION_ID),
        on_become_host=lambda: events["host_b"].append(time.monotonic()),
        on_become_target=lambda h: events["target_b"].append(h),
        on_reset=lambda: events.__setitem__("resets", events["resets"] + 1),
    )

    # Register both on the bus
    bus.register("PC-A", machine_a.on_ws_message)
    bus.register("PC-B", machine_b.on_ws_message)

    # ── Round 1: A is HOST, B is TARGET ──────────────────────────────────────
    _separator("Round 1: PC-A FIST → HOST, PC-B THROW → TARGET")

    _assert_state(machine_a, RoleState.NEUTRAL, "A initial")
    _assert_state(machine_b, RoleState.NEUTRAL, "B initial")

    # PC-A: FIST gesture
    machine_a.on_gesture(GestureType.FIST)
    time.sleep(0.05)  # allow bus delivery

    _assert_state(machine_a, RoleState.HOST, "A after FIST")
    _assert_state(machine_b, RoleState.CANDIDATE, "B after host_announcing")
    assert len(events["host_a"]) == 1, "on_become_host(A) should have fired once"
    assert machine_b.host_device_id == "PC-A", f"B should know host=PC-A, got {machine_b.host_device_id}"
    print("  ✓ PC-B knows Host A = PC-A")

    # PC-B: THROW gesture (candidate claiming target)
    machine_b._last_throw_time = 0  # bypass cooldown in test
    machine_b.on_gesture(GestureType.THROW)
    time.sleep(0.05)

    # B sends target_claiming → A receives → A sends workspace_ready → B receives
    # B transitions: CANDIDATE → TARGET → TRANSFERRING (workspace_ready arrives immediately)
    # A transitions: HOST → TRANSFERRING (target_claiming received)
    b_state = machine_b.state
    assert b_state in (RoleState.TARGET, RoleState.TRANSFERRING), \
        f"B should be TARGET or TRANSFERRING after THROW, got {b_state!r}"
    print(f"  ✓ B after THROW: state = {b_state!r}")

    a_state = machine_a.state
    assert a_state in (RoleState.HOST, RoleState.TRANSFERRING), \
        f"A should be HOST or TRANSFERRING after target_claiming, got {a_state!r}"
    print(f"  ✓ A after target_claiming: state = {a_state!r}")
    assert machine_a.target_device_id == "PC-B", f"Host A should know target is PC-B, got {machine_a.target_device_id}"
    print("  ✓ Host A identified Target B = PC-B")

    assert len(events["target_b"]) == 1, "on_become_target(B) should have fired"
    assert events["target_b"][0] == "PC-A", f"B's target should be PC-A, got {events['target_b'][0]}"

    # ── Simulate workspace transfer complete ──────────────────────────────────
    _separator("Transfer Complete → All PCs reset to NEUTRAL")
    machine_b.notify_transfer_complete()
    time.sleep(0.05)

    _assert_state(machine_a, RoleState.NEUTRAL, "A after reset")
    _assert_state(machine_b, RoleState.NEUTRAL, "B after reset")
    assert events["resets"] >= 1, "on_reset should have fired at least once"
    print(f"  ✓ resets fired: {events['resets']}")

    # ── Round 2: B is HOST, A is TARGET ──────────────────────────────────────
    _separator("Round 2: PC-B FIST → HOST, PC-A THROW → TARGET (roles flip)")

    machine_b._last_fist_time = 0  # bypass cooldown
    machine_b.on_gesture(GestureType.FIST)
    time.sleep(0.05)

    _assert_state(machine_b, RoleState.HOST, "B after FIST (round 2)")
    _assert_state(machine_a, RoleState.CANDIDATE, "A after host_announcing (round 2)")
    assert machine_a.host_device_id == "PC-B"
    print("  ✓ Roles flipped: B is Host, A is Candidate")

    machine_a._last_throw_time = 0
    machine_a.on_gesture(GestureType.THROW)
    time.sleep(0.05)

    a_state2 = machine_a.state
    assert a_state2 in (RoleState.TARGET, RoleState.TRANSFERRING), \
        f"A (round 2) should be TARGET or TRANSFERRING, got {a_state2!r}"
    print(f"  ✓ A after THROW (round 2): state = {a_state2!r}")

    b_state2 = machine_b.state
    assert b_state2 in (RoleState.HOST, RoleState.TRANSFERRING), \
        f"B (round 2) should be HOST or TRANSFERRING after target_claiming, got {b_state2!r}"
    print(f"  ✓ B after target_claiming (round 2): state = {b_state2!r}")
    assert machine_b.target_device_id == "PC-A", f"Host B should know target is PC-A, got {machine_b.target_device_id}"
    print("  ✓ Host B identified Target A = PC-A")

    assert len(events["host_b"]) == 1 and len(events["target_a"]) == 1

    machine_a.notify_transfer_complete()
    time.sleep(0.05)

    _assert_state(machine_a, RoleState.NEUTRAL, "A final NEUTRAL")
    _assert_state(machine_b, RoleState.NEUTRAL, "B final NEUTRAL")

    # ── Log Stack embed + replay simulation ───────────────────────────────────
    _separator("Log Stack: embed in snapshot, replay on target")

    from services.workspace_logger.log_serializer import roundtrip_check
    from shared.types.workspace_types import WorkspaceSnapshot

    queue = WorkspaceLogQueue()
    queue.source_device_id = "PC-A"
    queue.enqueue(LogEntry(entry_type=LogEntryType.BROWSER_TAB, url="https://docs.python.org",
                        page_title="Python Docs", captured_at="2026-01-01T00:00:00Z"))
    queue.enqueue(LogEntry(entry_type=LogEntryType.CLIPBOARD, clipboard_text="Hello from A",
                        captured_at="2026-01-01T00:00:00Z"))
    queue.enqueue(LogEntry(entry_type=LogEntryType.WINDOW, window_title="VS Code",
                        captured_at="2026-01-01T00:00:00Z"))

    ok, msg = roundtrip_check(queue)
    assert ok, f"Log stack roundtrip failed: {msg}"

    snapshot = WorkspaceSnapshot(snapshot_id="test-snap-001", captured_at="2026-01-01T00:00:00Z",
                                  source_device_id="PC-A")
    snapshot.log_stack_data = queue.to_dict()

    # Verify deserialisable on target side
    restored = WorkspaceLogQueue.from_dict(snapshot.log_stack_data)
    assert restored.size == 3
    assert any(e.url == "https://docs.python.org" for e in restored.snapshot())
    print(f"  ✓ Log stack ({restored.size} entries) embedded and restored from snapshot")

    # ── OCR deduplication ─────────────────────────────────────────────────────
    _separator("OCR Deduplication: log entries excluded from OCR")

    from services.screen_reader.screen_reader_orchestrator import _deduplicate_ocr_text

    ocr_raw = """\
docs.python.org - Python 3 Documentation
Hello from A
Something only visible on screen (not in OS log)
VS Code - main.py"""

    excl = queue.exclusion_set
    filtered = _deduplicate_ocr_text(ocr_raw, excl)

    assert "docs.python.org" not in filtered, "URL line should be excluded"
    assert "Hello from A" not in filtered, "Clipboard line should be excluded"
    assert "VS Code" not in filtered, "Window title line should be excluded"
    assert "only visible on screen" in filtered, "Unique OCR text must remain"
    print("  ✓ OCR dedup: 3 lines excluded, 1 unique line preserved")

    # ── Target B smart reconstruction & failure notification ──────────────────
    _separator("Target B: Smart Reconstruction (Reuse, Reorient, Failure Notify)")

    import asyncio
    from unittest.mock import patch
    from shared.types.workspace_types import WindowState
    from services.workspace_reconstructor.reconstruction_orchestrator import reconstruct_workspace

    # Computer A captured 3 windows & 2 tabs
    # Window 1: Already open on B -> should be reused and reoriented
    # Window 2: New app -> launched on B
    # Window 3: Not installed on B -> fails and is notified to user
    recon_queue = WorkspaceLogQueue()
    recon_queue.enqueue(LogEntry(entry_type=LogEntryType.BROWSER_TAB, url="https://docs.python.org"))
    recon_queue.enqueue(LogEntry(entry_type=LogEntryType.WINDOW, process_name="existing.exe", window_title="Existing Doc - Word"))
    recon_queue.enqueue(LogEntry(entry_type=LogEntryType.WINDOW, process_name="newapp.exe", window_title="New Tool"))
    recon_queue.enqueue(LogEntry(entry_type=LogEntryType.WINDOW, process_name="uninstalled.exe", window_title="Special Enterprise App"))

    recon_snapshot = WorkspaceSnapshot(
        snapshot_id="test-snap-002",
        source_device_id="PC-A",
        log_stack_data=recon_queue.to_dict(),
        windows=[
            WindowState(title="Existing Doc - Word", process_name="existing.exe", x=50, y=50, width=1024, height=768),
            WindowState(title="New Tool", process_name="newapp.exe", x=100, y=100, width=800, height=600),
            WindowState(title="Special Enterprise App", process_name="uninstalled.exe", x=200, y=200, width=640, height=480),
        ]
    )

    notifications_sent = []

    with patch("services.workspace_reconstructor.reconstruction_orchestrator._snapshot_b_state") as mock_b_state, \
         patch("services.workspace_reconstructor.reconstruction_orchestrator._launch_app") as mock_launch, \
         patch("webbrowser.open") as mock_webbrowser, \
         patch("services.workspace_reconstructor.window_restorer._find_window_smart") as mock_find_win, \
         patch("services.workspace_reconstructor.window_restorer._reposition_window") as mock_repos, \
         patch("apps.client.notification.show_failed_transfer_report") as mock_notify:

        # On Target B: existing.exe is already running, its window has hwnd 5555
        mock_b_state.return_value = ({"existing.exe"}, {"existing doc - word": 5555})

        # Launch behavior: newapp succeeds, uninstalled fails
        def fake_launch(proc, exe, running_procs):
            if "newapp" in proc:
                running_procs.add("newapp.exe")
                return True, ""
            return False, "Application binary not found on Target B"
        mock_launch.side_effect = fake_launch

        # Window matching: Existing Doc is hwnd 5555; New Tool appears after launch (hwnd 6666); Enterprise not found
        def fake_find(title, process_name="", window_class=""):
            if "Existing" in title:
                return 5555, True
            if "New Tool" in title:
                return 6666, True
            return 0, False
        mock_find_win.side_effect = fake_find
        mock_repos.return_value = True
        mock_notify.side_effect = lambda **kwargs: notifications_sent.append(kwargs)

        report = asyncio.run(reconstruct_workspace(recon_snapshot, transfer_id="test-xfer-b"))

        # Verifications
        assert any("existing.exe" in item for item in report.reused_items), "Existing app on B must be reused"
        assert "newapp.exe" in report.launched_apps, "New app must be launched on B"
        assert any("uninstalled.exe" in item for item in report.failed_items), "Uninstalled app failure must be recorded"
        assert "Existing Doc - Word" in report.repositioned_windows, "Existing window must be reoriented"
        assert any("Special Enterprise App" in item for item in report.failed_items), "Missing window must be recorded as failed"
        assert len(notifications_sent) == 1, "User notification must be dispatched"
        assert len(notifications_sent[0]["failed_items"]) >= 2, "Notification must list all unachieved items"
        print("  ✓ Target B smart reconstruction: reuse, launch, reorient, and failed items notification verified")

    print(f"\n{'='*60}")
    print("  ✅ All virtual two-device tests PASSED")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    print("AeroSync — Virtual Two-Device Simulation\n")
    test_virtual_two_device()
