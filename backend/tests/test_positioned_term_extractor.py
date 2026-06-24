"""Tests for positioned vocabulary term extraction."""

from ai.pipelines.document_text_extraction import (
    BoundingBox,
    ExtractedDocument,
    PositionedWord,
    SourceFormat,
)
from ai.pipelines.positioned_term_extractor import (
    PositionedTerm,
    _reconstruct_with_offsets,
    _union_boxes,
    extract_positioned_terms,
    extract_positioned_terms_for_page,
)
from services.inspection_vocabulary import VocabCategory


def _bbox(x: float, y: float, width: float = 40.0, height: float = 12.0) -> BoundingBox:
    return BoundingBox(
        x=x,
        y=y,
        width=width,
        height=height,
        page_width=612.0,
        page_height=792.0,
    )


def _word(text: str, x: float, y: float, page_index: int = 0) -> PositionedWord:
    return PositionedWord(text=text, bbox=_bbox(x, y), page_index=page_index)


def test_reconstruct_with_offsets_tracks_word_spans() -> None:
    words = [_word("Rough-In", 10, 100), _word("Passed", 60, 100)]
    text, spans = _reconstruct_with_offsets(words)

    assert text == "Rough-In Passed"
    assert spans[0][:2] == (0, 8)
    assert spans[1][:2] == (9, 15)


def test_union_boxes_covers_multi_word_match() -> None:
    boxes = [_bbox(10, 100), _bbox(55, 100), _bbox(95, 100)]
    united = _union_boxes(boxes)

    assert united.x == 10
    assert united.y == 100
    assert united.width == 125  # 95 + 40 - 10
    assert united.height == 12


def test_extract_positioned_terms_for_page_maps_multi_word_phrase() -> None:
    words = [
        _word("Approved", 10, 200),
        _word("As", 60, 200),
        _word("Noted", 85, 200),
    ]
    terms = extract_positioned_terms_for_page(
        words,
        page_index=0,
        categories=(VocabCategory.INSPECTION_STATUS,),
    )

    assert len(terms) == 1
    assert terms[0].term.canonical == "Approved As Noted"
    assert terms[0].page_index == 0
    assert terms[0].bbox.x == 10
    assert terms[0].bbox.width == 115  # 85 + 40 - 10


def test_extract_positioned_terms_across_pages() -> None:
    document = ExtractedDocument(
        source_format=SourceFormat.NATIVE_PDF,
        page_count=2,
        words=[
            _word("Passed", 10, 50, page_index=0),
            _word("Failed", 10, 50, page_index=1),
        ],
    )
    terms = extract_positioned_terms(
        document, categories=(VocabCategory.INSPECTION_STATUS,)
    )

    assert len(terms) == 2
    assert {t.term.canonical for t in terms} == {"Passed", "Failed"}
    assert {t.page_index for t in terms} == {0, 1}


def test_positioned_term_to_dict_includes_bbox_and_page() -> None:
    term = PositionedTerm(
        term=extract_positioned_terms_for_page(
            [_word("Open", 5, 10)],
            page_index=2,
            categories=(VocabCategory.INSPECTION_STATUS,),
        )[0].term,
        page_index=2,
        bbox=_bbox(5, 10),
    )
    payload = term.to_dict()

    assert payload["pageIndex"] == 2
    assert payload["bbox"]["pageWidth"] == 612.0
    assert payload["canonical"] == "Open"
