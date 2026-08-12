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
    split_paragraphs,
)
from legal_agent_assessment.dataset import DocumentKind, LawLinkage, LinkageStrength, StatuteUnitKind


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
