import pytest

from legal_agent_assessment.embedding import (
    TokenBudget,
    build_embed_request,
    estimate_tokens,
    parse_embed_response,
)


def test_build_embed_request_sets_input_type_and_texts() -> None:
    request = build_embed_request(["텍스트 하나", "텍스트 둘"], input_type="search_document")

    assert request["texts"] == ["텍스트 하나", "텍스트 둘"]
    assert request["input_type"] == "search_document"


def test_parse_embed_response_reads_the_float_embeddings_list() -> None:
    body = {"embeddings": [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]}

    vectors = parse_embed_response(body, expected_count=2, expected_dimension=3)

    assert vectors == ((0.1, 0.2, 0.3), (0.4, 0.5, 0.6))


def test_parse_embed_response_reads_embeddings_by_type_shape() -> None:
    body = {"embeddings": {"float": [[0.1, 0.2, 0.3]]}}

    vectors = parse_embed_response(body, expected_count=1, expected_dimension=3)

    assert vectors == ((0.1, 0.2, 0.3),)


def test_parse_embed_response_rejects_wrong_count() -> None:
    body = {"embeddings": [[0.1, 0.2, 0.3]]}

    with pytest.raises(ValueError, match="expected 2 embedding"):
        parse_embed_response(body, expected_count=2, expected_dimension=3)


def test_parse_embed_response_rejects_wrong_dimension() -> None:
    body = {"embeddings": [[0.1, 0.2]]}

    with pytest.raises(ValueError, match="expected dimension 3"):
        parse_embed_response(body, expected_count=1, expected_dimension=3)


def test_estimate_tokens_is_a_conservative_overestimate_for_korean_text() -> None:
    # A real Cohere tokenizer isn't available offline; this is a documented,
    # deliberately conservative (over-counts, never under-counts) approximation
    # used only to pace the shared per-minute token budget, not for billing.
    # 5 chars // 1 char-per-token divisor -> paced hardest
    assert estimate_tokens("가나다라마") == 5
    assert estimate_tokens("") == 0


def test_token_budget_allows_spend_within_the_limit_without_waiting() -> None:
    clock = [0.0]
    budget = TokenBudget(limit_per_minute=1000, clock=lambda: clock[0])

    wait_seconds = budget.consume(500)

    assert wait_seconds == 0.0


def test_token_budget_waits_when_the_window_is_exhausted() -> None:
    clock = [0.0]
    budget = TokenBudget(limit_per_minute=1000, clock=lambda: clock[0])
    budget.consume(1000)

    wait_seconds = budget.consume(500)

    assert wait_seconds > 0.0


def test_token_budget_resets_after_a_minute_elapses() -> None:
    clock = [0.0]
    budget = TokenBudget(limit_per_minute=1000, clock=lambda: clock[0])
    budget.consume(1000)
    clock[0] = 61.0

    wait_seconds = budget.consume(500)

    assert wait_seconds == 0.0
