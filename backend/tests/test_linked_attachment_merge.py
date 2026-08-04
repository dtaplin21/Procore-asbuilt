"""Regression test for the exact bug: a large low-priority document must not
crowd out a small high-priority one, even when fetched first."""

from __future__ import annotations

from ai.pipelines.linked_attachment_merge import (
    LinkedAttachment,
    _priority_score,
    merge_linked_attachments_within_budget,
)


def _make(filename: str, word_count: int, pages: int, url: str | None = None) -> LinkedAttachment:
    text = " ".join(["word"] * word_count)
    return LinkedAttachment(
        url=url or f"https://example.com/{filename}",
        filename=filename,
        text=text,
        word_count=word_count,
        pages=pages,
    )


def test_small_priority_doc_survives_large_boilerplate_doc_processed_first() -> None:
    """Reproduces the exact reported bug: a 78-page submittal (22008 words)
    fetched before a 2-page install drawing (888 words) must not cause the
    install drawing to be dropped."""
    submittal = _make(
        "UMR 331000-5.0 - M&H - Sanitary Sewer PD_Approved (5).pdf",
        word_count=22008,
        pages=78,
    )
    install_drawing = _make(
        "7.20-7.24 U1.C4.20 6.00 Sanitary Sewer Install.pdf",
        word_count=888,
        pages=2,
    )

    result = merge_linked_attachments_within_budget(
        [submittal, install_drawing], word_budget=6000
    )

    assert install_drawing.filename in result["included"]
    assert install_drawing.filename not in result["dropped"]
    assert "Sanitary Sewer Install" in result["merged_text"]


def test_budget_exhaustion_drops_lowest_priority_not_first_fetched() -> None:
    a = _make("field_notes.pdf", word_count=3000, pages=3)
    b = _make("random_submittal.pdf", word_count=4000, pages=40)
    c = _make("install_plan.pdf", word_count=2000, pages=2)

    result = merge_linked_attachments_within_budget([a, b, c], word_budget=5000)

    assert "install_plan.pdf" in result["included"]
    assert "field_notes.pdf" in result["included"]
    assert "random_submittal.pdf" in result["dropped"]


def test_oversized_single_attachment_gets_truncated_not_dropped() -> None:
    only_doc = _make("huge_install_drawing.pdf", word_count=10000, pages=5)
    result = merge_linked_attachments_within_budget([only_doc], word_budget=6000)

    assert "huge_install_drawing.pdf" in result["included"]
    assert "huge_install_drawing.pdf" in result["truncated"]
    assert "[TRUNCATED]" in result["merged_text"]


def test_priority_score_favors_install_over_submittal_regardless_of_order() -> None:
    install = _make("some_install_plan.pdf", word_count=500, pages=2)
    submittal = _make("some_product_submittal.pdf", word_count=500, pages=2)
    assert _priority_score(install) > _priority_score(submittal)
