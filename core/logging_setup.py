"""Application logging with secret redaction.

Every message written to the rotating log file passes through the same
redaction used by memory and tool output — API keys, passwords and tokens
never reach disk.
"""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from core.safety import redact


class RedactionFilter(logging.Filter):
    """Scrubs secrets from log records (messages and formatted args)."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            record.msg = redact(str(record.msg))
            if record.args:
                record.args = tuple(redact(str(a)) for a in record.args)
        except Exception:  # noqa: BLE001 — logging must never crash the app
            return True
        return True


def setup_logging(data_dir: Path, *, level: int = logging.INFO) -> logging.Logger:
    logger = logging.getLogger("screenai")
    if logger.handlers:  # already configured
        return logger
    logger.setLevel(level)
    path = data_dir / "screenai.log"
    handler = logging.handlers.RotatingFileHandler(
        path, maxBytes=512_000, backupCount=2, encoding="utf-8"
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    )
    handler.addFilter(RedactionFilter())
    logger.addHandler(handler)
    return logger
