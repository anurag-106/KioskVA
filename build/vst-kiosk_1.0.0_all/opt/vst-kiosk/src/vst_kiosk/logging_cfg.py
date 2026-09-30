"""Logging configuration for VST Kiosk."""

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configure logging with console output (captured by journalctl via systemd)."""
    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    if not root.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        )
        root.addHandler(handler)
