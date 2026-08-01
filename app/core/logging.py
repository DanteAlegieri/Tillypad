import sys
from pathlib import Path

from loguru import logger


def configure_logging() -> None:
    Path("logs").mkdir(exist_ok=True)

    logger.remove()
    logger.add(sys.stderr, level="INFO", enqueue=True)
    logger.add(
        "logs/app.log",
        rotation="5 MB",
        retention="14 days",
        encoding="utf-8",
        level="INFO",
        enqueue=True,
    )
