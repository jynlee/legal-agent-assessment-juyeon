"""Pure-retrieval evaluation against the frozen test set: Recall@10, MRR.

    uv run python scripts/evaluate_retrieval.py --contributor jynlee

No generation call is made -- SUBMISSION.md asks retrieval (deterministic,
given a frozen index and a fixed query) to be measured separately from
generation (stochastic). Reuses exactly the retrieval half of
LegalAgent.answer_sync: embed the query (input_type="search_query"),
BM25 top-50 + k-NN top-50, RRF fuse (k=60), top-10 -- the same constants
reports/decisions/2026-08-13-retrieval-design.md fixed.

Recall@10/MRR are computed only for questions with expected_status
"answered" (a real required-positive chunk_id exists to recall). The 10
unanswerable/out-of-scope questions are still retrieved against (for
transparency: what would generation have seen), but no metric is computed
for them -- there is no positive to recall.

Writes a per-run usage log (embedding calls, estimated tokens, cost,
latency) to reports/usage/, matching scripts/index_chunks.py's pattern.
"""

import argparse
import json
import os
import pathlib
import sys
import time
from typing import Any

import boto3

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from opensearch_client import build_client

from legal_agent_assessment.embedding import (
    EMBEDDING_DIMENSION,
    build_embed_request,
    estimate_tokens,
    parse_embed_response,
)
from legal_agent_assessment.eval import lexical_overlap_ratio
from legal_agent_assessment.opensearch_index import index_name
from legal_agent_assessment.retrieval import (
    build_bm25_query,
    build_knn_query,
    reciprocal_rank_fusion,
)

_BM25_SIZE = 50
_KNN_SIZE = 50
_FUSED_TOP_N = 10
_RRF_K = 60

# Same rate as scripts/index_chunks.py's COHERE_EMBED_V4_USD_PER_MILLION_TOKENS.
_COHERE_EMBED_V4_USD_PER_MILLION_TOKENS = 0.12


def load_test_set(path: pathlib.Path) -> list[dict[str, Any]]:
    """Read the 50-question test set."""

    data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    assert len(data) == 50, f"expected 50 test-set entries, got {len(data)}"
    return data


def embed_query(bedrock_client: Any, question: str, model_id: str) -> tuple[float, ...]:
    """Embed one query with input_type=search_query, matching agent.py's real path."""

    request = build_embed_request([question], input_type="search_query")
    response = bedrock_client.invoke_model(modelId=model_id, body=json.dumps(request))
    body = json.loads(response["body"].read())
    (vector,) = parse_embed_response(body, expected_count=1, expected_dimension=EMBEDDING_DIMENSION)
    return vector


def retrieve_fused_chunk_ids(
    opensearch_client: Any, index: str, question: str, query_vector: tuple[float, ...]
) -> list[str]:
    """Run BM25 + k-NN + RRF fusion for one question; return fused chunk_ids, top-10."""

    bm25_response = opensearch_client.search(
        index=index, body=build_bm25_query(question, size=_BM25_SIZE)
    )
    knn_response = opensearch_client.search(
        index=index, body=build_knn_query(query_vector, size=_KNN_SIZE)
    )
    bm25_ids = [hit["_source"]["chunk_id"] for hit in bm25_response["hits"]["hits"]]
    knn_ids = [hit["_source"]["chunk_id"] for hit in knn_response["hits"]["hits"]]
    fused = reciprocal_rank_fusion([bm25_ids, knn_ids], k=_RRF_K)
    return [chunk_id for chunk_id, _score in fused[:_FUSED_TOP_N]]


def score_answerable_question(
    fused_ids: list[str], relevant_chunk_ids: list[str]
) -> tuple[int, float]:
    """Return (recall_at_10, reciprocal_rank) for one answerable question.

    recall_at_10 is 1 if any relevant_chunk_id is in the fused top-10, else
    0. reciprocal_rank is 1/(1-indexed rank of the first relevant chunk
    found in fused_ids), or 0.0 if none of the relevant ids appear in the
    top-10 at all -- MRR uses the same top-10 cutoff as Recall@10 here
    (reports/decisions/2026-08-13-retrieval-evaluation-design.md Decision 4
    ties both metrics to what generation actually receives), not the full
    pre-fusion top-50 pool.

    This metric is deliberately binary/hit-based, not a set-overlap
    fraction, because Decision 6 of that same design doc states the
    per-question Recall@10 is "0 or 1, since there is exactly one required
    positive per answerable question under Decision 3." The assertion
    below enforces that invariant at call time: Decision 3 explicitly
    permits (but never requires) recording additional optional positives
    for a question, and if that ever happens without also revisiting this
    function, a set-based "any positive found" hit would silently keep
    returning 1 even when only one of several recorded positives was
    actually retrieved -- quietly changing what the metric means without
    any error. Raising here instead keeps that drift from rotting silently.
    """

    assert len(relevant_chunk_ids) == 1, (
        "score_answerable_question assumes exactly one required positive per "
        "answerable question (reports/decisions/2026-08-13-retrieval-evaluation-design.md "
        f"Decision 6), got {len(relevant_chunk_ids)}: {relevant_chunk_ids!r}. "
        "If a second optional positive was intentionally added per Decision 3, "
        "this function's binary recall formula needs to be revisited first."
    )

    for rank, chunk_id in enumerate(fused_ids, start=1):
        if chunk_id in relevant_chunk_ids:
            return 1, 1.0 / rank
    return 0, 0.0


def main() -> None:
    """Run the full pure-retrieval evaluation once."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contributor", required=True)
    args = parser.parse_args()

    region = os.environ.get("AWS_REGION", "ap-northeast-2")
    bedrock_region = os.environ.get("BEDROCK_REGION", region)
    embedding_model_id = os.environ.get("EMBEDDING_MODEL_ID", "global.cohere.embed-v4:0")
    name = index_name(args.contributor)

    opensearch_client = build_client(
        url=os.environ.get("OPENSEARCH_URL", "http://localhost:9200"),
        profile=os.environ["AWS_PROFILE"],
        region=region,
    )
    bedrock_client = boto3.client("bedrock-runtime", region_name=bedrock_region)

    test_set_path = (
        pathlib.Path(__file__).resolve().parents[1] / "reports" / "eval" / "retrieval_test_set.json"
    )
    questions = load_test_set(test_set_path)

    started = time.perf_counter()
    embedding_calls = 0
    estimated_tokens = 0
    per_question_results: list[dict[str, Any]] = []
    per_domain: dict[str, list[int]] = {}
    per_domain_mrr: dict[str, list[float]] = {}

    try:
        for entry in questions:
            question_text = entry["question"]
            query_vector = embed_query(bedrock_client, question_text, embedding_model_id)
            embedding_calls += 1
            estimated_tokens += estimate_tokens(question_text)

            fused_ids = retrieve_fused_chunk_ids(
                opensearch_client, name, question_text, query_vector
            )

            result: dict[str, Any] = {"id": entry["id"], "domain": entry["domain"]}
            if entry["expected_status"] == "answered":
                recall, reciprocal_rank = score_answerable_question(
                    fused_ids, entry["relevant_chunk_ids"]
                )
                result["recall_at_10"] = recall
                result["reciprocal_rank"] = reciprocal_rank
                domain = entry["domain"]
                per_domain.setdefault(domain, []).append(recall)
                per_domain_mrr.setdefault(domain, []).append(reciprocal_rank)

                source_chunk_id = entry.get("source_chunk_id")
                if source_chunk_id is not None:
                    # The source chunk's own text isn't available here without
                    # a lookup; the overlap check runs at draft time in Tasks
                    # 2-3, this just re-confirms it was recorded, not zero.
                    result["source_chunk_id"] = source_chunk_id
            else:
                result["note"] = "no positive judgement -- retrieved for transparency only"
                result["fused_top_10"] = fused_ids
            per_question_results.append(result)

        all_recalls = [r["recall_at_10"] for r in per_question_results if "recall_at_10" in r]
        all_mrrs = [r["reciprocal_rank"] for r in per_question_results if "reciprocal_rank" in r]
        aggregate = {
            "recall_at_10": sum(all_recalls) / len(all_recalls) if all_recalls else None,
            "mrr": sum(all_mrrs) / len(all_mrrs) if all_mrrs else None,
            "answerable_count": len(all_recalls),
        }
        per_domain_summary = {
            domain: {
                "recall_at_10": sum(recalls) / len(recalls),
                "mrr": sum(per_domain_mrr[domain]) / len(per_domain_mrr[domain]),
                "count": len(recalls),
            }
            for domain, recalls in per_domain.items()
        }

        print(
            json.dumps(
                {"aggregate": aggregate, "per_domain": per_domain_summary},
                ensure_ascii=False,
                indent=2,
            )
        )

        elapsed = time.perf_counter() - started
        usage = {
            "index": name,
            "status": "succeeded",
            "question_count": len(questions),
            "embedding_calls": embedding_calls,
            "estimated_tokens": estimated_tokens,
            "estimated_cost_usd": round(
                estimated_tokens / 1_000_000 * _COHERE_EMBED_V4_USD_PER_MILLION_TOKENS, 6
            ),
            "elapsed_seconds": round(elapsed, 2),
            "aggregate": aggregate,
        }
    except BaseException:
        elapsed = time.perf_counter() - started
        usage = {
            "index": name,
            "status": "failed",
            "question_count": len(questions),
            "embedding_calls": embedding_calls,
            "estimated_tokens": estimated_tokens,
            "estimated_cost_usd": round(
                estimated_tokens / 1_000_000 * _COHERE_EMBED_V4_USD_PER_MILLION_TOKENS, 6
            ),
            "elapsed_seconds": round(elapsed, 2),
            "aggregate": None,
        }
        _write_usage_log(usage)
        raise

    _write_usage_log(usage)

    print("\n>>> Lexical-overlap check (answerable questions):")
    lexical_overlap: list[dict[str, Any]] = []
    for entry in questions:
        if entry["expected_status"] != "answered":
            continue
        source_chunk_id = entry.get("source_chunk_id")
        # The overlap check needs the source chunk's actual text -- fetch it
        # by chunk_id via an exact-match `term` query on the `chunk_id`
        # keyword field, not a scored/relevance (BM25) search -- this is a
        # direct id lookup, returning the one document whose chunk_id
        # exactly equals source_chunk_id (or nothing, if it isn't indexed).
        lookup = opensearch_client.search(
            index=name,
            body={"size": 1, "query": {"term": {"chunk_id": source_chunk_id}}},
        )
        hits = lookup["hits"]["hits"]
        if not hits:
            print(f">>> {entry['id']}: source_chunk_id {source_chunk_id!r} not found in index")
            continue
        source_text = hits[0]["_source"]["text"]
        ratio = lexical_overlap_ratio(entry["question"], source_text)
        flag = " <-- HIGH OVERLAP, review" if ratio > 0.5 else ""
        print(f">>> {entry['id']}: overlap={ratio:.2f}{flag}")
        lexical_overlap.append({"id": entry["id"], "ratio": ratio, "high_overlap": ratio > 0.5})

    _write_evaluation_results(aggregate, per_domain_summary, per_question_results, lexical_overlap)


def _write_usage_log(usage: dict[str, Any]) -> None:
    """Write one usage-log dict to `reports/usage/`, timestamped."""

    usage_dir = pathlib.Path(__file__).resolve().parents[1] / "reports" / "usage"
    usage_dir.mkdir(parents=True, exist_ok=True)
    usage_path = usage_dir / f"{time.time_ns()}-evaluate-retrieval.json"
    usage_path.write_text(json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f">>> usage log written to {usage_path}")


def _write_evaluation_results(
    aggregate: dict[str, Any],
    per_domain: dict[str, Any],
    per_question: list[dict[str, Any]],
    lexical_overlap: list[dict[str, Any]],
) -> None:
    """Write the full per-run evaluation output to a committed results file.

    Unlike reports/usage/ (a timestamped log per run), this file is a
    single committed snapshot at reports/eval/retrieval_evaluation_results.json
    -- the raw per-question/per-domain/lexical-overlap material the eventual
    Retrieval evaluation report (SUBMISSION.md) draws its numbers from,
    which previously existed only as stdout output and was never persisted.
    """

    results = {
        "aggregate": aggregate,
        "per_domain": per_domain,
        "per_question": per_question,
        "lexical_overlap": lexical_overlap,
    }
    results_dir = pathlib.Path(__file__).resolve().parents[1] / "reports" / "eval"
    results_dir.mkdir(parents=True, exist_ok=True)
    results_path = results_dir / "retrieval_evaluation_results.json"
    results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f">>> evaluation results written to {results_path}")


if __name__ == "__main__":
    main()
