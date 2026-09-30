"""Upstream WebSocket client — connects to the VST Server.

Implements exponential backoff reconnection (2s -> 4s -> 8s -> max 30s).
"""

import asyncio
import json
import logging
import ssl

import websockets

from .config import KioskConfig
from .relay import MessageRelay

logger = logging.getLogger(__name__)

MIN_BACKOFF = 2
MAX_BACKOFF = 30


class ServerConnection:
    def __init__(self, config: KioskConfig, relay: MessageRelay):
        self.config = config
        self.relay = relay
        self._ws: websockets.WebSocketClientProtocol | None = None
        self._backoff = MIN_BACKOFF
        self._task: asyncio.Task | None = None

    @property
    def ws_url(self) -> str:
        scheme = "ws" if not self.config.ssl_verify and self.config.server_port != 443 else "wss"
        return f"{scheme}://{self.config.server_ip}:{self.config.server_port}/ws/kiosk/{self.config.kiosk_id}"

    def _create_ssl_context(self) -> ssl.SSLContext:
        if not self.config.ssl_verify:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            return ctx
        ctx = ssl.create_default_context()
        if self.config.ssl_ca_bundle:
            ctx.load_verify_locations(self.config.ssl_ca_bundle)
        return ctx

    def start(self) -> None:
        self._task = asyncio.create_task(self._run_forever())

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        if self._ws:
            await self._ws.close()

    async def send(self, message: str) -> None:
        if self._ws:
            try:
                await self._ws.send(message)
            except Exception:
                logger.warning("Failed to send message upstream")

    async def _run_forever(self) -> None:
        """Main loop: connect, listen, reconnect on failure."""
        while True:
            try:
                await self._connect_and_listen()
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Server connection error")

            await self.relay.set_server_connected(False)
            logger.info("Reconnecting in %ds...", self._backoff)
            await asyncio.sleep(self._backoff)
            self._backoff = min(self._backoff * 2, MAX_BACKOFF)

    async def _connect_and_listen(self) -> None:
        ssl_ctx = self._create_ssl_context() if self.ws_url.startswith("wss://") else None
        logger.info("Connecting to %s", self.ws_url)

        async with websockets.connect(
            self.ws_url,
            ssl=ssl_ctx,
            ping_interval=20,
            ping_timeout=10,
            close_timeout=5,
        ) as ws:
            self._ws = ws
            self._backoff = MIN_BACKOFF
            await self.relay.set_server_connected(True)
            logger.info("Connected to server")

            # Send sync request to get fresh config
            sync_msg = json.dumps({"type": "sync_request"})
            await ws.send(sync_msg)

            async for message in ws:
                if isinstance(message, str):
                    logger.info("RAW from server: %s", message[:500])
                    await self.relay.handle_server_message(message)
                else:
                    logger.warning("Received binary message from server (%d bytes), ignoring", len(message))

        self._ws = None
