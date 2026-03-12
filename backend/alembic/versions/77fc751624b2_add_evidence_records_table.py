"""add evidence_records table

Revision ID: 77fc751624b2
Revises: a2b3c4d5e6f7
Create Date: 2026-03-11 12:47:33.333711

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '77fc751624b2'
down_revision = 'a2b3c4d5e6f7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "evidence_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("type", sa.String(length=50), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=50), nullable=False, server_default="new"),
        sa.Column("source_id", sa.String(length=255), nullable=True),
        sa.Column("text_content", sa.Text(), nullable=True),
        sa.Column("dates", sa.JSON(), nullable=True),
        sa.Column("attachments_json", sa.JSON(), nullable=True),
        sa.Column("cross_refs_json", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=True, server_default=sa.func.now()),
    )

    op.create_index("ix_evidence_records_project_id", "evidence_records", ["project_id"])
    op.create_index("ix_evidence_records_type", "evidence_records", ["type"])
    op.create_index("ix_evidence_records_status", "evidence_records", ["status"])



def downgrade() -> None:
    op.drop_index("ix_evidence_records_status", table_name="evidence_records")
    op.drop_index("ix_evidence_records_type", table_name="evidence_records")
    op.drop_index("ix_evidence_records_project_id", table_name="evidence_records")
    op.drop_table("evidence_records")

