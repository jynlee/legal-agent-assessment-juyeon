import json

import pytest

from legal_agent_assessment.contracts import Citation
from legal_agent_assessment.rerank import ParsedRerank, build_rerank_prompt, parse_rerank_response

_CANDIDATES = [
    Citation(
        document_id="precedent-000001",
        chunk_id="precedent-000001#body-000",
        title="판례 제목 1",
        excerpt="본문 예시 1",
    ),
    Citation(
        document_id="doc-000002",
        chunk_id="doc-000002#body-000",
        title="법령 제목 2",
        excerpt="본문 예시 2",
    ),
]


def test_build_rerank_prompt_includes_the_question_and_every_candidate() -> None:
    prompt = build_rerank_prompt("약사법 제1조는 무엇을 규정하나요?", _CANDIDATES)

    assert "약사법 제1조는 무엇을 규정하나요?" in prompt
    assert "precedent-000001#body-000" in prompt
    assert "본문 예시 1" in prompt
    assert "doc-000002#body-000" in prompt
    assert "본문 예시 2" in prompt


def test_parse_rerank_response_reads_relevant_chunk_ids_in_order() -> None:
    raw = json.dumps({"relevant_chunk_ids": ["doc-000002#body-000", "precedent-000001#body-000"]})

    parsed = parse_rerank_response(
        raw, candidate_ids=["precedent-000001#body-000", "doc-000002#body-000"]
    )

    assert parsed == ParsedRerank(chunk_ids=("doc-000002#body-000", "precedent-000001#body-000"))


def test_parse_rerank_response_drops_ids_the_model_invented() -> None:
    """Never trust a returned id that was not actually offered as a
    candidate -- the same "never trust the model" philosophy generation.py
    already applies to cited_chunk_ids."""

    raw = json.dumps({"relevant_chunk_ids": ["precedent-000001#body-000", "made-up-id#body-000"]})

    parsed = parse_rerank_response(raw, candidate_ids=["precedent-000001#body-000"])

    assert parsed.chunk_ids == ("precedent-000001#body-000",)


def test_parse_rerank_response_drops_duplicate_ids_keeping_first_occurrence() -> None:
    raw = json.dumps({"relevant_chunk_ids": ["a", "b", "a"]})

    parsed = parse_rerank_response(raw, candidate_ids=["a", "b"])

    assert parsed.chunk_ids == ("a", "b")


def test_parse_rerank_response_caps_at_ten_ids() -> None:
    candidate_ids = [f"id-{i}" for i in range(15)]
    raw = json.dumps({"relevant_chunk_ids": candidate_ids})

    parsed = parse_rerank_response(raw, candidate_ids=candidate_ids)

    assert len(parsed.chunk_ids) == 10
    assert parsed.chunk_ids == tuple(candidate_ids[:10])


def test_parse_rerank_response_treats_a_missing_key_as_no_relevant_ids() -> None:
    parsed = parse_rerank_response(json.dumps({}), candidate_ids=["a"])

    assert parsed.chunk_ids == ()


def test_parse_rerank_response_raises_on_unparseable_json() -> None:
    with pytest.raises(ValueError, match="could not parse"):
        parse_rerank_response("not json at all", candidate_ids=["a"])


def test_parse_rerank_response_unwraps_a_markdown_fenced_json_object() -> None:
    body = json.dumps({"relevant_chunk_ids": ["a"]})

    parsed = parse_rerank_response(f"```json\n{body}\n```", candidate_ids=["a"])

    assert parsed.chunk_ids == ("a",)


def test_parse_rerank_response_tolerates_trailing_prose_after_the_closing_fence() -> None:
    """Same real crash shape found in generation.py earlier tonight --
    applied here from the start rather than waiting to hit it live."""

    raw = (
        '```json\n{"relevant_chunk_ids": ["a"]}\n```\n\n**설명:** 이 근거가 가장 관련성이 높습니다.'
    )

    parsed = parse_rerank_response(raw, candidate_ids=["a"])

    assert parsed.chunk_ids == ("a",)
