"""Hybrid BM25 + exact k-NN retrieval: query builders, RRF fusion, and
OpenSearch-hit-to-contract mapping.

Implements reports/decisions/2026-08-13-retrieval-design.md. Pure: no
OpenSearch client, no network, no filesystem, matching AGENTS.md's
separation of deterministic logic from I/O. src/legal_agent_assessment/
agent.py is the network-facing caller.
"""

from collections.abc import Sequence
from typing import Any


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
