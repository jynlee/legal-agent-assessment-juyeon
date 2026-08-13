import asyncio
import json
from typing import Any

import pytest

from legal_agent_assessment.agent import LegalAgent
from legal_agent_assessment.contracts import (
    AnswerStatus,
    GeneralLegalAgent,
    GeneralLegalRequest,
    RuntimeVersions,
)
from legal_agent_assessment.embedding import EMBEDDING_DIMENSION

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
    """One OpenSearch hit whose `_id` deliberately differs from `chunk_id`.

    scripts/index_chunks.py happens to set `_id = chunk.chunk_id` today, but
    the agent must not depend on that indexing-side choice: keying off `_id`
    would make any re-index with auto-generated ids silently return
    insufficient_evidence for every query.
    """

    return {
        "_id": f"opensearch-internal-{chunk_id}",
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

    def __init__(
        self,
        *,
        embedding_model_id: str,
        generation_response_text: str,
        generation_stop_reason: str = "end_turn",
        generation_usage: dict[str, int] | None = None,
    ) -> None:
        self._embedding_model_id = embedding_model_id
        self._generation_response_text = generation_response_text
        self._generation_stop_reason = generation_stop_reason
        self._generation_usage = generation_usage or {"input_tokens": 1200, "output_tokens": 90}
        self.invoke_calls: list[dict[str, Any]] = []

    def invoke_model(self, *, modelId: str, body: str) -> dict[str, Any]:
        self.invoke_calls.append({"modelId": modelId, "body": json.loads(body)})
        payload: dict[str, Any]
        if modelId == self._embedding_model_id:
            payload = {"embeddings": [[0.1] * EMBEDDING_DIMENSION]}
        else:
            payload = {
                "content": [{"type": "text", "text": self._generation_response_text}],
                "stop_reason": self._generation_stop_reason,
                "usage": dict(self._generation_usage),
            }
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
    # Matched back through `_source["chunk_id"]`, not the hit's `_id`.
    assert response.citations[0].chunk_id == "c1"
    assert len(response.retrieval_hits) == 1
    assert response.limitations == ()

    # The two searches must not be swapped: BM25 first, then exact k-NN, both
    # against the configured index.
    bm25_call, knn_call = opensearch.search_calls
    assert bm25_call["index"] == "legal-kit-assessment-jynlee-chunk-v1-index-v1"
    assert knn_call["index"] == "legal-kit-assessment-jynlee-chunk-v1-index-v1"
    assert "multi_match" in bm25_call["body"]["query"]
    assert "script_score" in knn_call["body"]["query"]
    assert knn_call["body"]["query"]["script_score"]["script"]["source"] == "knn_score"


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


def test_answer_matches_citations_when_opensearch_ids_differ_from_chunk_ids() -> None:
    """The agent must key off `_source["chunk_id"]`, never OpenSearch's `_id`.

    scripts/index_chunks.py sets `_id = chunk.chunk_id` today, but a re-index
    using auto-generated ids (the cluster has auto_create_index: true) would,
    if this regressed, make every query return insufficient_evidence while
    `retrieval_hits` still looked healthy -- a silent, total failure.
    """

    hits = [
        {
            "_id": "opensearch-internal-id-1",
            "_source": {
                "chunk_id": "c1",
                "document_id": "doc1",
                "title": "제목",
                "text": "약사법 제1조 본문",
            },
        }
    ]
    opensearch = _FakeOpenSearchClient(list(hits), list(hits))
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
    assert [citation.chunk_id for citation in response.citations] == ["c1"]
    assert [hit.chunk_id for hit in response.retrieval_hits] == ["c1"]
    # The prompt labels sources by chunk_id, so the model can only ever cite
    # that form -- never the internal `_id`.
    generation_prompt = bedrock.invoke_calls[1]["body"]["messages"][0]["content"]
    assert "[c1]" in generation_prompt
    assert "opensearch-internal-id-1" not in generation_prompt


def test_answer_records_dropped_citations_in_limitations_when_only_some_are_real() -> None:
    """One real citation and one invented one: the answer stands, but the
    discarded id is surfaced through `limitations` rather than vanishing."""

    bm25_hits = [_hit("c1", "doc1", text="약사법 제1조 본문")]
    opensearch = _FakeOpenSearchClient(bm25_hits, [])
    generation_text = json.dumps(
        {
            "status": "answered",
            "answer": "약사법 제1조는 목적을 규정합니다.",
            "cited_chunk_ids": ["c1", "made-up-chunk"],
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
    assert [citation.chunk_id for citation in response.citations] == ["c1"]
    assert len(response.limitations) == 1
    assert "made-up-chunk" in response.limitations[0]


def test_answer_raises_a_named_error_when_generation_is_truncated_at_max_tokens() -> None:
    """A max_tokens stop leaves an unparseable JSON fragment -- the failure
    must name truncation, not surface as generic 'unparseable JSON'."""

    bm25_hits = [_hit("c1", "doc1")]
    opensearch = _FakeOpenSearchClient(bm25_hits, [])
    bedrock = _FakeBedrockClient(
        embedding_model_id="embed-v4",
        generation_response_text='{"status": "answered", "answer": "잘린',
        generation_stop_reason="max_tokens",
    )
    agent = LegalAgent(
        opensearch_client=opensearch,
        bedrock_client=bedrock,
        index_name="legal-kit-assessment-jynlee-chunk-v1-index-v1",
        embedding_model_id="embed-v4",
        generation_model_id="claude-sonnet",
        versions=_VERSIONS,
    )

    with pytest.raises(RuntimeError, match="truncated"):
        agent.answer_sync(GeneralLegalRequest(request_id="r1", question="질문"))


def test_answer_reports_embed_and_generation_usage_through_the_callback() -> None:
    bm25_hits = [_hit("c1", "doc1", text="약사법 제1조 본문")]
    opensearch = _FakeOpenSearchClient(bm25_hits, [])
    generation_text = json.dumps(
        {
            "status": "answered",
            "answer": "약사법 제1조는 목적을 규정합니다.",
            "cited_chunk_ids": ["c1"],
        }
    )
    bedrock = _FakeBedrockClient(
        embedding_model_id="embed-v4",
        generation_response_text=generation_text,
        generation_usage={"input_tokens": 4321, "output_tokens": 77},
    )
    agent = LegalAgent(
        opensearch_client=opensearch,
        bedrock_client=bedrock,
        index_name="legal-kit-assessment-jynlee-chunk-v1-index-v1",
        embedding_model_id="embed-v4",
        generation_model_id="claude-sonnet",
        versions=_VERSIONS,
    )

    reported: list[tuple[str, dict[str, Any]]] = []
    agent.answer_sync(
        GeneralLegalRequest(request_id="r1", question="약사법 제1조는?"),
        on_usage=lambda step, values: reported.append((step, values)),
    )

    assert [step for step, _values in reported] == ["embed", "generate"]
    assert reported[0][1]["estimated_tokens"] > 0
    assert reported[1][1] == {"input_tokens": 4321, "output_tokens": 77}


def test_answer_reports_only_embed_usage_when_retrieval_is_empty() -> None:
    """No generation call happened, so no generation usage may be claimed."""

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

    reported: list[str] = []
    agent.answer_sync(
        GeneralLegalRequest(request_id="r1", question="질문"),
        on_usage=lambda step, _values: reported.append(step),
    )

    assert reported == ["embed"]


def test_legal_agent_satisfies_the_protocol_and_answers_through_the_async_entry_point() -> None:
    """`answer` -- not `answer_sync` -- is what contracts.py's Protocol
    requires; the annotation below is the static conformance check, and
    asyncio.run exercises the coroutine itself without pytest-asyncio."""

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
    agent: GeneralLegalAgent = LegalAgent(
        opensearch_client=opensearch,
        bedrock_client=bedrock,
        index_name="legal-kit-assessment-jynlee-chunk-v1-index-v1",
        embedding_model_id="embed-v4",
        generation_model_id="claude-sonnet",
        versions=_VERSIONS,
    )

    response = asyncio.run(
        agent.answer(GeneralLegalRequest(request_id="r1", question="약사법 제1조는?"))
    )

    assert response.status is AnswerStatus.ANSWERED
    assert response.answer == "약사법 제1조는 목적을 규정합니다."
    assert [citation.chunk_id for citation in response.citations] == ["c1"]
    assert len(response.retrieval_hits) == 1
