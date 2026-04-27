"""Shared test fixtures."""

import pytest

from vst_kiosk.config import KioskConfig
from vst_kiosk.db import KioskDB


@pytest.fixture
def config(tmp_path):
    return KioskConfig(
        server_ip="127.0.0.1",
        server_port=9443,
        kiosk_id="KIOSK-TEST",
        local_port=8099,
        db_path=str(tmp_path / "test.db"),
        purge_days=30,
        log_level="DEBUG",
        ssl_verify=False,
    )


@pytest.fixture
def db(config):
    database = KioskDB(config.db_path)
    database.init_db()
    yield database
    database.close()
