"""Logging for the API and the worker.

- One pipeline for our own logs (structlog) and library logs (uvicorn, SQLAlchemy, OpenAI…).
- Console: coloured and readable in local dev (LOG_JSON=false), JSON elsewhere.
- File: always JSON, rotated, in LOG_DIR/<service>.log (var/logs/api.log, var/logs/worker.log).
- Secrets are masked before anything is written.
"""

import logging
import logging.handlers
import re
import sys
from pathlib import Path

import structlog

_SECRET_PATTERNS = [
    re.compile(r"(?i)(password|passwd|secret|token|api[_-]?key|authorization)(\"?\s*[:=]\s*\"?)([^\s\",}]+)"),
]

# Libraries that are too chatty at INFO.
_QUIET = {
    "httpx": logging.WARNING,
    "httpcore": logging.WARNING,
    "openai": logging.WARNING,
    "openai.agents": logging.WARNING,
    "mcp": logging.WARNING,
    "asyncio": logging.WARNING,
    "watchfiles": logging.WARNING,
    "uvicorn.access": logging.WARNING,  # replaced by our own request log line
}


_SECRET_KEYS = {
    "password",
    "passwd",
    "secret",
    "token",
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "refresh_token",
}


def _is_secret_key(key: str) -> bool:
    k = key.lower()
    return k in _SECRET_KEYS or k.endswith(("_password", "_secret", "_api_key", "_access_token"))


def _redact(_logger, _method, event_dict):
    """Mask values that look like credentials before a log line is written."""
    for key, value in list(event_dict.items()):
        if isinstance(value, str):
            for pattern in _SECRET_PATTERNS:
                value = pattern.sub(r"\1\2***", value)
            event_dict[key] = value
        if _is_secret_key(key):
            event_dict[key] = "***"
    return event_dict


def configure_logging(
    level: str = "INFO",
    json: bool = True,
    *,
    service: str = "api",
    log_dir: Path | None = None,
    log_sql: bool = False,
) -> None:
    shared = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso" if json else "%Y-%m-%d %H:%M:%S", utc=False),
        structlog.processors.StackInfoRenderer(),
        _redact,
    ]
    structlog.configure(
        processors=[*shared, structlog.stdlib.ProcessorFormatter.wrap_for_formatter],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    console = logging.StreamHandler(sys.stdout)
    console.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                _redact,  # again, after tracebacks are rendered to text
                structlog.processors.JSONRenderer()
                if json
                else structlog.dev.ConsoleRenderer(colors=sys.stdout.isatty()),
            ],
        )
    )
    handlers: list[logging.Handler] = [console]

    if log_dir is not None:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.handlers.RotatingFileHandler(
            log_dir / f"{service}.log", maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                foreign_pre_chain=shared,
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.format_exc_info,
                    _redact,
                    structlog.processors.JSONRenderer(),
                ],
            )
        )
        handlers.append(file_handler)

    root = logging.getLogger()
    root.handlers = handlers
    root.setLevel(level.upper())

    # Route uvicorn's own loggers through the same handlers.
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        lg = logging.getLogger(name)
        lg.handlers = []
        lg.propagate = True
    for name, lvl in _QUIET.items():
        logging.getLogger(name).setLevel(lvl)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.INFO if log_sql else logging.WARNING)


log = structlog.get_logger("oneclarity")
