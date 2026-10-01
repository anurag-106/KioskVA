"""Entry point: python -m vst_kiosk"""

import logging
import sys
from pathlib import Path

import uvicorn

from .app import create_app
from .config import load_config
from .logging_cfg import setup_logging


def main():
    config = load_config()
    setup_logging(config.log_level)

    tls = {}
    if config.local_cert or config.local_key:
        missing = [p for p in (config.local_cert, config.local_key) if not p or not Path(p).is_file()]
        if missing:
            # Refuse to silently fall back to plain HTTP when HTTPS was configured
            logging.getLogger(__name__).error("Local TLS configured but cert/key not found: %s", missing)
            sys.exit(1)
        tls = {"ssl_certfile": config.local_cert, "ssl_keyfile": config.local_key}

    app = create_app(config)
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=config.local_port,
        log_level=config.log_level.lower(),
        **tls,
    )


if __name__ == "__main__":
    main()
