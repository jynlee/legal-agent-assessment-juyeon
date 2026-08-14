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


@pytest.mark.parametrize("raw", ["[]", "null", "42", '"answered"'])
def test_parse_answer_response_raises_on_valid_json_that_is_not_an_object(raw: str) -> None:
    """Valid JSON of the wrong shape must fail the same documented way as
    undecodable text -- ValueError, not AttributeError/TypeError from
    calling dict methods on a list, None, int or str."""

    with pytest.raises(ValueError, match="could not parse"):
        parse_answer_response(raw)


def test_parse_answer_response_unwraps_a_markdown_fenced_json_object() -> None:
    """Returning JSON inside a ```json fence is a very common real model
    output pattern, and is not a malformed answer."""

    body = json.dumps(
        {
            "status": "answered",
            "answer": "약사법 제1조는 목적을 규정합니다.",
            "cited_chunk_ids": ["precedent-000001#body-000"],
        }
    )

    parsed = parse_answer_response(f"```json\n{body}\n```")

    assert parsed == ParsedAnswer(
        status=AnswerStatus.ANSWERED,
        answer="약사법 제1조는 목적을 규정합니다.",
        cited_chunk_ids=("precedent-000001#body-000",),
    )


def test_parse_answer_response_unwraps_an_untagged_fence() -> None:
    body = json.dumps({"status": "insufficient_evidence", "answer": None, "cited_chunk_ids": []})

    parsed = parse_answer_response(f"```\n{body}\n```")

    assert parsed.status is AnswerStatus.INSUFFICIENT_EVIDENCE


def test_parse_answer_response_treats_null_cited_chunk_ids_as_no_citations() -> None:
    """A null (not a list) cited_chunk_ids on an *answered* response used to
    raise TypeError inside tuple(). It degrades to () instead; agent.py then
    correctly refuses, since ANSWERED requires >=1 real citation."""

    raw = json.dumps({"status": "answered", "answer": "답변", "cited_chunk_ids": None})

    parsed = parse_answer_response(raw)

    assert parsed.status is AnswerStatus.ANSWERED
    assert parsed.answer == "답변"
    assert parsed.cited_chunk_ids == ()


def test_parse_answer_response_tolerates_null_cited_chunk_ids_on_a_refusal() -> None:
    raw = json.dumps({"status": "insufficient_evidence", "answer": None, "cited_chunk_ids": None})

    parsed = parse_answer_response(raw)

    assert parsed == ParsedAnswer(
        status=AnswerStatus.INSUFFICIENT_EVIDENCE, answer=None, cited_chunk_ids=()
    )


def test_parse_answer_response_drops_non_string_cited_chunk_ids() -> None:
    """A real chunk_id is always a string in this codebase, so a number or a
    nested object can never match a retrieved id -- dropping it matches this
    module's never-trust-the-model philosophy."""

    raw = json.dumps(
        {
            "status": "answered",
            "answer": "답변",
            "cited_chunk_ids": ["precedent-000001#body-000", 7, None, {"chunk_id": "x"}],
        }
    )

    parsed = parse_answer_response(raw)

    assert parsed.cited_chunk_ids == ("precedent-000001#body-000",)


def test_build_answer_prompt_instructs_out_of_scope_for_non_legal_questions() -> None:
    prompt = build_answer_prompt("질문", [_CITATION])

    # A phrase unique to the out_of_scope instruction paragraph itself, not
    # the JSON-shape line at the end (which also contains "out_of_scope" and
    # so would let this assertion pass even if the instruction paragraph
    # were deleted entirely).
    assert "is not a legal question at all" in prompt


def test_parse_answer_response_reads_an_out_of_scope_response() -> None:
    raw = json.dumps({"status": "out_of_scope", "answer": None, "cited_chunk_ids": []})

    parsed = parse_answer_response(raw)

    assert parsed == ParsedAnswer(status=AnswerStatus.OUT_OF_SCOPE, answer=None, cited_chunk_ids=())


def test_parse_answer_response_clears_answer_and_citations_when_out_of_scope_model_misbehaves() -> (
    None
):
    """Same never-trust-the-model rule as the existing insufficient_evidence
    misbehavior test -- an out_of_scope response must never carry answer
    text or citations, regardless of what the raw model output claims."""

    raw = json.dumps(
        {
            "status": "out_of_scope",
            "answer": "이건 사실 답변입니다.",
            "cited_chunk_ids": ["precedent-000001#body-000"],
        }
    )

    parsed = parse_answer_response(raw)

    assert parsed.status is AnswerStatus.OUT_OF_SCOPE
    assert parsed.answer is None
    assert parsed.cited_chunk_ids == ()
