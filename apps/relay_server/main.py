"""
AeroSync Relay Server — FastAPI Application Entry Point

This is the main FastAPI application that serves as the cloud relay
for workspace transfer between paired devices.
"""

import asyncio
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.utils.logger import get_logger
from shared.constants import APP_NAME, APP_VERSION, APP_DESCRIPTION, API_V1_PREFIX

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Application lifespan manager.
    
    Handles startup and shutdown events:
    - Startup: Initialize database, start session cleanup task
    - Shutdown: Close database connections, cancel background tasks
    """
    # --- Startup ---
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
    
    # Import here to avoid circular imports
    from apps.relay_server.core.database import init_database, close_database
    
    await init_database()
    logger.info("Database initialized")
    
    # Start background session cleanup task
    cleanup_task = asyncio.create_task(_session_cleanup_loop())
    logger.info("Session cleanup background task started")
    
    yield
    
    # --- Shutdown ---
    logger.info("Shutting down...")
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    
    await close_database()
    logger.info("Shutdown complete")


async def _session_cleanup_loop() -> None:
    """Background task that cleans up expired sessions every 5 minutes."""
    from apps.relay_server.services.session_service import cleanup_expired_sessions
    
    while True:
        try:
            await asyncio.sleep(5 * 60)  # 5 minutes
            count = await cleanup_expired_sessions()
            if count > 0:
                logger.info(f"Cleaned up {count} expired sessions")
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Session cleanup error: {e}")


def create_app() -> FastAPI:
    """
    Create and configure the FastAPI application.
    
    Returns:
        FastAPI: The configured application instance.
    """
    app = FastAPI(
        title=APP_NAME,
        version=APP_VERSION,
        description=APP_DESCRIPTION,
        lifespan=lifespan,
    )
    
    # Load settings for CORS
    try:
        from config.settings import get_settings
        settings = get_settings()
        origins = settings.server.allowed_origins_list
    except Exception:
        origins = ["http://localhost:1420", "http://localhost:5173", "tauri://localhost"]
    
    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=".*",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    # Register routers
    from apps.relay_server.routers import auth, devices, sessions, websocket, constellations
    
    app.include_router(auth.router, prefix=f"{API_V1_PREFIX}/auth", tags=["Authentication"])
    app.include_router(devices.router, prefix=f"{API_V1_PREFIX}/devices", tags=["Devices"])
    app.include_router(constellations.router, prefix=f"{API_V1_PREFIX}/constellations", tags=["Constellations"])
    app.include_router(sessions.router, prefix=f"{API_V1_PREFIX}/sessions", tags=["Sessions"])
    app.include_router(websocket.router, tags=["WebSocket"])
    
    # Health check endpoint
    @app.get("/health", tags=["Health"])
    async def health_check():
        """Health check endpoint for monitoring and deployment probes."""
        return {
            "status": "ok",
            "version": APP_VERSION,
            "service": APP_NAME,
        }
    
    logger.info(f"{APP_NAME} v{APP_VERSION} application created")
    return app


# Create the application instance
app = create_app()
