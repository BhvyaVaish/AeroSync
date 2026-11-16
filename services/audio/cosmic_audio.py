"""
AeroSync Cosmic Audio Engine

Generates celestial, non-blocking audio feedback for gesture events,
transfer phases, and calibration.

Sounds:
  • play_capture_packed_sound(): Host A — Ascending celestial warp chime
    (Triggered when Host A finishes packing workspace, ready for transfer)
  • play_throw_received_sound(): Target B — Harmonious cosmic arrival chime
    (Triggered when Target B receives package and finishes workspace reconstruction)
  • play_fist_detect_sound(): Subtle arming blip
  • play_calibration_step_sound(): Pulse for calibration milestones
"""

import logging
import sys
import threading
import time

logger = logging.getLogger(__name__)


def _play_beeps(notes: list[tuple[int, int]], pause_s: float = 0.02) -> None:
    """Helper to play a sequence of (frequency_hz, duration_ms) tones on Windows."""
    if sys.platform != "win32":
        return

    try:
        import winsound
        for freq, dur in notes:
            winsound.Beep(max(37, min(32767, int(freq))), max(10, int(dur)))
            if pause_s > 0:
                time.sleep(pause_s)
    except Exception as exc:
        logger.debug("[CosmicAudio] Audio playback failed: %s", exc)


def _async_play(notes: list[tuple[int, int]], pause_s: float = 0.02) -> None:
    """Play notes asynchronously in a background daemon thread."""
    t = threading.Thread(
        target=_play_beeps,
        args=(notes, pause_s),
        name="CosmicAudioThread",
        daemon=True
    )
    t.start()


def play_capture_packed_sound() -> None:
    """
    Host A Sound: Data fully captured, packed & armed for transfer.
    Ascending energetic celestial warp arpeggio (C5 -> E5 -> G5 -> C6).
    """
    logger.info("[CosmicAudio] Playing Capture & Packed chime (Host A)")
    # (Frequency Hz, Duration ms)
    notes = [
        (523, 70),   # C5
        (659, 70),   # E5
        (784, 80),   # G5
        (1046, 160), # C6 (high resonant ring)
    ]
    _async_play(notes, pause_s=0.015)


def play_throw_received_sound() -> None:
    """
    Target B Sound: Data thrown, received & workspace reconstructed.
    Triumphant cosmic beam landing harmonic (A5 -> E5 -> D5 -> A5).
    """
    logger.info("[CosmicAudio] Playing Throw & Received chime (Target B)")
    notes = [
        (880, 80),   # A5
        (659, 80),   # E5
        (587, 90),   # D5
        (880, 200),  # A5 (long triumph landing)
    ]
    _async_play(notes, pause_s=0.02)


def play_fist_detect_sound() -> None:
    """Subtle confirmation tone when Fist gesture is held and confirmed."""
    notes = [
        (440, 50),
        (880, 90),
    ]
    _async_play(notes, pause_s=0.01)


def play_fist_long_sound() -> None:
    """Checklist popup chime when Long Fist (2s+) is held."""
    notes = [
        (440, 60),
        (554, 60),
        (659, 120),
    ]
    _async_play(notes, pause_s=0.02)


def play_calibration_step_sound(step: int = 1) -> None:
    """Pulse chime during user calibration progress (step 1=start, 2=phase2, 3=complete)."""
    if step == 3:
        # Complete
        notes = [(587, 60), (784, 80), (1174, 160)]
    elif step == 2:
        # Phase 2
        notes = [(659, 50), (880, 70)]
    else:
        # Step 1
        notes = [(523, 50), (659, 60)]
    _async_play(notes, pause_s=0.015)


def play_undo_sound() -> None:
    """
    Workspace Undo / Rollback Sound:
    Descending celestial rewind harmonic (C6 -> G5 -> E5 -> C5).
    Plays when workspace rollback is triggered via Undo gesture or shortcut.
    """
    logger.info("[CosmicAudio] Playing Workspace Undo / Rollback chime")
    notes = [
        (1046, 70),  # C6
        (784, 70),   # G5
        (659, 80),   # E5
        (523, 160),  # C5 (deep settling tone)
    ]
    _async_play(notes, pause_s=0.015)
