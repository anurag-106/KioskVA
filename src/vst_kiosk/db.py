"""SQLite debug database for logging all kiosk events.

Uses Python's built-in sqlite3. Every DB call runs on one dedicated writer
thread (one connection, writes in order, no lock contention). Log writes are
fire-and-forget: they never delay relaying a message to the browser.
"""

import asyncio
import logging
import sqlite3
from concurrent.futures import ThreadPoolExecutor
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
        self._conn: sqlite3.Connection | None = None
        self._writer = ThreadPoolExecutor(max_workers=1, thread_name_prefix="kiosk-db")

    def _get_conn(self) -> sqlite3.Connection:
        """The writer thread's connection (only ever used on that thread)."""
        if self._conn is None:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
        return self._conn

    def _init_db(self) -> None:
        conn = self._get_conn()
        conn.executescript(SCHEMA)
        conn.commit()
        logger.info("Database initialized at %s", self._db_path)

    def init_db(self) -> None:
        self._writer.submit(self._init_db).result()

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

    # --- Async wrappers: queue the write and return immediately ---
    # (the _log_* functions catch and log their own errors)

    async def log_connection(self, target: str, event: str, details: str = "") -> None:
        self._writer.submit(self._log_connection, target, event, details)

    async def log_message(self, direction: str, msg_type: str, raw_json: str) -> None:
        self._writer.submit(self._log_message, direction, msg_type, raw_json)

    async def log_alert(self, room_id: int, alert_state: str, event: str) -> None:
        self._writer.submit(self._log_alert, room_id, alert_state, event)

    async def log_device_status(self, room_id: int, status: str) -> None:
        self._writer.submit(self._log_device_status, room_id, status)

    async def purge(self, days: int) -> None:
        await asyncio.wrap_future(self._writer.submit(self._purge, days))

    def _close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    def close(self) -> None:
        """Flush queued writes, then close."""
        self._writer.submit(self._close).result()
        self._writer.shutdown(wait=True)
