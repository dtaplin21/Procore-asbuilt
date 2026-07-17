"""AI pipeline entry points.

Inspection location matching is migrating from regex-only vocabulary terms
(term_extractor.py) to a clue-based document extraction pipeline
(document_extraction_schemas -> clue_extractor -> drawing_location_resolver).
The legacy inspection_query_builder module is not used in this repo.
"""

from ai.pipelines.candidate_tile_selector import find_candidate_tiles_from_clues
from ai.pipelines.clue_extractor import build_clues
from ai.pipelines.document_classifier import classify_document
from ai.pipelines.document_extraction_orchestrator import run_document_extraction
from ai.pipelines.inspection_mapping import run_inspection_mapping
from ai.pipelines.type_specific_extractor import extract_type_specific_fields
from ai.pipelines.universal_field_extractor import extract_universal_fields

__all__ = [
    "build_clues",
    "classify_document",
    "extract_type_specific_fields",
    "extract_universal_fields",
    "find_candidate_tiles_from_clues",
    "run_document_extraction",
    "run_inspection_mapping",
]
