import sys

from loguru import logger


def configure_logging() -> None:
    """Configure Loguru with a single INFO-level stderr sink."""
    logger.remove()
    logger.add(sys.stderr, level="INFO", backtrace=False, diagnose=False)
