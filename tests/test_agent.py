import json
from typing import Any

from legal_agent_assessment.agent import LegalAgent
from legal_agent_assessment.contracts import AnswerStatus, GeneralLegalRequest, RuntimeVersions

_VERSIONS = RuntimeVersions(
    dataset="dataset-2026-08-11-v2.1",
    normalization="norm-v1",
    chunking="chunk-v1",
    index="index-v1",
    embedding_model="global.cohere.embed-v4:0",
    generation_model="global.anthropic.claude-sonnet-4-6",
    prompt="prompt-v1",
)


def _hit(chunk_id: str, document_id: str, *, text: str = "본문") -> dict[str, Any]:
    return {
        "_id": chunk_id,
        "_source": {
            "chunk_id": chunk_id,
            "document_id": document_id,
            "title": "제목",
            "text": text,
        },
    }


class _FakeOpenSearchClient:
    """Returns canned `_search` hits in call order: first BM25, then k-NN."""

    def __init__(self, *responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.search_calls: list[dict[str, Any]] = []

    def search(self, *, index: str, body: dict[str, Any]) -> dict[str, Any]:
        self.search_calls.append({"index": index, "body": body})
        hits = self._responses.pop(0)
        return {"hits": {"hits": hits}}


class _FakeBedrockClient:
    """Routes `invoke_model` by `modelId`: embedding vs. generation."""

    def __init__(self, *, embedding_model_id: str, generation_response_text: str) -> None:
        self._embedding_model_id = embedding_model_id
        self._generation_response_text = generation_response_text
        self.invoke_calls: list[dict[str, Any]] = []

    def invoke_model(self, *, modelId: str, body: str) -> dict[str, Any]:
        self.invoke_calls.append({"modelId": modelId, "body": json.loads(body)})
        if modelId == self._embedding_model_id:
            payload = {"embeddings": [[0.1] * 1536]}
        else:
            payload = {"content": [{"type": "text", "text": self._generation_response_text}]}
        return {"body": _FakeStreamingBody(json.dumps(payload))}


class _FakeStreamingBody:
    def __init__(self, text: str) -> None:
        self._text = text

    def read(self) -> bytes:
        return self._text.encode("utf-8")


def test_answer_skips_generation_when_retrieval_is_empty() -> None:
    opensearch = _FakeOpenSearchClient([], [])
    bedrock = _FakeBedrockClient(embedding_model_id="embed-v4", generation_response_text="unused")
    agent = LegalAgent(
        opensearch_client=opensearch,
        bedrock_client=bedrock,
        index_name="legal-kit-assessment-jynlee-chunk-v1-index-v1",
        embedding_model_id="embed-v4",
        generation_model_id="claude-sonnet",
        versions=_VERSIONS,
    )

    response = agent.answer_sync(GeneralLegalRequest(request_id="r1", question="질문"))

    assert response.status is AnswerStatus.INSUFFICIENT_EVIDENCE
    assert response.answer is None
    assert response.citations == ()
    # Only the query-embedding call happened -- no generation call spent on
    # a case retrieval already fully resolved.
    assert len(bedrock.invoke_calls) == 1


def test_answer_returns_answered_with_citations_when_generation_grounds_the_response() -> None:
    bm25_hits = [_hit("c1", "doc1", text="약사법 제1조 본문")]
    knn_hits = [_hit("c1", "doc1", text="약사법 제1조 본문")]
    opensearch = _FakeOpenSearchClient(bm25_hits, knn_hits)
    generation_text = json.dumps(
        {
            "status": "answered",
            "answer": "약사법 제1조는 목적을 규정합니다.",
            "cited_chunk_ids": ["c1"],
        }
    )
    bedrock = _FakeBedrockClient(
        embedding_model_id="embed-v4", generation_response_text=generation_text
    )
    agent = LegalAgent(
        opensearch_client=opensearch,
        bedrock_client=bedrock,
        index_name="legal-kit-assessment-jynlee-chunk-v1-index-v1",
        embedding_model_id="embed-v4",
        generation_model_id="claude-sonnet",
        versions=_VERSIONS,
    )

    response = agent.answer_sync(GeneralLegalRequest(request_id="r1", question="약사법 제1조는?"))

    assert response.status is AnswerStatus.ANSWERED
    assert response.answer == "약사법 제1조는 목적을 규정합니다."
    assert len(response.citations) == 1
    assert response.citations[0].chunk_id == "c1"
    assert len(response.retrieval_hits) == 1


def test_answer_returns_insufficient_evidence_when_generation_declines_despite_hits() -> None:
    bm25_hits = [_hit("c1", "doc1")]
    opensearch = _FakeOpenSearchClient(bm25_hits, [])
    generation_text = json.dumps(
        {"status": "insufficient_evidence", "answer": None, "cited_chunk_ids": []}
    )
    bedrock = _FakeBedrockClient(
        embedding_model_id="embed-v4", generation_response_text=generation_text
    )
    agent = LegalAgent(
        opensearch_client=opensearch,
        bedrock_client=bedrock,
        index_name="legal-kit-assessment-jynlee-chunk-v1-index-v1",
        embedding_model_id="embed-v4",
        generation_model_id="claude-sonnet",
        versions=_VERSIONS,
    )

    response = agent.answer_sync(
        GeneralLegalRequest(request_id="r1", question="표시광고법 위반인가요?")
    )

    assert response.status is AnswerStatus.INSUFFICIENT_EVIDENCE
    assert response.answer is None
    assert response.citations == ()
    # Retrieval diagnostics are still reported -- only answer/citations are
    # constrained by contracts.py's validator.
    assert len(response.retrieval_hits) == 1


def test_answer_falls_back_to_insufficient_evidence_when_claude_cites_nothing_retrieved() -> None:
    bm25_hits = [_hit("c1", "doc1")]
    opensearch = _FakeOpenSearchClient(bm25_hits, [])
    # Claims ANSWERED but cites a chunk_id this agent never retrieved --
    # must not be trusted as a real citation.
    generation_text = json.dumps(
        {"status": "answered", "answer": "지어낸 답변", "cited_chunk_ids": ["never-retrieved"]}
    )
    bedrock = _FakeBedrockClient(
        embedding_model_id="embed-v4", generation_response_text=generation_text
    )
    agent = LegalAgent(
        opensearch_client=opensearch,
        bedrock_client=bedrock,
        index_name="legal-kit-assessment-jynlee-chunk-v1-index-v1",
        embedding_model_id="embed-v4",
        generation_model_id="claude-sonnet",
        versions=_VERSIONS,
    )

    response = agent.answer_sync(GeneralLegalRequest(request_id="r1", question="질문"))

    assert response.status is AnswerStatus.INSUFFICIENT_EVIDENCE
    assert response.answer is None
    assert response.citations == ()


def test_answer_sends_search_query_input_type_never_search_document() -> None:
    opensearch = _FakeOpenSearchClient([], [])
    bedrock = _FakeBedrockClient(embedding_model_id="embed-v4", generation_response_text="unused")
    agent = LegalAgent(
        opensearch_client=opensearch,
        bedrock_client=bedrock,
        index_name="legal-kit-assessment-jynlee-chunk-v1-index-v1",
        embedding_model_id="embed-v4",
        generation_model_id="claude-sonnet",
        versions=_VERSIONS,
    )

    agent.answer_sync(GeneralLegalRequest(request_id="r1", question="질문"))

    embed_call = bedrock.invoke_calls[0]
    assert embed_call["body"]["input_type"] == "search_query"
