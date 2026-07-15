"""AI pipeline entry points.

Inspection location matching is migrating from regex-only vocabulary terms
(term_extractor.py) to a clue-based document extraction pipeline
(document_extraction_schemas -> clue_extractor -> drawing_location_resolver).
The legacy inspection_query_builder module is not used in this repo.
"""

from ai.pipelines.clue_extractor import build_clues
from ai.pipelines.document_classifier import classify_document
from ai.pipelines.inspection_mapping import run_inspection_mapping

__all__ = ["build_clues", "classify_document", "run_inspection_mapping"]
