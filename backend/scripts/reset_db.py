from __future__ import annotations

"""
Database reset utility.

Drops *all* tables in the configured database, then recreates tables from the current ORM models.

Right now the ORM model registry is intentionally empty (no table models), so this will leave you
with an empty database that’s ready for the new data model.

WARNING: Destructive. Do not run against production.
"""

import os
import sys

# Ensure backend/ is on the import path when running this script directly.
sys.path.append(os.path.dirname(os.path.dirname(__file__)))

from sqlalchemy import MetaData  # noqa: E402

from database import engine, init_db  # noqa: E402


def main() -> None:
    metadata = MetaData()
    metadata.reflect(bind=engine)

    tables = list(metadata.tables.keys())
    if not tables:
        print("No tables found. Nothing to drop.")
    else:
        print("Dropping tables:")
        for t in tables:
            print(f"- {t}")
        metadata.drop_all(bind=engine)
        print("Dropped all tables.")

    init_db()
    print("Database initialized (tables created from current ORM models).")


if __name__ == "__main__":
    main()

