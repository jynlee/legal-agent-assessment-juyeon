"""Full generation-pipeline evaluation: refusal accuracy, citation
integrity, and grounding, against the frozen 50-question test set.

    OPENSEARCH_URL=http://localhost:9201 \
    uv run python scripts/evaluate_generation.py --contributor jynlee

Runs every question in reports/eval/retrieval_test_set.json through the
real LegalAgent.answer_sync (retrieval + generation) once each -- the same
method scripts/serve_legal_agent.py uses for one real question, run here
over all 50. For every response that comes back "answered", a second real
Bedrock call judges whether the answer is actually supported by its own
cited excerpts (legal_agent_assessment.judge, same fixed Sonnet 4.6
model). Implements reports/decisions/2026-08-14-generation-evaluation-design.md
in full.

This makes ~50 real generation calls plus ~40 real judge calls -- a real,
budgeted cost (estimated $1.5-2 for a full run, per the design doc's own
estimate from one real demo call). Writes a per-run usage log to
reports/usage/ and a committed results snapshot to
reports/eval/generation_evaluation_results.json.
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

from legal_agent_assessment.agent import LegalAgent
from legal_agent_assessment.chunking import NORMALIZATION_VERSION
from legal_agent_assessment.contracts import GeneralLegalRequest, RuntimeVersions
from legal_agent_assessment.generation import PROMPT_VERSION
from legal_agent_assessment.judge import (
    JUDGE_PROMPT_VERSION,
    build_judge_prompt,
    parse_judge_response,
)
from legal_agent_assessment.opensearch_index import CHUNKING_VERSION, INDEX_VERSION, index_name

# Same rates as scripts/serve_legal_agent.py -- restated here rather than
# imported, matching scripts/evaluate_retrieval.py's own precedent of
# duplicating a small pricing constant instead of importing another
# script's whole module graph for one float.
COHERE_EMBED_V4_USD_PER_MILLION_TOKENS = 0.12
CLAUDE_SONNET_INPUT_USD_PER_MILLION_TOKENS = 3.00
CLAUDE_SONNET_OUTPUT_USD_PER_MILLION_TOKENS = 15.00


def estimated_cost_usd(
    *, embed_estimated_tokens: int, generation_input_tokens: int, generation_output_tokens: int
) -> float:
    """Estimated USD: real generation tokens (answer + judge calls), estimated embed tokens."""

    return round(
        embed_estimated_tokens / 1_000_000 * COHERE_EMBED_V4_USD_PER_MILLION_TOKENS
        + generation_input_tokens / 1_000_000 * CLAUDE_SONNET_INPUT_USD_PER_MILLION_TOKENS
        + generation_output_tokens / 1_000_000 * CLAUDE_SONNET_OUTPUT_USD_PER_MILLION_TOKENS,
        6,
    )


def load_test_set(path: pathlib.Path) -> list[dict[str, Any]]:
    """Read the 50-question test set."""

    data: list[dict[str, Any]] = json.loads(path.read_text(encoding="utf-8"))
    assert len(data) == 50, f"expected 50 test-set entries, got {len(data)}"
    return data


def call_judge(
    bedrock_client: Any, model_id: str, question: str, answer: str, citations: Any
) -> tuple[Any, int, int, str | None]:
    """Call the judge once; return (ParsedVerdict | None, input_tokens, output_tokens, parse_error).

    Token usage is read from the real Bedrock response and returned
    unconditionally, even when the judge's text fails to parse as the
    required JSON verdict -- real money was spent on the call either way,
    and losing that accounting on a parse failure would silently
    undercount cost. A parse failure (e.g. the judge responds with prose
    reasoning instead of the requested bare JSON object) returns
    `(None, input_tokens, output_tokens, str(error))` instead of raising,
    so one malformed judge response records as a `judge_parse_error` for
    that question rather than crashing the entire 50-question run --
    real, real-cost failure mode observed on 2026-08-14.
    """

    prompt = build_judge_prompt(question, answer, citations)
    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 512,
        # Assistant-turn prefill (seeding the response with "{") was tried
        # first and rejected outright by this model/endpoint: "This model
        # does not support assistant message prefill. The conversation
        # must end with a user message." (real ValidationException,
        # 2026-08-14). A top-level `system` prompt is the next-strongest
        # lever available -- system instructions carry more weight than
        # the same text embedded in the user turn, without needing prefill.
        "system": (
            "You only ever output a single raw JSON object as your entire "
            "response. Never include prose, analysis, markdown formatting, "
            "or any text before or after the JSON object."
        ),
        "messages": [{"role": "user", "content": prompt}],
    }
    response = bedrock_client.invoke_model(modelId=model_id, body=json.dumps(request_body))
    body = json.loads(response["body"].read())
    text: str = body["content"][0]["text"]
    usage = body.get("usage") or {}
    input_tokens = int(usage.get("input_tokens", 0))
    output_tokens = int(usage.get("output_tokens", 0))

    try:
        verdict = parse_judge_response(text)
    except ValueError as error:
        return None, input_tokens, output_tokens, str(error)

    return verdict, input_tokens, output_tokens, None


def main() -> None:
    """Run the full generation evaluation once, over all 50 questions."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contributor", required=True)
    args = parser.parse_args()

    region = os.environ.get("AWS_REGION", "ap-northeast-2")
    bedrock_region = os.environ.get("BEDROCK_REGION", region)
    embedding_model_id = os.environ.get("EMBEDDING_MODEL_ID", "global.cohere.embed-v4:0")
    generation_model_id = os.environ["BEDROCK_MODEL_ID_SONNET"]
    name = index_name(args.contributor)

    opensearch_client = build_client(
        url=os.environ.get("OPENSEARCH_URL", "http://localhost:9200"),
        profile=os.environ["AWS_PROFILE"],
        region=region,
    )
    bedrock_client = boto3.client("bedrock-runtime", region_name=bedrock_region)

    versions = RuntimeVersions(
        dataset=os.environ.get("DATASET_VERSION", "dataset-2026-08-11-v2.1"),
        normalization=NORMALIZATION_VERSION,
        chunking=CHUNKING_VERSION,
        index=INDEX_VERSION,
        embedding_model=embedding_model_id,
        generation_model=generation_model_id,
        prompt=PROMPT_VERSION,
    )
    agent = LegalAgent(
        opensearch_client=opensearch_client,
        bedrock_client=bedrock_client,
        index_name=name,
        embedding_model_id=embedding_model_id,
        generation_model_id=generation_model_id,
        versions=versions,
    )

    test_set_path = (
        pathlib.Path(__file__).resolve().parents[1] / "reports" / "eval" / "retrieval_test_set.json"
    )
    questions = load_test_set(test_set_path)

    started = time.perf_counter()
    embed_estimated_tokens_total = 0
    generation_input_tokens_total = 0
    generation_output_tokens_total = 0
    per_question_results: list[dict[str, Any]] = []
    limitations_fired_count = 0

    try:
        for entry in questions:
            question_start = time.perf_counter()
            question_text = entry["question"]
            expected_status = entry["expected_status"]

            embed_tokens_this_call = 0
            gen_input_this_call = 0
            gen_output_this_call = 0

            def record_usage(step: str, values: dict[str, Any]) -> None:
                nonlocal embed_tokens_this_call, gen_input_this_call, gen_output_this_call
                if step == "embed":
                    embed_tokens_this_call += int(values.get("estimated_tokens", 0))
                elif step == "generate":
                    gen_input_this_call += int(values.get("input_tokens", 0))
                    gen_output_this_call += int(values.get("output_tokens", 0))

            request = GeneralLegalRequest(
                request_id=f"geneval-{entry['id']}", question=question_text
            )
            response = agent.answer_sync(request, on_usage=record_usage)

            result: dict[str, Any] = {
                "id": entry["id"],
                "domain": entry["domain"],
                "status": str(response.status),
                "expected_status": expected_status,
                "status_matches_expected": str(response.status) == expected_status,
                "citation_count": len(response.citations),
                "limitations_count": len(response.limitations),
                "retrieval_hit_count": len(response.retrieval_hits),
            }
            if response.limitations:
                limitations_fired_count += 1

            if response.status == "answered" and response.answer is not None:
                # Persisted so a future judge-only re-run (a different
                # prompt, or re-judging just the parse-error subset) never
                # needs to pay for regeneration again -- regeneration is
                # also not exactly reproducible (generation is stochastic),
                # so re-judging the same saved answer is the only way to
                # cleanly isolate "did the judge get better" from "did the
                # answer change."
                result["answer"] = response.answer
                result["citations"] = [
                    {
                        "chunk_id": citation.chunk_id,
                        "title": citation.title,
                        "excerpt": citation.excerpt,
                    }
                    for citation in response.citations
                ]

                verdict, judge_input_tokens, judge_output_tokens, judge_error = call_judge(
                    bedrock_client,
                    generation_model_id,
                    question_text,
                    response.answer,
                    response.citations,
                )
                gen_input_this_call += judge_input_tokens
                gen_output_this_call += judge_output_tokens
                if verdict is not None:
                    result["grounding"] = verdict.grounding
                    result["grounding_justification"] = verdict.justification
                else:
                    result["grounding"] = "judge_parse_error"
                    result["grounding_justification"] = judge_error

            result["latency_ms"] = round((time.perf_counter() - question_start) * 1000, 1)
            embed_estimated_tokens_total += embed_tokens_this_call
            generation_input_tokens_total += gen_input_this_call
            generation_output_tokens_total += gen_output_this_call
            per_question_results.append(result)

        answerable = [r for r in per_question_results if r["expected_status"] == "answered"]
        insufficient = [
            r for r in per_question_results if r["expected_status"] == "insufficient_evidence"
        ]
        out_of_scope = [r for r in per_question_results if r["expected_status"] == "out_of_scope"]
        graded = [r for r in per_question_results if "grounding" in r]

        aggregate = {
            "question_count": len(per_question_results),
            "answered_status_match_rate": (
                sum(1 for r in answerable if r["status_matches_expected"]) / len(answerable)
                if answerable
                else None
            ),
            "insufficient_evidence_refusal_accuracy": (
                sum(1 for r in insufficient if r["status_matches_expected"]) / len(insufficient)
                if insufficient
                else None
            ),
            "out_of_scope_refusal_accuracy": (
                sum(1 for r in out_of_scope if r["status_matches_expected"]) / len(out_of_scope)
                if out_of_scope
                else None
            ),
            "insufficient_evidence_misclassified_as_out_of_scope": sum(
                1 for r in insufficient if r["status"] == "out_of_scope"
            ),
            "limitations_fired_count": limitations_fired_count,
            "graded_answer_count": len(graded),
            "grounded_count": sum(1 for r in graded if r["grounding"] == "grounded"),
            "partially_grounded_count": sum(
                1 for r in graded if r["grounding"] == "partially_grounded"
            ),
            "unsupported_count": sum(1 for r in graded if r["grounding"] == "unsupported"),
            "judge_parse_error_count": sum(
                1 for r in graded if r["grounding"] == "judge_parse_error"
            ),
        }

        print(json.dumps(aggregate, ensure_ascii=False, indent=2))

        elapsed = time.perf_counter() - started
        usage = {
            "index": name,
            "status": "succeeded",
            "question_count": len(questions),
            "embed_estimated_tokens": embed_estimated_tokens_total,
            "generation_input_tokens": generation_input_tokens_total,
            "generation_output_tokens": generation_output_tokens_total,
            "estimated_cost_usd": estimated_cost_usd(
                embed_estimated_tokens=embed_estimated_tokens_total,
                generation_input_tokens=generation_input_tokens_total,
                generation_output_tokens=generation_output_tokens_total,
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
            "embed_estimated_tokens": embed_estimated_tokens_total,
            "generation_input_tokens": generation_input_tokens_total,
            "generation_output_tokens": generation_output_tokens_total,
            "estimated_cost_usd": estimated_cost_usd(
                embed_estimated_tokens=embed_estimated_tokens_total,
                generation_input_tokens=generation_input_tokens_total,
                generation_output_tokens=generation_output_tokens_total,
            ),
            "elapsed_seconds": round(elapsed, 2),
            "aggregate": None,
        }
        _write_usage_log(usage)
        raise

    _write_usage_log(usage)
    _write_results(aggregate, per_question_results)


def _write_usage_log(usage: dict[str, Any]) -> None:
    """Write one usage-log dict to `reports/usage/`, timestamped."""

    usage_dir = pathlib.Path(__file__).resolve().parents[1] / "reports" / "usage"
    usage_dir.mkdir(parents=True, exist_ok=True)
    usage_path = usage_dir / f"{time.time_ns()}-evaluate-generation.json"
    usage_path.write_text(json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f">>> usage log written to {usage_path}")


def _write_results(aggregate: dict[str, Any], per_question: list[dict[str, Any]]) -> None:
    """Write the full per-run evaluation output to a committed results file."""

    results = {
        "aggregate": aggregate,
        "per_question": per_question,
        "judge_prompt_version": JUDGE_PROMPT_VERSION,
    }
    results_dir = pathlib.Path(__file__).resolve().parents[1] / "reports" / "eval"
    results_dir.mkdir(parents=True, exist_ok=True)
    results_path = results_dir / "generation_evaluation_results.json"
    results_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f">>> evaluation results written to {results_path}")


if __name__ == "__main__":
    main()
