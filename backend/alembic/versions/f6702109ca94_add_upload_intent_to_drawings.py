"""add upload intent to drawings

Revision ID: f6702109ca94
Revises: g7h8i9j0k1l2
Create Date: 2026-04-22 17:07:04.473428

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = 'f6702109ca94'
down_revision = 'g7h8i9j0k1l2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "drawings",
        sa.Column("upload_intent", sa.String(length=16), nullable=True),
    )
    op.create_check_constraint(
        "ck_drawings_upload_intent_valid",
        "drawings",
        "upload_intent IN ('master', 'sub') OR upload_intent IS NULL",
    )


def downgrade() -> None:
    op.drop_constraint("ck_drawings_upload_intent_valid", "drawings", type_="check")
    op.drop_column("drawings", "upload_intent")

