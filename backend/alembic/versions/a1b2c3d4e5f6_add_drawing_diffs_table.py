"""add drawing_diffs table

Revision ID: a1b2c3d4e5f6
Revises: 61eebd8aec0e
Create Date: 2026-02-13

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '61eebd8aec0e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drawing_diffs",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "alignment_id",
            sa.Integer(),
            sa.ForeignKey("drawing_alignments.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "finding_id",
            sa.Integer(),
            sa.ForeignKey("findings.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("summary", sa.String(), nullable=False),
        sa.Column("severity", sa.String(), nullable=False),
        sa.Column("diff_regions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    op.create_index(
        "ix_drawing_diffs_alignment_id",
        "drawing_diffs",
        ["alignment_id"],
    )
    op.create_index(
        "ix_drawing_diffs_finding_id",
        "drawing_diffs",
        ["finding_id"],
    )
    op.create_index(
        "ix_drawing_diffs_severity",
        "drawing_diffs",
        ["severity"],
    )
    op.create_index(
        "ix_drawing_diffs_created_at",
        "drawing_diffs",
        ["created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_drawing_diffs_created_at", table_name="drawing_diffs")
    op.drop_index("ix_drawing_diffs_severity", table_name="drawing_diffs")
    op.drop_index("ix_drawing_diffs_finding_id", table_name="drawing_diffs")
    op.drop_index("ix_drawing_diffs_alignment_id", table_name="drawing_diffs")
    op.drop_table("drawing_diffs")
