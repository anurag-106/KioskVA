"""Configuration loader for VST Kiosk.

Reads /etc/vst-kiosk.conf (INI format) with environment variable overrides.
"""

import configparser
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_CONF_PATH = "/etc/vst-kiosk.conf"
PKG_CERT_DIR = Path("/etc/vst-kiosk")


def _pkg_file(name: str) -> str:
    """Path of a cert installed by the .deb, if present. Keeps upgraded kiosks
    (whose edited /etc/vst-kiosk.conf predates these keys) on HTTPS."""
    path = PKG_CERT_DIR / name
    return str(path) if path.is_file() else ""


@dataclass(frozen=True)
class KioskConfig:
    server_ip: str
    server_port: int = 443
    kiosk_id: str = "KIOSK-DEFAULT"
    local_port: int = 8080
    db_path: str = "/var/lib/vst-kiosk/kiosk.db"
    purge_days: int = 30
    log_level: str = "INFO"
    ssl_verify: bool = True
    ssl_ca_bundle: str = ""
    # Local HTTPS for the browser page; both empty = plain HTTP (dev only)
    local_cert: str = ""
    local_key: str = ""


def load_config(conf_path: str | None = None) -> KioskConfig:
    """Load configuration from INI file with env var overrides.

    Priority: environment variables > config file > defaults.
    """
    conf_path = conf_path or os.environ.get("VST_CONF_PATH", DEFAULT_CONF_PATH)
    parser = configparser.ConfigParser()

    if Path(conf_path).exists():
        parser.read(conf_path)

    def get(section: str, key: str, env_var: str, default: str) -> str:
        return os.environ.get(env_var, parser.get(section, key, fallback=default))

    ssl_verify_raw = get("ssl", "verify", "VST_SSL_VERIFY", "true")
    ssl_verify = ssl_verify_raw.lower() in ("true", "1", "yes")

    return KioskConfig(
        server_ip=get("server", "ip", "VST_SERVER_IP", "192.168.50.1"),
        server_port=int(get("server", "port", "VST_SERVER_PORT", "443")),
        kiosk_id=get("kiosk", "id", "VST_KIOSK_ID", "KIOSK-DEFAULT"),
        local_port=int(get("kiosk", "local_port", "VST_LOCAL_PORT", "8080")),
        db_path=get("database", "path", "VST_DB_PATH", "/var/lib/vst-kiosk/kiosk.db"),
        purge_days=int(get("database", "purge_days", "VST_PURGE_DAYS", "30")),
        log_level=get("logging", "level", "VST_LOG_LEVEL", "INFO"),
        ssl_verify=ssl_verify,
        ssl_ca_bundle=get("ssl", "ca_bundle", "VST_SSL_CA_BUNDLE", _pkg_file("server.crt")),
        local_cert=get("ssl", "local_cert", "VST_LOCAL_CERT", _pkg_file("local.crt")),
        local_key=get("ssl", "local_key", "VST_LOCAL_KEY", _pkg_file("local.key")),
    )
