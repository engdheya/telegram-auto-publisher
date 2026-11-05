"""Structured application logging with automatic secret redaction."""

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import get_settings
from app.utils.sanitize import mask_string


class RedactingFilter(logging.Filter):
    """Guarantees no log message ever leaks JWTs, session blobs, or raw codes."""

    def filter(self, record: logging.LogRecord) -> bool:
        if isinstance(record.msg, str):
            record.msg = mask_string(record.msg)
        if record.args:
            if isinstance(record.args, tuple):
                record.args = tuple(
                    mask_string(a) if isinstance(a, str) else a for a in record.args
                )
            elif isinstance(record.args, dict):
                record.args = {
                    k: (mask_string(v) if isinstance(v, str) else v)
                    for k, v in record.args.items()
                }
        return True


def configure_logging() -> logging.Logger:
    settings = get_settings()
    settings.ensure_directories()

    logger = logging.getLogger("tap")
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG if settings.APP_DEBUG else logging.INFO)
    fmt = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )
    redactor = RedactingFilter()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(fmt)
    stream_handler.addFilter(redactor)
    logger.addHandler(stream_handler)

    log_file = Path(settings.LOG_DIR) / "tap.log"
    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)
    file_handler.addFilter(redactor)
    logger.addHandler(file_handler)

    # Keep Telethon internal logs at WARNING so internal MTProto frames never clutter logs
    logging.getLogger("telethon").setLevel(logging.WARNING)
    return logger


logger = configure_logging()
