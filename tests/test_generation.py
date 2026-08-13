import json

import pytest

from legal_agent_assessment.contracts import AnswerStatus, Citation
from legal_agent_assessment.generation import (
    ParsedAnswer,
    build_answer_prompt,
    parse_answer_response,
)

_CITATION = Citation(
    document_id="precedent-000001",
    chunk_id="precedent-000001#body-000",
    title="판례 제목",
    excerpt="본문 예시",
)


def test_build_answer_prompt_includes_the_question_and_every_citation() -> None:
    prompt = build_answer_prompt("약사법 제1조는 무엇을 규정하나요?", [_CITATION])

    assert "약사법 제1조는 무엇을 규정하나요?" in prompt
    assert "precedent-000001#body-000" in prompt
    assert "본문 예시" in prompt


def test_build_answer_prompt_instructs_insufficient_evidence_over_fabrication() -> None:
    prompt = build_answer_prompt("질문", [_CITATION])

    assert "insufficient_evidence" in prompt


def test_parse_answer_response_reads_an_answered_response() -> None:
    raw = json.dumps(
        {
            "status": "answered",
            "answer": "약사법 제1조는 목적을 규정합니다.",
            "cited_chunk_ids": ["precedent-000001#body-000"],
        }
    )

    parsed = parse_answer_response(raw)

    assert parsed == ParsedAnswer(
        status=AnswerStatus.ANSWERED,
        answer="약사법 제1조는 목적을 규정합니다.",
        cited_chunk_ids=("precedent-000001#body-000",),
    )


def test_parse_answer_response_reads_an_insufficient_evidence_response() -> None:
    raw = json.dumps({"status": "insufficient_evidence", "answer": None, "cited_chunk_ids": []})

    parsed = parse_answer_response(raw)

    assert parsed == ParsedAnswer(
        status=AnswerStatus.INSUFFICIENT_EVIDENCE, answer=None, cited_chunk_ids=()
    )


def test_parse_answer_response_clears_answer_and_citations_when_the_model_misbehaves() -> None:
    """The model claims insufficient_evidence but still fills answer/citations --
    parsing must not trust those fields, matching contracts.py's
    validate_grounding_state, which would otherwise raise ValueError."""

    raw = json.dumps(
        {
            "status": "insufficient_evidence",
            "answer": "이건 사실 답변입니다.",
            "cited_chunk_ids": ["precedent-000001#body-000"],
        }
    )

    parsed = parse_answer_response(raw)

    assert parsed.status is AnswerStatus.INSUFFICIENT_EVIDENCE
    assert parsed.answer is None
    assert parsed.cited_chunk_ids == ()


def test_parse_answer_response_treats_an_unrecognized_status_as_insufficient_evidence() -> None:
    raw = json.dumps({"status": "maybe", "answer": "x", "cited_chunk_ids": ["a"]})

    parsed = parse_answer_response(raw)

    assert parsed.status is AnswerStatus.INSUFFICIENT_EVIDENCE
    assert parsed.answer is None
    assert parsed.cited_chunk_ids == ()


def test_parse_answer_response_raises_on_unparseable_json() -> None:
    with pytest.raises(ValueError, match="could not parse"):
        parse_answer_response("not json at all")
