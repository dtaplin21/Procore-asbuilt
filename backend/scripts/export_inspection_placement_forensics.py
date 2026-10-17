#!/usr/bin/env python3
"""Export placement forensics: OCR corpus, dossier, vision inputs, and scope trace path.

Usage (from backend/)::

    ./venv/bin/python scripts/export_inspection_placement_forensics.py --run-id 734
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, cast

_BACKEND_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _BACKEND_ROOT not in sys.path:
    sys.path.insert(0, _BACKEND_ROOT)

from ai.agents.evidence_dossier import build_evidence_dossier
from ai.pipelines.clue_fusion_scorer import fuse_candidate_scores, select_fused_winner
from ai.pipelines.document_text_extraction import extract_document
from ai.pipelines.location_match_orchestrator import generate_all_location_candidates
from ai.pipelines.pdf_link_follower import PdfLinkKind, extract_pdf_hyperlinks
from ai.pipelines.scope_geometry import infer_scope_kind
from ai.pipelines.scope_line_tracer import trace_scope_geometry
from ai.pipelines.vision_location_reasoner import (
    _is_strong_coordinate_winner,
    build_dossier_summary,
    should_invoke_vision,
)
from database import SessionLocal
from models.drawing_overlay import DrawingOverlay
from models.drawing_text_element import DrawingTextElement
from models.inspection_run import InspectionRun
from models.models import Drawing, EvidenceRecord
from services.inspection_index_export import build_inspection_index_inventory
from services.storage import storage_key_to_abs_path

_PREVIEW = 4000


def _master_rendition_path(session, master_drawing_id: int, page: int) -> Path | None:
    from ai.agents.inspection_location_agent import _master_rendition_path as _path

    return _path(session, master_drawing_id, page)


def export_forensics(session, *, run_id: int) -> dict[str, Any]:
    run = session.get(InspectionRun, run_id)
    if run is None:
        raise LookupError(f"run {run_id} not found")
    evidence_id = cast(int, run.evidence_id)
    master_id = cast(int, run.master_drawing_id)
    project_id = cast(int, run.project_id)

    report: dict[str, Any] = {
        "run_id": run_id,
        "evidence_id": evidence_id,
        "master_drawing_id": master_id,
        "run_status": run.status,
        "run_error": run.error_message,
    }

    try:
        report["index_inventory_summary"] = {
            "match_investigation": build_inspection_index_inventory(
                session, project_id=project_id, run_id=run_id
            ).get("match_investigation"),
        }
    except Exception as exc:
        report["index_inventory_error"] = str(exc)

    dossier = build_evidence_dossier(
        session,
        evidence_id=evidence_id,
        master_drawing_id=master_id,
        page=1,
        investigate=False,
        force_investigate=False,
    )

    report["dossier_for_match"] = {
        "evidence_kind": dossier.evidence_kind.value,
        "evidence_text_chars": len(dossier.evidence_text or ""),
        "reasoning_text_chars": len(dossier.reasoning_text or ""),
        "reasoning_text_preview": (dossier.reasoning_text or "")[:_PREVIEW],
        "evidence_text_preview": (dossier.evidence_text or "")[:2000],
        "expanded_clues": [
            {
                "type": c.clue_type,
                "values": list(c.expanded_values)[:8],
                "confidence": c.confidence,
            }
            for c in dossier.expanded_clues
        ],
        "linked_attachments": [
            {
                "filename": a.filename,
                "url": (a.url or "")[:200],
                "page_count": a.page_count,
                "text_preview_chars": len(a.text_preview or ""),
                "text_preview": (a.text_preview or "")[:_PREVIEW],
            }
            for a in dossier.linked_attachments
        ],
        "investigation_meta": dossier.investigation_meta,
        "scoped_survey_point_count": len(dossier.master_context.scoped_survey_points),
        "scoped_survey_points_sample": [
            {
                "drawing_id": (p.meta_json or {}).get("drawing_id"),
                "page": p.page,
                "station": p.station,
                "northing": p.northing,
                "easting": p.easting,
                "label_bbox": p.label_bbox_json,
            }
            for p in dossier.master_context.scoped_survey_points[:20]
        ],
    }

    report["vision_model_inputs"] = {
        "dossier_summary_would_send": build_dossier_summary(dossier),
        "dossier_summary_chars": len(build_dossier_summary(dossier)),
    }

    master_png = _master_rendition_path(session, master_id, 1)
    report["vision_model_inputs"]["master_page_1_png"] = (
        str(master_png) if master_png else None
    )
    if master_png and master_png.is_file():
        report["vision_model_inputs"]["master_png_bytes"] = master_png.stat().st_size

    candidates = generate_all_location_candidates(
        session,
        evidence_id=evidence_id,
        master_drawing_id=master_id,
        page=1,
    )
    report["location_candidates_count"] = len(candidates)
    report["location_candidates_sample"] = [
        {
            "method": c.method.value if hasattr(c.method, "value") else str(c.method),
            "source_drawing_id": c.source_drawing_id,
            "confidence": c.confidence,
            "bbox": c.bbox_fractional,
            "page": c.page,
        }
        for c in candidates[:15]
    ]

    ranked = fuse_candidate_scores(dossier, candidates)
    ordered = sorted(ranked, key=lambda s: -s.fused_score)
    report["fused_scores_top"] = [
        {
            "rank": i + 1,
            "fused_score": s.fused_score,
            "rationale": s.rationale,
            "clue_hits": [
                {"dimension": h.dimension, "value": h.clue_value, "weight": h.weight}
                for h in s.clue_hits
            ],
            "bbox": s.candidate.bbox_fractional,
            "method": s.candidate.method.value
            if hasattr(s.candidate.method, "value")
            else str(s.candidate.method),
        }
        for i, s in enumerate(ordered[:12])
    ]

    scope_kind = infer_scope_kind(dossier)
    report["scope_kind"] = scope_kind.value if hasattr(scope_kind, "value") else str(scope_kind)

    vision_would = should_invoke_vision(ranked, dossier)
    report["vision_pipeline"] = {
        "should_invoke_vision_heuristic": vision_would,
        "strong_coordinate_winner_top_candidate": (
            _is_strong_coordinate_winner(ordered[0]) if ordered else False
        ),
        "note": (
            "Vision localize runs whenever a master PNG exists; utility scope tries "
            "vision_trace before aux_survey_chain when master_png_path is set."
        ),
    }

    winner = select_fused_winner(ranked)
    if winner and winner.candidate.bbox_fractional:
        from ai.pipelines.location_match_orchestrator import _load_registration_transform
        from ai.agents.inspection_location_agent import (
            _master_scope_anchor_bbox,
            _registration_aux_drawing_id,
            _resolve_scope_source_drawing_id,
        )

        reg = _load_registration_transform(dossier.evidence)
        reg_aux = _registration_aux_drawing_id(dossier.evidence)
        source_id = _resolve_scope_source_drawing_id(
            dossier,
            winner.candidate.source_drawing_id,
            master_drawing_id=master_id,
            registration_transform=reg,
        )
        anchor = _master_scope_anchor_bbox(
            winner,
            ranked,
            master_drawing_id=master_id,
            session=session,
            page=1,
        )
        report["scope_trace_inputs"] = {
            "winner_rationale": winner.rationale,
            "anchor_bbox": anchor,
            "scope_source_drawing_id": source_id,
            "registration_transform": {
                "scale_x": reg.scale_x,
                "scale_y": reg.scale_y,
                "translate_x": reg.translate_x,
                "translate_y": reg.translate_y,
                "rotation_degrees": reg.rotation_degrees,
            }
            if reg
            else None,
            "registration_aux_drawing_id": reg_aux,
        }
        if anchor is not None:
            try:
                scope = trace_scope_geometry(
                    dossier,
                    anchor_bbox=anchor,
                    scope_kind=scope_kind,
                    page=1,
                    session=session,
                    master_png_path=master_png,
                    source_drawing_id=source_id,
                )
                report["scope_trace_result"] = {
                    "type": scope.type,
                    "points": scope.points,
                    "meta": scope.meta,
                }
            except Exception as exc:
                report["scope_trace_error"] = str(exc)

    overlay = (
        session.query(DrawingOverlay)
        .filter(DrawingOverlay.inspection_run_id == run_id)
        .order_by(DrawingOverlay.id.desc())
        .first()
    )
    if overlay:
        report["persisted_overlay"] = {
            "id": overlay.id,
            "status": overlay.status,
            "geometry": overlay.geometry,
            "meta": overlay.meta,
        }

    ev = session.get(EvidenceRecord, evidence_id)
    if ev and ev.storage_key:
        path = storage_key_to_abs_path(cast(str, ev.storage_key))
        if path.exists():
            doc = extract_document(path)
            report["base_pdf_native_ocr"] = {
                "pages": [
                    {
                        "page": i + 1,
                        "chars": len(doc.page_text(i)),
                        "preview": doc.page_text(i)[:1500],
                    }
                    for i in range(doc.page_count)
                ]
            }
            links = extract_pdf_hyperlinks(path)
            report["base_pdf_hyperlinks_not_followed_from_here"] = [
                {
                    "page": l.page_index + 1,
                    "uri": (l.uri or "")[:250],
                    "kind": str(l.kind),
                }
                for l in links
                if l.kind == PdfLinkKind.EXTERNAL_URI
            ]

    mi = (ev.meta or {}).get("matchInvestigation") if ev else {}
    linked_ids = list((mi or {}).get("linked_drawing_ids") or [])
    not_in_merge = []
    for fp in (mi or {}).get("merge_included") or []:
        pass
    report["not_indexed_or_partial"] = {
        "investigation_complete": (mi or {}).get("investigation_complete"),
        "skipped_link_count": (mi or {}).get("skipped"),
        "errors": (mi or {}).get("errors"),
        "merge_included": (mi or {}).get("merge_included"),
        "merge_truncated": (mi or {}).get("merge_truncated"),
        "merge_dropped": (mi or {}).get("merge_dropped"),
        "cover_lists_sheets_without_pdf_link": [
            "C4.21",
            "C6.00",
        ],
        "linked_drawing_ids_in_db": linked_ids,
    }
    for did in linked_ids:
        d = session.get(Drawing, int(did))
        if not d:
            continue
        count = (
            session.query(DrawingTextElement)
            .filter(DrawingTextElement.master_drawing_id == did)
            .count()
        )
        report.setdefault("linked_drawing_ocr_token_counts", {})[str(did)] = {
            "name": d.name,
            "text_elements": count,
            "index_status": d.index_status,
        }

    report["why_not_confident_placement"] = _placement_blockers(report)
    return report


def _placement_blockers(report: dict[str, Any]) -> list[str]:
    blockers: list[str] = []
    po = report.get("persisted_overlay") or {}
    meta = po.get("meta") or {}
    if meta.get("match_status") == "needs_review":
        blockers.append(
            "Match status is needs_review (below auto-accept threshold or ambiguous scope)."
        )
    geom = po.get("geometry") or {}
    gmeta = geom.get("meta") or {}
    src = gmeta.get("source") or meta.get("scope_source")
    if src in {"survey_endpoints", "aux_survey_chain", "aux_survey_chain_projected"}:
        blockers.append(
            f"Scope geometry fallback '{src}' — short segment from survey/station labels, "
            "not traced sewer linework on master."
        )
    ni = report.get("not_indexed_or_partial") or {}
    if not ni.get("investigation_complete"):
        blockers.append("PDF link investigation marked incomplete (skipped links or merge issues).")
    if ni.get("merge_truncated"):
        blockers.append(f"Merged OCR text truncated: {ni.get('merge_truncated')}")
    return blockers


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-id", type=int, required=True)
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output JSON path (default: Notes/inspection-run-{id}-placement-forensics.json)",
    )
    args = parser.parse_args()
    out = args.out or (
        Path(_BACKEND_ROOT).parent
        / "Notes"
        / f"inspection-run-{args.run_id}-placement-forensics.json"
    )

    session = SessionLocal()
    try:
        report = export_forensics(session, run_id=args.run_id)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(report, indent=2, default=str))
        print(f"Wrote {out} ({out.stat().st_size} bytes)")
    finally:
        session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
