"""
Clear all application rows while keeping tables, indexes, and alembic_version.

Uses PostgreSQL TRUNCATE ... RESTART IDENTITY CASCADE when connected to Postgres.
For SQLite (local tests), deletes all rows with foreign_keys temporarily disabled.

Does NOT run migrations or drop tables.

Usage::

    # Local: run from the backend app directory (where main.py and scripts/ live) so
    # pydantic loads ./.env. Use your venv if you have one, otherwise plain python.
    cd backend
    ./venv/bin/python scripts/reset_app_data.py
    python scripts/reset_app_data.py --yes
    python scripts/reset_app_data.py --yes --clear-uploads

    # Render (or similar) shells: there is usually NO ./venv inside backend/.
    # Use system Python on PATH, from the same backend/ directory, e.g.
    #   pwd && ls -la && which python && python --version
    #   python scripts/reset_app_data.py --yes
    #   python scripts/reset_app_data.py --yes --clear-uploads
    # If needed, try the service venv explicitly, for example:
    #   /opt/render/project/src/.venv/bin/python scripts/reset_app_data.py --yes

DATABASE_URL must be set (shell env on Render, or a .env file in the current working directory).

WARNING: Irreversible. Do not run against production unless you intend to wipe tenant data.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys

# Ensure backend/ is on sys.path when running as a file.
_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from sqlalchemy import text  # noqa: E402

from database import engine  # noqa: E402
from models.models import Base  # noqa: E402

_SKIP_TABLES = frozenset({"alembic_version"})


def _app_table_names() -> list[str]:
    # Sorted for stable output; PostgreSQL TRUNCATE ... CASCADE does not require ordering.
    return sorted(
        name for name in Base.metadata.tables.keys() if name not in _SKIP_TABLES
    )


def clear_uploads_dir() -> None:
    uploads = os.path.join(_BACKEND_ROOT, "uploads")
    if not os.path.isdir(uploads):
        return
    for name in os.listdir(uploads):
        path = os.path.join(uploads, name)
        try:
            if os.path.isfile(path) or os.path.islink(path):
                os.unlink(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
        except OSError as e:
            print(f"Warning: could not remove {path}: {e}", file=sys.stderr)


def reset_data_postgresql(table_names: list[str]) -> None:
    if not table_names:
        print("No application tables to truncate.")
        return
    quoted = ", ".join(f'"{n}"' for n in table_names)
    sql = text(f"TRUNCATE TABLE {quoted} RESTART IDENTITY CASCADE")
    with engine.begin() as conn:
        conn.execute(sql)


def reset_data_sqlite(table_names: list[str]) -> None:
    """SQLite: delete all rows with foreign_keys off (handles FK cycles between tables)."""
    with engine.begin() as conn:
        conn.execute(text("PRAGMA foreign_keys = OFF"))
        try:
            for name in table_names:
                conn.execute(text(f'DELETE FROM "{name}"'))
        finally:
            conn.execute(text("PRAGMA foreign_keys = ON"))
    try:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM sqlite_sequence WHERE name IN ("
                    + ",".join(f"'{n}'" for n in table_names)
                    + ")"
                )
            )
    except Exception:
        pass


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        help="Skip confirmation prompt",
    )
    parser.add_argument(
        "--clear-uploads",
        action="store_true",
        help="Delete files under backend/uploads/ after truncating (orphan file cleanup)",
    )
    args = parser.parse_args()

    table_names = _app_table_names()
    if not table_names:
        print("No tables registered on Base.metadata.")
        sys.exit(1)

    if not args.yes:
        print("This will DELETE ALL ROWS in these tables (schema and alembic_version stay):")
        for n in table_names:
            print(f"  - {n}")
        confirm = input('Type "RESET" and Enter to continue: ').strip()
        if confirm != "RESET":
            print("Aborted.")
            sys.exit(0)

    dialect = engine.dialect.name
    if dialect == "postgresql":
        reset_data_postgresql(table_names)
        print(f"Truncated {len(table_names)} tables (PostgreSQL).")
    elif dialect == "sqlite":
        reset_data_sqlite(table_names)
        print(f"Cleared {len(table_names)} tables (SQLite).")
    else:
        print(f"Unsupported dialect: {dialect}. Use PostgreSQL or SQLite.", file=sys.stderr)
        sys.exit(1)

    if args.clear_uploads:
        clear_uploads_dir()
        print("Cleared backend/uploads/ contents.")


if __name__ == "__main__":
    main()
