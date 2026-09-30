"""Entry point: python -m vst_kiosk"""

import uvicorn

from .app import create_app
from .config import load_config
from .logging_cfg import setup_logging


def main():
    config = load_config()
    setup_logging(config.log_level)

    app = create_app(config)
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=config.local_port,
        log_level=config.log_level.lower(),
    )


if __name__ == "__main__":
    main()
