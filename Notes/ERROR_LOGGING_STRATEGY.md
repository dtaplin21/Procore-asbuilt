# Error handling + logging strategy (Boundaries, JSON logs, correlation IDs)

This document captures the current backend error-handling and logging approach, including:
- **Where errors are caught** (the “boundary”)
- **How errors are shaped for clients**
- **How logs are emitted** (JSON, stdout)
- **How requests are correlated** (`X-Request-Id` / `request_id`)

## Goals

- **Don’t spam `try/except` everywhere**: let errors bubble until a boundary can format + log them.
- **Consistent API errors**: return structured JSON error payloads.
- **Searchable logs**: one JSON object per line, stable keys.
- **Correlate everything**: every log line for a request carries the same `request_id`.

---

## 1) Error boundary (FastAPI exception handlers)

The main “boundary” is in `backend/main.py`. It registers global exception handlers that:
- log the error (stack trace)
- return a consistent JSON error shape

Key handlers:

```42:118:backend/main.py
@app.exception_handler(AppError)
async def app_error_handler(request: Request, exc: AppError):
    logger.exception("AppError", extra={"error_code": exc.code})
    return JSONResponse(status_code=exc.status_code, content={"error": exc.to_response()})

@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(request: Request, exc: RequestValidationError):
    return JSONResponse(status_code=422, content={"error": {"code": "VALIDATION_ERROR", ...}})

@app.exception_handler(SQLAlchemyError)
async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError):
    logger.exception("Database error")
    return JSONResponse(status_code=500, content={"error": {"code": "DB_ERROR", ...}})

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(status_code=500, content={"error": {"code": "INTERNAL_ERROR", ...}})
```

### Typed domain errors

`backend/errors.py` defines `AppError` plus specific subclasses (Procore-related, upstream failures).
Services should raise these typed errors; the boundary formats them consistently:

```7:62:backend/errors.py
@dataclass
class AppError(Exception):
    message: str
    status_code: int = 500
    code: str = "APP_ERROR"
    details: Dict[str, Any] = field(default_factory=dict)
```

---

## 2) Request/response logging + correlation ID middleware

`backend/observability/request_logging_middleware.py` is an ASGI middleware that:
- reads incoming `X-Request-Id` (or generates a UUID)
- stores it in a `ContextVar`
- adds `X-Request-Id` to the response headers
- logs completion with method/path/status/duration
- logs unhandled exceptions with the request metadata

```22:97:backend/observability/request_logging_middleware.py
request_id = _get_header(scope, b"x-request-id") or str(uuid.uuid4())
token = set_request_id(request_id)
...
logger.info("request_complete", extra={... "status_code": status_code, "duration_ms": duration_ms})
reset_request_id(token)
```

### Request id storage (ContextVar)

`backend/observability/request_id.py`:

```7:17:backend/observability/request_id.py
_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
def get_request_id() -> Optional[str]:
    return _request_id_var.get()
```

---

## 3) JSON logging (stdout) + request_id injection

`backend/observability/logging_config.py` configures Python logging so that:
- **logs go to stdout**
- **format is JSON**
- **a filter injects `request_id` into every record**

```16:47:backend/observability/logging_config.py
class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = get_request_id()
        return True

class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {"ts": ..., "level": ..., "logger": ..., "msg": ..., "request_id": ...}
        ...
        return json.dumps(payload)
```

### Environment variables used

Log level selection is environment-driven:
- `APP_ENV` (default: `development`)
- `LOG_LEVEL` (optional override)

```65:67:backend/observability/logging_config.py
app_env = os.getenv("APP_ENV", "development").lower()
log_level = _resolve_log_level(app_env)
```

---

## 4) How to use this in services/routes

### Preferred pattern

- Services raise `AppError` (or subclasses) when you want a clean 4xx/5xx with structured details.
- Don’t wrap everything in route-level `try/except` unless you can do something meaningful.
- Use `logger = logging.getLogger("qcqa")` (or a specific name) and log with `extra={...}` so JSON logs include consistent fields.

### What the client receives

On `AppError`:

```json
{
  "error": {
    "code": "PROCORE_NOT_CONNECTED",
    "message": "No Procore connection found",
    "details": {"user_id": "..."}
  }
}
```

On unhandled exceptions:

```json
{
  "error": {
    "code": "INTERNAL_ERROR",
    "message": "Internal server error"
  }
}
```

---

## Notes / next improvements (if you want to harden it)

- `logging_config.py` still uses `datetime.utcnow()` for the log timestamp; the modern approach is timezone-aware UTC.
- Add standardized keys for upstream calls (service, endpoint, latency) and DB ops (table, operation).
- Consider adding a response body-size limit (avoid logging large payloads).
- Consider adding Alembic migrations; `create_all()` is not schema migration.

