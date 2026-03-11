"""add drawing_id to findings

Revision ID: a2b3c4d5e6f7
Revises: fff44cd00813
Create Date: 2026-02-13

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "a2b3c4d5e6f7"
down_revision = "fff44cd00813"
branch_labels = None
depends_on = None


FK_NAME = "fk_findings_drawing_id_drawings"


def upgrade() -> None:
    op.add_column(
        "findings",
        sa.Column("drawing_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        op.f("ix_findings_drawing_id"),
        "findings",
        ["drawing_id"],
        unique=False,
    )
    op.create_foreign_key(
        FK_NAME,
        "findings",
        "drawings",
        ["drawing_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(FK_NAME, "findings", type_="foreignkey")
    op.drop_index(op.f("ix_findings_drawing_id"), table_name="findings")
    op.drop_column("findings", "drawing_id")
