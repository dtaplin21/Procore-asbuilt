"""add evidence_drawing_links table

Revision ID: 94c34a2d0c77
Revises: c4d5e6f7a8b9
Create Date: 2026-03-11 20:59:20.889300

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '94c34a2d0c77'
down_revision = 'c4d5e6f7a8b9'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_drawing_links",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("evidence_id", sa.Integer(), sa.ForeignKey("evidence_records.id"), nullable=False),
        sa.Column("drawing_id", sa.Integer(), sa.ForeignKey("drawings.id"), nullable=False),
        sa.Column("link_type", sa.String(length=50), nullable=False, server_default="sheet_ref"),
        sa.Column("matched_text", sa.String(length=100), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("source", sa.String(length=50), nullable=False, server_default="regex"),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
    )

    op.create_index(
        "ix_evidence_drawing_links_project_evidence",
        "evidence_drawing_links",
        ["project_id", "evidence_id"],
    )
    op.create_index(
        "ix_evidence_drawing_links_project_drawing",
        "evidence_drawing_links",
        ["project_id", "drawing_id"],
    )
    op.create_index(
        "ix_evidence_drawing_links_evidence_drawing_unique",
        "evidence_drawing_links",
        ["evidence_id", "drawing_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_evidence_drawing_links_evidence_drawing_unique", table_name="evidence_drawing_links")
    op.drop_index("ix_evidence_drawing_links_project_drawing", table_name="evidence_drawing_links")
    op.drop_index("ix_evidence_drawing_links_project_evidence", table_name="evidence_drawing_links")
    op.drop_table("evidence_drawing_links")

