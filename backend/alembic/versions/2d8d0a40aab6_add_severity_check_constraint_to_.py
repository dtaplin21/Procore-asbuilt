"""add_severity_check_constraint_to_drawing_diffs

Revision ID: 2d8d0a40aab6
Revises: a1b2c3d4e5f6
Create Date: 2026-03-04 21:13:49.770965

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '2d8d0a40aab6'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        """
        ALTER TABLE drawing_diffs
        ADD CONSTRAINT ck_drawing_diffs_severity
        CHECK (severity IN ('low', 'medium', 'high', 'critical'))
        """
    )


def downgrade() -> None:
    op.execute("ALTER TABLE drawing_diffs DROP CONSTRAINT ck_drawing_diffs_severity")

