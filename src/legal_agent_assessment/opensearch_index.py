"""OpenSearch 3.5 index mapping and naming for indexed chunks.

Implements reports/decisions/2026-08-13-opensearch-mapping-design.md. Pure:
no OpenSearch client, no network, no filesystem, matching AGENTS.md's
separation of deterministic logic from I/O. `scripts/create_opensearch_index.py`
is the network-facing caller.
"""

from collections.abc import Sequence
from typing import Any

from legal_agent_assessment.chunking import (
    CHUNKING_VERSION,
    Chunk,
    JudgementChunkFields,
    StatuteChunkFields,
)
from legal_agent_assessment.dataset import LinkageStrength
from legal_agent_assessment.embedding import EMBEDDING_DIMENSION

INDEX_VERSION = "index-v1"

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


def _split_citation_list(value: str) -> list[str]:
    """Split one referencedProvisions/referencedPrecedents string into keyword tokens.

    `extract_issues` (chunking.py) joins multiple citations that accumulate
    under one issue number with "; " -- this reuses that exact separator
    rather than inventing a new citation-parsing rule.
    """

    return [part.strip() for part in value.split("; ") if part.strip()]


def chunk_to_document(chunk: Chunk, embedding: Sequence[float]) -> dict[str, Any]:
    """Build one OpenSearch document from a `Chunk` and its precomputed embedding.

    Fields absent on the source (None or empty) are omitted from the
    document entirely, not written as null/[] -- matching Decision 2's
    "intentional and typed" sparsity and letting `decided_on`'s `date`
    mapping (Task 1) stay untouched by the 3 sentinel-carrying chunks.
    """

    document: dict[str, Any] = {
        "chunk_id": chunk.chunk_id,
        "document_id": chunk.document_id,
        "chunk_type": str(chunk.chunk_type),
        "ordinal": chunk.ordinal,
        "text": chunk.text,
        "content_hash": chunk.content_hash,
        "document_kind": str(chunk.document_kind),
        "dataset_version": chunk.dataset_version,
        "normalization_version": chunk.normalization_version,
        "chunking_version": chunk.chunking_version,
        "title": chunk.title,
        "locator": chunk.locator,
        "embedding": list(embedding),
    }
    if chunk.source_uri is not None:
        document["source_uri"] = chunk.source_uri
    if chunk.official_number is not None:
        document["official_number"] = chunk.official_number

    core: list[str] = []
    candidate: list[str] = []
    unlinked: list[str] = []
    for linkage in chunk.linked_laws:
        target = {
            LinkageStrength.CORE: core,
            LinkageStrength.CANDIDATE: candidate,
            LinkageStrength.UNLINKED: unlinked,
        }[linkage.strength]
        target.append(linkage.law_name)
    document["linked_law_names_core"] = core
    document["linked_law_names_candidate"] = candidate
    document["linked_law_names_unlinked"] = unlinked

    if isinstance(chunk.kind_fields, JudgementChunkFields):
        judgement_fields = chunk.kind_fields
        document["case_name"] = judgement_fields.case_name
        document["court"] = judgement_fields.court
        document["case_number"] = judgement_fields.case_number
        if judgement_fields.decided_on is not None:
            document["decided_on"] = judgement_fields.decided_on
        if judgement_fields.referenced_provisions:
            provisions = judgement_fields.referenced_provisions
            document["referenced_provisions"] = _split_citation_list(provisions)
        if judgement_fields.referenced_precedents:
            precedents = judgement_fields.referenced_precedents
            document["referenced_precedents"] = _split_citation_list(precedents)
        if judgement_fields.issue_ordinal is not None:
            document["issue_ordinal"] = judgement_fields.issue_ordinal
    elif isinstance(chunk.kind_fields, StatuteChunkFields):
        statute_fields = chunk.kind_fields
        document["law_name"] = statute_fields.law_name
        document["unit_kind"] = str(statute_fields.unit_kind)
        document["status"] = statute_fields.status
        document["layout"] = statute_fields.layout
        if statute_fields.article_number is not None:
            document["article_number"] = statute_fields.article_number
        if statute_fields.appendix_number is not None:
            document["appendix_number"] = statute_fields.appendix_number

    return document


__all__ = [
    "EMBEDDING_DIMENSION",
    "INDEX_MAPPING_PROPERTIES",
    "INDEX_VERSION",
    "build_index_body",
    "chunk_to_document",
    "index_name",
    "index_settings",
]
