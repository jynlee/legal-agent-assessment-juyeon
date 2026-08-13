"""Concrete GeneralLegalAgent, backed by injected OpenSearch and Bedrock clients.

Implements reports/decisions/2026-08-13-retrieval-design.md Decision 5:
clients are constructor-injected -- CONTRACT.md's "replaceable ... adapters"
-- never built internally, so this orchestration is exercised in tests with
fake clients and no real network call. scripts/serve_legal_agent.py is the
only place real clients are built.
"""

import json
from typing import Any

from legal_agent_assessment.contracts import (
    AnswerStatus,
    GeneralLegalRequest,
    GeneralLegalResponse,
    RuntimeVersions,
)
from legal_agent_assessment.embedding import (
    EMBEDDING_DIMENSION,
    build_embed_request,
    parse_embed_response,
)
from legal_agent_assessment.generation import build_answer_prompt, parse_answer_response
from legal_agent_assessment.retrieval import (
    build_bm25_query,
    build_knn_query,
    reciprocal_rank_fusion,
    source_to_citation,
    source_to_retrieval_hit,
)

_BM25_SIZE = 50
_KNN_SIZE = 50
_FUSED_TOP_N = 10
_RRF_K = 60
_GENERATION_MAX_TOKENS = 1024


class LegalAgent:
    """Hybrid-retrieval, single-turn `GeneralLegalAgent` implementation."""

    def __init__(
        self,
        *,
        opensearch_client: Any,
        bedrock_client: Any,
        index_name: str,
        embedding_model_id: str,
        generation_model_id: str,
        versions: RuntimeVersions,
    ) -> None:
        self._opensearch = opensearch_client
        self._bedrock = bedrock_client
        self._index_name = index_name
        self._embedding_model_id = embedding_model_id
        self._generation_model_id = generation_model_id
        self._versions = versions

    async def answer(self, request: GeneralLegalRequest) -> GeneralLegalResponse:
        """Answer one independent question without Peitho runtime objects."""

        return self.answer_sync(request)

    def answer_sync(self, request: GeneralLegalRequest) -> GeneralLegalResponse:
        """Synchronous core: every call here is I/O-bound, not CPU-bound, so
        a thin `async def answer` delegating to this makes the class usable
        from both async and synchronous test/CLI code without duplicating
        logic. `answer` is the Protocol-required entry point."""

        query_vector = self._embed_query(request.question)
        bm25_hits = self._search(build_bm25_query(request.question, size=_BM25_SIZE))
        knn_hits = self._search(build_knn_query(query_vector, size=_KNN_SIZE))

        sources_by_id = {hit["_id"]: hit["_source"] for hit in (*bm25_hits, *knn_hits)}
        fused = reciprocal_rank_fusion(
            [[hit["_id"] for hit in bm25_hits], [hit["_id"] for hit in knn_hits]],
            k=_RRF_K,
        )[:_FUSED_TOP_N]

        if not fused:
            return GeneralLegalResponse(
                request_id=request.request_id,
                status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                versions=self._versions,
            )

        retrieval_hits = tuple(
            source_to_retrieval_hit(sources_by_id[chunk_id], rank=rank, score=score)
            for rank, (chunk_id, score) in enumerate(fused, start=1)
        )
        candidate_citations = {
            chunk_id: source_to_citation(sources_by_id[chunk_id]) for chunk_id, _score in fused
        }

        prompt = build_answer_prompt(request.question, tuple(candidate_citations.values()))
        raw_response = self._generate(prompt)
        parsed = parse_answer_response(raw_response)

        if parsed.status is not AnswerStatus.ANSWERED:
            return GeneralLegalResponse(
                request_id=request.request_id,
                status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                retrieval_hits=retrieval_hits,
                versions=self._versions,
            )

        cited = tuple(
            candidate_citations[chunk_id]
            for chunk_id in parsed.cited_chunk_ids
            if chunk_id in candidate_citations
        )
        if not cited:
            # Claimed ANSWERED but cited nothing this agent actually
            # retrieved -- contracts.py requires >=1 real citation for
            # ANSWERED, and fabricating one from an unlisted chunk_id would
            # be worse than refusing.
            return GeneralLegalResponse(
                request_id=request.request_id,
                status=AnswerStatus.INSUFFICIENT_EVIDENCE,
                retrieval_hits=retrieval_hits,
                versions=self._versions,
            )

        return GeneralLegalResponse(
            request_id=request.request_id,
            status=AnswerStatus.ANSWERED,
            answer=parsed.answer,
            citations=cited,
            retrieval_hits=retrieval_hits,
            versions=self._versions,
        )

    def _embed_query(self, question: str) -> tuple[float, ...]:
        request_body = build_embed_request([question], input_type="search_query")
        response = self._bedrock.invoke_model(
            modelId=self._embedding_model_id, body=json.dumps(request_body)
        )
        body = json.loads(response["body"].read())
        (vector,) = parse_embed_response(
            body, expected_count=1, expected_dimension=EMBEDDING_DIMENSION
        )
        return vector

    def _search(self, query: dict[str, Any]) -> list[dict[str, Any]]:
        response = self._opensearch.search(index=self._index_name, body=query)
        hits: list[dict[str, Any]] = response["hits"]["hits"]
        return hits

    def _generate(self, prompt: str) -> str:
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": _GENERATION_MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = self._bedrock.invoke_model(
            modelId=self._generation_model_id, body=json.dumps(request_body)
        )
        body = json.loads(response["body"].read())
        text: str = body["content"][0]["text"]
        return text


__all__ = ["LegalAgent"]
