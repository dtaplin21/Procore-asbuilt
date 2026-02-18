"""added defaults to findings

Revision ID: 5a8be9bdea35
Revises: f604b560c614
Create Date: 2026-02-18 07:15:48.173894

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '5a8be9bdea35'
down_revision = 'f604b560c614'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Set resolved default to false
    op.alter_column(
        "findings",
        "resolved",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=sa.text("false"),
    )

    # Set created_at default to now() and make NOT NULL
    op.alter_column(
        "findings",
        "created_at",
        existing_type=sa.DateTime(),
        nullable=False,
        server_default=sa.func.now(),
    )


def downgrade() -> None:
    # Remove default from resolved
    op.alter_column(
        "findings",
        "resolved",
        existing_type=sa.Boolean(),
        nullable=False,
        server_default=None,
    )

    # Remove default and allow NULL again on created_at
    op.alter_column(
        "findings",
        "created_at",
        existing_type=sa.DateTime(),
        nullable=True,
        server_default=None,
    )

