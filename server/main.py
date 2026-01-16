"""
FastAPI Main Application
========================

Main entry point for the Autonomous Coding UI server.
Provides REST API, WebSocket, and static file serving.
"""

import asyncio
import atexit
import logging
import os
import shutil
import signal
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request, WebSocket

logger = logging.getLogger(__name__)

# Environment configuration for Docker support
ALLOW_EXTERNAL_ACCESS = os.getenv("ALLOW_EXTERNAL_ACCESS", "false").lower() == "true"
CORS_ORIGINS_ENV = os.getenv("CORS_ORIGINS", "")
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .routers import (
    agent_router,
    assistant_chat_router,
    features_router,
    projects_router,
    spec_creation_router,
)
from .schemas import SetupStatus
from .services.assistant_chat_session import cleanup_all_sessions as cleanup_assistant_sessions
from .services.container_manager import (
    cleanup_all_containers,
    cleanup_idle_containers,
    restore_managers_from_registry,
    start_agent_health_monitor,
    start_hound_trigger_monitor,
)
from .services.beads_sync_manager import initialize_all_projects, start_beads_sync_poller
from .websocket import project_websocket

# Idle container check interval (seconds)
IDLE_CHECK_INTERVAL = 60

# Paths
ROOT_DIR = Path(__file__).parent.parent
UI_DIST_DIR = ROOT_DIR / "ui" / "dist"


async def idle_container_monitor():
    """Background task to stop idle containers."""
    while True:
        try:
            await asyncio.sleep(IDLE_CHECK_INTERVAL)
            stopped = await cleanup_idle_containers()
            if stopped:
                import logging
                logging.getLogger(__name__).info(f"Stopped idle containers: {stopped}")
        except asyncio.CancelledError:
            break
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Idle monitor error: {e}")


def cleanup_on_exit():
    """Fallback cleanup function called on exit."""
    try:
        logger.info("atexit cleanup triggered, stopping containers...")
        # Run async cleanup in sync context
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(cleanup_all_containers())
        loop.close()
        logger.info("atexit cleanup complete")
    except Exception as e:
        logger.error(f"Error in atexit cleanup: {e}")


def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown."""
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}, initiating shutdown...")
        # The lifespan cleanup will be triggered by FastAPI

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Register atexit handler as fallback
    atexit.register(cleanup_on_exit)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup and shutdown."""
    logger.info("Starting Autonomous Coding UI server...")

    # Setup signal handlers
    setup_signal_handlers()

    # Restore container managers from registry (for server restarts)
    try:
        restored = await restore_managers_from_registry()
        if restored:
            logger.info(f"Restored {restored} container managers from registry")
    except Exception as e:
        logger.warning(f"Failed to restore container managers: {e}")

    # Initialize beads-sync for all registered projects
    try:
        await initialize_all_projects()
    except Exception as e:
        logger.warning(f"Failed to initialize beads-sync: {e}")

    # Startup - start background monitors
    idle_monitor_task = asyncio.create_task(idle_container_monitor())
    health_monitor_task = asyncio.create_task(start_agent_health_monitor())
    beads_sync_task = asyncio.create_task(start_beads_sync_poller())
    hound_trigger_task = asyncio.create_task(start_hound_trigger_monitor())

    yield

    # Shutdown - cleanup all running agents, containers, and sessions
    logger.info("Shutting down server, cleaning up containers...")

    idle_monitor_task.cancel()
    health_monitor_task.cancel()
    beads_sync_task.cancel()
    hound_trigger_task.cancel()
    try:
        await idle_monitor_task
    except asyncio.CancelledError:
        pass
    try:
        await health_monitor_task
    except asyncio.CancelledError:
        pass
    try:
        await beads_sync_task
    except asyncio.CancelledError:
        pass
    try:
        await hound_trigger_task
    except asyncio.CancelledError:
        pass

    logger.info("Stopping all containers...")
    await cleanup_all_containers()
    await cleanup_assistant_sessions()

    logger.info("Shutdown complete.")


# Create FastAPI app
app = FastAPI(
    title="Autonomous Coding UI",
    description="Web UI for the Autonomous Coding Agent",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS configuration - configurable via CORS_ORIGINS env var
# Use "*" for CORS_ORIGINS to allow all origins (useful in Docker)
if CORS_ORIGINS_ENV == "*":
    cors_origins = ["*"]
elif CORS_ORIGINS_ENV:
    cors_origins = [origin.strip() for origin in CORS_ORIGINS_ENV.split(",")]
else:
    cors_origins = [
        "http://localhost:5173",      # Vite dev server
        "http://127.0.0.1:5173",
        "http://localhost:8888",      # Production
        "http://127.0.0.1:8888",
    ]

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================================
# Security Middleware
# ============================================================================

@app.middleware("http")
async def require_localhost(request: Request, call_next):
    """Only allow requests from localhost (unless ALLOW_EXTERNAL_ACCESS is set)."""
    # Skip localhost check if external access is enabled (for Docker)
    if ALLOW_EXTERNAL_ACCESS:
        return await call_next(request)

    client_host = request.client.host if request.client else None

    # Allow localhost connections
    if client_host not in ("127.0.0.1", "::1", "localhost", None):
        raise HTTPException(status_code=403, detail="Localhost access only")

    return await call_next(request)


# ============================================================================
# Include Routers
# ============================================================================

app.include_router(projects_router)
app.include_router(features_router)
app.include_router(agent_router)
app.include_router(spec_creation_router)
app.include_router(assistant_chat_router)


# ============================================================================
# WebSocket Endpoint
# ============================================================================

@app.websocket("/ws/projects/{project_name}")
async def websocket_endpoint(websocket: WebSocket, project_name: str):
    """WebSocket endpoint for real-time project updates."""
    await project_websocket(websocket, project_name)


# ============================================================================
# Setup & Health Endpoints
# ============================================================================

@app.get("/api/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


@app.get("/api/setup/status", response_model=SetupStatus)
async def setup_status():
    """Check system setup status."""
    # Check for Claude CLI
    claude_cli = shutil.which("claude") is not None

    # Check for Claude credentials (OAuth token or API key in environment)
    credentials = bool(os.getenv("CLAUDE_CODE_OAUTH_TOKEN") or os.getenv("ANTHROPIC_API_KEY"))

    # Check for Node.js and npm
    node = shutil.which("node") is not None
    npm = shutil.which("npm") is not None

    return SetupStatus(
        claude_cli=claude_cli,
        credentials=credentials,
        node=node,
        npm=npm,
    )


# ============================================================================
# Static File Serving (Production)
# ============================================================================

# Serve React build files if they exist
if UI_DIST_DIR.exists():
    # Mount static assets
    app.mount("/assets", StaticFiles(directory=UI_DIST_DIR / "assets"), name="assets")

    @app.get("/")
    async def serve_index():
        """Serve the React app index.html."""
        return FileResponse(UI_DIST_DIR / "index.html")

    @app.get("/{path:path}")
    async def serve_spa(path: str):
        """
        Serve static files or fall back to index.html for SPA routing.
        """
        # Check if the path is an API route (shouldn't hit this due to router ordering)
        if path.startswith("api/") or path.startswith("ws/"):
            raise HTTPException(status_code=404)

        # Try to serve the file directly
        file_path = UI_DIST_DIR / path
        if file_path.exists() and file_path.is_file():
            return FileResponse(file_path)

        # Fall back to index.html for SPA routing
        return FileResponse(UI_DIST_DIR / "index.html")


# ============================================================================
# Main Entry Point
# ============================================================================

if __name__ == "__main__":
    import uvicorn
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", "8888"))
    uvicorn.run(
        "server.main:app",
        host=host,
        port=port,
        reload=True,
    )
