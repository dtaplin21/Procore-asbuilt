"""AI agent implementations."""

from ai.agents.evidence_dossier import EvidenceDossier, build_evidence_dossier
from ai.agents.tools.master_search import (
    expand_term_with_legend,
    load_master_regions,
    search_master_by_clues,
)

from services.inspection_match_persistence import AgentMatchResult

__all__ = [
    "AgentMatchResult",
    "EvidenceDossier",
    "InspectionLocationAgent",
    "build_evidence_dossier",
    "expand_term_with_legend",
    "load_master_regions",
    "search_master_by_clues",
]


def __getattr__(name: str):
    if name == "InspectionLocationAgent":
        from ai.agents.inspection_location_agent import InspectionLocationAgent

        return InspectionLocationAgent
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
