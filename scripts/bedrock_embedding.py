"""Batched, self-paced Bedrock Cohere Embed v4 calls.

Batches texts to stay well under Bedrock's per-request payload limits and
paces sends against the shared 300,000 token/minute quota
(OPENSEARCH_ACCESS.md) via `TokenBudget`, rather than retrying after a
throttle -- a throttle cannot be retried away once the minute's budget is
spent.
"""

import json
import time
from collections.abc import Sequence
from typing import Any, Literal

from legal_agent_assessment.embedding import (
    EMBEDDING_DIMENSION,
    TokenBudget,
    build_embed_request,
    estimate_tokens,
    parse_embed_response,
)

BATCH_SIZE = 32


def embed_batch(
    client: Any,
    texts: Sequence[str],
    *,
    model_id: str,
    input_type: Literal["search_document", "search_query"],
    dimension: int = EMBEDDING_DIMENSION,
    budget: TokenBudget,
) -> list[tuple[float, ...]]:
    """Embed every text in `texts`, batched and paced, preserving order."""

    vectors: list[tuple[float, ...]] = []
    for start in range(0, len(texts), BATCH_SIZE):
        batch = texts[start : start + BATCH_SIZE]
        batch_tokens = sum(estimate_tokens(text) for text in batch)

        wait_seconds = budget.consume(batch_tokens)
        if wait_seconds > 0:
            time.sleep(wait_seconds)

        request = build_embed_request(batch, input_type=input_type, output_dimension=dimension)
        response = client.invoke_model(modelId=model_id, body=json.dumps(request))
        body = json.loads(response["body"].read())
        vectors.extend(
            parse_embed_response(body, expected_count=len(batch), expected_dimension=dimension)
        )
    return vectors
