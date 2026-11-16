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
) -> bool:
    """
    Capture, package, and send the workspace to a target device.

    Args:
        relay:              Authenticated RelayClient.
        target_device_id:  Destination device ID.  When None, the relay routes
                           within the constellation (target_claiming message
                           already told the relay who to route to).
        region:            Optional ScreenRegion to crop screen capture.
        log_stack:         Pre-warmed WorkspaceLogQueue from the OS Logger
                           (already populated at 1 Hz; instant access on FIST).
        log_exclusion_set: Content-ID set from the log stack for OCR dedup.

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

        # 3. Package & Encrypt
        package = create_package(snapshot)
        logger.info("Packaged size: %d bytes", package.total_size_bytes)

        # Celestial audio chime: Data fully packed & armed on Host A
        try:
            from services.audio.cosmic_audio import play_capture_packed_sound
            play_capture_packed_sound()
        except Exception:
            pass

        # 4. Initiate Session on relay
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
