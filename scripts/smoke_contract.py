"""Construct and serialize the frozen public contract without external services."""

from legal_agent_assessment import (
    AnswerStatus,
    GeneralLegalRequest,
    GeneralLegalResponse,
    RuntimeVersions,
)


def main() -> None:
    """Run the offline contract smoke check."""

    request = GeneralLegalRequest(request_id="smoke-1", question="테스트 질문")
    response = GeneralLegalResponse(
        request_id=request.request_id,
        status=AnswerStatus.INSUFFICIENT_EVIDENCE,
        limitations=("No dataset is loaded by the template.",),
        versions=RuntimeVersions(
            dataset="unreleased",
            normalization="unimplemented",
            chunking="unimplemented",
            index="unimplemented",
            embedding_model="global.cohere.embed-v4:0",
            generation_model="global.anthropic.claude-sonnet-4-6",
            prompt="unimplemented",
            rerank="unimplemented",
        ),
    )
    print(response.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
