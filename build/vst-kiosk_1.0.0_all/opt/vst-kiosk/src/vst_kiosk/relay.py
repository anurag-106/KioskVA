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
    DeviceStateChangeMessage,
    KeyboardEventMessage,
    NurseArrivedMessage,
    RoomAddedMessage,
    RoomRemovedMessage,
    parse_server_message,
)

logger = logging.getLogger(__name__)

MONITORING_EVENTS = ("on", "monitoring", "smart_resume_bed", "smart_resume_chair")


def keyboard_event_updates(event_status: str, monitoring_type: str) -> dict:
    """Room-state changes for a NUC keyboard_event (mirrored in frontend/js/app.js)."""
    if event_status == "off":
        return {"nuc_status": "paused"}
    if event_status in MONITORING_EVENTS:
        updates = {"nuc_status": "online"}
        if monitoring_type in ("bed", "chair"):   # "fall" keeps the current tile mode
            updates["monitoring_type"] = monitoring_type
        return updates
    return {}


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
            if msg_type == "config":
                # Still the server's full truth — keep it for late-joining browsers
                self._cached_config = data
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
            room_id = data.get("room_id") or 0
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
            found = self._update_room_in_cache(msg.room_id, {
                "active_alert": msg.alert_level,
                "alert_id": msg.alert_id,
                "event_type": msg.event_type,
            })
            if not found and self._cached_config is not None:
                # No tile for this room (fallback routing) — shown as a banner
                others = self._cached_config.setdefault("other_alerts", [])
                if not any(a.get("alert_id") == msg.alert_id for a in others):
                    others.append(raw_data)

        elif isinstance(msg, AlertClearedMessage):
            self._update_room_in_cache(msg.room_id, {
                "active_alert": None,
                "alert_id": None,
                "event_type": None,
            })
            if self._cached_config is not None:
                self._cached_config["other_alerts"] = [
                    a for a in self._cached_config.get("other_alerts", [])
                    if a.get("alert_id") != msg.alert_id
                ]

        elif isinstance(msg, DeviceOfflineMessage):
            self._update_room_in_cache(msg.room_id, {
                "nuc_status": "offline",
            })

        elif isinstance(msg, DeviceOnlineMessage):
            self._update_room_in_cache(msg.room_id, {
                "nuc_status": "online",
            })

        elif isinstance(msg, KeyboardEventMessage):
            # Real NUC events: "off" = paused; "on" / "monitoring" /
            # "smart_resume_*" = monitoring in monitoringType's mode.
            # Alerts are NOT cleared here — the server sends alert_cleared.
            updates = keyboard_event_updates(msg.event_status, msg.monitoring_type)
            if updates:
                self._update_room_in_cache(msg.room_id, updates)

        elif isinstance(msg, DeviceStateChangeMessage):
            state = msg.current_state
            updates = {}
            if "pause_status" in msg.changes or "type" in msg.changes:
                if state.get("pause_status") == "paused":
                    updates["nuc_status"] = "paused"
                elif state.get("type") == "calibration":
                    updates["nuc_status"] = "calibration"
                else:
                    updates["nuc_status"] = "online"
            if "mode" in msg.changes and state.get("mode") in ("bed", "chair"):
                updates["monitoring_type"] = state["mode"]
            if updates:
                self._update_room_in_cache(msg.room_id, updates)

        elif isinstance(msg, NurseArrivedMessage):
            # Informational only: the alert stays active until the server sends
            # alert_cleared (matches the browser and the server's config)
            pass

        elif isinstance(msg, RoomRemovedMessage):
            self._remove_room_from_cache(msg.room_id)

    def _update_room_in_cache(self, room_id: int | None, updates: dict) -> bool:
        """Apply incremental updates to a room in the cached config.
        Returns False if the room is not in this kiosk's grid."""
        if not self._cached_config or room_id is None:
            return False
        for unit in self._cached_config.get("units", []):
            for room in unit.get("rooms", []):
                if room.get("room_id") == room_id:
                    room.update(updates)
                    return True
        return False

    def _remove_room_from_cache(self, room_id: int) -> None:
        if not self._cached_config:
            return
        for unit in self._cached_config.get("units", []):
            unit["rooms"] = [
                r for r in unit.get("rooms", []) if r.get("room_id") != room_id
            ]

    async def _log_event(self, msg: Any) -> None:
        """Log specific events to dedicated SQLite tables."""
        room_id = getattr(msg, "room_id", None) or 0
        if isinstance(msg, AlertMessage):
            await self.db.log_alert(room_id, msg.alert_level, "new")
        elif isinstance(msg, AlertClearedMessage):
            await self.db.log_alert(room_id, "", "cleared")
        elif isinstance(msg, DeviceOfflineMessage):
            await self.db.log_device_status(room_id, "offline")
        elif isinstance(msg, DeviceOnlineMessage):
            await self.db.log_device_status(room_id, "online")

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
