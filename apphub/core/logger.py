import logging
import os
from pathlib import Path

APP_NAME = "apphub"
DEFAULT_LEVEL = logging.DEBUG
DEFAULT_LOG_FILE = Path("apphub.log")
FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"


def configure_logging(force: bool = False) -> logging.Logger:
    logger = logging.getLogger(APP_NAME)

    if logger.handlers and not force:
        return logger

    if force:
        logger.handlers.clear()

    level = getattr(
        logging, os.getenv("APPHUB_LOG_LEVEL", "DEBUG").upper(), DEFAULT_LEVEL
    )
    logger.setLevel(level)
    logger.propagate = False

    formatter = logging.Formatter(FORMAT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    logger.addHandler(console)

    raw_path = os.getenv("APPHUB_LOG_FILE")
    if raw_path not in {"", "off", "none", "disabled"}:
        path = Path(raw_path).expanduser() if raw_path else DEFAULT_LOG_FILE
        path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(path, encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(f"{APP_NAME}.{name}")
