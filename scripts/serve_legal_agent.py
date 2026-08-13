"""Answer one question through the real hybrid-retrieval GeneralLegalAgent.

    uv run python scripts/serve_legal_agent.py --contributor jynlee \
        --question "약사법 제1조는 무엇을 규정하나요?"

Requires the index to already exist and be populated
(scripts/create_opensearch_index.py, scripts/index_chunks.py). Writes a
per-query usage log (embedding + generation token counts, latency) to
reports/usage/, self-instrumented per SUBMISSION.md's Work report
requirement -- shared billing cannot attribute this by contributor.
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
from legal_agent_assessment.contracts import GeneralLegalRequest, RuntimeVersions
from legal_agent_assessment.embedding import estimate_tokens
from legal_agent_assessment.opensearch_index import CHUNKING_VERSION, INDEX_VERSION, index_name


def write_usage_log(usage: dict[str, Any]) -> None:
    """Write one per-query usage-log dict to `reports/usage/`, timestamped."""

    usage_dir = pathlib.Path(__file__).resolve().parents[1] / "reports" / "usage"
    usage_dir.mkdir(parents=True, exist_ok=True)
    usage_path = usage_dir / f"{int(time.time())}-serve-legal-agent.json"
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
        normalization="norm-v1",
        chunking=CHUNKING_VERSION,
        index=INDEX_VERSION,
        embedding_model=embedding_model_id,
        generation_model=generation_model_id,
        prompt="prompt-v1",
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
    started = time.perf_counter()
    response = agent.answer_sync(request)
    elapsed_seconds = time.perf_counter() - started

    print(response.model_dump_json(indent=2))

    write_usage_log(
        {
            "index": name,
            "status": str(response.status),
            "question_estimated_tokens": estimate_tokens(args.question),
            "citation_count": len(response.citations),
            "retrieval_hit_count": len(response.retrieval_hits),
            "elapsed_seconds": round(elapsed_seconds, 2),
        }
    )


if __name__ == "__main__":
    main()
