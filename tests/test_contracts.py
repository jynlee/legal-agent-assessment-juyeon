import pytest
from pydantic import ValidationError

from legal_agent_assessment import (
    AnswerStatus,
    Citation,
    GeneralLegalRequest,
    GeneralLegalResponse,
    RuntimeVersions,
)


@pytest.fixture
def versions() -> RuntimeVersions:
    return RuntimeVersions(
        dataset="dataset-v1",
        normalization="norm-v1",
        chunking="chunks-v1",
        index="index-v1",
        embedding_model="global.cohere.embed-v4:0",
        generation_model="global.anthropic.claude-sonnet-4-6",
        prompt="prompt-v1",
    )


def test_request_and_grounded_answer_round_trip(versions: RuntimeVersions) -> None:
    request = GeneralLegalRequest(request_id="req-1", question="환불 규정은 무엇인가요?")
    response = GeneralLegalResponse(
        request_id=request.request_id,
        status=AnswerStatus.ANSWERED,
        answer="검색된 근거에 따른 답변입니다.",
        citations=(
            Citation(
                document_id="doc-1",
                chunk_id="chunk-1",
                title="공식 자료",
                excerpt="근거가 되는 최소 인용문",
            ),
        ),
        versions=versions,
    )

    restored = GeneralLegalResponse.model_validate_json(response.model_dump_json())

    assert restored == response


def test_answered_response_requires_a_citation(versions: RuntimeVersions) -> None:
    with pytest.raises(ValidationError, match="at least one citation"):
        GeneralLegalResponse(
            request_id="req-1",
            status=AnswerStatus.ANSWERED,
            answer="근거가 없는 답변",
            versions=versions,
        )


def test_non_answer_cannot_smuggle_answer_text(versions: RuntimeVersions) -> None:
    with pytest.raises(ValidationError, match="cannot contain answer text"):
        GeneralLegalResponse(
            request_id="req-1",
            status=AnswerStatus.OUT_OF_SCOPE,
            answer="범위 밖이지만 답변을 생성함",
            versions=versions,
        )
