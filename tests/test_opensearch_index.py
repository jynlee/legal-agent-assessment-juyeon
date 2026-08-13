from legal_agent_assessment.opensearch_index import (
    CHUNKING_VERSION,
    INDEX_VERSION,
    build_index_body,
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
    ):
        assert field in properties, f"missing mapping field: {field}"

    assert properties["decided_on"] == {"type": "date", "format": "yyyyMMdd"}
    assert properties["text"]["analyzer"] == "standard"
    assert "nori_tokenizer" not in str(body)
