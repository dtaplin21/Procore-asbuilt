"""Read-only agent tools for master search, legend expansion, and PDF investigation."""

from ai.agents.tools.master_search import (
    expand_term_with_legend,
    load_master_regions,
    search_master_by_clues,
)
from ai.agents.tools.pdf_investigation import (
    EvidenceInvestigationPayload,
    PdfInvestigationResult,
    RenderedPdfPage,
    extract_page_clues,
    follow_and_capture_links,
    investigate_pdf_links,
    list_pdf_hyperlinks,
    render_pdf_page,
    run_pdf_investigation,
)

__all__ = [
    "EvidenceInvestigationPayload",
    "PdfInvestigationResult",
    "RenderedPdfPage",
    "expand_term_with_legend",
    "extract_page_clues",
    "follow_and_capture_links",
    "investigate_pdf_links",
    "list_pdf_hyperlinks",
    "load_master_regions",
    "render_pdf_page",
    "run_pdf_investigation",
    "search_master_by_clues",
]
