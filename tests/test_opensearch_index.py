import pytest

from legal_agent_assessment.chunking import (
    Chunk,
    ChunkType,
    JudgementChunkFields,
    StatuteChunkFields,
)
from legal_agent_assessment.dataset import LawLinkage, LinkageStrength, StatuteUnitKind
from legal_agent_assessment.opensearch_index import (
    CHUNKING_VERSION,
    INDEX_VERSION,
    build_index_body,
    chunk_to_document,
    index_name,
)


def test_index_name_follows_the_documented_convention() -> None:
    name = index_name("jynlee")

    assert name == f"legal-kit-assessment-jynlee-{CHUNKING_VERSION}-{INDEX_VERSION}"


def test_index_name_accepts_explicit_versions() -> None:
    name = index_name("jynlee", chunking_version="chunk-v9", index_version="index-v9")

    assert name == "legal-kit-assessment-jynlee-chunk-v9-index-v9"


def test_build_index_body_sets_one_shard_and_the_requested_replicas() -> None:
    body = build_index_body(number_of_replicas=0)

    assert body["settings"]["index"]["number_of_shards"] == 1
    assert body["settings"]["index"]["number_of_replicas"] == 0


def test_build_index_body_has_no_knn_method_block() -> None:
    body = build_index_body(number_of_replicas=1)

    embedding = body["mappings"]["properties"]["embedding"]
    assert embedding == {"type": "knn_vector", "dimension": 1536}


def test_build_index_body_declares_every_kind_specific_field() -> None:
    body = build_index_body(number_of_replicas=0)
    properties = body["mappings"]["properties"]

    for field in (
        "chunk_id",
        "document_id",
        "chunk_type",
        "ordinal",
        "text",
        "content_hash",
        "document_kind",
        "dataset_version",
        "normalization_version",
        "chunking_version",
        "title",
        "source_uri",
        "official_number",
        "locator",
        "linked_law_names_core",
        "linked_law_names_candidate",
        "linked_law_names_unlinked",
        "case_name",
        "court",
        "decided_on",
        "case_number",
        "referenced_provisions",
        "referenced_precedents",
        "issue_ordinal",
        "law_name",
        "unit_kind",
        "article_number",
        "appendix_number",
        "status",
        "layout",
        "record_limitations",
    ):
        assert field in properties, f"missing mapping field: {field}"

    assert properties["decided_on"] == {"type": "date", "format": "yyyyMMdd"}
    assert properties["text"]["analyzer"] == "standard"
    assert "nori_tokenizer" not in str(body)


_EMBEDDING = tuple(0.1 for _ in range(1536))


def _judgement_chunk(**overrides: object) -> Chunk:
    defaults: dict[str, object] = dict(
        chunk_id="precedent-000001#body-000",
        document_id="precedent-000001",
        chunk_type=ChunkType.BODY,
        ordinal=0,
        text="본문 예시",
        content_hash="sha256:" + "a" * 64,
        document_kind="judgement",
        dataset_version="dataset-v1",
        normalization_version="norm-v1",
        chunking_version="chunk-v1",
        title="판례 제목",
        source_uri="https://example.org/case",
        official_number="2020구합1",
        locator="이유 > 1",
        linked_laws=(
            LawLinkage(law_name="약사법", strength=LinkageStrength.CORE),
            LawLinkage(law_name="의료법", strength=LinkageStrength.CANDIDATE),
            LawLinkage(law_name="개인정보보호법", strength=LinkageStrength.UNLINKED),
        ),
        kind_fields=JudgementChunkFields(
            case_name="사건명",
            court="서울행정법원",
            decided_on="20200101",
            case_number="2020구합1",
            referenced_provisions="제1조; 제2조",
            referenced_precedents="",
            issue_ordinal=1,
        ),
    )
    defaults.update(overrides)
    return Chunk(**defaults)  # type: ignore[arg-type]


def _statute_chunk(**overrides: object) -> Chunk:
    defaults: dict[str, object] = dict(
        chunk_id="law-000001#body-000",
        document_id="law-000001",
        chunk_type=ChunkType.BODY,
        ordinal=0,
        text="제1조 본문",
        content_hash="sha256:" + "b" * 64,
        document_kind="statute",
        dataset_version="dataset-v1",
        normalization_version="norm-v1",
        chunking_version="chunk-v1",
        title="약사법 제1조",
        source_uri="https://law.go.kr/약사법",
        official_number="279725",
        locator="제1조",
        linked_laws=(),
        kind_fields=StatuteChunkFields(
            law_name="약사법",
            unit_kind=StatuteUnitKind.ARTICLE,
            article_number="1",
            appendix_number=None,
            status="current",
            layout="text",
        ),
    )
    defaults.update(overrides)
    return Chunk(**defaults)  # type: ignore[arg-type]


def test_chunk_to_document_carries_common_fields_and_embedding() -> None:
    document = chunk_to_document(_judgement_chunk(), _EMBEDDING)

    assert document["chunk_id"] == "precedent-000001#body-000"
    assert document["chunk_type"] == "body"
    assert document["embedding"] == list(_EMBEDDING)
    assert len(document["embedding"]) == 1536


def test_chunk_to_document_omits_record_limitations_when_absent() -> None:
    document = chunk_to_document(_judgement_chunk(), _EMBEDDING)

    assert "record_limitations" not in document


def test_chunk_to_document_carries_record_limitations_when_present() -> None:
    chunk = _judgement_chunk(
        record_limitations=("판시사항·판결요지·참조조문·참조판례가 모두 비어 있어 본문만 제공된다",)
    )

    document = chunk_to_document(chunk, _EMBEDDING)

    assert document["record_limitations"] == [
        "판시사항·판결요지·참조조문·참조판례가 모두 비어 있어 본문만 제공된다"
    ]


def test_chunk_to_document_splits_linked_laws_by_strength() -> None:
    document = chunk_to_document(_judgement_chunk(), _EMBEDDING)

    assert document["linked_law_names_core"] == ["약사법"]
    assert document["linked_law_names_candidate"] == ["의료법"]
    assert document["linked_law_names_unlinked"] == ["개인정보보호법"]


def test_chunk_to_document_splits_referenced_citations_on_semicolon() -> None:
    document = chunk_to_document(_judgement_chunk(), _EMBEDDING)

    assert document["referenced_provisions"] == ["제1조", "제2조"]
    assert "referenced_precedents" not in document  # empty string -> omitted, not []


def test_chunk_to_document_omits_decided_on_when_sentinel_resolved_to_none() -> None:
    chunk = _judgement_chunk(
        kind_fields=JudgementChunkFields(
            case_name="사건명",
            court="서울행정법원",
            decided_on=None,
            case_number="2020구합1",
        )
    )

    document = chunk_to_document(chunk, _EMBEDDING)

    assert "decided_on" not in document


def test_chunk_to_document_carries_statute_fields_and_omits_judgement_fields() -> None:
    document = chunk_to_document(_statute_chunk(), _EMBEDDING)

    assert document["law_name"] == "약사법"
    assert document["unit_kind"] == "article"
    assert document["article_number"] == "1"
    assert "appendix_number" not in document
    assert "case_name" not in document
    assert "court" not in document
    assert document["linked_law_names_core"] == []


def test_chunk_to_document_rejects_an_unhandled_kind_fields_type() -> None:
    """A third kind_fields type must fail loudly, not silently drop its fields."""

    chunk = _statute_chunk(kind_fields=object())

    with pytest.raises(ValueError, match="unhandled kind_fields type"):
        chunk_to_document(chunk, _EMBEDDING)
