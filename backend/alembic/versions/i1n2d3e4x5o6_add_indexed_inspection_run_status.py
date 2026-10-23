"""allow inspection run status indexed

Revision ID: i1n2d3e4x5o6
Revises: r7u8n9p0r1o2
Create Date: 2026-10-21

An index-only job finishes as indexed. complete stays reserved for a match.
"""

from __future__ import annotations

from alembic import op

revision = "i1n2d3e4x5o6"
down_revision = "r7u8n9p0r1o2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE inspection_runs DROP CONSTRAINT IF EXISTS ck_inspection_runs_status")
    op.execute(
        """
        ALTER TABLE inspection_runs
        ADD CONSTRAINT ck_inspection_runs_status
        CHECK (status IN ('queued', 'processing', 'complete', 'indexed', 'failed'))
        """
    )


def downgrade() -> None:
    op.execute(
        """
        UPDATE inspection_runs
        SET status = 'complete'
        WHERE status = 'indexed'
        """
    )
    op.execute("ALTER TABLE inspection_runs DROP CONSTRAINT IF EXISTS ck_inspection_runs_status")
    op.execute(
        """
        ALTER TABLE inspection_runs
        ADD CONSTRAINT ck_inspection_runs_status
        CHECK (status IN ('queued', 'processing', 'complete', 'failed'))
        """
    )
