"""
AeroSync Transfer Receiver

Orchestrates receiving and reconstructing a workspace.
"""

import logging

from apps.client.relay_client import RelayClient
from apps.client.notification import show_toast
from services.workspace_packager.packager import unpack_package
from services.workspace_reconstructor.reconstruction_orchestrator import reconstruct_workspace

logger = logging.getLogger(__name__)


async def receive_workspace(relay: RelayClient, transfer_id: str) -> bool:
    """
    Accept, download, unpack, and reconstruct an incoming workspace transfer.
    
    Args:
        relay: Authenticated RelayClient.
        transfer_id: The ID of the pending transfer.
        
    Returns:
        True if successful, False otherwise.
    """
    logger.info(f"Receiving workspace transfer: {transfer_id}")
    show_toast("Incoming Transfer", "Receiving workspace...")
    
    try:
        # 1. Accept Session (gets the decryption key)
        encrypted_key_hex, error = await relay.accept_session(transfer_id)
        if error or not encrypted_key_hex:
            logger.error(f"Failed to accept session: {error}")
            show_toast("Transfer Failed", "Could not accept transfer.")
            await relay.complete_session(transfer_id, False, str(error))
            return False
            
        aes_key = bytes.fromhex(encrypted_key_hex)
            
        # 2. Download Package
        show_toast("AeroSync", "Downloading package...")
        package_bytes, error = await relay.download_package(transfer_id)
        if error or not package_bytes:
            logger.error(f"Failed to download package: {error}")
            show_toast("Transfer Failed", "Could not download workspace.")
            await relay.complete_session(transfer_id, False, str(error))
            return False
            
        # 3. Unpack & Decrypt
        show_toast("AeroSync", "Reconstructing workspace...")
        try:
            snapshot = unpack_package(package_bytes, aes_key)
        except Exception as e:
            logger.error(f"Failed to unpack/decrypt: {e}")
            show_toast("Transfer Failed", "Failed to decrypt workspace.")
            await relay.complete_session(transfer_id, False, "Decryption failed")
            return False
            
        # 4. Reconstruct Workspace (sends detailed toast notification including failed items)
        report = await reconstruct_workspace(snapshot, transfer_id=transfer_id)

        # Cosmic arrival chime: Data thrown, received & reconstructed on Target B
        try:
            from services.audio.cosmic_audio import play_throw_received_sound
            play_throw_received_sound()
        except Exception:
            pass
        
        # 5. Mark Complete
        await relay.complete_session(transfer_id, report.success)
        logger.info(
            f"Reconstruction complete for {transfer_id}: success={report.success}, "
            f"launched={len(report.launched_apps)}, tabs={len(report.restored_tabs)}, "
            f"failed={len(report.failed_items)}"
        )
        return report.success
        
    except Exception as e:
        logger.error(f"Unexpected error receiving transfer: {e}")
        show_toast("Transfer Error", "An unexpected error occurred.")
        await relay.complete_session(transfer_id, False, str(e))
        return False
