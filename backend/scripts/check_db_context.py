"""
Print the DB URL used by backend/alembic (password redacted) and verify schema.

Run from repo root or backend/ — ensure ``backend/.env`` is loaded by using:

    cd backend && python3 scripts/check_db_context.py

Matches what Alembic uses: :func:`config.settings.database_url`.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# backend/ on path
BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

os.chdir(BACKEND_ROOT)

from sqlalchemy import create_engine, text  # noqa: E402
from sqlalchemy.engine import make_url
from sqlalchemy.exc import SQLAlchemyError  # noqa: E402

from config import settings, sqlalchemy_connect_args  # noqa: E402


def redact_sqlalchemy_url(raw: str) -> str:
    u = make_url(raw)
    if u.password is not None:
        return str(u.set(password="***"))
    return str(u)


def main() -> int:
    raw_url = settings.database_url
    safe = redact_sqlalchemy_url(raw_url)
    print("Resolved DATABASE_URL (password redacted):")
    print(f"  {safe}")
    print(f"CWD: {os.getcwd()}")
    env_path = BACKEND_ROOT / ".env"
    print(f"backend/.env exists: {env_path.is_file()}")

    engine = create_engine(
        raw_url,
        pool_pre_ping=True,
        connect_args=sqlalchemy_connect_args(),
    )
    with engine.connect() as conn:
        row = conn.execute(
            text(
                "SELECT current_database(), current_user, inet_server_addr(), inet_server_port()"
            )
        ).one()
        print("\nConnected as:")
        print(f"  database: {row[0]}")
        print(f"  user:     {row[1]}")
        host_part = f"{row[2]}:{row[3]}" if row[2] is not None else "(local socket / null addr)"
        print(f"  server:   {host_part}")

        has_master = conn.execute(
            text(
                """
                SELECT 1
                FROM information_schema.columns
                WHERE table_schema = 'public'
                  AND table_name = 'projects'
                  AND column_name = 'master_drawing_id'
                """
            )
        ).scalar()
        print("\nSchema check (public.projects):")
        print(
            f"  master_drawing_id column: {'present' if has_master else 'MISSING'}"
        )

        try:
            ver = conn.execute(
                text(
                    "SELECT version_num FROM alembic_version ORDER BY version_num DESC LIMIT 1"
                )
            ).scalar()
            if ver:
                print(f"\nalembic_version (latest row): {ver}")
            else:
                print("\nalembic_version: (empty table)")
        except SQLAlchemyError as e:
            print(f"\nalembic_version: could not read — {e}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
