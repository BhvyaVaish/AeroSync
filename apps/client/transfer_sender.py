"""
AeroSync Transfer Sender

Orchestrates the outbound transfer of a workspace from Host A to Target B.

Steps:
  1. Capture live workspace (browser tabs, windows, clipboard, screen OCR)
     — using the pre-built OS log stack for fast, pre-warmed data
  2. Embed the log stack into the WorkspaceSnapshot
  3. Package & AES-256-GCM encrypt the snapshot
  4. Initiate a session on the relay server
  5. Upload the encrypted package
  6. Mark as uploaded (sends transfer notification to Target B)
"""

import logging
from typing import Optional, Set

from apps.client.relay_client import RelayClient
from apps.client.notification import show_toast
from services.workspace_capture.capture_orchestrator import capture_workspace
from services.workspace_packager.packager import create_package

logger = logging.getLogger(__name__)


async def send_workspace(
    relay: RelayClient,
    target_device_id: Optional[str],
    region=None,
    log_stack=None,
    log_exclusion_set: Optional[Set[str]] = None,
    target_lan_endpoint: Optional[dict] = None,
) -> bool:
    """
    Capture, package, and send the workspace to a target device.

    Args:
        relay:               Authenticated RelayClient.
        target_device_id:    Destination device ID.
        region:              Optional ScreenRegion to crop screen capture.
        log_stack:           Pre-warmed WorkspaceLogQueue from the OS Logger.
        log_exclusion_set:   Content-ID set from the log stack for OCR dedup.
        target_lan_endpoint: Optional direct LAN socket endpoint (ip, port) for Gigabit P2P transfer.

    Returns:
        True if successfully sent, False otherwise.
    """
    logger.info("Starting workspace transfer to %s", target_device_id)
    show_toast("AeroSync", "Capturing workspace…")

    try:
        # 1. Capture Workspace (OS log already warm; OCR deduplicates against it)
        snapshot = await capture_workspace(
            screen_region=region,
            log_exclusion_set=log_exclusion_set or set(),
        )

        # 2. Embed log stack data into snapshot (so Target B can replay the stack)
        if log_stack is not None:
            try:
                snapshot.log_stack_data = log_stack.to_dict()
                logger.info(
                    "Embedded log stack: %d entries into snapshot",
                    log_stack.size,
                )
            except Exception as exc:
                logger.warning("Failed to embed log stack: %s", exc)

        # 2b. Delta Sync: prepare differential snapshot if base exists
        try:
            from services.delta_sync.delta_engine import get_delta_engine
            delta_engine = get_delta_engine()
            snapshot = delta_engine.prepare_outbound_snapshot(target_device_id, snapshot)
            if snapshot.is_delta:
                logger.info(
                    "[DeltaSync] Beaming DIFFERENTIAL snapshot (base=%s): %s",
                    snapshot.base_snapshot_id,
                    snapshot.delta_summary,
                )
                show_toast("AeroSync ⚡ Delta Sync", "Beaming modified workspace changes…")
            else:
                logger.info("[DeltaSync] Beaming FULL baseline snapshot (%s)", snapshot.snapshot_id)
        except Exception as exc:
            logger.debug("[DeltaSync] Delta prep failed (proceeding full): %s", exc)

        # 3. Package & Encrypt
        package = create_package(snapshot)
        logger.info("Packaged size: %d bytes", package.total_size_bytes)

        # Celestial audio chime: Data fully packed & armed on Host A
        try:
            from services.audio.cosmic_audio import play_capture_packed_sound
            play_capture_packed_sound()
        except Exception:
            pass

        # 4a. Zero-Cloud Direct Gigabit LAN P2P Transfer (Priority 1)
        if target_lan_endpoint:
            lan_ip = target_lan_endpoint.get("ip")
            lan_port = target_lan_endpoint.get("port")
            if lan_ip and lan_port:
                logger.info("[LanP2P] Attempting direct LAN socket beam to %s:%d", lan_ip, lan_port)
                show_toast("AeroSync P2P", "Direct LAN Gigabit Beam connecting…")
                from services.lan_transfer.lan_p2p import LanP2PSender
                p2p_ok = await LanP2PSender.send_direct_lan(
                    ip=lan_ip,
                    port=lan_port,
                    transfer_id="lan-" + (target_device_id or "p2p"),
                    aes_key=package.aes_key,
                    encrypted_payload=package.encrypted_payload,
                    timeout_s=2.0,
                )
                if p2p_ok:
                    logger.info("[LanP2P] Direct LAN P2P transfer successful! Zero-cloud gigabit transfer complete ⚡")
                    show_toast("AeroSync ⚡", "Gigabit Direct LAN Beam Complete! (Zero-Cloud)")
                    return True
                else:
                    logger.info("[LanP2P] Direct LAN connection unavailable or timed out — seamlessly falling back to Relay Server")

        # 4b. Fallback: Initiate Session on relay
        transfer_id, error = await relay.initiate_session(target_device_id)
        if error:
            logger.error("Failed to initiate session: %s", error)
            show_toast("Transfer Failed", "Could not initiate transfer with server.")
            return False

        logger.info("Session initiated: %s", transfer_id)
        show_toast("AeroSync", "Uploading workspace package…")

        # 5. Upload Package Binary
        success, error = await relay.upload_package(transfer_id, package.encrypted_payload)
        if not success:
            logger.error("Upload failed: %s", error)
            show_toast("Transfer Failed", "Upload failed.")
            return False

        # 6. Notify relay: upload complete, deliver decryption key to target
        # In full E2EE the AES key would be encrypted with the target's public key.
        # For this self-hosted MVP, it travels over the HTTPS relay channel.
        key_hex = package.aes_key.hex()
        success, error = await relay.mark_uploaded(transfer_id, package.total_size_bytes, key_hex)
        if not success:
            logger.error("Failed to mark as uploaded: %s", error)
            show_toast("Transfer Failed", "Failed to finalize upload.")
            return False

        logger.info("Workspace successfully sent to %s", target_device_id)
        show_toast("Transfer Complete ✅", "Workspace sent successfully!")
        return True

    except Exception as exc:
        logger.error("Unexpected error during transfer: %s", exc)
        show_toast("Transfer Error", "An unexpected error occurred.")
        return False
