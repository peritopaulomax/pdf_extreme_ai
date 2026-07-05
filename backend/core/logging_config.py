"""Configuracao centralizada de logging."""

from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any


class _JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        for key in ("project_id", "conversation_id", "turn_id", "user"):
            value = getattr(record, key, None)
            if value is not None:
                payload[key] = value
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging() -> None:
    """Configura logging estruturado (JSON em producao, texto em dev)."""
    env = (os.environ.get("ENVIRONMENT") or os.environ.get("ENV", "")).strip().lower()
    is_prod = env in ("production", "prod")
    level = os.environ.get("LOG_LEVEL", "INFO" if is_prod else "DEBUG").upper()

    handler = logging.StreamHandler(sys.stdout)
    if is_prod:
        handler.setFormatter(_JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s - %(name)s - %(levelname)s - %(message)s")
        )

    root = logging.getLogger()
    root.setLevel(level)
    root.handlers = []
    root.addHandler(handler)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
