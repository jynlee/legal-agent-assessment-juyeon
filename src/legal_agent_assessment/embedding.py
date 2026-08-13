"""Cohere Embed v4 request/response shape and shared-quota pacing.

Pure: no boto3, no network. `scripts/bedrock_embedding.py` is the
network-facing caller (AGENTS.md's I/O separation). The exact response
shape below is confirmed against the real endpoint by
`scripts/smoke_bedrock_embedding.py` before `scripts/bedrock_embedding.py`
is written against it -- see that script's docstring.
"""

import time
from collections.abc import Callable, Sequence
from typing import Any, Literal

EMBEDDING_DIMENSION = 1536


def build_embed_request(
    texts: Sequence[str], *, input_type: Literal["search_document", "search_query"]
) -> dict[str, Any]:
    """Bedrock Cohere Embed v4 invoke_model request body.

    ASSIGNMENT.md's Fixed constraints: ingest text uses "search_document",
    query text (out of scope for this plan) uses "search_query" -- sending
    both sides the same input_type is a defect, not a shortcut.

    Always requests `output_dimension: EMBEDDING_DIMENSION` (1536). The
    endpoint's default, unrequested output is 1024-dimensional -- confirmed
    empirically against the real endpoint -- which would silently mismatch
    the already-created OpenSearch index's `knn_vector` mapping (dimension
    1536). This is a fixed constant, not a caller-supplied parameter, because
    ASSIGNMENT.md requires ingest and query to use the same dimension.
    """

    return {
        "texts": list(texts),
        "input_type": input_type,
        "output_dimension": EMBEDDING_DIMENSION,
    }


def parse_embed_response(
    response_body: dict[str, Any], *, expected_count: int, expected_dimension: int
) -> tuple[tuple[float, ...], ...]:
    """Extract embedding vectors, accepting either Cohere response shape.

    Bedrock's Cohere Embed has returned a flat `embeddings: [[...], ...]`
    list historically, and an `embeddings: {"float": [[...], ...]}` shape
    when `embedding_types` is requested. This project's request never sets
    `embedding_types`, so the flat shape is expected -- both are accepted so
    a shape change on the real endpoint fails on the *count/dimension*
    assertions below, with a clear message, rather than a silent KeyError.
    """

    raw = response_body.get("embeddings")
    if isinstance(raw, dict):
        raw = raw.get("float")
    if not isinstance(raw, list):
        raise ValueError(f"unrecognized embed response shape: {response_body!r}")

    if len(raw) != expected_count:
        raise ValueError(f"expected {expected_count} embedding(s), got {len(raw)}")

    vectors = tuple(tuple(float(x) for x in vector) for vector in raw)
    for vector in vectors:
        if len(vector) != expected_dimension:
            raise ValueError(f"expected dimension {expected_dimension}, got {len(vector)}")
    return vectors


def estimate_tokens(text: str) -> int:
    """Conservative token-count overestimate, for pacing only, not billing.

    No offline Cohere tokenizer is available. One token per character is a
    safe overestimate for Korean legal text (real subword tokenization is
    never denser than 1 token/char), so pacing against it never exceeds the
    real shared quota -- it only paces more cautiously than strictly needed.
    """

    return len(text)


class TokenBudget:
    """Self-paced token budget against a shared per-minute quota.

    `clock` is injectable so tests run without a real 60-second wait
    (OPENSEARCH_ACCESS.md: "a throttle cannot be retried away once the
    minute's budget is spent" -- this paces sends instead of retrying).
    """

    def __init__(
        self, *, limit_per_minute: int, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._limit = limit_per_minute
        self._clock = clock
        self._window_start = clock()
        self._spent = 0

    def consume(self, tokens: int) -> float:
        """Record `tokens` spent now; return seconds the caller should sleep first."""

        now = self._clock()
        if now - self._window_start >= 60.0:
            self._window_start = now
            self._spent = 0

        wait_seconds = 0.0
        if self._spent + tokens > self._limit:
            wait_seconds = 60.0 - (now - self._window_start)
            self._window_start = now + wait_seconds
            self._spent = 0

        self._spent += tokens
        return max(0.0, wait_seconds)


__all__ = [
    "EMBEDDING_DIMENSION",
    "TokenBudget",
    "build_embed_request",
    "estimate_tokens",
    "parse_embed_response",
]
