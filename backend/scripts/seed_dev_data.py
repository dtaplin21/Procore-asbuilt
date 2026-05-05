"""
Insert local development mock data: demo user, company membership, and projects.

Drawing uploads enqueue a render job; ``JobQueue.user_id`` must resolve via
``UserCompany`` (company member) or any ``User`` row — this seed ensures both.

Idempotent: safe to run multiple times; skips rows that already exist (matched by
stable Procore-style external IDs and demo user email).

Usage (from ``backend/`` so ``.env`` and imports resolve)::

    cd backend
    ./venv/bin/python scripts/seed_dev_data.py
    ./venv/bin/python scripts/seed_dev_data.py --yes

By default this script **refuses** when ``APP_ENV=production``. Pass
``--allow-production`` only if you intentionally seed a production-like DB.

After a full wipe::

    ./venv/bin/python scripts/reset_app_data.py --yes
    ./venv/bin/python scripts/seed_dev_data.py --yes
"""

from __future__ import annotations

import argparse
import os
import sys
from typing import cast

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from config import settings  # noqa: E402
from database import SessionLocal  # noqa: E402
from models.models import Company, Project, User, UserCompany  # noqa: E402

DEV_USER_EMAIL = "dev-seed@example.local"
DEV_COMPANY_PROCORE_ID = "dev-seed-company"
DEV_PROJECTS: tuple[tuple[str, str], ...] = (
    ("Demo Tower A", "dev-seed-project-a"),
    ("Demo Plaza B", "dev-seed-project-b"),
)


def seed() -> None:
    db = SessionLocal()
    try:
        company = (
            db.query(Company)
            .filter(Company.procore_company_id == DEV_COMPANY_PROCORE_ID)
            .one_or_none()
        )
        if company is None:
            company = Company(
                name="Dev Seed Co",
                procore_company_id=DEV_COMPANY_PROCORE_ID,
            )
            db.add(company)
            db.flush()
            print(f"Created company: {company.name!r} (id={company.id})")
        else:
            print(f"Company already exists: {company.name!r} (id={company.id})")

        cid = cast(int, company.id)

        user = db.query(User).filter(User.email == DEV_USER_EMAIL).one_or_none()
        if user is None:
            user = User(email=DEV_USER_EMAIL)
            db.add(user)
            db.flush()
            print(f"Created user: {DEV_USER_EMAIL!r} (id={user.id})")
        else:
            print(f"User already exists: {DEV_USER_EMAIL!r} (id={user.id})")

        uid = cast(int, user.id)
        uc = (
            db.query(UserCompany)
            .filter(
                UserCompany.user_id == uid,
                UserCompany.company_id == cid,
            )
            .one_or_none()
        )
        if uc is None:
            db.add(
                UserCompany(
                    user_id=uid,
                    company_id=cid,
                    role="admin",
                )
            )
            db.flush()
            print(f"Linked user {uid} to company {cid} (user_companies)")
        else:
            print(f"User↔company link already exists (user_companies id={uc.id})")

        for name, procore_pid in DEV_PROJECTS:
            existing = (
                db.query(Project)
                .filter(
                    Project.company_id == cid,
                    Project.procore_project_id == procore_pid,
                )
                .one_or_none()
            )
            if existing:
                print(f"  Project skip (exists): {name!r} (id={existing.id})")
                continue
            p = Project(
                company_id=cid,
                name=name,
                procore_project_id=procore_pid,
                status="active",
            )
            db.add(p)
            db.flush()
            print(f"  Created project: {name!r} (id={p.id})")

        db.commit()
        print("Dev seed complete.")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed development user, company, membership, and projects."
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Non-interactive (skip confirmation).",
    )
    parser.add_argument(
        "--allow-production",
        action="store_true",
        help="Allow running when APP_ENV is production (dangerous).",
    )
    args = parser.parse_args()

    if settings.app_env == "production" and not args.allow_production:
        print(
            "Refusing to seed: APP_ENV=production. "
            "Use a development database or pass --allow-production.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not args.yes:
        try:
            confirm = input("Insert dev seed data into this database? [y/N]: ").strip().lower()
        except EOFError:
            confirm = ""
        if confirm not in ("y", "yes"):
            print("Aborted.")
            sys.exit(0)

    seed()


if __name__ == "__main__":
    main()
