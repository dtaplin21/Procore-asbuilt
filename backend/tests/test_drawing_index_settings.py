"""Master drawing auto-index settings (Phase 0d)."""

from config import Settings


def test_drawing_index_settings_defaults():
    s = Settings(database_url="postgresql://u:p@localhost:5432/db")
    assert s.drawing_index_enabled is True
    assert s.drawing_index_tile_size_normalized == 0.08
    assert s.drawing_index_min_cluster_words == 2
    assert s.drawing_index_ocr_max_pages == 0
    assert s.drawing_index_auto_region_mode == "cluster"


def test_drawing_index_auto_region_mode_normalizes_case():
    s = Settings(
        database_url="postgresql://u:p@localhost:5432/db",
        drawing_index_auto_region_mode="HYBRID",
    )
    assert s.drawing_index_auto_region_mode == "hybrid"


def test_drawing_index_settings_override():
    s = Settings(
        database_url="postgresql://u:p@localhost:5432/db",
        drawing_index_enabled=False,
        drawing_index_tile_size_normalized=0.12,
        drawing_index_min_cluster_words=3,
        drawing_index_ocr_max_pages=5,
        drawing_index_auto_region_mode="grid",
    )
    assert s.drawing_index_enabled is False
    assert s.drawing_index_tile_size_normalized == 0.12
    assert s.drawing_index_min_cluster_words == 3
    assert s.drawing_index_ocr_max_pages == 5
    assert s.drawing_index_auto_region_mode == "grid"
