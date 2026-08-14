"""Concrete GeneralLegalAgent, backed by injected OpenSearch and Bedrock clients.

Implements reports/decisions/2026-08-13-retrieval-design.md Decision 5:
clients are constructor-injected -- CONTRACT.md's "replaceable ... adapters"
-- never built internally, so this orchestration is exercised in tests with
fake clients and no real network call. scripts/serve_legal_agent.py is the
only place real clients are built.
"""

import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from botocore.exceptions import (  # type: ignore[import-untyped]
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)
from opensearchpy.exceptions import ConnectionError as OpenSearchConnectionError
from opensearchpy.exceptions import ConnectionTimeout as OpenSearchConnectionTimeout

from legal_agent_assessment.contracts import (
    AnswerStatus,
    GeneralLegalRequest,
    GeneralLegalResponse,
    RuntimeVersions,
)
from legal_agent_assessment.embedding import (
    EMBEDDING_DIMENSION,
    build_embed_request,
    estimate_tokens,
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


@dataclass(frozen=True, slots=True)
class _GenerationResult:
    """One generation call's text plus the token usage Bedrock reported."""

    text: str
    usage: dict[str, Any]


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

    async def answer(
        self,
        request: GeneralLegalRequest,
        *,
        on_usage: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> GeneralLegalResponse:
        """Answer one independent question without Peitho runtime objects."""

        return self.answer_sync(request, on_usage=on_usage)

    def answer_sync(
        self,
        request: GeneralLegalRequest,
        *,
        on_usage: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> GeneralLegalResponse:
        """Answer one question, converting a narrow set of known
        OpenSearch/Bedrock connectivity failures into a `DEPENDENCY_UNAVAILABLE`
        response instead of letting them raise.

        Only genuine "could not reach the service at all" failures are
        caught here -- an OpenSearch/Bedrock error that reached the service
        and was rejected (bad index name, malformed request, auth failure)
        is a real bug and must keep propagating uncaught, not be silently
        reported as an infrastructure outage
        (reports/decisions/2026-08-14-out-of-scope-and-dependency-unavailable-design.md
        Decision 2). `_answer_sync_unguarded` carries the actual
        answering logic and its own detailed docstring.
        """

        try:
            return self._answer_sync_unguarded(request, on_usage=on_usage)
        except (
            OpenSearchConnectionError,
            OpenSearchConnectionTimeout,
            EndpointConnectionError,
            ConnectTimeoutError,
            ReadTimeoutError,
        ):
            return GeneralLegalResponse(
                request_id=request.request_id,
                status=AnswerStatus.DEPENDENCY_UNAVAILABLE,
                versions=self._versions,
            )

    def _answer_sync_unguarded(
        self,
        request: GeneralLegalRequest,
        *,
        on_usage: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> GeneralLegalResponse:
        """Synchronous core: every call here is I/O-bound, not CPU-bound, so
        a thin `async def answer` delegating to this makes the class usable
        from both async and synchronous test/CLI code without duplicating
        logic. `answer` is the Protocol-required entry point.

        `on_usage(step, values)` is invoked after every paid Bedrock call
        that actually returned -- `"embed"` with `{"estimated_tokens": int}`
        (no real Cohere token count is available, same reason
        `embedding.estimate_tokens` exists), and `"generate"` with the real
        `{"input_tokens": int, "output_tokens": int}` Bedrock reports.
        Reporting incrementally, rather than returning a total, means a
        caller can still record the spend already incurred when a later step
        raises -- the same reason `scripts/bedrock_embedding.py`'s
        `embed_batch` takes `on_batch_complete`. Optional and `None` by
        default: existing call sites are unaffected.

        Every `RetrievalHit.score` this method emits is the *fused* RRF
        score (`retrieval.reciprocal_rank_fusion`), not a raw BM25 score and
        not a raw cosine similarity -- comparable only within one response.
        """

        query_vector = self._embed_query(request.question)
        if on_usage is not None:
            on_usage("embed", {"estimated_tokens": estimate_tokens(request.question)})

        bm25_hits = self._search(build_bm25_query(request.question, size=_BM25_SIZE))
        knn_hits = self._search(build_knn_query(query_vector, size=_KNN_SIZE))

        # Keyed off the indexed `chunk_id` field, never OpenSearch's own
        # `_id`: `Citation.chunk_id`, `RetrievalHit.chunk_id` and the
        # prompt's `[label]`s all use that field, and the two happen to be
        # equal today only because scripts/index_chunks.py chooses to set
        # `_id = chunk.chunk_id`. Depending on that choice from here would
        # make any future re-index with auto-generated ids fail silently:
        # nothing would ever match, and every answer would degrade to
        # insufficient_evidence with healthy-looking retrieval_hits.
        sources_by_id = {
            hit["_source"]["chunk_id"]: hit["_source"] for hit in (*bm25_hits, *knn_hits)
        }
        fused = reciprocal_rank_fusion(
            [
                [hit["_source"]["chunk_id"] for hit in bm25_hits],
                [hit["_source"]["chunk_id"] for hit in knn_hits],
            ],
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
        generation = self._generate(prompt)
        if on_usage is not None:
            # Real counts, straight from the Bedrock Anthropic Messages API
            # response body. Missing keys default to 0 rather than raising:
            # losing a usage number must never fail an answer that was
            # already paid for and successfully produced.
            on_usage(
                "generate",
                {
                    "input_tokens": int(generation.usage.get("input_tokens", 0)),
                    "output_tokens": int(generation.usage.get("output_tokens", 0)),
                },
            )
        parsed = parse_answer_response(generation.text)

        if parsed.status is AnswerStatus.OUT_OF_SCOPE:
            return GeneralLegalResponse(
                request_id=request.request_id,
                status=AnswerStatus.OUT_OF_SCOPE,
                retrieval_hits=retrieval_hits,
                versions=self._versions,
            )

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

        # Partially fabricated citations: some cited ids were real, some were
        # not. The answer still stands on its real citations, but the
        # discarded ids are surfaced through `limitations` rather than
        # dropped without a trace -- a response that quietly cites fewer
        # sources than the model claimed is exactly what that field is for.
        dropped_ids = sorted(
            {chunk_id for chunk_id in parsed.cited_chunk_ids if chunk_id not in candidate_citations}
        )
        limitations = (
            (f"Model cited unknown chunk_id(s), dropped: {', '.join(dropped_ids)}",)
            if dropped_ids
            else ()
        )

        return GeneralLegalResponse(
            request_id=request.request_id,
            status=AnswerStatus.ANSWERED,
            answer=parsed.answer,
            citations=cited,
            retrieval_hits=retrieval_hits,
            limitations=limitations,
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

    def _generate(self, prompt: str) -> _GenerationResult:
        request_body = {
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": _GENERATION_MAX_TOKENS,
            "messages": [{"role": "user", "content": prompt}],
        }
        response = self._bedrock.invoke_model(
            modelId=self._generation_model_id, body=json.dumps(request_body)
        )
        body = json.loads(response["body"].read())

        # A `max_tokens` stop leaves a truncated JSON fragment, which
        # `parse_answer_response` can only report as "unparseable JSON" --
        # naming truncation here keeps the real cause from being buried.
        if body.get("stop_reason") == "max_tokens":
            raise RuntimeError(
                "generation was truncated: the model hit max_tokens "
                f"({_GENERATION_MAX_TOKENS}) before finishing its JSON response"
            )

        text: str = body["content"][0]["text"]
        usage: dict[str, Any] = body.get("usage") or {}
        return _GenerationResult(text=text, usage=usage)


__all__ = ["LegalAgent"]
