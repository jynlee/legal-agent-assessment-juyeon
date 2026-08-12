"""Deterministic normalization and chunking for default-corpus judgements.

Every example here is synthetic, matching the shapes described in
reports/decisions/2026-08-11-normalization-and-chunking-design.md. Real
dataset payloads are never committed.
"""

from datetime import UTC, datetime

from legal_agent_assessment.chunking import (
    CHUNKING_VERSION,
    NORMALIZATION_VERSION,
    TARGET_MAX_CHARS,
    Chunk,
    ChunkType,
    JudgementChunkFields,
    StatuteChunkFields,
    StatuteSection,
    chunk_statute_record,
    find_table_spans,
    pack_lines_to_budget,
    split_paragraphs,
    split_statute_sections,
)
from legal_agent_assessment.dataset import (
    DocumentKind,
    LawLinkage,
    LinkageStrength,
    SourceAdmission,
    SourceProvenance,
    SourceRecord,
    StatuteIdentity,
    StatuteUnitKind,
    UsageDisposition,
)
from legal_agent_assessment.dataset_validation import content_hash as _content_hash


def _statute_record(
    *,
    document_id: str = "doc-example",
    title: str = "약사법 제1조",
    text: str,
    unit_kind: StatuteUnitKind = StatuteUnitKind.ARTICLE,
    article_number: str | None = "1",
    appendix_number: str | None = None,
) -> SourceRecord:
    identity = StatuteIdentity(
        unit_kind=unit_kind,
        law_name="약사법",
        law_id="001783",
        mst="279725",
        instrument_kind="법률",
        responsible_ministry="보건복지부",
        promulgated_on="20251111",
        effective_on="20261112",
        unit_effective_on="20261112",
        article_number=article_number,
        appendix_number=appendix_number,
    )
    return SourceRecord(
        document_id=document_id,
        document_kind=DocumentKind.STATUTE,
        title=title,
        text=text,
        content_hash=_content_hash(text),
        identity=identity,
        provenance=SourceProvenance(
            provider="법제처",
            publisher_statement="법제처 국가법령정보 공동활용(www.law.go.kr)",
            source_url="https://www.law.go.kr/법령/약사법",
            source_reference="국가법령정보센터 약사법 제1조 (MST 279725)",
            acquired_at=datetime(2026, 8, 11, 8, 3, 28, tzinfo=UTC),
        ),
        admission=SourceAdmission.EXEMPT,
        usage=UsageDisposition.INDEX_ELIGIBLE,
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


def test_pack_lines_to_budget_returns_one_piece_under_budget() -> None:
    text = "짧은 조각"

    assert pack_lines_to_budget(text, target_max_chars=TARGET_MAX_CHARS) == (text,)


def test_pack_lines_to_budget_never_splits_a_line_and_reconstructs_exactly() -> None:
    lines = [f"줄{i}: " + ("내용" * 10) for i in range(10)]
    text = "\n".join(lines)

    pieces = pack_lines_to_budget(text, target_max_chars=80)

    assert "\n".join(pieces) == text
    assert len(pieces) > 1
    for piece in pieces:
        assert len(piece) <= 80


def test_pack_lines_to_budget_keeps_an_oversized_single_line_whole() -> None:
    text = "가" * (TARGET_MAX_CHARS + 500)

    pieces = pack_lines_to_budget(text, target_max_chars=TARGET_MAX_CHARS)

    assert pieces == (text,)


def test_chunk_statute_record_returns_one_unsplit_chunk_for_a_short_article() -> None:
    record = _statute_record(text="제1조(목적) 이 법은 약사에 관한 사항을 규정한다.")

    chunks = chunk_statute_record(record, dataset_version="dataset-v2")

    assert len(chunks) == 1
    chunk = chunks[0]
    assert chunk.text == record.text
    assert chunk.locator == "약사법 제1조"
    assert chunk.title == "약사법 제1조"
    assert chunk.source_uri == "https://www.law.go.kr/법령/약사법"
    assert chunk.official_number == "279725"
    assert chunk.kind_fields.status == "current"
    assert chunk.kind_fields.layout == "text"
    assert chunk.chunk_id == "doc-example#body-000"


def test_chunk_statute_record_splits_a_long_article_at_markers() -> None:
    item = "이것은 충분히 긴 항목 설명 문장입니다. " * 40
    text = "\n".join(f"{n}. {item}" for n in range(1, 8))
    assert len(text) >= TARGET_MAX_CHARS, "fixture must exceed the split threshold"
    record = _statute_record(document_id="doc-long-article", text=text)

    chunks = chunk_statute_record(record, dataset_version="dataset-v2")

    assert len(chunks) > 1
    for chunk in chunks:
        assert chunk.kind_fields.layout == "text"
    markers = [c.locator.split(" > ")[-1] for c in chunks]
    assert markers == [str(n) for n in range(1, 8)]


def test_chunk_statute_record_protects_a_table_row_from_a_marker_split() -> None:
    padding = "본문 설명. " * 200
    assert len(padding) * 2 >= TARGET_MAX_CHARS, "fixture must exceed the split threshold"
    text = f"{padding}\n┌───┬───┐\n│마. 위반 │근거 │\n└───┴───┘\n{padding}"
    record = _statute_record(
        document_id="doc-table",
        title="공중위생관리법 시행규칙 별표 7",
        text=text,
        unit_kind=StatuteUnitKind.APPENDIX,
        article_number=None,
        appendix_number="0007",
    )

    chunks = chunk_statute_record(record, dataset_version="dataset-v2")

    table_chunks = [c for c in chunks if c.kind_fields.layout == "table"]
    assert len(table_chunks) == 1
    assert "마." in table_chunks[0].text
    assert table_chunks[0].text.count("┌") == 1  # the whole table stayed one piece


def test_chunk_statute_record_keeps_layout_text_for_oversized_markerless_prose() -> None:
    """Regression: an oversized piece with no table content must not be
    mislabeled layout="table" just because it needed size-budget packing."""

    # Newlines matter here: pack_lines_to_budget never splits mid-line, so a
    # fixture with no "\n" at all would come back as a single oversized
    # piece and never actually exercise the multi-chunk fallback path this
    # test is for.
    paragraph = "이 조문은 번호도 목차도 없이 계속 이어지는 산문입니다. " * 8
    text = "\n".join([paragraph] * 8)
    assert len(text) >= TARGET_MAX_CHARS, "fixture must exceed the split threshold"
    record = _statute_record(document_id="doc-no-markers", text=text)

    chunks = chunk_statute_record(record, dataset_version="dataset-v2")

    assert len(chunks) > 1
    assert all(c.kind_fields.layout == "text" for c in chunks)
    assert "\n".join(c.text for c in chunks) == text


def test_chunk_statute_record_flags_a_repealed_placeholder() -> None:
    record = _statute_record(
        document_id="doc-repealed",
        title="약사법 제19조",
        text="제19조 삭제 <2011.3.30>",
    )

    chunks = chunk_statute_record(record, dataset_version="dataset-v2")

    assert len(chunks) == 1
    assert chunks[0].kind_fields.status == "repealed"
