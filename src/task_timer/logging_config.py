from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger


def configure_logging(data_dir: Path, *, verbose_console: bool = False) -> Path:
    logs_dir = data_dir / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    log_path = (logs_dir / "chronicle.log").resolve()

    logger.remove()
    logger.add(
        log_path,
        level="INFO",
        rotation="1 MB",
        retention="14 days",
        compression="zip",
        enqueue=True,
        backtrace=True,
        diagnose=False,
        format="{time:YYYY-MM-DD HH:mm:ss.SSS} | {level: <8} | {name}:{function}:{line} | {message}",
    )
    if verbose_console:
        logger.add(sys.stderr, level="DEBUG")
    return log_path
