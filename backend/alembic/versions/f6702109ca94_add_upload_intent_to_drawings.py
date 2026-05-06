"""add upload intent to drawings

Revision ID: f6702109ca94
Revises: g7h8i9j0k1l2
Create Date: 2026-04-22 17:07:04.473428

Upgrade is idempotent: if ``upload_intent`` (or the check constraint) was applied
outside Alembic — e.g. manual DDL or a failed migration that rolled back only the
version row — this revision skips duplicate DDL so ``alembic upgrade`` can continue.

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


revision = "f6702109ca94"
down_revision = "g7h8i9j0k1l2"
branch_labels = None
depends_on = None

CHK = "ck_drawings_upload_intent_valid"
CHK_SQL = "upload_intent IN ('master', 'sub') OR upload_intent IS NULL"


def _drawings_column_names(bind: sa.engine.Connection) -> set[str]:
    insp = inspect(bind)
    return {c["name"] for c in insp.get_columns("drawings")}


def _drawings_check_constraint_names(bind: sa.engine.Connection) -> set[str]:
    insp = inspect(bind)
    return {c["name"] for c in insp.get_check_constraints("drawings")}


def upgrade() -> None:
    conn = op.get_bind()

    if "upload_intent" not in _drawings_column_names(conn):
        op.add_column(
            "drawings",
            sa.Column("upload_intent", sa.String(length=16), nullable=True),
        )

    if CHK not in _drawings_check_constraint_names(conn):
        op.create_check_constraint(
            CHK,
            "drawings",
            CHK_SQL,
        )


def downgrade() -> None:
    conn = op.get_bind()

    if CHK in _drawings_check_constraint_names(conn):
        op.drop_constraint(CHK, "drawings", type_="check")

    if "upload_intent" in _drawings_column_names(conn):
        op.drop_column("drawings", "upload_intent")
