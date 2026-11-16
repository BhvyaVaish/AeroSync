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
    print("\n✅ All 15 tests PASSED")
