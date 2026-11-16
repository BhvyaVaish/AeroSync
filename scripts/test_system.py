import asyncio
import os
import sys

# Add project root to sys.path
sys.path.insert(0, os.path.abspath("."))

from services.workspace_capture.capture_orchestrator import capture_workspace
from services.workspace_packager.packager import create_package, unpack_package
from services.workspace_reconstructor.reconstruction_orchestrator import reconstruct_workspace
from shared.types.workspace_types import WorkspaceSnapshot, WindowState, TabInfo, BrowserState, ClipboardContent
from shared.types.screen_types import ActionPlan, ActionItem

async def main():
    print("=== Testing Capture ===")
    snapshot = await capture_workspace()
    print(f"Captured {len(snapshot.windows)} windows, {len(snapshot.browsers)} browsers, {len(snapshot.monitors)} monitors")
    
    print("\n=== Testing Packager & Crypto ===")
    package = create_package(snapshot)
    print(f"Package created: {len(package.encrypted_payload)} bytes encrypted, key length: {len(package.aes_key)}")
    
    unpacked = unpack_package(package.encrypted_payload, package.aes_key, package.header.checksum_sha256)
    print(f"Package unpacked successfully! ID: {unpacked.snapshot_id}")
    assert unpacked.snapshot_id == snapshot.snapshot_id
    print("Packager roundtrip: PASS")

    print("\n=== Testing Reconstruction with Mock Windows/Tabs/Clipboard ===")
    mock_snapshot = WorkspaceSnapshot(
        snapshot_id="test-mock-snap",
        captured_at="2026-11-15T12:00:00Z",
        source_device_id="dev-1",
        source_platform="windows",
        browsers=[
            BrowserState(
                browser_type="chrome",
                tabs=[TabInfo(url="https://github.com", title="GitHub")]
            )
        ],
        windows=[
            WindowState(
                title="Notepad",
                process_name="notepad.exe",
                x=100,
                y=100,
                width=800,
                height=600
            )
        ],
        monitors=[],
        clipboard=ClipboardContent(type="text", content="AeroSync Test Clipboard"),
        action_plan=ActionPlan(
            actions=[
                ActionItem(type="create_text_file", content="AeroSync Reconstructed Text", filename_hint="reconstruct_test"),
            ],
            summary="Reconstruct screen content",
            overall_confidence=0.9,
        ),
    )
    mock_pkg = create_package(mock_snapshot)
    mock_unpacked = unpack_package(mock_pkg.encrypted_payload, mock_pkg.aes_key, mock_pkg.header.checksum_sha256)
    report2 = await reconstruct_workspace(mock_unpacked, transfer_id="test-transfer-456")
    print("Mock Reconstruction report:", report2)
    print("Mock Steps completed:", report2.steps_completed)
    print("Mock Steps failed:", report2.steps_failed)
    print("Mock Warnings:", report2.warnings)

    # Clean up any created test text file on Desktop
    import glob
    for f in glob.glob(os.path.expanduser("~/Desktop/AeroSync_*_reconstruct_test.txt")):
        try:
            os.remove(f)
        except Exception:
            pass

if __name__ == "__main__":
    asyncio.run(main())
