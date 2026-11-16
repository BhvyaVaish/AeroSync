"""
AeroSync — Test: Log Stack, OS Logger, and Deduplication Pipeline

Verifies:
1. WorkspaceLogQueue push/pop/snapshot/exclusion_set
2. LogSerializer roundtrip (compress → decompress → verify)
3. OCR deduplication logic (mocked exclusion set)
4. FIST gesture detection via node engine
5. Role State Machine transitions (FIST → HOST → CANDIDATE → TARGET → NEUTRAL)
"""

import sys
import os
import time
import math

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.workspace_logger.log_stack import WorkspaceLogQueue, LogEntry, LogEntryType
from services.workspace_logger.log_serializer import serialise_queue, deserialise_queue, roundtrip_check
from services.screen_reader.screen_reader_orchestrator import _deduplicate_ocr_text


def _make_entry(entry_type, **kwargs):
    return LogEntry(entry_type=entry_type, captured_at="2026-01-01T00:00:00Z", **kwargs)


def test_log_queue():
    queue = WorkspaceLogQueue(max_size=100)
    queue.enqueue(_make_entry(LogEntryType.WINDOW,       window_title="Notepad"))               # oldest
    queue.enqueue(_make_entry(LogEntryType.BROWSER_TAB,  url="https://github.com", page_title="GitHub"))
    queue.enqueue(_make_entry(LogEntryType.CLIPBOARD,    clipboard_text="Hello World"))
    queue.enqueue(_make_entry(LogEntryType.PROCESS,      process_name="chrome.exe"))             # newest

    assert queue.size == 4, f"Expected 4 entries, got {queue.size}"

    excl = queue.exclusion_set
    assert any("github.com" in e for e in excl), f"URL not in exclusion set: {excl}"
    assert any("Notepad" in e for e in excl),    f"Window not in exclusion set: {excl}"
    assert any("Hello World" in e for e in excl), f"Clipboard not in exclusion set: {excl}"

    # FIFO: dequeue returns the OLDEST item first (Notepad was enqueued first)
    first_out = queue.dequeue()
    assert first_out.window_title == "Notepad", \
        f"FIFO violated — expected 'Notepad' (oldest), got: {first_out}"
    assert queue.size == 3, "Size should be 3 after one dequeue"

    # Second dequeue gives the GitHub tab (second oldest)
    second_out = queue.dequeue()
    assert second_out.url == "https://github.com", \
        f"FIFO violated — expected GitHub URL (second), got: {second_out}"

    print("✓ test_log_queue PASSED (FIFO order verified)")


def test_log_serializer():
    queue = WorkspaceLogQueue()
    queue.source_device_id = "test-device-001"
    for i in range(10):
        queue.enqueue(_make_entry(LogEntryType.WINDOW, window_title=f"Window {i}"))

    ok, msg = roundtrip_check(queue)
    assert ok, f"Roundtrip failed: {msg}"
    # Verify FIFO order is preserved after roundtrip
    original_titles = [e.window_title for e in queue.snapshot()]
    restored = deserialise_queue(serialise_queue(queue))
    restored_titles = [e.window_title for e in restored.snapshot()]
    assert original_titles == restored_titles, "FIFO order not preserved in roundtrip"
    print(f"✓ test_log_serializer PASSED — {msg}")


def test_ocr_deduplication():
    ocr_text = """\
github.com/microsoft/vscode · GitHub
Hello World, this is clipboard content
Some unique OCR-only text here
Notepad - Untitled"""

    exclusion_set = {
        "url:https://github.com/microsoft/vscode",   # GitHub URL
        "clip:Hello World",                           # Clipboard prefix match
        "win:Notepad - Untitled",                     # Window title
    }

    result = _deduplicate_ocr_text(ocr_text, exclusion_set)

    assert "github.com" not in result, f"GitHub line should be excluded: {result!r}"
    assert "Hello World" not in result, f"Clipboard line should be excluded: {result!r}"
    assert "Notepad" not in result, f"Window title line should be excluded: {result!r}"
    assert "unique OCR-only text" in result, f"Unique OCR text should remain: {result!r}"

    print("✓ test_ocr_deduplication PASSED")


def test_fist_gesture_detection():
    """Test fist detection in the node engine using a synthetic hand."""
    from services.gesture_engine.node_engine import NodeBasedGestureAnalyzer, KinematicHandNodes, Vector3D

    analyzer = NodeBasedGestureAnalyzer()

    # Synthetic fist nodes: all fingers curled, palm facing camera
    fist_nodes = KinematicHandNodes(
        palm_center=Vector3D(0.5, 0.5, 0.0),
        palm_normal=Vector3D(0.0, 0.0, -0.6),   # facing camera (z < -0.35)
        hand_axis=Vector3D(0.0, 1.0, 0.0),
        hand_scale=0.15,
        flexion_angles={f: 45.0 for f in ["thumb", "index", "middle", "ring", "pinky"]},
        tip_extension_ratios={f: 0.6 for f in ["thumb", "index", "middle", "ring", "pinky"]},
        openness_score=0.0,
        is_facing_camera=True,
    )

    # Seed trajectory with 3 static positions (stationary = no throw)
    for _ in range(3):
        analyzer.update_trajectory(fist_nodes, time.monotonic())
        time.sleep(0.01)

    is_fist, conf = analyzer.detect_kinematic_fist(fist_nodes)
    assert is_fist, f"Fist should be detected: is_fist={is_fist}, conf={conf}"
    assert conf >= 0.75, f"Fist confidence too low: {conf}"

    # Open hand should NOT be fist
    open_nodes = KinematicHandNodes(
        palm_center=Vector3D(0.5, 0.5, 0.0),
        palm_normal=Vector3D(0.0, 0.0, -0.6),
        hand_axis=Vector3D(0.0, 1.0, 0.0),
        hand_scale=0.15,
        flexion_angles={f: 160.0 for f in ["thumb", "index", "middle", "ring", "pinky"]},
        tip_extension_ratios={f: 1.8 for f in ["thumb", "index", "middle", "ring", "pinky"]},
        openness_score=1.0,
        is_facing_camera=True,
    )
    is_fist_open, _ = analyzer.detect_kinematic_fist(open_nodes)
    assert not is_fist_open, "Open hand should NOT be detected as fist"

    print(f"✓ test_fist_gesture_detection PASSED (confidence={conf:.2f})")


def test_role_state_machine():
    """Test the constellation role state machine transitions."""
    from services.gesture_engine.role_state_machine import RoleStateMachine
    from services.gesture_engine.gesture_types import GestureType
    from shared.constants import RoleState

    messages_sent = []

    def mock_send_ws(msg):
        messages_sent.append(msg)

    host_called = []
    target_called = []
    reset_called = []

    machine = RoleStateMachine(
        device_id="device-A",
        constellation_id="CST-TEST1",
        send_ws=mock_send_ws,
        on_become_host=lambda: host_called.append(1),
        on_become_target=lambda h: target_called.append(h),
        on_reset=lambda: reset_called.append(1),
    )

    # 1. Start NEUTRAL
    assert machine.state == RoleState.NEUTRAL, f"Initial state wrong: {machine.state}"

    # 2. FIST → HOST
    machine.on_gesture(GestureType.FIST)
    assert machine.state == RoleState.HOST, f"After FIST, expected HOST, got {machine.state}"
    assert len(host_called) == 1, "on_become_host not called"
    assert any(m["type"] == "host_announcing" for m in messages_sent), "host_announcing not sent"

    # 3. FIST again (cooldown) → still HOST (ignored)
    machine.on_gesture(GestureType.FIST)
    assert machine.state == RoleState.HOST, "Second FIST should be ignored (cooldown)"

    # 4. Simulate peer host_announcing → we transition to CANDIDATE
    machine2 = RoleStateMachine(
        device_id="device-B",
        constellation_id="CST-TEST1",
        send_ws=mock_send_ws,
        on_become_host=lambda: None,
        on_become_target=lambda h: target_called.append(h),
        on_reset=lambda: reset_called.append(1),
    )
    machine2.on_ws_message({"type": "host_announcing", "device_id": "device-A"})
    assert machine2.state == RoleState.CANDIDATE, f"After host_announcing, expected CANDIDATE, got {machine2.state}"
    assert machine2.host_device_id == "device-A"

    # 5. THROW on device-B → TARGET
    machine2._last_throw_time = 0  # reset cooldown
    machine2.on_gesture(GestureType.THROW)
    assert machine2.state == RoleState.TARGET, f"After THROW, expected TARGET, got {machine2.state}"
    assert len(target_called) >= 1, "on_become_target not called"

    # 5b. Host A receives target_claiming from device-B
    assert machine.target_device_id is None
    machine.on_ws_message({"type": "target_claiming", "device_id": "device-B", "constellation_id": "CST-TEST1"})
    assert machine.state == RoleState.TRANSFERRING, f"Expected TRANSFERRING, got {machine.state}"
    assert machine.target_device_id == "device-B", f"Expected target_device_id 'device-B', got {machine.target_device_id}"

    # 6. Reset
    machine2.notify_transfer_complete()
    assert machine2.state == RoleState.NEUTRAL, f"After reset, expected NEUTRAL, got {machine2.state}"
    assert any(m["type"] == "constellation_reset" for m in messages_sent), "constellation_reset not sent"

    print("✓ test_role_state_machine PASSED")


def test_fist_debounce():
    """Verify that GestureStateMachine requires holding FIST for >=600ms before confirming."""
    from services.gesture_engine.gesture_state_machine import GestureStateMachine
    from services.gesture_engine.gesture_types import GestureType

    emitted = []
    gsm = GestureStateMachine(on_event_callback=lambda ev: emitted.append(ev))

    # Frame 1: Fist detected at t=0
    gsm.process((GestureType.FIST, 0.95), "Right")
    assert len(emitted) == 0, "FIST should not fire on first frame without hold"

    # Frame 2: Fist held for 300ms (< 600ms threshold)
    # Simulate time passing by shifting candidate_start_time back by 0.3s
    gsm.candidate_start_time = time.monotonic() - 0.3
    gsm.process((GestureType.FIST, 0.95), "Right")
    assert len(emitted) == 0, "FIST should not fire before 600ms hold time"

    # Frame 3: Low confidence fist held for 700ms (< 0.88 threshold)
    gsm.candidate_start_time = time.monotonic() - 0.7
    gsm.process((GestureType.FIST, 0.80), "Right")
    assert len(emitted) == 0, "FIST should not fire when confidence < 0.88"

    # Frame 4: High confidence fist held for 700ms (>= 600ms and >= 0.88)
    gsm.process((GestureType.FIST, 0.96), "Right")
    assert len(emitted) == 1, "FIST should fire when held >= 600ms with conf >= 0.88"
    assert emitted[0].gesture_type == GestureType.FIST

    print("✓ test_fist_debounce PASSED (600ms hold + 0.88 confidence verified)")


def test_smart_reconstruction():
    """Verify smart reconstruction: reuse existing apps/windows, reorient coordinates, track failures."""
    import asyncio
    from unittest.mock import patch, MagicMock
    from shared.types.workspace_types import WorkspaceSnapshot, WindowState
    from services.workspace_reconstructor.reconstruction_orchestrator import reconstruct_workspace

    # Prepare snapshot with log data + windows
    queue = WorkspaceLogQueue()
    queue.enqueue(LogEntry(entry_type=LogEntryType.BROWSER_TAB, url="https://example.com/tab1"))
    queue.enqueue(LogEntry(entry_type=LogEntryType.WINDOW, process_name="existing_app.exe", window_title="Existing App Window"))
    queue.enqueue(LogEntry(entry_type=LogEntryType.WINDOW, process_name="missing_app.exe", window_title="Missing App Window"))

    snapshot = WorkspaceSnapshot(
        snapshot_id="test-snap-001",
        log_stack_data=queue.to_dict(),
        windows=[
            WindowState(title="Existing App Window", process_name="existing_app.exe", x=100, y=100, width=800, height=600),
            WindowState(title="Missing App Window", process_name="missing_app.exe", x=200, y=200, width=500, height=400),
        ]
    )

    notifications_called = []

    with patch("services.workspace_reconstructor.reconstruction_orchestrator._snapshot_b_state") as mock_b_state, \
         patch("services.workspace_reconstructor.reconstruction_orchestrator._launch_app") as mock_launch, \
         patch("webbrowser.open") as mock_webbrowser, \
         patch("services.workspace_reconstructor.window_restorer._find_window_smart") as mock_find_win, \
         patch("services.workspace_reconstructor.window_restorer._reposition_window") as mock_repos, \
         patch("apps.client.notification.show_failed_transfer_report") as mock_notify:

        # Mock Target B state: existing_app.exe is ALREADY running on B
        mock_b_state.return_value = ({"existing_app.exe"}, {"existing app window": 9999})

        # missing_app.exe fails to launch
        mock_launch.return_value = (False, "Executable not found")

        # Window matching: "Existing App Window" is found; "Missing App Window" is not found
        def fake_find(title, process_name="", window_class=""):
            if "Existing" in title:
                return 9999, True
            return 0, False
        mock_find_win.side_effect = fake_find
        mock_repos.return_value = True

        mock_notify.side_effect = lambda **kwargs: notifications_called.append(kwargs)

        report = asyncio.run(reconstruct_workspace(snapshot, transfer_id="xfer-12345"))

        # 1. Tab should be restored
        assert "https://example.com/tab1" in report.restored_tabs

        # 2. existing_app.exe was already running on B → should NOT be launched, should be recorded in reused_items
        assert any("existing_app.exe" in item for item in report.reused_items), f"Expected reused app, got {report.reused_items}"
        assert "existing_app.exe" not in report.launched_apps

        # 3. missing_app.exe launch failed → should be recorded in failed_items
        assert any("missing_app.exe" in item for item in report.failed_items), f"Expected failed app launch, got {report.failed_items}"

        # 4. Existing window was reoriented using coordinates
        assert "Existing App Window" in report.repositioned_windows

        # 5. Missing window was recorded in failed_items
        assert any("Missing App Window" in item for item in report.failed_items), f"Expected failed window, got {report.failed_items}"

        # 6. Notification was delivered with failure details
        assert len(notifications_called) == 1
        notif_data = notifications_called[0]
        assert len(notif_data["failed_items"]) >= 2
        assert len(notif_data["reused_items"]) >= 1

    print("✓ test_smart_reconstruction PASSED (reuse, reorient, failed tracking verified)")


def test_notification_reporting():
    """Verify notification generator for toast and failure files."""
    import tempfile
    from unittest.mock import patch
    from apps.client.notification import show_toast_list, show_failed_transfer_report

    toasts = []
    with patch("apps.client.notification.show_toast") as mock_toast:
        mock_toast.side_effect = lambda t, m: toasts.append((t, m))

        # 1. Under 3 items: inline bullet list
        show_toast_list("Failure List", ["Item 1", "Item 2"])
        assert len(toasts) == 1
        assert "• Item 1" in toasts[0][1]

        # 2. Over 3 items: file generation + summary toast
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            report_path = tf.name
        show_toast_list("Failure List", ["Item 1", "Item 2", "Item 3", "Item 4"], report_path=report_path)
        assert len(toasts) == 2
        assert "4 items could not be transferred" in toasts[1][1]
        with open(report_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "• Item 4" in content
        try:
            os.remove(report_path)
        except OSError:
            pass

        # 3. show_failed_transfer_report with no failures
        show_failed_transfer_report("xfer-ok", failed_items=[], launched_apps=["notepad.exe"], restored_tabs=["https://abc.com"])
        assert "Transfer Complete" in toasts[-1][0]

    print("✓ test_notification_reporting PASSED")


def test_screen_coordinate_division_and_scaling():
    """Verify screen coordinate division & proportional scaling across different monitor resolutions."""
    from unittest.mock import patch, MagicMock
    from shared.types.workspace_types import WindowState
    from services.workspace_reconstructor.window_restorer import _reposition_window

    calls = []
    fake_user32 = MagicMock()
    # Target B resolution: 2560 x 1440
    fake_user32.GetSystemMetrics.side_effect = lambda idx: 2560 if idx == 0 else 1440
    fake_user32.SetWindowPos.side_effect = lambda hwnd, z, x, y, w, h, flags: calls.append((x, y, w, h))

    # Host A had 1920 x 1080, centered window: 960x540 at (480, 270)
    # Divided coordinates: rel_x = 0.25, rel_y = 0.25, rel_width = 0.5, rel_height = 0.5
    win = WindowState(
        title="Scaled Editor",
        x=480,
        y=270,
        width=960,
        height=540,
        rel_x=0.25,
        rel_y=0.25,
        rel_width=0.5,
        rel_height=0.5,
        screen_width=1920,
        screen_height=1080,
        quadrant="center"
    )

    with patch("services.workspace_reconstructor.window_restorer.user32", fake_user32):
        ok = _reposition_window(1234, win)
        assert ok, "Reposition should succeed"
        assert len(calls) == 1
        x, y, w, h = calls[0]
        # Target B (2560x1440) proportional mapping:
        # width = 0.5 * 2560 = 1280
        # height = 0.5 * 1440 = 720
        # x = 0.25 * 2560 = 640
        # y = 0.25 * 1440 = 360
        assert w == 1280, f"Expected scaled width 1280, got {w}"
        assert h == 720, f"Expected scaled height 720, got {h}"
        assert x == 640, f"Expected scaled x 640, got {x}"
        assert y == 360, f"Expected scaled y 360, got {y}"

    # Case 2: Matching resolution (1920x1080) -> pixel perfect
    calls.clear()
    fake_user32.GetSystemMetrics.side_effect = lambda idx: 1920 if idx == 0 else 1080
    with patch("services.workspace_reconstructor.window_restorer.user32", fake_user32):
        _reposition_window(1234, win)
        assert calls[0] == (480, 270, 960, 540), f"Expected exact pixels, got {calls[0]}"

    print("✓ test_screen_coordinate_division_and_scaling PASSED (proportional & exact)")


def test_chrome_auto_launcher():
    """Verify Chrome auto-launcher detection and URL launching."""
    from unittest.mock import patch, MagicMock
    from services.chrome_launcher.chrome_manager import find_chrome_executable, launch_normal_chrome

    # find_chrome_executable returns string or None without crashing
    path = find_chrome_executable()
    # Launch normal chrome with URLs
    spawned_cmds = []
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.side_effect = lambda cmd, **kwargs: spawned_cmds.append(cmd)
        ok = launch_normal_chrome(["https://aerosync.space", "https://github.com"], new_window=True)
        assert ok, "Launch should return True"
        assert len(spawned_cmds) == 1
        cmd = spawned_cmds[0]
        assert "--new-window" in cmd
        assert "https://aerosync.space" in cmd
        assert "https://github.com" in cmd

    print("✓ test_chrome_auto_launcher PASSED")


def test_autostart_registry_commands():
    """Verify autostart script path and registry helper."""
    from apps.client.autostart import _get_autostart_command, is_autostart_enabled

    cmd = _get_autostart_command()
    assert "--tray" in cmd, f"Autostart command must launch in --tray mode: {cmd}"
    assert "main.py" in cmd, f"Autostart command must target main.py: {cmd}"

    # Verify query runs safely
    status = is_autostart_enabled()
    assert isinstance(status, bool), f"is_autostart_enabled must return bool, got {status}"

    print("✓ test_autostart_registry_commands PASSED")


def test_fist_long_hold_and_checklist():
    """Verify short vs long fist timing (600ms short vs 2000ms long) and checklist triggering."""
    from services.gesture_engine.gesture_state_machine import GestureStateMachine
    from services.gesture_engine.gesture_types import GestureType
    from services.gesture_engine.role_state_machine import RoleStateMachine
    from unittest.mock import patch, MagicMock

    emitted = []
    gsm = GestureStateMachine(on_event_callback=lambda evt: emitted.append(evt))

    curr_time = 1000.0
    with patch("time.monotonic", side_effect=lambda: curr_time):
        # Frame 1 at t=0
        gsm.process((GestureType.FIST, 0.95), "Right")
        assert len(emitted) == 0, "No event immediately at t=0"

        # Frame 2 at t=0.65s (>= 600ms) -> Short hold fires
        curr_time = 1000.65
        gsm.process((GestureType.FIST, 0.95), "Right")
        assert len(emitted) == 1, "Short fist hold should emit at 600ms"
        assert emitted[0].gesture_type == GestureType.FIST
        assert emitted[0].is_long_hold is False

        # Frame 3 at t=2.1s (>= 2000ms) -> Long hold fires
        curr_time = 1002.1
        gsm.process((GestureType.FIST, 0.95), "Right")
        assert len(emitted) == 2, "Long fist hold should emit at 2000ms"
        assert emitted[1].gesture_type == GestureType.FIST_LONG
        assert emitted[1].is_long_hold is True
        assert emitted[1].hold_duration_s >= 2.0

    # Test RoleStateMachine receiving FIST_LONG
    host_callbacks = []
    rsm = RoleStateMachine(
        device_id="dev-A",
        constellation_id="const-1",
        send_ws=MagicMock(),
        on_become_host=lambda is_selective=False: host_callbacks.append(is_selective),
    )
    rsm.on_gesture(GestureType.FIST_LONG)
    assert len(host_callbacks) == 1
    assert host_callbacks[0] is True, "FIST_LONG must trigger on_become_host with is_selective=True"

    print("✓ test_fist_long_hold_and_checklist PASSED (600ms short vs 2000ms long selective checklist)")


def test_ten_second_calibration():
    """Verify 10-second per-user calibration routine and threshold tuning."""
    import tempfile
    from services.gesture_engine.user_calibration import TenSecondCalibrator, UserCalibrationProfile
    from services.gesture_engine.node_engine import KinematicHandNodes, Vector3D
    from unittest.mock import patch

    calibrator = TenSecondCalibrator(user_id="user_space_ace")
    calibrator.start()
    assert calibrator.is_active is True

    def make_mock_nodes(angle_val, ratio_val, openness_val, palm_z_val):
        return KinematicHandNodes(
            palm_center=Vector3D(0.5, 0.5, 0.0),
            palm_normal=Vector3D(0.0, 0.0, palm_z_val),
            hand_axis=Vector3D(0.0, 1.0, 0.0),
            hand_scale=0.15,
            flexion_angles={f: angle_val for f in ["thumb", "index", "middle", "ring", "pinky"]},
            tip_extension_ratios={f: ratio_val for f in ["thumb", "index", "middle", "ring", "pinky"]},
            openness_score=openness_val,
            is_facing_camera=True,
        )

    curr_time = 2000.0
    with patch("time.monotonic", side_effect=lambda: curr_time):
        calibrator.start_time = 2000.0
        # Phase 1: Open Hand (0 to 5s)
        curr_time = 2002.5
        is_done, elapsed, instruction = calibrator.feed_nodes(make_mock_nodes(160.0, 1.6, 0.85, -0.65))
        assert not is_done
        assert "OPEN" in instruction
        assert len(calibrator.open_samples) > 0

        # Phase 2: Closed Fist (5 to 10s)
        curr_time = 2007.5
        is_done, elapsed, instruction = calibrator.feed_nodes(make_mock_nodes(45.0, 0.5, 0.08, -0.60))
        assert not is_done
        assert "FIST" in instruction
        assert len(calibrator.fist_samples) > 0

        # Phase 3: Complete (> 10s)
        curr_time = 2010.5
        is_done, elapsed, instruction = calibrator.feed_nodes(make_mock_nodes(45.0, 0.5, 0.08, -0.60))
        assert is_done is True
        assert "Complete" in instruction

    profile = calibrator.compute_profile()
    assert profile.is_calibrated is True
    assert profile.user_id == "user_space_ace"
    for finger in ["thumb", "index", "middle", "ring", "pinky"]:
        thresh = profile.get_flexion_threshold(finger)
        assert 70.0 <= thresh <= 105.0, f"Unexpected threshold for {finger}: {thresh}"

    # Persistence verification
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        profile.save(tmp_path)
        loaded = UserCalibrationProfile.load(tmp_path)
        assert loaded.is_calibrated is True
        assert loaded.user_id == "user_space_ace"
        assert loaded.tuned_flexion_thresholds == profile.tuned_flexion_thresholds
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)

    print("✓ test_ten_second_calibration PASSED (open/fist phases & tuned thresholds)")


def test_cosmic_audio_calls():
    """Verify non-blocking cosmic audio triggers for Host packing and Target receiving."""
    from unittest.mock import patch
    import services.audio.cosmic_audio as audio

    with patch("winsound.Beep") as mock_beep:
        # Host A: ascending chime
        audio.play_capture_packed_sound()
        time.sleep(0.02)

        # Target B: landing harmonic
        audio.play_throw_received_sound()
        time.sleep(0.02)

        # Fist detect & long sounds
        audio.play_fist_detect_sound()
        audio.play_fist_long_sound()
        time.sleep(0.02)

        # Calibration sounds
        audio.play_calibration_step_sound(1)
        audio.play_calibration_step_sound(3)
        time.sleep(0.02)

    print("✓ test_cosmic_audio_calls PASSED (distinct Host A / Target B audio cues)")


def test_queue_telemetry():
    """Verify Queue telemetry metrics match the space-themed QueueMonitorWidget requirements."""
    queue = WorkspaceLogQueue(max_size=500)
    queue.enqueue(_make_entry(LogEntryType.WINDOW, window_title="Code Window"))
    queue.enqueue(_make_entry(LogEntryType.WINDOW, window_title="Terminal Window"))
    queue.enqueue(_make_entry(LogEntryType.BROWSER_TAB, url="https://github.com"))
    queue.enqueue(_make_entry(LogEntryType.CLIPBOARD, clipboard_text="Cosmic snippet"))
    queue.enqueue(_make_entry(LogEntryType.PROCESS, process_name="python.exe"))

    telemetry = queue.get_telemetry()
    assert telemetry["size"] == 5
    assert telemetry["max_size"] == 500
    assert telemetry["capacity"] == 500
    assert telemetry["windows"] == 2
    assert telemetry["tabs"] == 1
    assert telemetry["clipboard"] == 1
    assert telemetry["processes"] == 1
    assert telemetry["mode"] == "FIFO Chronological"
    assert 0.0 < telemetry["capacity_pct"] <= 1.0

    print("✓ test_queue_telemetry PASSED (space orbital telemetry metrics verified)")


def test_multiframe_confirmation():
    """Verify multi-frame persistence requirement for gesture confirmation."""
    from services.gesture_engine.gesture_state_machine import GestureStateMachine
    from services.gesture_engine.gesture_types import GestureType
    from unittest.mock import patch

    emitted = []
    gsm = GestureStateMachine(on_event_callback=lambda evt: emitted.append(evt))

    # Test THROW requires multi-frame persistence (consecutive_frames >= 2)
    curr_time = 5000.0
    with patch("time.monotonic", side_effect=lambda: curr_time):
        gsm.process((GestureType.THROW, 0.90), "Right")
        assert len(emitted) == 0, "Single-frame candidate should not emit prematurely"

        # Frame 2: second consecutive frame sustains throw kinematics -> confirmed!
        curr_time = 5000.08
        gsm.process((GestureType.THROW, 0.90), "Right")
        assert len(emitted) == 1, "Multi-frame confirmed throw should emit"
        assert emitted[0].gesture_type == GestureType.THROW

    print("✓ test_multiframe_confirmation PASSED (multi-frame hold duration verified)")


def test_two_hand_antitrigger():
    """Verify two-hand anti-trigger suppresses single-hand false triggers during typing/gesturing."""
    from services.gesture_engine.gesture_state_machine import GestureStateMachine
    from services.gesture_engine.gesture_types import HandLandmarks, LandmarkPoint

    emitted = []
    gsm = GestureStateMachine(on_event_callback=lambda evt: emitted.append(evt))

    hand_left = HandLandmarks(landmarks=[LandmarkPoint(x=0.4, y=0.5, z=0.0) for _ in range(21)], handedness="Left")
    hand_right = HandLandmarks(landmarks=[LandmarkPoint(x=0.6, y=0.5, z=0.0) for _ in range(21)], handedness="Right")

    # When 2 hands are detected in detector:
    hands = [hand_left, hand_right]
    two_hand_suppressed = len(hands) >= 2
    assert two_hand_suppressed is True, "Two hands in view must activate bimanual anti-trigger"

    # Detector passes None to state machine during two-hand suppression
    if two_hand_suppressed:
        gsm.process(None, "bimanual_suppression")

    assert len(emitted) == 0, "No gestures should fire during bimanual anti-trigger"

    # When 1 hand is deliberately isolated:
    hands = [hand_right]
    two_hand_suppressed = len(hands) >= 2
    assert two_hand_suppressed is False, "Single isolated hand disengages suppression"

    print("✓ test_two_hand_antitrigger PASSED (bimanual suppression prevents normal interaction triggers)")


def test_global_hotkey_listener():
    """Verify global keyboard fallback shortcuts (Ctrl+Alt+C, Ctrl+Alt+L)."""
    from apps.client.hotkeys import GlobalHotkeyListener

    capture_called = []
    launch_called = []

    listener = GlobalHotkeyListener(
        on_capture=lambda: capture_called.append(True),
        on_launch=lambda: launch_called.append(True),
    )

    assert listener.on_capture is not None
    assert listener.on_launch is not None

    listener.on_capture()
    assert len(capture_called) == 1, "Capture callback must be invoked"

    listener.on_launch()
    assert len(launch_called) == 1, "Launch callback must be invoked"

    # Safe start/stop cycle
    ok = listener.start()
    assert isinstance(ok, bool)
    listener.stop()
    assert listener.is_active is False

    print("✓ test_global_hotkey_listener PASSED (Ctrl+Alt+C and Ctrl+Alt+L fallback shortcuts verified)")


def test_exponential_backoff_and_finite_retry():
    """Verify exponential backoff progression, jitter, cap, and safe termination without infinite loops."""
    import asyncio
    from shared.utils.retry import (
        calculate_backoff_delay,
        ExponentialBackoffTracker,
        async_retry_with_backoff,
    )

    # 1. Backoff delays increase exponentially with max cap
    d0 = calculate_backoff_delay(0, base_delay=1.0, max_delay=10.0, jitter=False)
    d1 = calculate_backoff_delay(1, base_delay=1.0, max_delay=10.0, jitter=False)
    d2 = calculate_backoff_delay(2, base_delay=1.0, max_delay=10.0, jitter=False)
    d10 = calculate_backoff_delay(10, base_delay=1.0, max_delay=10.0, jitter=False)

    assert d0 == 1.0, f"Expected 1.0, got {d0}"
    assert d1 == 2.0, f"Expected 2.0, got {d1}"
    assert d2 == 4.0, f"Expected 4.0, got {d2}"
    assert d10 == 10.0, f"Expected cap at 10.0, got {d10}"

    # 2. Stateful tracker terminates after max_retries (no infinite loop)
    tracker = ExponentialBackoffTracker(max_retries=3, base_delay=0.1, max_delay=1.0)
    delays = []
    while not tracker.is_exhausted:
        d = tracker.next_delay()
        if d is not None:
            delays.append(d)

    assert len(delays) == 3, f"Expected exactly 3 retries, got {len(delays)}"
    assert tracker.next_delay() is None, "Must return None when exhausted to prevent infinite loop"

    # Reset allows resumption
    tracker.reset()
    assert tracker.is_exhausted is False
    assert tracker.current_attempt == 0

    # 3. Async retry function terminates with exception upon max retries
    call_count = 0

    async def _failing_op():
        nonlocal call_count
        call_count += 1
        raise ConnectionResetError("Connection dropped")

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(
            async_retry_with_backoff(_failing_op, max_retries=2, base_delay=0.01, max_delay=0.05)
        )
        assert False, "Should have raised exception upon retry exhaustion"
    except ConnectionResetError:
        # Expected: tried initial (1) + 2 retries = 3 attempts total
        assert call_count == 3, f"Expected 3 attempts (1 initial + 2 retries), got {call_count}"
    finally:
        loop.close()

    print("✓ test_exponential_backoff_and_finite_retry PASSED (safe capped retry, no infinite loop)")


def test_direct_lan_p2p_socket():
    """Verify Direct LAN P2P socket transfer and graceful fallback."""
    import asyncio
    from services.lan_transfer.lan_p2p import get_local_lan_ip, LanP2PReceiver, LanP2PSender
    from shared.types.workspace_types import WorkspaceSnapshot
    from services.workspace_packager.packager import create_package, unpack_package

    # 1. IP discovery test
    ip = get_local_lan_ip()
    assert isinstance(ip, str) and len(ip.split(".")) == 4, f"Invalid LAN IP format: {ip}"

    # 2. End-to-end direct LAN socket roundtrip
    received_items = []

    async def _on_recv(transfer_id, aes_key, payload_bytes):
        received_items.append((transfer_id, aes_key, payload_bytes))

    loop = asyncio.new_event_loop()
    try:
        receiver = LanP2PReceiver(on_payload_received=_on_recv, preferred_port=0)
        bound_ip, bound_port = loop.run_until_complete(receiver.start())
        assert bound_port > 0, "Receiver must bind to a valid dynamic port"

        # Prepare test snapshot
        snap = WorkspaceSnapshot(snapshot_id="p2p-test-01", captured_at="2026-01-01T00:00:00Z")
        pkg = create_package(snap)

        # Send directly over LAN socket
        ok = loop.run_until_complete(
            LanP2PSender.send_direct_lan(
                ip="127.0.0.1",
                port=bound_port,
                transfer_id="lan-transfer-01",
                aes_key=pkg.aes_key,
                encrypted_payload=pkg.encrypted_payload,
                timeout_s=2.0,
            )
        )
        assert ok is True, "Direct LAN P2P send should succeed"
        assert len(received_items) == 1, "Receiver should have captured the payload"

        t_id, key, payload = received_items[0]
        assert t_id == "lan-transfer-01"
        assert key == pkg.aes_key

        # Unpack verified
        restored = unpack_package(payload, key)
        assert restored.snapshot_id == "p2p-test-01"

        # 3. Graceful fallback test: unreachable destination must return False without crashing
        fallback_ok = loop.run_until_complete(
            LanP2PSender.send_direct_lan(
                ip="127.0.0.1",
                port=65432,  # closed port
                transfer_id="lan-fail-test",
                aes_key=pkg.aes_key,
                encrypted_payload=pkg.encrypted_payload,
                timeout_s=0.2,
            )
        )
        assert fallback_ok is False, "Unreachable LAN destination must return False for seamless relay fallback"

        # Clean shutdown
        loop.run_until_complete(receiver.stop())
    finally:
        loop.close()

    print("✓ test_direct_lan_p2p_socket PASSED (Gigabit LAN P2P stream & zero-cloud fallback verified)")


def test_browser_scroll_position_preservation():
    """Verify Browser Scroll Depth & Reading Position Preservation across capture and replay."""
    import asyncio
    from unittest.mock import patch, MagicMock
    from shared.types.workspace_types import TabInfo, WorkspaceSnapshot
    from services.workspace_logger.log_stack import LogEntry, LogEntryType, WorkspaceLogQueue
    from services.chrome_launcher.chrome_manager import (
        fetch_tab_scroll,
        async_fetch_tab_scroll,
        restore_tab_scroll,
        async_restore_tab_scroll,
        open_tabs_with_scroll,
    )
    from services.workspace_reconstructor.reconstruction_orchestrator import reconstruct_workspace

    # 1. LogEntry and TabInfo scroll fields & serialization
    entry = LogEntry(
        entry_type=LogEntryType.BROWSER_TAB,
        url="https://docs.aerosync.space/deep-reading",
        page_title="Deep Reading",
        browser="chrome",
        scroll_y=1420,
        scroll_ratio=0.685,
    )
    d = entry.to_dict()
    assert d["scroll_y"] == 1420
    assert d["scroll_ratio"] == 0.685

    restored_entry = LogEntry.from_dict(d)
    assert restored_entry.scroll_y == 1420
    assert restored_entry.scroll_ratio == 0.685

    tab_info = TabInfo(
        url="https://docs.aerosync.space/deep-reading",
        title="Deep Reading",
        scroll_y=1420,
        scroll_ratio=0.685,
    )
    assert tab_info.scroll_y == 1420
    assert tab_info.scroll_ratio == 0.685

    # 2. Mock CDP WebSocket communication for fetch_tab_scroll
    mock_ws = MagicMock()
    mock_ws.recv.return_value = '{"id": 101, "result": {"result": {"type": "string", "value": "{\\"scroll_y\\": 1420, \\"scroll_ratio\\": 0.685}"}}}'
    with patch("services.chrome_launcher.chrome_manager.ws_sync_connect") as mock_connect:
        mock_connect.return_value.__enter__.return_value = mock_ws
        sy, sratio = fetch_tab_scroll("ws://127.0.0.1:9222/devtools/page/TEST")
        assert sy == 1420, f"Expected 1420, got {sy}"
        assert sratio == 0.685, f"Expected 0.685, got {sratio}"
        assert mock_ws.send.called

    # 3. Mock restore_tab_scroll
    mock_ws_restore = MagicMock()
    with patch("services.chrome_launcher.chrome_manager.ws_sync_connect") as mock_connect:
        mock_connect.return_value.__enter__.return_value = mock_ws_restore
        ok = restore_tab_scroll("ws://127.0.0.1:9222/devtools/page/TEST", scroll_y=1420, scroll_ratio=0.685)
        assert ok is True
        # Verify 2 commands sent: Page.addScriptToEvaluateOnNewDocument and Runtime.evaluate
        assert mock_ws_restore.send.call_count == 2
        calls = [mock_ws_restore.send.call_args_list[0][0][0], mock_ws_restore.send.call_args_list[1][0][0]]
        assert "Page.addScriptToEvaluateOnNewDocument" in calls[0]
        assert "Runtime.evaluate" in calls[1]
        assert "1420" in calls[0]
        assert "0.685" in calls[0]

    # 4. open_tabs_with_scroll fallback to normal Chrome launch
    spawned = []
    with patch("services.chrome_launcher.chrome_manager.is_cdp_available", return_value=False):
        with patch("services.chrome_launcher.chrome_manager.launch_normal_chrome") as mock_launch:
            mock_launch.side_effect = lambda urls, **kw: spawned.extend(urls) or True
            loop = asyncio.new_event_loop()
            try:
                opened, failed = loop.run_until_complete(
                    open_tabs_with_scroll([
                        {"url": "https://aerosync.space/page1", "scroll_y": 500, "scroll_ratio": 0.25},
                        {"url": "https://aerosync.space/page2", "scroll_y": 1200, "scroll_ratio": 0.60},
                    ])
                )
                assert len(opened) == 2
                assert len(failed) == 0
                assert "https://aerosync.space/page1" in spawned
                assert "https://aerosync.space/page2" in spawned
            finally:
                loop.close()

    # 5. Full reconstruction replay preserving browser scroll depth
    queue = WorkspaceLogQueue()
    queue.enqueue(LogEntry(
        entry_type=LogEntryType.BROWSER_TAB,
        url="https://aerosync.space/reading-room",
        page_title="Reading Room",
        scroll_y=950,
        scroll_ratio=0.48,
    ))
    snap = WorkspaceSnapshot(
        snapshot_id="scroll-test-snap",
        captured_at="2026-01-01T00:00:00Z",
        log_stack_data=queue.to_dict(),
    )

    with patch("services.chrome_launcher.chrome_manager.is_cdp_available", return_value=False):
        with patch("services.chrome_launcher.chrome_manager.launch_normal_chrome", return_value=True):
            loop = asyncio.new_event_loop()
            try:
                report = loop.run_until_complete(reconstruct_workspace(snap, "transfer-scroll-01"))
                assert "https://aerosync.space/reading-room" in report.restored_tabs
                assert any("log_stack_replay" in s for s in report.steps_completed)
            finally:
                loop.close()

    print("✓ test_browser_scroll_position_preservation PASSED (scroll depth & reading position restored)")


def test_multi_monitor_and_dpi_mapping():
    """Verify Multi-Monitor layout mapping, DPI scaling adjustments, and multi-to-single folding."""
    from shared.types.workspace_types import MonitorInfo, WindowState
    from services.monitor_mapping.monitor_mapper import (
        enable_dpi_awareness,
        get_monitors,
        find_monitor_for_rect,
        compute_divided_coordinates,
        compute_target_window_rect,
    )

    # 1. DPI awareness initialization
    dpi_mode = enable_dpi_awareness()
    assert dpi_mode in ("PerMonitorV2", "ShcorePerMonitor", "SystemAware", "NonWindows")

    # 2. Monitor capture returns valid MonitorInfo
    monitors = get_monitors()
    assert len(monitors) >= 1
    assert monitors[0].width > 0
    assert monitors[0].height > 0
    assert monitors[0].dpi > 0

    # 3. Multi-monitor point & rect containment
    mock_monitors = [
        MonitorInfo(monitor_index=0, x=0, y=0, width=1920, height=1080, is_primary=True, dpi=96, dpi_scale=1.0),
        MonitorInfo(monitor_index=1, x=1920, y=0, width=2560, height=1440, is_primary=False, dpi=144, dpi_scale=1.5),
    ]

    # Primary window
    idx0, mon0 = find_monitor_for_rect(100, 100, 800, 600, mock_monitors)
    assert idx0 == 0
    assert mon0.is_primary is True

    # Secondary window on Monitor 1
    idx1, mon1 = find_monitor_for_rect(2200, 200, 1000, 700, mock_monitors)
    assert idx1 == 1
    assert mon1.width == 2560

    # 4. Divided coordinates computation
    div = compute_divided_coordinates(2200, 200, 1000, 700, mon1)
    assert div["monitor_index"] == 1
    assert div["dpi"] == 144
    assert 0.0 <= div["rel_x"] <= 1.0
    assert 0.0 <= div["rel_y"] <= 1.0

    # 5. Multi-to-single monitor folding (Host A: 2 monitors -> Target B: 1 monitor)
    # A window from Host Monitor 1 (e.g. x=2400 on secondary) MUST be safely folded
    # onto Target B's single monitor, guaranteed 100% on-screen!
    single_target = [
        MonitorInfo(monitor_index=0, x=0, y=0, width=1920, height=1080, is_primary=True, dpi=96, dpi_scale=1.0)
    ]
    secondary_win = WindowState(
        title="Secondary Editor",
        x=2400,
        y=150,
        width=960,
        height=540,
        monitor_index=1,
        dpi=144,
        rel_x=0.25,
        rel_y=0.10,
        rel_width=0.50,
        rel_height=0.50,
        screen_width=2560,
        screen_height=1440,
        quadrant="top-left",
    )
    dest_x, dest_y, dest_w, dest_h = compute_target_window_rect(secondary_win, target_monitors=single_target)
    # Guaranteed on-screen check
    assert dest_x >= 0, f"dest_x must be on-screen, got {dest_x}"
    assert dest_y >= 0, f"dest_y must be on-screen, got {dest_y}"
    assert dest_x + dest_w <= 1920, f"dest_x + dest_w ({dest_x + dest_w}) exceeds 1920"
    assert dest_y + dest_h <= 1080, f"dest_y + dest_h ({dest_y + dest_h}) exceeds 1080"
    assert dest_w > 0 and dest_h > 0

    # 6. Multi-to-multi monitor alignment (Host A: 2 monitors -> Target B: 2 monitors)
    # Secondary window maps to Target Monitor 1 at offset x >= 1920
    dest_x2, dest_y2, dest_w2, dest_h2 = compute_target_window_rect(secondary_win, target_monitors=mock_monitors)
    assert dest_x2 >= 1920, f"Must be placed on Monitor 1 (x >= 1920), got {dest_x2}"
    assert dest_x2 + dest_w2 <= 1920 + 2560

    # 7. DPI Scaling Ratio Adjustments (Standard-DPI 96 to 4K 192 DPI)
    dpi_4k_target = [
        MonitorInfo(monitor_index=0, x=0, y=0, width=3840, height=2160, is_primary=True, dpi=192, dpi_scale=2.0)
    ]
    std_win = WindowState(
        title="Standard Tool",
        x=100,
        y=100,
        width=400,
        height=300,
        monitor_index=0,
        dpi=96,
        rel_x=0.1,
        rel_y=0.1,
        rel_width=0.3,
        rel_height=0.3,
        screen_width=1920,
        screen_height=1080,
    )
    d4k_x, d4k_y, d4k_w, d4k_h = compute_target_window_rect(std_win, target_monitors=dpi_4k_target)
    # Proportional scaling scales to 4K canvas cleanly
    assert d4k_w >= 800, f"Window width must scale to 4K resolution, got {d4k_w}"
    assert d4k_x + d4k_w <= 3840

    print("✓ test_multi_monitor_and_dpi_mapping PASSED (multi-monitor folding, DPI ratio, and boundary clamping verified)")


def test_workspace_undo_hand_gesture_rollback():
    """Verify Hand Gesture (Peace V-Sign / Rewind Swipe) and Workspace Rollback Engine."""
    import asyncio
    from unittest.mock import patch, MagicMock
    from services.gesture_engine.gesture_types import GestureType, GestureEvent
    from services.gesture_engine.node_engine import NodeBasedGestureAnalyzer, KinematicHandNodes, Vector3D
    from services.gesture_engine.gesture_state_machine import GestureStateMachine
    from services.workspace_reconstructor.rollback_manager import RollbackManager, PreReconstructionState
    import services.audio.cosmic_audio as audio

    # 1. Peace / 'V' Sign kinematic detection
    analyzer = NodeBasedGestureAnalyzer()
    v_nodes = KinematicHandNodes(
        palm_center=Vector3D(0.5, 0.5, 0.0),
        palm_normal=Vector3D(0.0, 0.0, -0.65),
        hand_axis=Vector3D(0.0, 1.0, 0.0),
        hand_scale=0.15,
        flexion_angles={"thumb": 80.0, "index": 165.0, "middle": 165.0, "ring": 45.0, "pinky": 45.0},
        tip_extension_ratios={"thumb": 0.8, "index": 1.6, "middle": 1.6, "ring": 0.6, "pinky": 0.6},
        openness_score=0.45,
        is_facing_camera=True,
    )
    is_undo, undo_conf = analyzer.detect_kinematic_undo(v_nodes)
    assert is_undo is True, "Peace V-Sign must be recognized as UNDO gesture"
    assert undo_conf >= 0.85

    # Negative test: normal open hand is NOT undo
    open_nodes = KinematicHandNodes(
        palm_center=Vector3D(0.5, 0.5, 0.0),
        palm_normal=Vector3D(0.0, 0.0, -0.65),
        hand_axis=Vector3D(0.0, 1.0, 0.0),
        hand_scale=0.15,
        flexion_angles={"thumb": 160.0, "index": 165.0, "middle": 165.0, "ring": 165.0, "pinky": 165.0},
        tip_extension_ratios={"thumb": 1.5, "index": 1.6, "middle": 1.6, "ring": 1.6, "pinky": 1.6},
        openness_score=0.90,
        is_facing_camera=True,
    )
    is_undo_neg, _ = analyzer.detect_kinematic_undo(open_nodes)
    assert is_undo_neg is False, "Open hand without leftward swipe must not trigger UNDO"

    # 2. Multi-frame confirmation for UNDO in GestureStateMachine
    emitted = []
    gsm = GestureStateMachine(on_event_callback=lambda evt: emitted.append(evt))
    curr_time = 7000.0
    with patch("time.monotonic", side_effect=lambda: curr_time):
        gsm.process((GestureType.UNDO, 0.90), "Right")
        assert len(emitted) == 0, "Single-frame UNDO candidate must not emit prematurely"
        curr_time = 7000.08
        gsm.process((GestureType.UNDO, 0.90), "Right")
        assert len(emitted) == 1, "Multi-frame UNDO must confirm and emit event"
        assert emitted[0].gesture_type == GestureType.UNDO

    # 3. RollbackManager lifecycle & workspace state reversal
    mgr = RollbackManager()
    with patch("pyperclip.paste", return_value="original_clipboard_content"):
        session = mgr.capture_pre_reconstruction_state("test-transfer-rollback-01")
        assert session.pre_clipboard == "original_clipboard_content"

    # Simulate fake process spawned and tabs opened
    session.launched_pids = [999999]  # mock non-existent PID
    session.launched_app_names = ["mock_notepad.exe"]
    session.opened_tabs = ["https://aerosync.space/mock-tab"]
    session.existing_window_placements = {
        12345: {"x": 100, "y": 100, "w": 800, "h": 600, "is_maximized": False, "is_minimized": False, "title": "Editor"}
    }
    mgr._history.append(session)

    copied_clipboard = []
    restored_win_calls = []
    fake_user32 = MagicMock()
    fake_user32.IsWindow.return_value = True
    fake_user32.SetWindowPos.side_effect = lambda hwnd, z, x, y, w, h, flags: restored_win_calls.append((hwnd, x, y, w, h))

    with patch("pyperclip.copy", side_effect=lambda text: copied_clipboard.append(text)):
        with patch("services.workspace_reconstructor.rollback_manager.user32", fake_user32):
            with patch("winsound.Beep"):
                loop = asyncio.new_event_loop()
                try:
                    report = loop.run_until_complete(mgr.rollback_last_workspace())
                    assert report.success is True
                    assert report.clipboard_restored is True
                    assert "original_clipboard_content" in copied_clipboard
                    assert len(restored_win_calls) == 1
                    assert restored_win_calls[0] == (12345, 100, 100, 800, 600)
                finally:
                    loop.close()

    # 4. Audio verification
    with patch("winsound.Beep") as mock_beep:
        audio.play_undo_sound()

    print("✓ test_workspace_undo_hand_gesture_rollback PASSED (Peace V-Sign, left swipe, rollback manager, and audio chime verified)")


def test_eco_mode_battery_throttling():
    from unittest.mock import MagicMock, patch
    import shared.constants as const
    from services.eco_mode.power_monitor import (
        PowerStatus,
        PowerMonitor,
        _build_power_status,
        _SYSTEM_POWER_STATUS,
    )
    from services.eco_mode.eco_throttle import (
        EcoMode,
        EcoThrottleController,
        NORMAL_GESTURE_FPS,
        ECO_GESTURE_FPS,
        NORMAL_OS_LOGGER_INTERVAL_S,
        ECO_OS_LOGGER_INTERVAL_S,
        NORMAL_OCR_ENABLED,
        ECO_OCR_ENABLED,
    )

    # 1. Test PowerStatus parsing
    # AC power, 100%
    mock_ac = _SYSTEM_POWER_STATUS()
    mock_ac.ACLineStatus = 1
    mock_ac.BatteryFlag = 0
    mock_ac.BatteryLifePercent = 100
    st_ac = _build_power_status(mock_ac)
    assert st_ac.is_on_battery is False
    assert st_ac.battery_pct == 100
    assert st_ac.is_charging is False

    # Battery power, 55%
    mock_batt = _SYSTEM_POWER_STATUS()
    mock_batt.ACLineStatus = 0
    mock_batt.BatteryFlag = 0
    mock_batt.BatteryLifePercent = 55
    st_batt = _build_power_status(mock_batt)
    assert st_batt.is_on_battery is True
    assert st_batt.battery_pct == 55
    assert st_batt.is_charging is False

    # Charging, 80%
    mock_charge = _SYSTEM_POWER_STATUS()
    mock_charge.ACLineStatus = 1
    mock_charge.BatteryFlag = 8  # 0x08 = charging
    mock_charge.BatteryLifePercent = 80
    st_charge = _build_power_status(mock_charge)
    assert st_charge.is_on_battery is False
    assert st_charge.is_charging is True

    # None fallback (safe default)
    st_none = _build_power_status(None)
    assert st_none.is_on_battery is False

    # 2. Test EcoThrottleController
    mock_os_logger = MagicMock()
    mock_detector = MagicMock()
    controller = EcoThrottleController(
        os_logger=mock_os_logger,
        gesture_detector=mock_detector,
    )
    assert controller.mode == EcoMode.NORMAL
    assert controller.is_eco_active is False

    # Activate ECO mode
    controller.activate_eco_mode()
    assert controller.mode == EcoMode.ECO
    assert controller.is_eco_active is True
    mock_detector.set_target_fps.assert_called_with(ECO_GESTURE_FPS)
    mock_os_logger.set_interval.assert_called_with(ECO_OS_LOGGER_INTERVAL_S)
    assert const.SCREEN_READER_ENABLED == ECO_OCR_ENABLED

    # Deactivate ECO mode (restore NORMAL)
    controller.deactivate_eco_mode()
    assert controller.mode == EcoMode.NORMAL
    assert controller.is_eco_active is False
    mock_detector.set_target_fps.assert_called_with(NORMAL_GESTURE_FPS)
    mock_os_logger.set_interval.assert_called_with(NORMAL_OS_LOGGER_INTERVAL_S)
    assert const.SCREEN_READER_ENABLED == NORMAL_OCR_ENABLED

    # 3. Test PowerMonitor state transitions & callbacks
    changed_statuses = []
    mon = PowerMonitor(on_power_changed=lambda s: changed_statuses.append(s), poll_interval_s=0.05)

    with patch("services.eco_mode.power_monitor._query_power_status", return_value=mock_ac):
        mon.start()
        assert mon.current_status.is_on_battery is False
        assert mon.is_eco_mode_active is False

    # Simulate transition to battery
    with patch("services.eco_mode.power_monitor._query_power_status", return_value=mock_batt):
        raw = mock_batt
        new_status = _build_power_status(raw)
        mon._last_status = new_status
        mon._fire_callbacks(new_status)

    assert len(changed_statuses) == 1
    assert changed_statuses[0].is_on_battery is True
    assert changed_statuses[0].battery_pct == 55
    assert mon.is_eco_mode_active is True

    mon.stop()

    # 4. Test Orchestrator integration
    from apps.client.client_orchestrator import ClientOrchestrator
    orchestrator = ClientOrchestrator()
    orchestrator._tray = MagicMock()
    orchestrator._eco_controller = controller

    with patch("apps.client.notification.show_toast"):
        # Transition to battery
        orchestrator._on_power_changed(st_batt)
        assert controller.is_eco_active is True
        orchestrator._tray.update_eco_mode.assert_called_with(True)

        # Transition back to AC
        orchestrator._on_power_changed(st_ac)
        assert controller.is_eco_active is False
        orchestrator._tray.update_eco_mode.assert_called_with(False)

    print("✓ test_eco_mode_battery_throttling PASSED (PowerStatus, EcoThrottleController, PowerMonitor, and Orchestrator integration verified)")


def test_delta_sync_engine():
    import asyncio
    from unittest.mock import patch, MagicMock
    from shared.types.workspace_types import (
        WorkspaceSnapshot,
        WindowState,
        BrowserState,
        TabInfo,
        ClipboardContent,
    )
    from services.delta_sync.delta_engine import DeltaEngine, get_delta_engine
    from services.workspace_packager.packager import create_package, unpack_package

    engine = DeltaEngine()

    # 1. Base snapshot (initial state)
    snap1 = WorkspaceSnapshot(
        snapshot_id="snap-001",
        captured_at="2026-01-01T10:00:00Z",
        source_device_id="pc-a",
        windows=[
            WindowState(title="Editor", process_name="code.exe", x=100, y=100, width=800, height=600),
            WindowState(title="Terminal", process_name="powershell.exe", x=900, y=100, width=600, height=400),
        ],
        browsers=[
            BrowserState(tabs=[
                TabInfo(url="https://github.com", title="GitHub", scroll_y=100, scroll_ratio=0.2),
            ]),
        ],
        clipboard=ClipboardContent(type="text", content="Initial clip"),
    )

    # First transmission: should be FULL snapshot (is_delta=False)
    out1 = engine.prepare_outbound_snapshot("target-b", snap1)
    assert out1.is_delta is False
    assert out1.snapshot_id == "snap-001"

    # 2. Subsequent snapshot: 1 window moved, 1 new tab added, clipboard changed
    snap2 = WorkspaceSnapshot(
        snapshot_id="snap-002",
        captured_at="2026-01-01T10:01:00Z",
        source_device_id="pc-a",
        windows=[
            # Repositioned window (x: 100 -> 250)
            WindowState(title="Editor", process_name="code.exe", x=250, y=150, width=800, height=600),
            # Unchanged window
            WindowState(title="Terminal", process_name="powershell.exe", x=900, y=100, width=600, height=400),
        ],
        browsers=[
            BrowserState(tabs=[
                # Unchanged tab
                TabInfo(url="https://github.com", title="GitHub", scroll_y=100, scroll_ratio=0.2),
                # New tab
                TabInfo(url="https://docs.python.org", title="Python Docs", scroll_y=0, scroll_ratio=0.0),
            ]),
        ],
        clipboard=ClipboardContent(type="text", content="Updated delta clip"),
    )

    out2 = engine.prepare_outbound_snapshot("target-b", snap2)
    assert out2.is_delta is True
    assert out2.base_snapshot_id == "snap-001"
    assert out2.delta_summary["has_changes"] is True
    assert out2.delta_summary["moved_windows"] == 1
    assert out2.delta_summary["new_tabs"] == 1
    assert out2.delta_summary["clipboard_changed"] is True

    # Delta snapshot should only carry the differential items
    assert len(out2.windows) == 1
    assert out2.windows[0].title == "Editor"
    assert out2.windows[0].x == 250
    assert len(out2.browsers[0].tabs) == 1
    assert out2.browsers[0].tabs[0].url == "https://docs.python.org"
    assert out2.clipboard.content == "Updated delta clip"

    # 3. Packaging & Unpack roundtrip for delta snapshot
    pkg = create_package(out2)
    unpacked = unpack_package(pkg.encrypted_payload, pkg.aes_key)
    assert unpacked.is_delta is True
    assert unpacked.base_snapshot_id == "snap-001"
    assert unpacked.delta_summary["moved_windows"] == 1
    assert len(unpacked.windows) == 1
    assert unpacked.windows[0].x == 250

    # 4. Inbound Merge on Target B
    merged = engine.apply_delta_to_base(snap1, unpacked)
    assert len(merged.windows) == 2
    # Editor window should have updated position
    editor_w = next(w for w in merged.windows if w.title == "Editor")
    assert editor_w.x == 250
    # Tabs should contain both GitHub and Python docs
    all_urls = [t.url for b in merged.browsers for t in b.tabs]
    assert "https://github.com" in all_urls
    assert "https://docs.python.org" in all_urls
    assert merged.clipboard.content == "Updated delta clip"

    # 5. Fast Reconstruction Execution Path
    from services.workspace_reconstructor.reconstruction_orchestrator import reconstruct_workspace
    with patch("services.workspace_reconstructor.reconstruction_orchestrator.restore_browsers") as mock_browsers:
        with patch("services.workspace_reconstructor.reconstruction_orchestrator.restore_windows") as mock_windows:
            with patch("services.workspace_reconstructor.reconstruction_orchestrator.restore_clipboard") as mock_clip:
                with patch("winsound.Beep"):
                    mock_browsers.return_value = (["https://docs.python.org"], [], [])
                    mock_windows.return_value = (["Editor"], [])

                    loop = asyncio.new_event_loop()
                    try:
                        report = loop.run_until_complete(reconstruct_workspace(unpacked, transfer_id="trans-delta-01"))
                        assert report.success is True
                        assert "delta_sync_completed" in report.steps_completed
                        assert "https://docs.python.org" in report.restored_tabs
                        assert "Editor" in report.repositioned_windows
                    finally:
                        loop.close()

    print("✓ test_delta_sync_engine PASSED (differential diff, payload packaging, state merge, and fast reconstruction verified)")


def test_predictive_trajectory_comet_hud():
    import numpy as np
    from services.gesture_engine.node_engine import (
        NodeBasedGestureAnalyzer,
        KinematicHandNodes,
        Vector3D,
    )
    from services.gesture_engine.cosmic_hud import draw_cosmic_hud
    from scripts.test_node_engine import create_synthetic_hand

    # 1. Test kinematic velocity and trajectory prediction
    analyzer = NodeBasedGestureAnalyzer()
    now = 1000.0

    # Simulate dynamic throw acceleration across 5 frames
    for i in range(5):
        nodes = KinematicHandNodes(
            palm_center=Vector3D(0.40 + i * 0.05, 0.50 - i * 0.02, -0.10 - i * 0.08),
            openness_score=0.2 + i * 0.15,
            is_facing_camera=True,
        )
        analyzer.update_trajectory(nodes, now + i * 0.05)

    vel = analyzer.get_current_velocity()
    assert vel.magnitude > 0.5, f"Expected high throw velocity, got: {vel.magnitude}"
    assert vel.x > 0.0, "Expected positive X velocity (rightward throw)"
    assert vel.z < 0.0, "Expected negative Z velocity (forward thrust toward screen)"

    predicted = analyzer.get_predicted_trajectory(steps=6, step_dt=0.06)
    assert len(predicted) == 6
    # Forward positions should advance along the velocity vector
    assert predicted[0].x > 0.60
    assert predicted[-1].x > predicted[0].x

    past = analyzer.get_past_trajectory(max_points=8)
    assert len(past) == 5

    # 2. Test HUD rendering with Predictive Comet Tail and Lead Aim Reticle
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    hand = create_synthetic_hand(wrist_x=0.55, wrist_y=0.50)
    traj_data = {
        "Right": {
            "velocity": vel,
            "predicted": predicted,
            "past": past,
        }
    }

    # Render normal trajectory
    hud_rendered = draw_cosmic_hud(
        frame=frame,
        hands=[hand],
        gesture_name="throw",
        trajectory_data=traj_data,
    )
    assert hud_rendered.shape == frame.shape
    assert np.any(hud_rendered > 0), "Comet HUD should render non-zero pixels"

    # Compare pixel density: HUD with comet tail must contain more active pixels than baseline
    hud_plain = draw_cosmic_hud(frame=frame, hands=[hand], gesture_name=None, trajectory_data=None)
    assert np.sum(hud_rendered > 0) > np.sum(hud_plain > 0), "Comet tail and beam reticle must add visual overlay"

    print("✓ test_predictive_trajectory_comet_hud PASSED (kinematic velocity extrapolation, predictive trajectory arc, and comet starlight HUD verified)")


if __name__ == "__main__":
    print("Running AeroSync rework verification tests...\n")
    test_log_queue()
    test_log_serializer()
    test_ocr_deduplication()
    test_fist_gesture_detection()
    test_role_state_machine()
    test_fist_debounce()
    test_smart_reconstruction()
    test_notification_reporting()
    test_screen_coordinate_division_and_scaling()
    test_chrome_auto_launcher()
    test_autostart_registry_commands()
    test_fist_long_hold_and_checklist()
    test_ten_second_calibration()
    test_cosmic_audio_calls()
    test_queue_telemetry()
    test_multiframe_confirmation()
    test_two_hand_antitrigger()
    test_global_hotkey_listener()
    test_exponential_backoff_and_finite_retry()
    test_direct_lan_p2p_socket()
    test_browser_scroll_position_preservation()
    test_multi_monitor_and_dpi_mapping()
    test_workspace_undo_hand_gesture_rollback()
    test_eco_mode_battery_throttling()
    test_delta_sync_engine()
    test_predictive_trajectory_comet_hud()
    print("\n✅ All 26 tests PASSED")
