"""Batched, self-paced Bedrock Cohere Embed v4 calls.

Batches texts to stay well under Bedrock's per-request payload limits and
paces sends against the shared 300,000 token/minute quota
(OPENSEARCH_ACCESS.md) via the caller-supplied `TokenBudget`, rather than
retrying after a throttle -- a throttle cannot be retried away once the
minute's budget is spent. Callers set the budget's limit *below* the raw
shared quota, because `estimate_tokens` is an approximation and the quota
is shared with other contributors.
"""

import json
import time
from collections.abc import Callable, Sequence
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
    on_batch_complete: Callable[[int, int], None] | None = None,
) -> list[tuple[float, ...]]:
    """Embed every text in `texts`, batched and paced, preserving order.

    `on_batch_complete(batch_tokens, calls_so_far)` is invoked after every
    batch that actually returned, so a caller can keep a running record of
    the shared quota it has already spent. Without it, a failure partway
    through this loop (throttle, expired credentials, a network blip at
    batch 120 of 247) would leave the caller unable to report the spend it
    had already incurred, since `embed_batch` never returns. Optional and
    `None` by default: existing call sites are unaffected.
    """

    vectors: list[tuple[float, ...]] = []
    for calls, start in enumerate(range(0, len(texts), BATCH_SIZE), start=1):
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

        if on_batch_complete is not None:
            on_batch_complete(batch_tokens, calls)
    return vectors
