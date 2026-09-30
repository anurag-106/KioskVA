"""Message relay — the central nervous system of the kiosk.

Brokers messages between the upstream VST server and local browser clients.
Maintains a cached copy of the current room state so new browser connections
get immediate data.
"""

import json
import logging
from typing import Any

from fastapi import WebSocket

from .db import KioskDB
from .models import (
    AlertClearedMessage,
    AlertMessage,
    ConfigMessage,
    ConnectionStatusMessage,
    DeviceOfflineMessage,
    DeviceOnlineMessage,
    KeyboardEventMessage,
    NurseArrivedMessage,
    RoomAddedMessage,
    RoomRemovedMessage,
    parse_server_message,
)

logger = logging.getLogger(__name__)


class MessageRelay:
    def __init__(self, db: KioskDB):
        self.db = db
        self._browser_clients: set[WebSocket] = set()
        self._cached_config: dict | None = None
        self._server_connected: bool = False

    @property
    def server_connected(self) -> bool:
        return self._server_connected

    async def set_server_connected(self, connected: bool) -> None:
        self._server_connected = connected
        status_msg = ConnectionStatusMessage(
            type="connection_status",
            connected=connected,
            message="connected" if connected else "disconnected",
        )
        await self._broadcast(status_msg.model_dump())
        await self.db.log_connection(
            "server",
            "connected" if connected else "disconnected",
        )

    def register_browser(self, ws: WebSocket) -> None:
        self._browser_clients.add(ws)
        logger.info("Browser client connected (total: %d)", len(self._browser_clients))

    def unregister_browser(self, ws: WebSocket) -> None:
        self._browser_clients.discard(ws)
        logger.info("Browser client disconnected (total: %d)", len(self._browser_clients))

    async def get_initial_state(self) -> list[dict]:
        """Return messages to send to a newly connected browser."""
        messages = []
        if self._cached_config:
            messages.append(self._cached_config)
        messages.append(
            ConnectionStatusMessage(
                type="connection_status",
                connected=self._server_connected,
                message="connected" if self._server_connected else "disconnected",
            ).model_dump()
        )
        return messages

    async def handle_server_message(self, raw: str) -> None:
        """Process a message received from the upstream VST server."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.error("Invalid JSON from server: %s", raw[:200])
            await self.db.log_message("server_in", "parse_error", raw[:1000])
            return

        msg_type = data.get("type", "unknown")
        await self.db.log_message("server_in", msg_type, raw[:5000])

        try:
            msg = parse_server_message(data)
        except Exception:
            logger.warning("Unknown or invalid message type: %s", msg_type)
            await self._broadcast(data)
            return

        await self._update_cache(msg, data)
        await self._log_event(msg)
        await self._broadcast(data)

    async def handle_browser_message(self, raw: str, send_upstream: Any = None) -> None:
        """Process a message from a browser client."""
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            logger.error("Invalid JSON from browser: %s", raw[:200])
            return

        msg_type = data.get("type", "unknown")
        await self.db.log_message("browser_in", msg_type, raw[:5000])

        if msg_type == "ack" and send_upstream:
            alert_id = data.get("alert_id", "")
            room_id = data.get("room_id", 0)
            await self.db.log_alert(room_id, "", "acked")
            await send_upstream(raw)
            await self.db.log_message("server_out", "ack", raw)

        elif msg_type == "sync_request" and send_upstream:
            await send_upstream(raw)
            await self.db.log_message("server_out", "sync_request", raw)

    async def _update_cache(self, msg: Any, raw_data: dict) -> None:
        """Update the cached room state based on the message type."""
        if isinstance(msg, ConfigMessage):
            self._cached_config = raw_data

        elif isinstance(msg, AlertMessage):
            self._update_room_in_cache(msg.room_id, {
                "active_alert": msg.alert_level,
            })

        elif isinstance(msg, AlertClearedMessage):
            self._update_room_in_cache(msg.room_id, {
                "active_alert": None,
            })

        elif isinstance(msg, DeviceOfflineMessage):
            self._update_room_in_cache(msg.room_id, {
                "nuc_status": "offline",
            })

        elif isinstance(msg, DeviceOnlineMessage):
            self._update_room_in_cache(msg.room_id, {
                "nuc_status": "online",
            })

        elif isinstance(msg, KeyboardEventMessage):
            updates = {}
            # Map event_status to nuc_status for display
            status_map = {
                "system_paused": "paused",
                "system_resumed": "online",
                "off": "deactivated",
                "system_on_bed": "online",
                "system_on_chair": "online",
                "calibration": "calibration",
            }
            mapped = status_map.get(msg.event_status)
            if mapped:
                updates["nuc_status"] = mapped
            # Only update monitoring_type for explicit mode switches
            if msg.event_status in ("system_on_bed", "system_on_chair"):
                updates["monitoring_type"] = msg.monitoring_type
            # If resuming or switching mode, clear any stale alert
            if msg.event_status in ("system_resumed", "system_on_bed", "system_on_chair"):
                updates["active_alert"] = None
            if updates:
                self._update_room_in_cache(msg.room_id, updates)

        elif isinstance(msg, NurseArrivedMessage):
            # Clear alert — nurse is present
            self._update_room_in_cache(msg.room_id, {
                "active_alert": None,
            })

        elif isinstance(msg, RoomRemovedMessage):
            self._remove_room_from_cache(msg.room_id)

    def _update_room_in_cache(self, room_id: int, updates: dict) -> None:
        """Apply incremental updates to a room in the cached config."""
        if not self._cached_config:
            return
        for unit in self._cached_config.get("units", []):
            for room in unit.get("rooms", []):
                if room.get("room_id") == room_id:
                    room.update(updates)
                    return

    def _remove_room_from_cache(self, room_id: int) -> None:
        if not self._cached_config:
            return
        for unit in self._cached_config.get("units", []):
            unit["rooms"] = [
                r for r in unit.get("rooms", []) if r.get("room_id") != room_id
            ]

    async def _log_event(self, msg: Any) -> None:
        """Log specific events to dedicated SQLite tables."""
        if isinstance(msg, AlertMessage):
            await self.db.log_alert(msg.room_id, msg.alert_level, "new")
        elif isinstance(msg, AlertClearedMessage):
            await self.db.log_alert(msg.room_id, "", "cleared")
        elif isinstance(msg, DeviceOfflineMessage):
            await self.db.log_device_status(msg.room_id, "offline")
        elif isinstance(msg, DeviceOnlineMessage):
            await self.db.log_device_status(msg.room_id, "online")

    async def _broadcast(self, data: dict) -> None:
        """Send a message to all connected browser clients."""
        if not self._browser_clients:
            return
        text = json.dumps(data)
        disconnected = set()
        for ws in self._browser_clients:
            try:
                await ws.send_text(text)
            except Exception:
                disconnected.add(ws)
        for ws in disconnected:
            self.unregister_browser(ws)
