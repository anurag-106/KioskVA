"""Browser-facing WebSocket endpoint.

Serves local Chromium browser clients at /ws. Sends cached state on connect,
then relays real-time updates. Forwards ack/sync_request messages upstream.
"""

import logging

from fastapi import WebSocket, WebSocketDisconnect

from .relay import MessageRelay
from .server_ws import ServerConnection

logger = logging.getLogger(__name__)


async def websocket_endpoint(
    ws: WebSocket,
    relay: MessageRelay,
    server_conn: ServerConnection,
) -> None:
    await ws.accept()
    relay.register_browser(ws)

    try:
        # Send cached state immediately so the browser renders without waiting
        initial = await relay.get_initial_state()
        for msg in initial:
            await ws.send_json(msg)

        # Listen for messages from the browser
        while True:
            raw = await ws.receive_text()
            await relay.handle_browser_message(raw, send_upstream=server_conn.send)

    except WebSocketDisconnect:
        logger.info("Browser WebSocket disconnected normally")
    except Exception:
        logger.exception("Browser WebSocket error")
    finally:
        relay.unregister_browser(ws)
