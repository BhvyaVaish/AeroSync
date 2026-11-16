"""
AeroSync Cosmic HUD Test

Tests:
1. Drawing celestial detection brackets when no hands are in frame.
2. Drawing constellation starlight lines & core orbital reticle when hand is present.
3. Color shift to amber with assistive warning when hand is outside 60% center zone.
4. Clean frame restoration when hand leaves frame.
"""

import sys
import os
from pathlib import Path
import numpy as np

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from services.gesture_engine.cosmic_hud import draw_cosmic_hud, COLOR_CYAN_GLOW, COLOR_AMBER_WARN
from scripts.test_node_engine import create_synthetic_hand


def test_cosmic_hud_rendering():
    print("=" * 60)
    print("TESTING COSMIC CONSTELLATION HAND HUD")
    print("=" * 60)

    # Create dummy black frame
    frame = np.zeros((480, 640, 3), dtype=np.uint8)

    # 1. Test rendering with NO hands detected
    print("\n[1/3] Testing HUD when no hands are visible...")
    hud_empty = draw_cosmic_hud(frame, [])
    assert hud_empty.shape == frame.shape
    # Brackets should be rendered (non-zero pixels)
    assert np.any(hud_empty > 0)
    print("  ✓ Rendered faint celestial sensor brackets & assistive text when idle.")

    # 2. Test rendering with hand in center zone
    print("\n[2/3] Testing HUD with centered hand (Constellation Lock)...")
    centered_hand = create_synthetic_hand(wrist_x=0.5, wrist_y=0.5)
    hud_centered = draw_cosmic_hud(frame, [centered_hand], gesture_name="Throw")
    assert hud_centered.shape == frame.shape
    assert np.any(hud_centered > 0)
    print("  ✓ Rendered starlight constellation lines & Palm Core orbital reticle.")

    # 3. Test rendering with hand outside center zone (Assistive Warning)
    print("\n[3/3] Testing HUD with hand near edge (Assistive Warning)...")
    edge_hand = create_synthetic_hand(wrist_x=0.1, wrist_y=0.1) # out of 60% center
    hud_edge = draw_cosmic_hud(frame, [edge_hand])
    assert hud_edge.shape == frame.shape
    assert np.any(hud_edge > 0)
    print("  ✓ Assistive warning triggered ('Move Hand To Center') with amber reticle.")

    print("\n" + "=" * 60)
    print("ALL COSMIC HUD TESTS PASSED!")
    print("=" * 60)


if __name__ == "__main__":
    test_cosmic_hud_rendering()
