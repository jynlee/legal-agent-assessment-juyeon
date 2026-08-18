"""Answer one question through the real hybrid-retrieval GeneralLegalAgent.

    uv run python scripts/serve_legal_agent.py --contributor jynlee \
        --question "약사법 제1조는 무엇을 규정하나요?"

Requires the index to already exist and be populated
(scripts/create_opensearch_index.py, scripts/index_chunks.py). Writes a
per-query usage log (embedding (estimated) + generation (real) token counts,
latency, and estimated cost) to reports/usage/, self-instrumented per
SUBMISSION.md's Work report requirement -- shared billing cannot attribute
this by contributor. A run that fails partway through still leaves the
usage record for whatever was already paid for.
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
from legal_agent_assessment.embedding import estimate_tokens
from legal_agent_assessment.generation import PROMPT_VERSION
from legal_agent_assessment.opensearch_index import CHUNKING_VERSION, INDEX_VERSION, index_name
from legal_agent_assessment.rerank import RERANK_PROMPT_VERSION

# Cohere Embed v4 on Bedrock: $0.12 per 1,000,000 input tokens (AWS Bedrock
# published pricing, confirmed 2026-08-13). Restated here rather than imported
# from scripts/index_chunks.py, which would pull that script's whole
# indexing-only import graph in for one float.
COHERE_EMBED_V4_USD_PER_MILLION_TOKENS = 0.12

# Claude Sonnet on Bedrock, current tier: $3.00 / $15.00 per 1,000,000 input /
# output tokens (public Anthropic and AWS Bedrock pricing pages for Sonnet
# 4.x, read 2026-08-13). NOT independently reconfirmed against the exact
# `claude-sonnet-4-6` model id used here -- treat the derived
# `estimated_cost_usd` as an estimate for contributor attribution, not a bill.
CLAUDE_SONNET_INPUT_USD_PER_MILLION_TOKENS = 3.00
CLAUDE_SONNET_OUTPUT_USD_PER_MILLION_TOKENS = 15.00


def estimated_cost_usd(
    *, embed_estimated_tokens: int, generation_input_tokens: int, generation_output_tokens: int
) -> float:
    """Estimated USD for one query: real generation tokens, estimated embed tokens."""

    return round(
        embed_estimated_tokens / 1_000_000 * COHERE_EMBED_V4_USD_PER_MILLION_TOKENS
        + generation_input_tokens / 1_000_000 * CLAUDE_SONNET_INPUT_USD_PER_MILLION_TOKENS
        + generation_output_tokens / 1_000_000 * CLAUDE_SONNET_OUTPUT_USD_PER_MILLION_TOKENS,
        6,
    )


def write_usage_log(usage: dict[str, Any]) -> None:
    """Write one per-query usage-log dict to `reports/usage/`, timestamped."""

    usage_dir = pathlib.Path(__file__).resolve().parents[1] / "reports" / "usage"
    usage_dir.mkdir(parents=True, exist_ok=True)
    # Nanosecond resolution, not whole seconds: two queries run back to back
    # in the same second would otherwise overwrite each other's record.
    usage_path = usage_dir / f"{time.time_ns()}-serve-legal-agent.json"
    usage_path.write_text(json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f">>> usage log written to {usage_path}")


def main() -> None:
    """Answer one question against the real index and Bedrock endpoints."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--contributor", required=True)
    parser.add_argument("--question", required=True)
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
        # legal_agent_assessment.chunking's constant -- the one stamped onto
        # every indexed document by `chunk_to_document`. Deliberately NOT
        # legal_agent_assessment.cleaning.NORMALIZATION_VERSION, a different
        # constant with the same name and a different value.
        normalization=NORMALIZATION_VERSION,
        chunking=CHUNKING_VERSION,
        index=INDEX_VERSION,
        embedding_model=embedding_model_id,
        generation_model=generation_model_id,
        prompt=PROMPT_VERSION,
        rerank=RERANK_PROMPT_VERSION,
    )
    agent = LegalAgent(
        opensearch_client=opensearch_client,
        bedrock_client=bedrock_client,
        index_name=name,
        embedding_model_id=embedding_model_id,
        generation_model_id=generation_model_id,
        versions=versions,
    )

    request = GeneralLegalRequest(request_id=f"cli-{int(time.time())}", question=args.question)

    # Running totals, updated by the agent after every paid Bedrock call that
    # actually returned, so a failure partway through still reports the spend
    # really incurred (same pattern as scripts/index_chunks.py).
    embed_estimated_tokens = 0
    generation_input_tokens = 0
    generation_output_tokens = 0
    citation_count = 0
    retrieval_hit_count = 0

    def record_usage(step: str, values: dict[str, Any]) -> None:
        nonlocal embed_estimated_tokens, generation_input_tokens, generation_output_tokens
        if step == "embed":
            embed_estimated_tokens += int(values.get("estimated_tokens", 0))
        elif step == "generate":
            generation_input_tokens += int(values.get("input_tokens", 0))
            generation_output_tokens += int(values.get("output_tokens", 0))

    def usage_now(status: str, elapsed_seconds: float, answer_status: str | None) -> dict[str, Any]:
        """Snapshot this query's usage as of right now, for either outcome."""

        return {
            "index": name,
            "status": status,
            "answer_status": answer_status,
            "question_estimated_tokens": estimate_tokens(args.question),
            # `estimate_tokens`'s docstring: an approximation, not billing --
            # no real Cohere token count comes back from the embed endpoint.
            "embed_estimated_tokens": embed_estimated_tokens,
            # Real counts, reported by the Bedrock Anthropic Messages API.
            "generation_input_tokens": generation_input_tokens,
            "generation_output_tokens": generation_output_tokens,
            "estimated_cost_usd": estimated_cost_usd(
                embed_estimated_tokens=embed_estimated_tokens,
                generation_input_tokens=generation_input_tokens,
                generation_output_tokens=generation_output_tokens,
            ),
            "citation_count": citation_count,
            "retrieval_hit_count": retrieval_hit_count,
            "elapsed_seconds": round(elapsed_seconds, 2),
        }

    started = time.perf_counter()
    try:
        response = agent.answer_sync(request, on_usage=record_usage)
    except BaseException:
        # Bedrock calls may already have been paid for even though this run is
        # about to fail -- record what was actually spent rather than losing
        # it, then let the failure propagate. BaseException, not Exception, so
        # a Ctrl-C mid-call still leaves the record behind.
        write_usage_log(usage_now("failed", time.perf_counter() - started, None))
        raise
    elapsed_seconds = time.perf_counter() - started

    citation_count = len(response.citations)
    retrieval_hit_count = len(response.retrieval_hits)

    print(response.model_dump_json(indent=2))

    write_usage_log(usage_now("succeeded", elapsed_seconds, str(response.status)))


if __name__ == "__main__":
    main()
