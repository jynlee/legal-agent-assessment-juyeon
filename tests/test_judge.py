import json

import pytest

from legal_agent_assessment.contracts import Citation
from legal_agent_assessment.judge import ParsedVerdict, build_judge_prompt, parse_judge_response

_CITATION = Citation(
    document_id="precedent-000001",
    chunk_id="precedent-000001#body-000",
    title="판례 제목",
    excerpt="본문 예시",
)


def test_build_judge_prompt_includes_the_question_answer_and_every_citation() -> None:
    prompt = build_judge_prompt(
        "약사법 제1조는 무엇을 규정하나요?", "국민보건 향상을 목적으로 합니다.", [_CITATION]
    )

    assert "약사법 제1조는 무엇을 규정하나요?" in prompt
    assert "국민보건 향상을 목적으로 합니다." in prompt
    assert "precedent-000001#body-000" in prompt
    assert "본문 예시" in prompt


def test_build_judge_prompt_instructs_the_three_verdict_categories() -> None:
    prompt = build_judge_prompt("질문", "답변", [_CITATION])

    assert "grounded" in prompt
    assert "partially_grounded" in prompt
    assert "unsupported" in prompt


def test_parse_judge_response_reads_a_grounded_verdict() -> None:
    raw = json.dumps({"grounding": "grounded", "justification": "모든 주장이 근거로 뒷받침됨."})

    parsed = parse_judge_response(raw)

    assert parsed == ParsedVerdict(
        grounding="grounded", justification="모든 주장이 근거로 뒷받침됨."
    )


def test_parse_judge_response_reads_a_partially_grounded_verdict() -> None:
    raw = json.dumps({"grounding": "partially_grounded", "justification": "일부만 근거에 있음."})

    parsed = parse_judge_response(raw)

    assert parsed.grounding == "partially_grounded"


def test_parse_judge_response_reads_an_unsupported_verdict() -> None:
    raw = json.dumps({"grounding": "unsupported", "justification": "근거에 없는 주장 포함."})

    parsed = parse_judge_response(raw)

    assert parsed.grounding == "unsupported"


def test_parse_judge_response_raises_on_an_unrecognized_grounding_value() -> None:
    raw = json.dumps({"grounding": "maybe", "justification": "..."})

    with pytest.raises(ValueError, match="unrecognized grounding value"):
        parse_judge_response(raw)


def test_parse_judge_response_raises_on_unparseable_json() -> None:
    with pytest.raises(ValueError, match="could not parse"):
        parse_judge_response("not json at all")


@pytest.mark.parametrize("raw", ["[]", "null", "42", '"grounded"'])
def test_parse_judge_response_raises_on_valid_json_that_is_not_an_object(raw: str) -> None:
    with pytest.raises(ValueError, match="could not parse"):
        parse_judge_response(raw)


def test_parse_judge_response_unwraps_a_markdown_fenced_json_object() -> None:
    body = json.dumps({"grounding": "grounded", "justification": "근거와 일치."})

    parsed = parse_judge_response(f"```json\n{body}\n```")

    assert parsed == ParsedVerdict(grounding="grounded", justification="근거와 일치.")


def test_parse_judge_response_defaults_a_missing_justification_to_empty_string() -> None:
    raw = json.dumps({"grounding": "grounded"})

    parsed = parse_judge_response(raw)

    assert parsed.justification == ""
