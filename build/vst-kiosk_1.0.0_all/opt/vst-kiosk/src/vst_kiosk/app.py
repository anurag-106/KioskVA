"""FastAPI application factory.

Creates the app with:
- Static file serving for the frontend
- WebSocket endpoint for browser clients
- Health check endpoint
- Lifespan management (DB init, server connection, daily purge)
"""

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import KioskConfig
from .db import KioskDB
from .local_ws import websocket_endpoint
from .relay import MessageRelay
from .server_ws import ServerConnection

logger = logging.getLogger(__name__)

# Resolve frontend path relative to this file
FRONTEND_DIR = Path(__file__).resolve().parent.parent.parent / "frontend"


def create_app(config: KioskConfig) -> FastAPI:
    db = KioskDB(config.db_path)
    relay = MessageRelay(db)
    server_conn = ServerConnection(config, relay)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Startup
        db.init_db()
        logger.info(
            "VST Kiosk starting — server=%s:%d kiosk_id=%s",
            config.server_ip,
            config.server_port,
            config.kiosk_id,
        )
        server_conn.start()
        purge_task = asyncio.create_task(_daily_purge(db, config.purge_days))

        yield

        # Shutdown
        purge_task.cancel()
        await server_conn.stop()
        db.close()
        logger.info("VST Kiosk stopped")

    app = FastAPI(title="VST Kiosk", version="1.0.0", lifespan=lifespan)

    @app.websocket("/ws")
    async def ws_route(ws: WebSocket):
        await websocket_endpoint(ws, relay, server_conn)

    @app.get("/health")
    async def health():
        return JSONResponse({
            "status": "ok",
            "kiosk_id": config.kiosk_id,
            "server_connected": relay.server_connected,
        })

    @app.get("/")
    async def index():
        return FileResponse(FRONTEND_DIR / "index.html")

    @app.post("/mock")
    async def inject_mock():
        """DEV ONLY: Inject mock room data to preview the UI."""
        mock_config = {
            "type": "config",
            "kiosk_id": config.kiosk_id,
            "facility": "Erie VA Medical Center",
            "synced_at": "2026-03-30T12:00:00.000000",
            "units": [
                {
                    "unit_id": 1,
                    "unit_name": "3 East",
                    "branch": "Building A",
                    "rooms": [
                        {"room_id": 1, "name": "560", "floor": "3", "device_id": "NUC-301", "nuc_status": "online", "active_alert": "highRisk", "monitoring_type": "bed"},
                        {"room_id": 2, "name": "561", "floor": "3", "device_id": "NUC-302", "nuc_status": "online", "active_alert": None, "monitoring_type": "chair"},
                        {"room_id": 3, "name": "562", "floor": "3", "device_id": "NUC-303", "nuc_status": "online", "active_alert": None, "monitoring_type": "bed"},
                        {"room_id": 4, "name": "563", "floor": "3", "device_id": "NUC-304", "nuc_status": "paused", "active_alert": None, "monitoring_type": "bed"},
                        {"room_id": 5, "name": "564", "floor": "3", "device_id": "NUC-305", "nuc_status": "offline", "active_alert": None, "monitoring_type": "bed"},
                        {"room_id": 6, "name": "565", "floor": "3", "device_id": "NUC-306", "nuc_status": "calibration", "active_alert": None, "monitoring_type": "chair"},
                        {"room_id": 7, "name": "566", "floor": "3", "device_id": "NUC-307", "nuc_status": "online", "active_alert": "lowRisk", "monitoring_type": "bed"},
                        {"room_id": 8, "name": "567", "floor": "3", "device_id": "", "nuc_status": "no_device", "active_alert": None, "monitoring_type": "bed"},
                        {"room_id": 14, "name": "568", "floor": "3", "device_id": "NUC-308", "nuc_status": "deactivated", "active_alert": None, "monitoring_type": "chair"},
                    ]
                },
                {
                    "unit_id": 2,
                    "unit_name": "4 West",
                    "branch": "Building B",
                    "rooms": [
                        {"room_id": 9, "name": "401", "floor": "4", "device_id": "NUC-401", "nuc_status": "online", "active_alert": None, "monitoring_type": "bed"},
                        {"room_id": 10, "name": "402", "floor": "4", "device_id": "NUC-402", "nuc_status": "online", "active_alert": "highRisk", "monitoring_type": "chair"},
                        {"room_id": 11, "name": "403", "floor": "4", "device_id": "NUC-403", "nuc_status": "online", "active_alert": None, "monitoring_type": "bed"},
                        {"room_id": 12, "name": "404", "floor": "4", "device_id": "NUC-404", "nuc_status": "offline", "active_alert": None, "monitoring_type": "bed"},
                        {"room_id": 13, "name": "405", "floor": "4", "device_id": "NUC-405", "nuc_status": "online", "active_alert": None, "monitoring_type": "chair"},
                    ]
                }
            ]
        }
        await relay.handle_server_message(json.dumps(mock_config))
        return JSONResponse({"status": "mock data injected"})

    # Mount static subdirectories (CSS, JS, audio, icons)
    if FRONTEND_DIR.exists():
        for subdir in ("css", "js", "audio", "icons"):
            sub_path = FRONTEND_DIR / subdir
            if sub_path.exists():
                app.mount(f"/{subdir}", StaticFiles(directory=str(sub_path)), name=subdir)

    return app


async def _daily_purge(db: KioskDB, purge_days: int) -> None:
    """Run DB purge once every 24 hours."""
    while True:
        await asyncio.sleep(86400)
        try:
            await db.purge(purge_days)
        except Exception:
            logger.exception("Daily purge failed")
