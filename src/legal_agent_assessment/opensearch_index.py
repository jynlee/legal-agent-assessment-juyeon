"""OpenSearch 3.5 index mapping and naming for indexed chunks.

Implements reports/decisions/2026-08-13-opensearch-mapping-design.md. Pure:
no OpenSearch client, no network, no filesystem, matching AGENTS.md's
separation of deterministic logic from I/O. `scripts/create_opensearch_index.py`
is the network-facing caller.
"""

from typing import Any

from legal_agent_assessment.chunking import CHUNKING_VERSION

INDEX_VERSION = "index-v1"
EMBEDDING_DIMENSION = 1536

_TEXT_WITH_KEYWORD: dict[str, Any] = {
    "type": "text",
    "analyzer": "standard",
    "fields": {"keyword": {"type": "keyword"}},
}

INDEX_MAPPING_PROPERTIES: dict[str, Any] = {
    # Common Chunk fields (Decision 1-2 of the mapping design).
    "chunk_id": {"type": "keyword"},
    "document_id": {"type": "keyword"},
    "chunk_type": {"type": "keyword"},
    "ordinal": {"type": "integer"},
    "text": {"type": "text", "analyzer": "standard"},
    "content_hash": {"type": "keyword"},
    "document_kind": {"type": "keyword"},
    "dataset_version": {"type": "keyword"},
    "normalization_version": {"type": "keyword"},
    "chunking_version": {"type": "keyword"},
    "title": _TEXT_WITH_KEYWORD,
    "source_uri": {"type": "keyword"},
    "official_number": {"type": "keyword"},
    "locator": {"type": "keyword"},
    "embedding": {"type": "knn_vector", "dimension": EMBEDDING_DIMENSION},
    # linked_laws, split by LinkageStrength (Decision 3, amended 2026-08-13).
    "linked_law_names_core": {"type": "keyword"},
    "linked_law_names_candidate": {"type": "keyword"},
    "linked_law_names_unlinked": {"type": "keyword"},
    # JudgementChunkFields (Decision 2).
    "case_name": _TEXT_WITH_KEYWORD,
    "court": {"type": "keyword"},
    "decided_on": {"type": "date", "format": "yyyyMMdd"},
    "case_number": {"type": "keyword"},
    "referenced_provisions": {"type": "keyword"},
    "referenced_precedents": {"type": "keyword"},
    "issue_ordinal": {"type": "integer"},
    # StatuteChunkFields (Decision 2).
    "law_name": _TEXT_WITH_KEYWORD,
    "unit_kind": {"type": "keyword"},
    "article_number": {"type": "keyword"},
    "appendix_number": {"type": "keyword"},
    "status": {"type": "keyword"},
    "layout": {"type": "keyword"},
}


def index_name(
    contributor: str,
    *,
    chunking_version: str = CHUNKING_VERSION,
    index_version: str = INDEX_VERSION,
) -> str:
    """Build the documented index name: legal-kit-assessment-<contributor>-<chunking>-<index>."""

    return f"legal-kit-assessment-{contributor}-{chunking_version}-{index_version}"


def index_settings(*, number_of_replicas: int) -> dict[str, Any]:
    """One shard always (Decision 7) -- replicas vary by target (0 local, 1 managed)."""

    return {"index": {"number_of_shards": 1, "number_of_replicas": number_of_replicas}}


def build_index_body(*, number_of_replicas: int) -> dict[str, Any]:
    """Full index-creation body: settings plus the mapping above."""

    return {
        "settings": index_settings(number_of_replicas=number_of_replicas),
        "mappings": {"properties": INDEX_MAPPING_PROPERTIES},
    }


__all__ = [
    "EMBEDDING_DIMENSION",
    "INDEX_MAPPING_PROPERTIES",
    "INDEX_VERSION",
    "build_index_body",
    "index_name",
    "index_settings",
]
