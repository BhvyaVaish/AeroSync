"""
AeroSync Workspace Packager

Serializes, compresses, and encrypts the WorkspaceSnapshot into a TransferPackage.
Provides reverse operations to unpack the package.
"""

import dataclasses
import json
import logging
import zlib
from typing import Optional

from shared.constants import COMPRESSION_LEVEL, PACKAGE_VERSION
from shared.types.workspace_types import WorkspaceSnapshot
from shared.utils.crypto import aes_encrypt, aes_decrypt, generate_aes_key, sha256_hash
from services.workspace_packager.schema import PackageHeader, TransferPackage

logger = logging.getLogger(__name__)


def create_package(snapshot: WorkspaceSnapshot) -> TransferPackage:
    """
    Package a WorkspaceSnapshot for transfer.
    
    Pipeline:
    1. Serialize snapshot to JSON
    2. Compress JSON with zlib
    3. Generate random AES key
    4. Encrypt compressed data with AES-GCM
    5. Calculate SHA-256 checksum of encrypted payload
    6. Construct package with header
    
    Args:
        snapshot: The workspace snapshot to package.
        
    Returns:
        TransferPackage containing the encrypted payload and the key.
    """
    logger.debug(f"Packaging snapshot {snapshot.snapshot_id}")
    
    # 1. Serialize
    snapshot_dict = dataclasses.asdict(snapshot)
    json_bytes = json.dumps(snapshot_dict).encode("utf-8")
    original_size = len(json_bytes)
    
    # 2. Compress
    compressed_bytes = zlib.compress(json_bytes, level=COMPRESSION_LEVEL)
    compressed_size = len(compressed_bytes)
    
    # 3. Generate key
    aes_key = generate_aes_key()
    
    # 4. Encrypt
    encrypted_payload = aes_encrypt(compressed_bytes, aes_key)
    
    # 5. Checksum
    checksum = sha256_hash(encrypted_payload)
    
    # 6. Build package
    header = PackageHeader(
        version=PACKAGE_VERSION,
        checksum_sha256=checksum,
        timestamp_iso=snapshot.captured_at,
        source_device_id=snapshot.source_device_id
    )
    
    # Serialize header to bytes (fixed format or JSON prefix)
    # For simplicity, we just return the TransferPackage object, 
    # the actual file upload format will be the encrypted payload bytes,
    # and the header metadata is sent via the API.
    
    package = TransferPackage(
        header=header,
        encrypted_payload=encrypted_payload,
        aes_key=aes_key
    )
    
    logger.info(
        f"Packaged snapshot {snapshot.snapshot_id}. "
        f"Size: {original_size}B -> {compressed_size}B (compressed) -> {len(encrypted_payload)}B (encrypted)"
    )
    
    return package


def unpack_package(encrypted_payload: bytes, aes_key: bytes, expected_checksum: Optional[str] = None) -> WorkspaceSnapshot:
    """
    Unpack a received encrypted payload.
    
    Pipeline:
    1. Verify checksum (if provided)
    2. Decrypt with AES-GCM
    3. Decompress with zlib
    4. Parse JSON
    5. Construct WorkspaceSnapshot
    
    Args:
        encrypted_payload: The encrypted bytes.
        aes_key: The AES key required to decrypt.
        expected_checksum: Optional expected SHA-256 checksum from the API metadata.
        
    Returns:
        WorkspaceSnapshot object.
        
    Raises:
        ValueError: If checksum verification fails or decryption fails.
    """
    # 1. Verify checksum if provided
    if expected_checksum:
        actual_checksum = sha256_hash(encrypted_payload)
        if actual_checksum != expected_checksum:
            raise ValueError(f"Checksum mismatch. Expected {expected_checksum}, got {actual_checksum}")
        
    # 2. Decrypt
    try:
        compressed_bytes = aes_decrypt(encrypted_payload, aes_key)
    except Exception as e:
        raise ValueError(f"Failed to decrypt package: {e}")
        
    # 3. Decompress
    try:
        json_bytes = zlib.decompress(compressed_bytes)
    except Exception as e:
        raise ValueError(f"Failed to decompress package: {e}")
        
    # 4 & 5. Parse and construct
    try:
        data = json.loads(json_bytes.decode("utf-8"))
        # We need to properly reconstruct the nested dataclasses
        from shared.types.workspace_types import BrowserState, WindowState, MonitorInfo, ClipboardContent, TabInfo
        
        # Helper to convert dicts to dataclasses
        browsers = []
        for b in data.get("browsers", []):
            tabs = [TabInfo(**t) for t in b.get("tabs", [])]
            b_copy = b.copy()
            b_copy["tabs"] = tabs
            browsers.append(BrowserState(**b_copy))
            
        windows = [WindowState(**w) for w in data.get("windows", [])]
        monitors = [MonitorInfo(**m) for m in data.get("monitors", [])]
        
        clipboard_data = data.get("clipboard")
        clipboard = ClipboardContent(**clipboard_data) if clipboard_data else ClipboardContent()

        # Reconstruct screen_content and action_plan if present
        screen_content = None
        sc_data = data.get("screen_content")
        if sc_data:
            from shared.types.screen_types import ScreenContent, ScreenRegion
            reg_data = sc_data.get("region", {})
            region = ScreenRegion(**reg_data) if reg_data else ScreenRegion()
            screen_content = ScreenContent(
                region=region,
                ocr_text=sc_data.get("ocr_text", ""),
                screenshot_base64=sc_data.get("screenshot_base64", ""),
                captured_at=sc_data.get("captured_at", ""),
                ocr_confidence=sc_data.get("ocr_confidence", 0.0),
                is_full_screen=sc_data.get("is_full_screen", True),
            )

        action_plan = None
        ap_data = data.get("action_plan")
        if ap_data:
            from shared.types.screen_types import ActionPlan, ActionItem
            actions = [ActionItem(**a) for a in ap_data.get("actions", [])]
            action_plan = ActionPlan(
                actions=actions,
                summary=ap_data.get("summary", ""),
                overall_confidence=ap_data.get("overall_confidence", 0.0),
                fallback_used=ap_data.get("fallback_used", False),
            )

        snapshot = WorkspaceSnapshot(
            snapshot_id=data.get("snapshot_id", ""),
            captured_at=data.get("captured_at", ""),
            source_device_id=data.get("source_device_id", ""),
            source_platform=data.get("source_platform", "windows"),
            browsers=browsers,
            windows=windows,
            monitors=monitors,
            clipboard=clipboard,
            capture_duration_ms=data.get("capture_duration_ms", 0),
            capture_warnings=data.get("capture_warnings", []),
            screen_content=screen_content,
            action_plan=action_plan,
            log_stack_data=data.get("log_stack_data"),
            is_delta=data.get("is_delta", False),
            base_snapshot_id=data.get("base_snapshot_id"),
            delta_summary=data.get("delta_summary"),
        )
        return snapshot
        
    except Exception as e:
        raise ValueError(f"Failed to parse snapshot data: {e}")


# Simple test block
if __name__ == "__main__":
    import asyncio
    from services.workspace_capture.capture_orchestrator import capture_workspace
    
    async def run_test():
        print("Capturing workspace...")
        snapshot = await capture_workspace()
        
        print("Packaging...")
        package = create_package(snapshot)
        
        print(f"Encrypted size: {package.total_size_bytes} bytes")
        print(f"Checksum: {package.header.checksum_sha256}")
        
        print("Unpackaging...")
        restored = unpack_package(
            package.encrypted_payload, 
            package.aes_key, 
            package.header.checksum_sha256
        )
        
        print(f"Restored snapshot ID: {restored.snapshot_id}")
        assert restored.snapshot_id == snapshot.snapshot_id
        assert len(restored.windows) == len(snapshot.windows)
        print("Round-trip successful!")
        
    asyncio.run(run_test())
