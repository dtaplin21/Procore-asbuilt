from __future__ import annotations

import json
import logging
import logging.config
import os
import sys
from datetime import datetime
from typing import Any, Dict

# When running the backend (e.g. `cd backend && python -m uvicorn main:app`),
# the import root is the backend directory, so `observability.*` is the correct prefix.
from observability.request_id import get_request_id


class RequestIdFilter(logging.Filter):
    """
    Attach request_id to every LogRecord using ContextVar getter.
    """
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()  # may be None
        return True


class JsonFormatter(logging.Formatter):
    """
    One JSON object per line. Keep keys consistent so logs are searchable.
    """
    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, Any] = {
            "ts": datetime.utcnow().isoformat(timespec="milliseconds") + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
            "request_id": getattr(record, "request_id", None),
        }

        # Include common extras if present (must match keys passed via logger.info(..., extra={...}))
        for key in (
            "method",
            "path",
            "status_code",
            "duration_ms",
            "endpoint",
            "upstream_status",
            "app_env",
            "log_level",
            "error_class",
            "retry_after",
            # workflow_logging.py
            "project_id",
            "job_id",
            "status",
            "previous_status",
            "finding_id",
            "evidence_ids",
            "finding_type",
            "severity",
            # location_match_logging.py
            "evidence_id",
            "inspection_id",
            "inspection_run_id",
            "master_drawing_id",
            "drawing_id",
            "page",
            "match_status",
            "match_method",
            "confidence",
            "bbox",
            "notes",
            "match_detail",
            "candidates",
            "candidate_count",
            "overlay_id",
            "region_id",
            "master_index_ready",
            "master_index_status",
            "match_job_id",
            "match_deferred",
            "index_status",
            "region_count",
            "evidence_point_count",
            "scoped_point_count",
            "auxiliary_drawing_ids",
            "clue_count",
            "evidence_kind",
            # linked_drawing_logging.py
            "followed_count",
            "skipped_count",
            "fetched_pdf_count",
            "supplemental_chars",
            "link_errors",
            "registered_drawing_ids",
            "deduped_drawing_ids",
            "registered_count",
            "deduped_count",
            "url",
            "linked_filename",
            "body_bytes",
            "text_words",
            "pages",
            "captured",
            "skip_reason",
            "sheet_refs",
            "existing_drawing_id",
            "storage_key",
            "fetched_pdf_count",
            "attachment_filename",
            "words",
            "depth",
            "attachment_id",
            "resolved_host",
            "reason",
        ):
            if hasattr(record, key):
                payload[key] = getattr(record, key)

        # If exception info exists, include it (keeps it structured)
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)

        return json.dumps(payload, ensure_ascii=False)


def _resolve_log_level(app_env: str) -> str:
    """
    Env rules:
      - LOG_LEVEL overrides if set
      - else: development -> DEBUG, production -> INFO
    """
    override = os.getenv("LOG_LEVEL")
    if override:
        return override.upper()

    if app_env == "production":
        return "INFO"
    return "DEBUG"


def configure_logging() -> None:
    app_env = os.getenv("APP_ENV", "development").lower()
    log_level = _resolve_log_level(app_env)

    config = {
        "version": 1,
        "disable_existing_loggers": False,

        "filters": {
            "request_id": {"()": RequestIdFilter},
        },

        "formatters": {
            "json": {"()": JsonFormatter},
        },

        "handlers": {
            "stdout": {
                "class": "logging.StreamHandler",
                "level": log_level,
                "formatter": "json",
                "filters": ["request_id"],
                "stream": sys.stdout,
            }
        },

        "root": {
            "level": log_level,
            "handlers": ["stdout"],
        },

        # Optional: tune noisy loggers here
        "loggers": {
            "uvicorn": {"level": log_level},
            "uvicorn.error": {"level": log_level},
            "uvicorn.access": {"level": log_level, "handlers": ["stdout"], "propagate": False},
            "httpx": {"level": log_level},
        },
    }

    logging.config.dictConfig(config)

    # Nice startup line so you know config loaded
    logging.getLogger("app").info(
        "logging_configured",
        extra={"app_env": app_env, "log_level": log_level},
    )
