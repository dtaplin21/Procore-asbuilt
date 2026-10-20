"""Inspection + sheet digitization settings defaults (production parity)."""

from config import Settings


def test_production_defaults_enable_sheet_digitization_without_strict_placement() -> None:
    s = Settings(
        database_url="postgresql://u:p@localhost:5432/db",
        app_env="production",
    )
    assert s.sheet_digitization_enabled is True
    assert s.inspection_placement_strict is False
    assert s.drawing_index_enabled is True
    assert s.inspection_index_align_with_master is True


def test_explicit_false_overrides_production_defaults() -> None:
    s = Settings(
        database_url="postgresql://u:p@localhost:5432/db",
        app_env="production",
        sheet_digitization_enabled=False,
        inspection_placement_strict=False,
    )
    assert s.sheet_digitization_enabled is False
    assert s.inspection_placement_strict is False
