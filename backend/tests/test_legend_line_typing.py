"""Unit tests for legend_line_typing (Steps 2–3)."""

from __future__ import annotations

import dataclasses

from ai.pipelines.legend_line_typing import (
    ChainTyping,
    LegendTemplate,
    LineTypeRow,
    classify_chains,
    extract_swatch_style,
    match_line_type,
    select_chains_for_storage,
    template_families,
)


def test_match_line_type_boilerplate_and_ties() -> None:
    types = [
        LineTypeRow(1, "Sanitary Sewer Main", "SS"),
        LineTypeRow(2, "Storm Drain Main", "SD"),
        LineTypeRow(3, "Fire Water Line", "FW"),
        LineTypeRow(4, "Electrical Line", "E"),
    ]
    lt, why = match_line_type(types, "SEWER LINE \u2014 HCAI PERMIT (SHOWN FOR REFERENCE ONLY)")
    assert lt and lt.id == 1, why
    lt, why = match_line_type(types, "FIRE WATER LINE \u2014 HCAI PERMIT (SHOWN FOR REFERENCE ONLY)")
    assert lt and lt.id == 3, why
    lt, why = match_line_type(types, "ELECTRICAL LINE \u2014 HCAI PERMIT (SHOWN FOR REFERENCE ONLY)")
    assert lt and lt.id == 4, why
    for generic in ("UTILITY LINE", "UTILITY LINE (SEPARATE PHASE)", "PROPERTY LINE", "EXISTING UTILITY LINE"):
        lt, why = match_line_type(types, generic)
        assert lt is None, (generic, why)
    two_sewers = types + [LineTypeRow(9, "Sanitary Sewer Force Main", "SS")]
    lt, why = match_line_type(two_sewers, "SEWER LINE")
    assert lt is None and "ambiguous" in why, why


def test_classify_families_and_unmatched() -> None:
    @dataclasses.dataclass
    class St:
        stroke_width_bucket: float
        color: tuple[int, int, int] | None = None
        kind_guess: str = "solid"

    @dataclasses.dataclass
    class Ch:
        points: tuple[tuple[float, float], ...]
        color: tuple[int, int, int] | None
        style: St

    mid = (115, 115, 115)
    tpls = [
        LegendTemplate(1, "Sanitary Sewer Main", "SS", St(0.72, mid), 7),
        LegendTemplate(3, "Fire Water Line", "FW", St(0.72, mid), 8),
        LegendTemplate(2, "Storm Drain Main", "SD", St(1.44, (0, 0, 0)), 3),
    ]
    assert [len(f) for f in template_families(tpls)] == [2, 1]
    chains = [
        Ch(((0, 0), (1, 0)), mid, St(0.72, mid)),
        Ch(((0, 0), (1, 0)), (0, 0, 0), St(1.44)),
        Ch(((0, 0), (1, 0)), (192, 192, 192), St(0.9)),
        Ch(((0, 0), (1, 0)), mid, St(0.9)),
    ]
    ty = classify_chains(chains, tpls)
    assert [t.status for t in ty] == ["ambiguous_family", "typed", "unmatched", "unmatched"]
    assert ty[1].legend_line_type_id == 2 and ty[0].candidate_type_ids == (1, 3)


def test_extract_swatch_style_ignores_overlapping_plan_line() -> None:
    @dataclasses.dataclass
    class Sg:
        x0: float
        y0: float
        x1: float
        y1: float
        color: tuple[int, int, int]
        stroke_width: float

    mid = (115, 115, 115)
    bbox = (0.724, 0.0935, 0.784, 0.101)
    segs = [
        Sg(0.7122, 0.1002, 0.7378, 0.1002, (192, 192, 192), 0.9),
        Sg(0.7406, 0.0984, 0.7526, 0.0984, mid, 0.72),
        Sg(0.7555, 0.0983, 0.7562, 0.0983, mid, 0.72),
        Sg(0.7613, 0.0984, 0.7733, 0.0984, mid, 0.72),
    ]
    sw = extract_swatch_style(segs, bbox)
    assert sw and sw.color == mid and sw.stroke_width_bucket == 0.72 and sw.kind_guess == "stub_gap"


def test_select_chains_for_storage_wanted_type_first() -> None:
    @dataclasses.dataclass
    class St:
        stroke_width_bucket: float
        color: tuple[int, int, int] | None = None

    @dataclasses.dataclass
    class Ch:
        points: tuple[tuple[float, float], ...]
        color: tuple[int, int, int] | None
        style: St

    mid = (115, 115, 115)
    many = [Ch(((0, 0), (0.9, 0)), (192, 192, 192), St(0.9)) for _ in range(50)]
    short_ss = [Ch(((0.5, 0.5), (0.505, 0.5)), mid, St(0.72)) for _ in range(3)]
    allc = many + short_ss
    tpl = LegendTemplate(1, "Sanitary Sewer Main", "SS", St(0.72, mid))
    ty = classify_chains(allc, [tpl])
    keep, _ = select_chains_for_storage(allc, ty, plan_bbox=None, wanted_type_ids=(), max_chains=5)
    assert all(i < 50 for i in keep)
    ty2 = [
        ChainTyping(
            t.chain_index,
            "typed" if t.chain_index >= 50 else t.status,
            "SS" if t.chain_index >= 50 else None,
            1 if t.chain_index >= 50 else None,
            (1,) if t.chain_index >= 50 else (),
            None,
        )
        for t in ty
    ]
    keep2, tiers2 = select_chains_for_storage(allc, ty2, plan_bbox=None, wanted_type_ids=(1,), max_chains=5)
    assert {50, 51, 52} <= set(keep2) and tiers2["tier1"] == 3 and tiers2["wanted_dropped"] == 0

    many_wanted = [
        ChainTyping(i, "typed", "SS", 1, (1,), None) for i in range(6)
    ]
    short = [Ch(((0.1, 0.1), (0.11, 0.1)), mid, St(0.72)) for _ in range(6)]
    keep3, tiers3 = select_chains_for_storage(short, many_wanted, plan_bbox=None, wanted_type_ids=(1,), max_chains=2)
    assert set(keep3) == {0, 1, 2, 3, 4, 5}
    assert tiers3["dropped"] == 0 and tiers3["wanted_dropped"] == 0
