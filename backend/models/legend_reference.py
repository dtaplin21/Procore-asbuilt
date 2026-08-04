"""Legend / abbreviation reference tables transcribed from cover-sheet legends (e.g. C0.00).

Nullable ``project_id``: ``NULL`` rows are general-purpose defaults usable across
projects; project-scoped rows override or extend firm-specific definitions.
"""

from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, UniqueConstraint, func

from .base import Base


class DrawingLegendAbbreviation(Base):
    __tablename__ = "drawing_legend_abbreviations"

    id = Column(Integer, primary_key=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    abbreviation = Column(String, nullable=False, index=True)
    expansion = Column(String, nullable=False)
    category = Column(String, nullable=True)
    source_sheet = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "abbreviation",
            name="uq_legend_abbrev_per_project",
        ),
    )


class DrawingLegendLineType(Base):
    __tablename__ = "drawing_legend_line_types"

    id = Column(Integer, primary_key=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    line_type_name = Column(String, nullable=False)
    abbreviation_code = Column(String, nullable=True, index=True)
    category = Column(String, nullable=True)
    existing_style_desc = Column(String, nullable=True)
    proposed_style_desc = Column(String, nullable=True)
    source_sheet = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())


class DrawingLegendSymbol(Base):
    __tablename__ = "drawing_legend_symbols"

    id = Column(Integer, primary_key=True)
    project_id = Column(
        Integer,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    symbol_name = Column(String, nullable=False)
    abbreviation_code = Column(String, nullable=True, index=True)
    category = Column(String, nullable=True)
    existing_desc = Column(String, nullable=True)
    proposed_desc = Column(String, nullable=True)
    source_sheet = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
