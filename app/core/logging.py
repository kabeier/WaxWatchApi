from __future__ import annotations

import json
import logging
import re
import sys
from datetime import datetime, timezone
from logging import Logger
from typing import Any

REDACTED_VALUE = "***redacted***"
SENSITIVE_KEYS = {
    "access_token",
    "token",
    "authorization",
    "client_secret",
    "refresh_token",
    "password",
}
TOKEN_PATTERNS = [
    re.compile(r"(Bearer\s+)([^\s]+)", flags=re.IGNORECASE),
    re.compile(r"(Discogs\s+token=)([^\s]+)", flags=re.IGNORECASE),
]


def redact_sensitive_data(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            k: (REDACTED_VALUE if k.lower() in SENSITIVE_KEYS else redact_sensitive_data(v))
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact_sensitive_data(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_sensitive_data(item) for item in value)
    if isinstance(value, str):
        redacted = value
        for pattern in TOKEN_PATTERNS:
            redacted = pattern.sub(rf"\1{REDACTED_VALUE}", redacted)
        return redacted
    return value


class RequestIDFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = "-"
        return True


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "event": redact_sensitive_data(record.getMessage()),
            "request_id": getattr(record, "request_id", "-"),
        }

        reserved = {
            "name",
            "msg",
            "args",
            "levelname",
            "levelno",
            "pathname",
            "filename",
            "module",
            "exc_info",
            "exc_text",
            "stack_info",
            "lineno",
            "funcName",
            "created",
            "msecs",
            "relativeCreated",
            "thread",
            "threadName",
            "processName",
            "process",
        }
        for k, v in record.__dict__.items():
            if k in reserved:
                continue
            if k not in payload:
                if k.lower() in SENSITIVE_KEYS:
                    payload[k] = REDACTED_VALUE
                else:
                    payload[k] = redact_sensitive_data(v)

        if record.exc_info:
            payload["exc_info"] = redact_sensitive_data(self.formatException(record.exc_info))

        return json.dumps(payload, default=str)


def configure_logging(*, level: str = "INFO", json_logs: bool = True) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.addFilter(RequestIDFilter())

    if json_logs:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(request_id)s | %(message)s")
        )

    root = logging.getLogger()
    root.setLevel(getattr(logging, level.upper(), logging.INFO))

    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(handler)

    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.INFO)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> Logger:
    return logging.getLogger(name)
