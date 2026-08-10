"""add suite to location_match_labels

Revision ID: u0s1u2i3t4e5
Revises: g1l2m3a4b5e6
Create Date: 2026-08-10

Eval suite slug so labels can be filtered per project/dataset.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "u0s1u2i3t4e5"
down_revision = "g1l2m3a4b5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "location_match_labels" not in inspector.get_table_names():
        return

    columns = {col["name"] for col in inspector.get_columns("location_match_labels")}
    if "suite" not in columns:
        op.add_column(
            "location_match_labels",
            sa.Column(
                "suite",
                sa.String(),
                nullable=False,
                server_default="default",
            ),
        )
        op.execute(
            sa.text(
                "UPDATE location_match_labels "
                "SET suite = 'ucsf' "
                "WHERE label_id LIKE 'ucsf-%'"
            )
        )

    indexes = {idx["name"] for idx in inspector.get_indexes("location_match_labels")}
    if "ix_location_match_labels_suite" not in indexes:
        op.create_index(
            "ix_location_match_labels_suite",
            "location_match_labels",
            ["suite"],
        )


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)
    if "location_match_labels" not in inspector.get_table_names():
        return

    indexes = {idx["name"] for idx in inspector.get_indexes("location_match_labels")}
    if "ix_location_match_labels_suite" in indexes:
        op.drop_index(
            "ix_location_match_labels_suite",
            table_name="location_match_labels",
        )

    columns = {col["name"] for col in inspector.get_columns("location_match_labels")}
    if "suite" in columns:
        op.drop_column("location_match_labels", "suite")
