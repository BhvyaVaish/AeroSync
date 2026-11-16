"""
AeroSync Client Entry Point
"""

import argparse
import asyncio
import logging
import sys

from apps.client import storage
from apps.client.client_orchestrator import ClientOrchestrator
from shared.utils.logger import setup_logging

logger = logging.getLogger(__name__)


async def main():
    parser = argparse.ArgumentParser(description="AeroSync Client")
    parser.add_argument("--server", default="http://127.0.0.1:8000", help="Relay Server URL")
    parser.add_argument("--tray", action="store_true", help="Launch directly into Windows System Tray mode")
    parser.add_argument("--enable-autostart", action="store_true", help="Configure Windows to auto-start AeroSync at login and exit")
    parser.add_argument("--disable-autostart", action="store_true", help="Remove AeroSync from Windows startup and exit")
    args = parser.parse_args()
    
    setup_logging(level=logging.INFO)

    if args.enable_autostart:
        from apps.client.autostart import enable_autostart
        ok = enable_autostart()
        print("AeroSync auto-start enabled:", ok)
        return

    if args.disable_autostart:
        from apps.client.autostart import disable_autostart
        ok = disable_autostart()
        print("AeroSync auto-start disabled:", ok)
        return
    
    # Save server URL config
    storage.set_server_url(args.server)
    
    orchestrator = ClientOrchestrator()
    
    try:
        await orchestrator.start()
    except KeyboardInterrupt:
        logger.info("Interrupted by user. Shutting down...")
    finally:
        await orchestrator.stop()


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
