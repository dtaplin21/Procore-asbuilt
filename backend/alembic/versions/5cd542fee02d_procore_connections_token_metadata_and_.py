"""procore_connections token metadata and uniqueness

Revision ID: 5cd542fee02d
Revises: 5a8be9bdea35
Create Date: 2026-02-25 21:45:17.524769

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '5cd542fee02d'
down_revision = '5a8be9bdea35'
branch_labels = None
depends_on = None




def upgrade():
    # 1) Add columns
    op.add_column(
        "procore_connections",
        sa.Column("token_type", sa.String(), server_default="Bearer", nullable=False),
    )
    op.add_column(
        "procore_connections",
        sa.Column("scope", sa.Text(), nullable=True),
    )
    op.add_column(
        "procore_connections",
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
    )

    # 2) Add unique constraint (company_id, procore_user_id)
    op.create_unique_constraint(
        "uq_procore_connections_company_user",
        "procore_connections",
        ["company_id", "procore_user_id"],
    )

    # 3) Add normal index on procore_user_id
    op.create_index(
        "ix_procore_connections_procore_user_id",
        "procore_connections",
        ["procore_user_id"],
        unique=False,
    )

    # 4) Optional: partial unique index for "only one active per procore_user_id"
    op.create_index(
        "uq_procore_connections_active_user",
        "procore_connections",
        ["procore_user_id"],
        unique=True,
        postgresql_where=sa.text("is_active = true"),
    )


def downgrade():
    # reverse order

    op.drop_index("uq_procore_connections_active_user", table_name="procore_connections")
    op.drop_index("ix_procore_connections_procore_user_id", table_name="procore_connections")

    op.drop_constraint(
        "uq_procore_connections_company_user",
        "procore_connections",
        type_="unique",
    )

    op.drop_column("procore_connections", "revoked_at")
    op.drop_column("procore_connections", "scope")
    op.drop_column("procore_connections", "token_type")
