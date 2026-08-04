"""add legend reference tables

Revision ID: p0l1e2g3e4n5
Revises: p9d2m4c6a8n0
Create Date: 2026-07-30

Stores transcribed cover-sheet legend abbreviations, line types, and symbols
for clue expansion during inspection matching.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "p0l1e2g3e4n5"
down_revision = "p9d2m4c6a8n0"
branch_labels = None
depends_on = None


def _inspector():
    return inspect(op.get_bind())


def _table_exists(name: str) -> bool:
    return _inspector().has_table(name)


def _index_exists(table: str, index_name: str) -> bool:
    return any(index["name"] == index_name for index in _inspector().get_indexes(table))


def _unique_on_columns_exists(table: str, columns: list[str]) -> bool:
    normalized = tuple(columns)
    for constraint in _inspector().get_unique_constraints(table):
        if tuple(constraint.get("column_names") or ()) == normalized:
            return True
    for index in _inspector().get_indexes(table):
        if index.get("unique") and tuple(index.get("column_names") or ()) == normalized:
            return True
    return False


def _create_index_if_missing(
    index_name: str,
    table_name: str,
    columns: list[str],
    *,
    unique: bool = False,
) -> None:
    if _index_exists(table_name, index_name):
        return
    op.create_index(index_name, table_name, columns, unique=unique)


def upgrade() -> None:
    if not _table_exists("drawing_legend_abbreviations"):
        op.create_table(
            "drawing_legend_abbreviations",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "project_id",
                sa.Integer(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("abbreviation", sa.String(), nullable=False),
            sa.Column("expansion", sa.String(), nullable=False),
            sa.Column("category", sa.String(), nullable=True),
            sa.Column("source_sheet", sa.String(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
            ),
        )

    _create_index_if_missing(
        "ix_drawing_legend_abbreviations_project_id",
        "drawing_legend_abbreviations",
        ["project_id"],
    )
    _create_index_if_missing(
        "ix_drawing_legend_abbreviations_abbreviation",
        "drawing_legend_abbreviations",
        ["abbreviation"],
    )
    if not _unique_on_columns_exists(
        "drawing_legend_abbreviations",
        ["project_id", "abbreviation"],
    ):
        _create_index_if_missing(
            "ix_legend_abbrev_lookup",
            "drawing_legend_abbreviations",
            ["project_id", "abbreviation"],
            unique=True,
        )

    if not _table_exists("drawing_legend_line_types"):
        op.create_table(
            "drawing_legend_line_types",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "project_id",
                sa.Integer(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("line_type_name", sa.String(), nullable=False),
            sa.Column("abbreviation_code", sa.String(), nullable=True),
            sa.Column("category", sa.String(), nullable=True),
            sa.Column("existing_style_desc", sa.String(), nullable=True),
            sa.Column("proposed_style_desc", sa.String(), nullable=True),
            sa.Column("source_sheet", sa.String(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
            ),
        )

    _create_index_if_missing(
        "ix_drawing_legend_line_types_project_id",
        "drawing_legend_line_types",
        ["project_id"],
    )
    _create_index_if_missing(
        "ix_legend_line_type_code",
        "drawing_legend_line_types",
        ["abbreviation_code"],
    )
    _create_index_if_missing(
        "ix_drawing_legend_line_types_abbreviation_code",
        "drawing_legend_line_types",
        ["abbreviation_code"],
    )

    if not _table_exists("drawing_legend_symbols"):
        op.create_table(
            "drawing_legend_symbols",
            sa.Column("id", sa.Integer(), primary_key=True),
            sa.Column(
                "project_id",
                sa.Integer(),
                sa.ForeignKey("projects.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("symbol_name", sa.String(), nullable=False),
            sa.Column("abbreviation_code", sa.String(), nullable=True),
            sa.Column("category", sa.String(), nullable=True),
            sa.Column("existing_desc", sa.String(), nullable=True),
            sa.Column("proposed_desc", sa.String(), nullable=True),
            sa.Column("source_sheet", sa.String(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.func.now(),
                nullable=True,
            ),
        )

    _create_index_if_missing(
        "ix_drawing_legend_symbols_project_id",
        "drawing_legend_symbols",
        ["project_id"],
    )
    _create_index_if_missing(
        "ix_legend_symbol_code",
        "drawing_legend_symbols",
        ["abbreviation_code"],
    )
    _create_index_if_missing(
        "ix_drawing_legend_symbols_abbreviation_code",
        "drawing_legend_symbols",
        ["abbreviation_code"],
    )


def downgrade() -> None:
    if _table_exists("drawing_legend_symbols"):
        for index_name in (
            "ix_legend_symbol_code",
            "ix_drawing_legend_symbols_abbreviation_code",
            "ix_drawing_legend_symbols_project_id",
        ):
            if _index_exists("drawing_legend_symbols", index_name):
                op.drop_index(index_name, table_name="drawing_legend_symbols")
        op.drop_table("drawing_legend_symbols")

    if _table_exists("drawing_legend_line_types"):
        for index_name in (
            "ix_legend_line_type_code",
            "ix_drawing_legend_line_types_abbreviation_code",
            "ix_drawing_legend_line_types_project_id",
        ):
            if _index_exists("drawing_legend_line_types", index_name):
                op.drop_index(index_name, table_name="drawing_legend_line_types")
        op.drop_table("drawing_legend_line_types")

    if _table_exists("drawing_legend_abbreviations"):
        for index_name in (
            "ix_legend_abbrev_lookup",
            "ix_drawing_legend_abbreviations_abbreviation",
            "ix_drawing_legend_abbreviations_project_id",
        ):
            if _index_exists("drawing_legend_abbreviations", index_name):
                op.drop_index(index_name, table_name="drawing_legend_abbreviations")
        op.drop_table("drawing_legend_abbreviations")
