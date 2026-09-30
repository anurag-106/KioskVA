"""SQLite debug database for logging all kiosk events.

Uses Python's built-in sqlite3. All writes run via asyncio.to_thread() to avoid
blocking the event loop.
"""

import asyncio
import logging
import sqlite3
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

SCHEMA = """
CREATE TABLE IF NOT EXISTS connection_log (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
    target    TEXT NOT NULL,
    event     TEXT NOT NULL,
    details   TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
    direction TEXT NOT NULL,
    msg_type  TEXT NOT NULL,
    raw_json  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alerts (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
    room_id     INTEGER NOT NULL,
    alert_state TEXT NOT NULL,
    event       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS device_status (
    id        INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%f','now')),
    room_id   INTEGER NOT NULL,
    status    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_connection_log_ts ON connection_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_messages_ts ON messages(timestamp);
CREATE INDEX IF NOT EXISTS idx_alerts_ts ON alerts(timestamp);
CREATE INDEX IF NOT EXISTS idx_device_status_ts ON device_status(timestamp);
"""

PURGE_SQL = """
DELETE FROM connection_log WHERE timestamp < strftime('%Y-%m-%dT%H:%M:%f', 'now', ?);
DELETE FROM messages WHERE timestamp < strftime('%Y-%m-%dT%H:%M:%f', 'now', ?);
DELETE FROM alerts WHERE timestamp < strftime('%Y-%m-%dT%H:%M:%f', 'now', ?);
DELETE FROM device_status WHERE timestamp < strftime('%Y-%m-%dT%H:%M:%f', 'now', ?);
"""


class KioskDB:
    def __init__(self, db_path: str):
        self._db_path = db_path
        self._local = threading.local()

    def _get_conn(self) -> sqlite3.Connection:
        """Get a thread-local SQLite connection."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            conn = sqlite3.connect(self._db_path, check_same_thread=False)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return conn

    def init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(SCHEMA)
        conn.commit()
        logger.info("Database initialized at %s", self._db_path)

    def _log_connection(self, target: str, event: str, details: str = "") -> None:
        try:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO connection_log (target, event, details) VALUES (?, ?, ?)",
                (target, event, details),
            )
            conn.commit()
        except Exception:
            logger.exception("Failed to log connection event")

    def _log_message(self, direction: str, msg_type: str, raw_json: str) -> None:
        try:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO messages (direction, msg_type, raw_json) VALUES (?, ?, ?)",
                (direction, msg_type, raw_json),
            )
            conn.commit()
        except Exception:
            logger.exception("Failed to log message")

    def _log_alert(self, room_id: int, alert_state: str, event: str) -> None:
        try:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO alerts (room_id, alert_state, event) VALUES (?, ?, ?)",
                (room_id, alert_state, event),
            )
            conn.commit()
        except Exception:
            logger.exception("Failed to log alert")

    def _log_device_status(self, room_id: int, status: str) -> None:
        try:
            conn = self._get_conn()
            conn.execute(
                "INSERT INTO device_status (room_id, status) VALUES (?, ?)",
                (room_id, status),
            )
            conn.commit()
        except Exception:
            logger.exception("Failed to log device status")

    def _purge(self, days: int) -> None:
        try:
            conn = self._get_conn()
            modifier = f"-{days} days"
            for line in PURGE_SQL.strip().split("\n"):
                if line.strip():
                    conn.execute(line.strip(), (modifier,))
            conn.commit()
            logger.info("Purged records older than %d days", days)
        except Exception:
            logger.exception("Failed to purge old records")

    # --- Async wrappers (fire-and-forget from the relay) ---

    async def log_connection(self, target: str, event: str, details: str = "") -> None:
        await asyncio.to_thread(self._log_connection, target, event, details)

    async def log_message(self, direction: str, msg_type: str, raw_json: str) -> None:
        await asyncio.to_thread(self._log_message, direction, msg_type, raw_json)

    async def log_alert(self, room_id: int, alert_state: str, event: str) -> None:
        await asyncio.to_thread(self._log_alert, room_id, alert_state, event)

    async def log_device_status(self, room_id: int, status: str) -> None:
        await asyncio.to_thread(self._log_device_status, room_id, status)

    async def purge(self, days: int) -> None:
        await asyncio.to_thread(self._purge, days)

    def close(self) -> None:
        conn = getattr(self._local, "conn", None)
        if conn:
            conn.close()
            self._local.conn = None
