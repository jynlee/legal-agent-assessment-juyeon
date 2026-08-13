"""Hybrid BM25 + exact k-NN retrieval: query builders, RRF fusion, and
OpenSearch-hit-to-contract mapping.

Implements reports/decisions/2026-08-13-retrieval-design.md. Pure: no
OpenSearch client, no network, no filesystem, matching AGENTS.md's
separation of deterministic logic from I/O. src/legal_agent_assessment/
agent.py is the network-facing caller.
"""

from collections.abc import Sequence
from typing import Any

from legal_agent_assessment.contracts import Citation, RetrievalHit


def build_bm25_query(question: str, *, size: int) -> dict[str, Any]:
    """OpenSearch `_search` body for BM25 over the indexed text fields.

    `text` (the chunk's own content) carries the primary weight; `title`/
    `case_name`/`law_name` carry a lower secondary weight for a query that
    names a specific law or case. These boosts are a tuning knob, not a
    fixed design decision (retrieval design Decision 2) -- revisit once
    ASSIGNMENT.md item 5/6's test set gives real signal.
    """

    return {
        "size": size,
        "query": {
            "multi_match": {
                "query": question,
                "fields": ["text^1", "title^0.5", "case_name^0.5", "law_name^0.5"],
            }
        },
    }


def build_knn_query(query_vector: Sequence[float], *, size: int) -> dict[str, Any]:
    """OpenSearch `_search` body for exact k-NN via `script_score`.

    Matches reports/decisions/2026-08-13-opensearch-mapping-design.md
    Decision 6 exactly: the index's `embedding` field has no `method` block,
    so the `knn` query clause (which requires an approximate-search method)
    cannot be used -- the k-NN plugin's `knn_score` script is the documented
    way to run exact k-NN against a `method`-less `knn_vector` field.
    """

    return {
        "size": size,
        "query": {
            "script_score": {
                "query": {"match_all": {}},
                "script": {
                    "lang": "knn",
                    "source": "knn_score",
                    "params": {
                        "field": "embedding",
                        "query_value": list(query_vector),
                        "space_type": "cosinesimil",
                    },
                },
            }
        },
    }


def reciprocal_rank_fusion(
    ranked_id_lists: Sequence[Sequence[str]], *, k: int = 60
) -> list[tuple[str, float]]:
    """Combine ranked chunk_id lists into one fused ranking via RRF.

    score(id) = sum, over every input list containing id, of
    1 / (k + rank_in_that_list) (1-indexed rank). `k=60` is the standard
    constant from the original RRF paper (Cormack, Clarke, Buettcher, 2009),
    not a project-specific guess (retrieval design Decision 2).

    Returns (chunk_id, score) pairs sorted by descending score. Python's
    `sorted` is stable, so ties preserve each id's first-appearance order
    across `ranked_id_lists` -- deterministic given the same inputs, which
    this project's retrieval must be for KOLAS-reproducible metrics
    (reports/decisions/2026-08-13-retrieval-design.md).
    """

    scores: dict[str, float] = {}
    for ranked_ids in ranked_id_lists:
        for rank, chunk_id in enumerate(ranked_ids, start=1):
            scores[chunk_id] = scores.get(chunk_id, 0.0) + 1.0 / (k + rank)
    return sorted(scores.items(), key=lambda pair: pair[1], reverse=True)


_EXCERPT_MAX_LENGTH = 2_000


def source_to_retrieval_hit(source: dict[str, Any], *, rank: int, score: float) -> RetrievalHit:
    """Build a `RetrievalHit` (internal diagnostic) from one hit's `_source`."""

    return RetrievalHit(
        document_id=source["document_id"],
        chunk_id=source["chunk_id"],
        rank=rank,
        score=score,
    )


def source_to_citation(source: dict[str, Any]) -> Citation:
    """Build a `Citation` (answer-facing) from one hit's `_source`.

    `excerpt` is the chunk's own stored `text`, trimmed to `Citation`'s
    2,000-character limit -- a working default, real and traceable to
    indexed content. ASSIGNMENT.md item 7's answer-composition work (out of
    scope for reports/decisions/2026-08-13-retrieval-design.md) may later
    select a more targeted excerpt; this keeps item 4 end-to-end functional
    in the meantime.
    """

    excerpt = source["text"]
    if len(excerpt) > _EXCERPT_MAX_LENGTH:
        excerpt = excerpt[: _EXCERPT_MAX_LENGTH - 3] + "..."

    return Citation(
        document_id=source["document_id"],
        chunk_id=source["chunk_id"],
        title=source["title"],
        source_uri=source.get("source_uri"),
        official_number=source.get("official_number"),
        locator=source.get("locator"),
        excerpt=excerpt,
    )


__all__ = [
    "build_bm25_query",
    "build_knn_query",
    "reciprocal_rank_fusion",
    "source_to_citation",
    "source_to_retrieval_hit",
]
