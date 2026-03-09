"""add idempotency keys and procore writebacks

Revision ID: fff44cd00813
Revises: b7c8d9e0f1a2
Create Date: 2026-03-09 11:37:04.471014

"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = 'fff44cd00813'
down_revision = 'b7c8d9e0f1a2'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "idempotency_keys",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("scope", sa.String(), nullable=False),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("request_hash", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="in_progress"),
        sa.Column("response_payload", sa.JSON(), nullable=True),
        sa.Column("resource_reference", sa.JSON(), nullable=True),
        sa.Column("locked_until", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("scope", "idempotency_key", name="uq_idempotency_scope_key"),
    )
    op.create_index("ix_idempotency_keys_scope_status", "idempotency_keys", ["scope", "status"])

    op.create_table(
        "procore_writebacks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("inspection_run_id", sa.Integer(), sa.ForeignKey("inspection_runs.id", ondelete="SET NULL"), nullable=True),
        sa.Column("finding_id", sa.Integer(), sa.ForeignKey("findings.id", ondelete="SET NULL"), nullable=True),
        sa.Column("writeback_type", sa.String(), nullable=False),
        sa.Column("mode", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="queued"),
        sa.Column("payload", sa.JSON(), nullable=True),
        sa.Column("procore_response", sa.JSON(), nullable=True),
        sa.Column("resource_reference", sa.JSON(), nullable=True),
        sa.Column("idempotency_key", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_procore_writebacks_project_created", "procore_writebacks", ["project_id", "created_at"])
    op.create_index("ix_procore_writebacks_run", "procore_writebacks", ["inspection_run_id"])
    op.create_index("ix_procore_writebacks_finding", "procore_writebacks", ["finding_id"])
    op.create_index("ix_procore_writebacks_type_status", "procore_writebacks", ["writeback_type", "status"])


def downgrade() -> None:
    op.drop_index("ix_procore_writebacks_type_status", table_name="procore_writebacks")
    op.drop_index("ix_procore_writebacks_finding", table_name="procore_writebacks")
    op.drop_index("ix_procore_writebacks_run", table_name="procore_writebacks")
    op.drop_index("ix_procore_writebacks_project_created", table_name="procore_writebacks")
    op.drop_table("procore_writebacks")

    op.drop_index("ix_idempotency_keys_scope_status", table_name="idempotency_keys")
    op.drop_table("idempotency_keys")

