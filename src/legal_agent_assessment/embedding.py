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
    texts: Sequence[str],
    *,
    input_type: Literal["search_document", "search_query"],
    output_dimension: int = EMBEDDING_DIMENSION,
) -> dict[str, Any]:
    """Bedrock Cohere Embed v4 invoke_model request body.

    ASSIGNMENT.md's Fixed constraints: ingest text uses "search_document",
    query text uses "search_query" (`agent.py`'s `_embed_query`) -- sending
    both sides the same input_type is a defect, not a shortcut.

    Always requests `output_dimension` (default `EMBEDDING_DIMENSION`, 1536).
    The endpoint's default, unrequested output is 1024-dimensional --
    confirmed empirically against the real endpoint -- which would silently
    mismatch the already-created OpenSearch index's `knn_vector` mapping
    (dimension 1536). `output_dimension` is exposed as an explicit,
    caller-overridable parameter -- symmetric with `parse_embed_response`'s
    `expected_dimension` -- but every real call site relies on the default,
    because ASSIGNMENT.md requires ingest and query to use the same
    dimension.
    """

    return {
        "texts": list(texts),
        "input_type": input_type,
        "output_dimension": output_dimension,
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
        # Summarize rather than repr the body: a real response carries many
        # full float vectors, and dumping them into a traceback or log buries
        # the actual problem (and can be megabytes).
        detail = f"top-level keys {sorted(response_body)}"
        if "embeddings" in response_body:
            embeddings = response_body["embeddings"]
            detail += f"; 'embeddings' is {type(embeddings).__name__}"
            if isinstance(embeddings, dict):
                detail += f" with keys {sorted(embeddings)}"
        raise ValueError(f"unrecognized embed response shape: {detail}")

    if len(raw) != expected_count:
        raise ValueError(f"expected {expected_count} embedding(s), got {len(raw)}")

    vectors = tuple(tuple(float(x) for x in vector) for vector in raw)
    for vector in vectors:
        if len(vector) != expected_dimension:
            raise ValueError(f"expected dimension {expected_dimension}, got {len(vector)}")
    return vectors


def estimate_tokens(text: str) -> int:
    """Conservative token-count approximation, for pacing only, not billing.

    No offline Cohere tokenizer is available. One token per character is a
    deliberately conservative approximation for Latin-script-oriented BPE,
    but it is *not* independently verified for Korean subword tokenization:
    a byte-level BPE can in principle emit more than one token per Hangul
    character, so this is an approximation rather than a guaranteed upper
    bound. That is exactly why callers should pace against real headroom
    below the raw shared-quota limit rather than up to it -- see
    `scripts/index_chunks.py`'s `TokenBudget` limit.
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
