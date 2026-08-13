"""Batching and progress reporting in scripts/bedrock_embedding.py.

The Bedrock call itself is faked: this repo does not unit-test network-facing
code, but the batching loop and its `on_batch_complete` accounting are pure
enough to check with a synthetic client.
"""

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from legal_agent_assessment.embedding import TokenBudget


def module():  # type: ignore[no-untyped-def]
    path = Path(__file__).parents[1] / "scripts" / "bedrock_embedding.py"
    spec = importlib.util.spec_from_file_location("bedrock_embedding", path)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


class _FakeBody:
    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def read(self) -> bytes:
        return json.dumps(self._payload).encode("utf-8")


class _FakeBedrock:
    """Returns one all-zero vector per requested text, optionally failing."""

    def __init__(self, *, dimension: int, fail_on_call: int | None = None) -> None:
        self.dimension = dimension
        self.fail_on_call = fail_on_call
        self.calls = 0

    def invoke_model(self, *, modelId: str, body: str) -> dict[str, Any]:
        self.calls += 1
        if self.calls == self.fail_on_call:
            raise RuntimeError("throttled")
        texts = json.loads(body)["texts"]
        vectors = [[0.0] * self.dimension for _ in texts]
        return {"body": _FakeBody({"embeddings": vectors})}


def _budget() -> TokenBudget:
    # Frozen clock and a limit far above the test spend: never sleeps.
    return TokenBudget(limit_per_minute=1_000_000, clock=lambda: 0.0)


def test_embed_batch_preserves_order_and_count_across_batches() -> None:
    bedrock = module()
    texts = [f"본문 {index}" for index in range(bedrock.BATCH_SIZE + 5)]

    vectors = bedrock.embed_batch(
        _FakeBedrock(dimension=4),
        texts,
        model_id="fake-model",
        input_type="search_document",
        dimension=4,
        budget=_budget(),
    )

    assert len(vectors) == len(texts)
    assert all(len(vector) == 4 for vector in vectors)


def test_embed_batch_reports_tokens_and_calls_after_every_batch() -> None:
    bedrock = module()
    texts = ["가나다" for _ in range(bedrock.BATCH_SIZE + 1)]
    reported: list[tuple[int, int]] = []

    bedrock.embed_batch(
        _FakeBedrock(dimension=2),
        texts,
        model_id="fake-model",
        input_type="search_document",
        dimension=2,
        budget=_budget(),
        on_batch_complete=lambda tokens, calls: reported.append((tokens, calls)),
    )

    # Two batches: a full one, then the single leftover text. estimate_tokens
    # is one token per character, so "가나다" is 3.
    assert reported == [(3 * bedrock.BATCH_SIZE, 1), (3, 2)]


def test_embed_batch_progress_survives_a_mid_run_failure() -> None:
    """The point of the callback: quota spent before the failure is still known."""

    bedrock = module()
    texts = ["가나다" for _ in range(bedrock.BATCH_SIZE * 3)]
    spent_tokens = 0
    spent_calls = 0

    def record(tokens: int, calls: int) -> None:
        nonlocal spent_tokens, spent_calls
        spent_tokens += tokens
        spent_calls = calls

    with pytest.raises(RuntimeError, match="throttled"):
        bedrock.embed_batch(
            _FakeBedrock(dimension=2, fail_on_call=3),
            texts,
            model_id="fake-model",
            input_type="search_document",
            dimension=2,
            budget=_budget(),
            on_batch_complete=record,
        )

    # Batches 1 and 2 completed and were paid for; batch 3 raised.
    assert spent_calls == 2
    assert spent_tokens == 3 * bedrock.BATCH_SIZE * 2


def test_embed_batch_works_without_a_progress_callback() -> None:
    bedrock = module()

    vectors = bedrock.embed_batch(
        _FakeBedrock(dimension=3),
        ["하나", "둘"],
        model_id="fake-model",
        input_type="search_document",
        dimension=3,
        budget=_budget(),
    )

    assert len(vectors) == 2
