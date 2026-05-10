"""P1.5 — persisted diff regions use bbox {x,y,width,height} only, normalized 0–1."""

from ai.pipelines.drawing_diff import _bbox_dict_normalized_01


def test_bbox_full_raster_is_one_by_one():
    b = _bbox_dict_normalized_01(0, 0, 200, 100, raster_w=200, raster_h=100)
    assert b == {"x": 0.0, "y": 0.0, "width": 1.0, "height": 1.0}


def test_bbox_clamps_width_height_to_page_bounds():
    b = _bbox_dict_normalized_01(50, 40, 200, 80, raster_w=100, raster_h=100)
    assert b["x"] == 0.5
    assert b["y"] == 0.4
    assert b["width"] == 0.5
    assert b["height"] == 0.6


def test_bbox_clamps_negative_origin():
    b = _bbox_dict_normalized_01(-10, 0, 30, 20, raster_w=100, raster_h=50)
    assert b["x"] == 0.0
    assert b["y"] == 0.0
    assert b["width"] == 0.3
    assert b["height"] == 0.4
