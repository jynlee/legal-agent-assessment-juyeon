"""Deterministic normalization and chunking for default-corpus judgements.

Every example here is synthetic, matching the shapes described in
reports/decisions/2026-08-11-normalization-and-chunking-design.md. Real
dataset payloads are never committed.
"""

from legal_agent_assessment.chunking import (
    CHUNKING_VERSION,
    NORMALIZATION_VERSION,
    Chunk,
    ChunkType,
    JudgementChunkFields,
    StatuteChunkFields,
    StatuteSection,
    find_table_spans,
    split_paragraphs,
    split_statute_sections,
)
from legal_agent_assessment.dataset import (
    DocumentKind,
    LawLinkage,
    LinkageStrength,
    StatuteUnitKind,
)


def test_split_paragraphs_splits_on_br_and_drops_empties() -> None:
    text = (
        "【주    문】<br/>  원심판결을 파기한다. <br/><br/>【이    유】  상고이유를 판단한다. <br/>"
    )

    paragraphs = split_paragraphs(text)

    assert paragraphs == (
        "【주    문】",
        "원심판결을 파기한다.",
        "【이    유】  상고이유를 판단한다.",
    )


def test_split_paragraphs_never_splits_on_a_bare_newline() -> None:
    text = "한 줄\n다음 줄<br/>다음 청크"

    paragraphs = split_paragraphs(text)

    assert paragraphs == ("한 줄\n다음 줄", "다음 청크")


def test_chunk_is_frozen_and_carries_judgement_kind_fields() -> None:
    chunk = Chunk(
        chunk_id="precedent-000001#body-000",
        document_id="precedent-000001",
        chunk_type=ChunkType.BODY,
        ordinal=0,
        text="본문 예시",
        content_hash="sha256:" + "a" * 64,
        document_kind=DocumentKind.JUDGEMENT,
        dataset_version="dataset-v1",
        normalization_version=NORMALIZATION_VERSION,
        chunking_version=CHUNKING_VERSION,
        title="의료법위반",
        source_uri="https://glaw.scourt.go.kr/example",
        official_number="2099도1111",
        locator="이유",
        linked_laws=(LawLinkage(law_name="의료법", strength=LinkageStrength.CORE),),
        kind_fields=JudgementChunkFields(
            case_name="의료법위반",
            court="대법원",
            decided_on="20990101",
            case_number="2099도1111",
        ),
    )

    assert chunk.chunk_type is ChunkType.BODY
    assert chunk.kind_fields.issue_ordinal is None
    assert chunk.kind_fields.referenced_provisions == ""

    try:
        chunk.text = "changed"  # type: ignore[misc]
        raised = False
    except AttributeError:
        raised = True
    assert raised, "Chunk must be frozen"


def test_chunk_carries_statute_kind_fields() -> None:
    chunk = Chunk(
        chunk_id="doc-example#body-000",
        document_id="doc-example",
        chunk_type=ChunkType.BODY,
        ordinal=0,
        text="제1조(목적) 이 법은 약사에 관한 사항을 규정한다.",
        content_hash="sha256:" + "b" * 64,
        document_kind=DocumentKind.STATUTE,
        dataset_version="dataset-v2",
        normalization_version=NORMALIZATION_VERSION,
        chunking_version=CHUNKING_VERSION,
        title="약사법 제1조",
        source_uri="https://www.law.go.kr/법령/약사법",
        official_number="279725",
        locator="제1조",
        linked_laws=(),
        kind_fields=StatuteChunkFields(
            law_name="약사법",
            unit_kind=StatuteUnitKind.ARTICLE,
            article_number="1",
        ),
    )

    assert chunk.document_kind is DocumentKind.STATUTE
    assert chunk.kind_fields.status == "current"
    assert chunk.kind_fields.layout == "text"
    assert chunk.kind_fields.appendix_number is None


def test_find_table_spans_returns_empty_for_plain_text() -> None:
    assert find_table_spans("그냥 평범한 조문 텍스트\n다음 줄") == ()


def test_find_table_spans_covers_a_single_contiguous_table_block() -> None:
    text = "머리말\n┌─┬─┐\n│a│b│\n└─┴─┘\n꼬리말"

    spans = find_table_spans(text)

    assert len(spans) == 1
    start, end = spans[0]
    assert text[start:end] == "┌─┬─┐\n│a│b│\n└─┴─┘"


def test_find_table_spans_keeps_two_separate_blocks_apart() -> None:
    text = "A\n│x│\nB\n│y│\nC"

    spans = find_table_spans(text)

    assert len(spans) == 2
    assert text[spans[0][0] : spans[0][1]] == "│x│"
    assert text[spans[1][0] : spans[1][1]] == "│y│"


def test_find_table_spans_detects_a_marker_line_inside_a_table_row() -> None:
    """The exact risk this design exists to catch: a 가/나/다 marker sitting
    on a table-formatted line must still be inside the detected span."""

    text = "제목\n┌───┬───┐\n│마. 위반 │근거 │\n└───┴───┘\n끝"

    spans = find_table_spans(text)

    assert len(spans) == 1
    start, end = spans[0]
    assert "마." in text[start:end]


def test_split_statute_sections_splits_plain_text_at_numbered_markers() -> None:
    text = "1. 첫 번째 항목 내용\n2. 두 번째 항목 내용"

    sections = split_statute_sections(text, table_spans=())

    assert [s.text for s in sections] == ["1. 첫 번째 항목 내용", "2. 두 번째 항목 내용"]
    assert [s.marker for s in sections] == ["1", "2"]
    assert all(not s.is_table for s in sections)


def test_split_statute_sections_splits_at_gana_markers() -> None:
    text = "가. 첫 목\n나. 두번째 목"

    sections = split_statute_sections(text, table_spans=())

    assert [s.marker for s in sections] == ["가", "나"]


def test_split_statute_sections_keeps_a_protected_span_whole_and_unsplit() -> None:
    """The exact risk this design exists to catch: a marker sitting inside a
    protected table span must never become a split point."""

    text = "머리말\n┌───┬───┐\n│마. 위반 │근거 │\n└───┴───┘\n꼬리말"
    table_spans = find_table_spans(text)

    sections = split_statute_sections(text, table_spans)

    table_sections = [s for s in sections if s.is_table]
    assert len(table_sections) == 1
    assert "마." in table_sections[0].text
    assert table_sections[0].marker is None
    # The table piece is not further split at "마." -- it is exactly the
    # protected span's full text.
    start, end = table_spans[0]
    assert table_sections[0].text == text[start:end]


def test_split_statute_sections_handles_text_around_a_protected_span() -> None:
    text = "1. 앞부분\n┌─┐\n│x│\n└─┘\n2. 뒷부분"
    table_spans = find_table_spans(text)

    sections = split_statute_sections(text, table_spans)

    kinds = [(s.marker, s.is_table) for s in sections]
    assert kinds == [("1", False), (None, True), ("2", False)]


def test_split_statute_sections_returns_the_whole_text_when_no_markers_or_tables() -> None:
    text = "번호도 목차도 없이 쭉 이어지는 산문 텍스트."

    sections = split_statute_sections(text, table_spans=())

    assert len(sections) == 1
    assert sections[0] == StatuteSection(text=text, marker=None, is_table=False)
