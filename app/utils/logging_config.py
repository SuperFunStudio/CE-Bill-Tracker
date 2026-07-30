"""Structured logging setup.

Historically `configure_logging()` was defined but never called, so structlog ran with library
defaults and every line landed in Cloud Logging as an unstructured `textPayload` — hard to query,
impossible to alert on by field. It is now called once at API boot (app/main.py).

Two render modes:
  * Cloud Run (K_SERVICE set) or LOG_FORMAT=json -> JSON lines that Cloud Logging parses into
    `jsonPayload`, with `severity`/`message` mapped to the fields the GCP log viewer understands so
    log-based metrics and alert policies can filter on status, client_ip, path, etc.
  * Local dev -> the human-readable ConsoleRenderer.

`merge_contextvars` is in the chain so anything bound via structlog.contextvars (request_id, client_ip,
uid — see app/utils/request_logging.py) rides along on every event emitted during that request.
"""
import logging
import os

import structlog

# GCP Cloud Logging severity levels. structlog's add_log_level emits lowercase names ("info");
# the log viewer keys off an uppercase `severity` field, so we translate.
_GCP_SEVERITY = {
    "debug": "DEBUG",
    "info": "INFO",
    "warning": "WARNING",
    "warn": "WARNING",
    "error": "ERROR",
    "critical": "CRITICAL",
    "exception": "ERROR",
}


def _gcp_event_fields(logger, method_name, event_dict):
    """Rename structlog's keys to the ones Cloud Logging renders natively.

    `event` -> `message` (the field the log viewer shows as the summary line) and
    `level` -> `severity` (uppercased) so severity-based filtering/alerting works. Runs only in the
    JSON path; the console renderer wants the original keys.
    """
    if "event" in event_dict:
        event_dict["message"] = event_dict.pop("event")
    level = event_dict.pop("level", method_name)
    event_dict["severity"] = _GCP_SEVERITY.get(str(level).lower(), "INFO")
    return event_dict


def _use_json() -> bool:
    fmt = os.getenv("LOG_FORMAT", "").strip().lower()
    if fmt == "json":
        return True
    if fmt == "console":
        return False
    # Default: JSON when running on Cloud Run (K_SERVICE is injected by the runtime), console locally.
    return bool(os.getenv("K_SERVICE"))


def configure_logging(log_level: str | None = None) -> None:
    level_name = (log_level or os.getenv("LOG_LEVEL", "INFO")).upper()
    logging.basicConfig(
        level=getattr(logging, level_name, logging.INFO),
        format="%(message)s",
    )

    shared = [
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_log_level,
        structlog.stdlib.add_logger_name,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    if _use_json():
        renderers = [_gcp_event_fields, structlog.processors.JSONRenderer()]
    else:
        renderers = [structlog.dev.ConsoleRenderer()]

    structlog.configure(
        processors=shared + renderers,
        wrapper_class=structlog.stdlib.BoundLogger,
        logger_factory=structlog.stdlib.LoggerFactory(),
        cache_logger_on_first_use=True,
    )


log = structlog.get_logger()
