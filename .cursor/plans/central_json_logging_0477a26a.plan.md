---
name: Central JSON logging
overview: Introduce a single, centralized Python logging configuration for the FastAPI backend that outputs JSON to stdout, supports env-driven log levels (DEV vs PROD), and automatically includes correlation IDs (request_id) in all log lines.
todos:
  - id: log-config-module
    content: Add backend/observability/logging_config.py implementing dictConfig-based stdout JSON logging and RequestIdFilter.
    status: pending
  - id: wire-main
    content: Update backend/main.py to call configure_logging() and remove basicConfig usage.
    status: pending
    dependencies:
      - log-config-module
  - id: verify-json-logs
    content: Run backend and validate /health produces JSON logs and includes request_id matching X-Request-Id header.
    status: pending
    dependencies:
      - wire-main
---

# Central JSON logging (FastAPI)

## Goal

Create a **single, centralized logging config** for the Python backend that:

- Logs to **stdout**
- Uses **JSON** (searchable, consistent fields)
- Sets log level via env (**DEV=debug, PROD=info**, with `LOG_LEVEL` override)
- Injects **correlation ID** (`request_id`) from `backend/observability/request_id.py` into every log line

## Current state (what we’ll replace)

- `backend/main.py` currently calls `logging.basicConfig(level=logging.INFO)` and uses ad-hoc `getLogger(...)`.

## Implementation approach

### 1) Add a centralized logging module

- Add [`backend/observability/logging_config.py`](/Users/dtaplin21/Desktop/Procore-Integrator/backend/observability/logging_config.py) containing:
- `RequestIdFilter` (reads `get_request_id()` and attaches `record.request_id`)
- `JsonFormatter` (emits one JSON object per line with consistent keys)
- `configure_logging()` which calls `logging.config.dictConfig(...)`
- Env behavior:
    - `APP_ENV=development|production` (default `development`)
    - `LOG_LEVEL` overrides (`DEBUG|INFO|WARNING|ERROR`)
    - Default: `development -> DEBUG`, `production -> INFO`

### 2) Wire it in at application startup

- Update [`backend/main.py`](/Users/dtaplin21/Desktop/Procore-Integrator/backend/main.py):
- Remove `logging.basicConfig(...)`
- Import and call `configure_logging()` **before** creating loggers / emitting logs.
- Keep existing exception-handler boundary (it will now produce JSON logs).

### 3) Ensure uvicorn/fastapi loggers are included

- In `dictConfig`, configure these loggers so they use the same stdout JSON handler:
- `uvicorn`, `uvicorn.error`, `uvicorn.access`
- `qcqa` and `qcqa.request`
- Set `disable_existing_loggers=False` so 3rd party loggers don’t go dark.

## JSON log shape (proposed)

Every line includes:

- `ts` (ISO8601 UTC)
- `level`
- `logger`
- `msg`
- `request_id` (nullable)
- `path`/`method`/`status_code`/`duration_ms` where provided via `extra={...}`
- `exc_info` only when an exception is present

## Testing/verification

- Run backend and hit `/health`.