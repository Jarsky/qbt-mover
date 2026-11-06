"""Log to stdout (docker logs) and a rotating file."""

import logging
import logging.handlers
import os
import sys

from . import __version__

logger = logging.getLogger("qbt-mover")


def configure(log_file):
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    formatter = logging.Formatter(
        f"[%(asctime)s] qbt-mover {__version__} [%(levelname)s] %(message)s",
        "%Y-%m-%d %H:%M:%S",
    )
    handlers = [logging.StreamHandler(sys.stdout)]
    problem = None
    try:
        os.makedirs(os.path.dirname(log_file), exist_ok=True)
        handlers.append(logging.handlers.RotatingFileHandler(log_file, maxBytes=10_000_000, backupCount=3))
    except OSError as exc:
        # Logging must never stop torrents being resumed.
        problem = f"Cannot write {log_file}: {exc}"
    for handler in handlers:
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    if problem:
        logger.warning(problem)
