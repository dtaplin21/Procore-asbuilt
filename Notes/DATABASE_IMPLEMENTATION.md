# Database Implementation (Reference)

This document captures the current end-to-end database implementation for the backend, so other views/components can reference the “source of truth” quickly.

## Overview

- **Backend framework**: FastAPI
- **ORM**: SQLAlchemy
- **DB connection**: configured via `DATABASE_URL` (loaded from `backend/.env`)
- **ORM source of truth**: `backend/models/models.py`
- **Session management**: `backend/database.py` provides `SessionLocal` + `get_db()`
- **Table creation**: `init_db()` uses `Base.metadata.create_all(...)`

## Configuration (`DATABASE_URL`)

`backend/config.py` loads settings from `backend/.env`:

```4:21:backend/config.py
class Settings(BaseSettings):
    database_url: str = "postgresql://user:password@localhost/procore_integrator"
    # ...
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )

settings = Settings()
```

Example values live in `backend/.env.example`:

```4:7:backend/.env.example
# Format: postgresql://username:password@host:port/database_name
DATABASE_URL=postgresql://user:password@localhost/procore_integrator
```

Recommended (psycopg v3) SQLAlchemy URL format:

```env
DATABASE_URL=postgresql+psycopg://USERNAME:PASSWORD@localhost:5432/DBNAME
```

## Engine, session factory, and FastAPI dependency

Defined in `backend/database.py`:

```1:20:backend/database.py
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from models.models import Base
from config import settings

DATABASE_URL = settings.database_url

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    Base.metadata.create_all(bind=engine)
```

How it’s used in routes:
- Routers declare `db: Session = Depends(get_db)`
- Services receive the `Session` and perform DB operations (queries/commits) once new models exist.

## ORM models (source of truth)

All ORM models + `Base` live in:
- `backend/models/models.py`

This file defines:
- `Base = declarative_base()`
- ORM tables such as `User`, `Company`, `ProcoreConnection`, `JobQueue`, `UsageLog`, `UserSettings`
- UTC-aware timestamps via `datetime.now(timezone.utc)` lambdas

## Startup initialization

FastAPI calls `init_db()` on startup in `backend/main.py`:

```150:153:backend/main.py
@app.on_event("startup")
async def startup_event():
    """Initialize database on startup"""
    init_db()
```

## CLI scripts

### Create tables

`backend/scripts/init_db.py`:

```6:18:backend/scripts/init_db.py
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from database import init_db

def main() -> None:
    init_db()
    print("Database initialized (tables created).")
```

Root package script:
- `npm run db:init` → runs `python3 backend/scripts/init_db.py`

### Reset database (drop all tables, then recreate)

`backend/scripts/reset_db.py`:

- Reflects existing tables from the configured database
- Drops them all
- Calls `init_db()` to recreate whatever the current ORM defines

Root package script:
- `npm run db:reset` → runs `python3 backend/scripts/reset_db.py`

## Notes / gotchas

- **Tables don’t disappear just because models change**: if you removed/changed models, you must run `db:reset` (destructive) or use migrations (Alembic) to reconcile.
- **`create_all()` is not migrations**: it’s fine early on, but you’ll likely want Alembic once the schema stabilizes.
- **Timezone**: the models use timezone-aware UTC timestamps (avoids deprecated `datetime.utcnow()` usage).

