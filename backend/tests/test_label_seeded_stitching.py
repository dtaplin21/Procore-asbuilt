"""Tests for label-seeded utility run tracing (Step 4)."""

from __future__ import annotations

from ai.pipelines.label_seeded_stitching import Label, Seg, trace_runs

GRAY = (115, 115, 115)


def _line_with_labels(y: float, x_start: float, n: int, *, stub=0.012, gap=0.0087, color=GRAY, code="SS"):
    segs, labs, x = [], [], x_start
    for _ in range(n):
        segs.append(Seg(x, y, x + stub, y, color, 0.72))
        gx0, gx1 = x + stub, x + stub + gap
        labs.append(Label(code, gx0 + 0.002, y - 0.002, gx1 - 0.002, y + 0.002))
        x = gx1
    segs.append(Seg(x, y, x + stub, y, color, 0.72))
    return segs, labs


def test_trace_from_middle_label_covers_full_run() -> None:
    segs, labs = _line_with_labels(0.5, 0.20, 5)
    runs = trace_runs(segs, [labs[2]], text_boxes=labs)
    assert len(runs) == 1 and runs[0].status == "traced"
    xs = [p[0] for p in runs[0].points]
    assert abs(min(xs) - 0.20) < 1e-6
    assert abs(max(xs) - (0.20 + 6 * 0.012 + 5 * 0.0087)) < 1e-6
    assert runs[0].stop_reasons == ("dead_end", "dead_end")


def test_multiple_labels_merge_into_one_run() -> None:
    segs, labs = _line_with_labels(0.5, 0.20, 5)
    runs = trace_runs(segs, labs, text_boxes=labs)
    assert len(runs) == 1 and len(runs[0].labels) == 5


def test_crossing_line_other_style_does_not_break_run() -> None:
    segs, labs = _line_with_labels(0.5, 0.20, 5)
    cross = [Seg(0.2 + 0.012 + 0.0043, 0.45, 0.2 + 0.012 + 0.0043, 0.55, (0, 0, 0), 1.44)]
    runs = trace_runs(segs + cross, labs, text_boxes=labs)
    assert len(runs) == 1 and runs[0].status == "traced"


def test_parallel_fw_not_absorbed_into_ss() -> None:
    segs, labs = _line_with_labels(0.5, 0.20, 5)
    fw, fw_labs = _line_with_labels(0.52, 0.20, 5, code="FW")
    runs = trace_runs(segs + fw, labs, text_boxes=labs + fw_labs)
    assert len(runs) == 1
    assert all(abs(p[1] - 0.5) < 0.001 for p in runs[0].points)


def test_wide_gap_not_bridged() -> None:
    segs, labs = _line_with_labels(0.5, 0.20, 5)
    wide = [s for s in segs if s.x1 < 0.20 + 3 * 0.0207]
    far = [Seg(s.x0 + 0.08, s.y0, s.x1 + 0.08, s.y1, s.color, s.width) for s in segs[3:]]
    runs = trace_runs(wide + far, [labs[0]], text_boxes=labs)
    assert runs[0].stop_reasons[1] == "dead_end"
    assert max(p[0] for p in runs[0].points) < 0.20 + 3 * 0.0207 + 0.001


def test_glyph_strokes_excluded() -> None:
    segs, labs = _line_with_labels(0.5, 0.20, 5)
    glyphs = [
        Seg(labs[2].x0 + 0.0005, 0.499, labs[2].x0 + 0.0020, 0.501, GRAY, 0.72),
        Seg(labs[2].x0 + 0.0021, 0.501, labs[2].x1 - 0.0005, 0.499, GRAY, 0.72),
    ]
    runs = trace_runs(segs + glyphs, [labs[2]], text_boxes=labs)
    assert runs[0].status == "traced"
    assert not any(i >= len(segs) for i in runs[0].stub_indices)


def test_branch_sets_ambiguous() -> None:
    seg_a = [Seg(0.20, 0.5, 0.212, 0.5, GRAY, 0.72)]
    lab = Label("SS", 0.2135, 0.498, 0.2175, 0.502)
    seg_b = [Seg(0.2195, 0.5, 0.231, 0.5, GRAY, 0.72)]
    fork_up = [Seg(0.2318, 0.5, 0.2438, 0.5 + 0.004, GRAY, 0.72)]
    fork_dn = [Seg(0.2318, 0.5, 0.2438, 0.5 - 0.004, GRAY, 0.72)]
    runs = trace_runs(seg_a + seg_b + fork_up + fork_dn, [lab], text_boxes=[lab])
    assert runs[0].ambiguous and runs[0].stop_reasons[1] == "branch"


def test_single_stub_no_run() -> None:
    runs = trace_runs(
        [Seg(0.20, 0.5, 0.212, 0.5, GRAY, 0.72)],
        [Label("SS", 0.2135, 0.498, 0.2175, 0.502)],
    )
    assert runs == []
