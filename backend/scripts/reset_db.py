from __future__ import annotations

"""
Legacy database utilities.

- **Preferred for beta / “empty the app data”:** use ``reset_app_data.py`` — truncates
  application tables, keeps schema and ``alembic_version``.

- **Full schema wipe + recreate from ORM:** ``--drop-schema`` (dangerous; breaks until
  ``alembic upgrade head`` or ``init_db()`` aligns with migrations).

WARNING: Destructive. Do not run against production without intent.
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import MetaData  # noqa: E402

from database import engine, init_db  # noqa: E402


def drop_all_and_reinit() -> None:
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
    print("If you use Alembic, run: alembic upgrade head")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--drop-schema",
        action="store_true",
        help="Drop ALL reflected tables (including alembic_version) and run init_db()",
    )
    args = parser.parse_args()

    if args.drop_schema:
        drop_all_and_reinit()
    else:
        print("No action specified.")
        print("  Data only (keep schema):  python scripts/reset_app_data.py")
        print("  Drop all tables + ORM init: python scripts/reset_db.py --drop-schema")
        sys.exit(2)


if __name__ == "__main__":
    main()
