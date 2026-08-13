"""Load default-corpus records, chunk them, embed them, and bulk-index them.

    uv run python scripts/index_chunks.py --rag-dir data --contributor jynlee \
        --dataset-version dataset-2026-08-11-v2.1

Requires the index to already exist (scripts/create_opensearch_index.py).
Writes a per-run usage log (embedding calls, tokens, latency) to
reports/usage/, self-instrumented per SUBMISSION.md's Work report
requirement -- shared billing cannot attribute this by contributor.
"""

import argparse
import json
import math
import os
import pathlib
import sys
import time

import boto3
from opensearchpy import helpers

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from bedrock_embedding import BATCH_SIZE, embed_batch
from opensearch_client import build_client

from legal_agent_assessment.chunking import chunk_record, chunk_statute_record
from legal_agent_assessment.dataset import DocumentKind, SourceRecord
from legal_agent_assessment.embedding import TokenBudget, estimate_tokens
from legal_agent_assessment.opensearch_index import chunk_to_document, index_name
from legal_agent_assessment.record_selection import select_records_for_indexing

# Cohere Embed v4 on Bedrock: $0.12 per 1,000,000 input tokens (AWS Bedrock
# published pricing, confirmed 2026-08-13).
COHERE_EMBED_V4_USD_PER_MILLION_TOKENS = 0.12


def load_records(rag_dir: pathlib.Path, files: list[str]) -> list[SourceRecord]:
    """Read every record from the named JSONL files under `rag_dir`."""

    records: list[SourceRecord] = []
    for name in files:
        path = rag_dir / name
        records.extend(
            SourceRecord.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return records


def write_usage_log(usage: dict) -> None:
    """Write one usage-log dict to `reports/usage/`, timestamped."""

    usage_dir = pathlib.Path("reports/usage")
    usage_dir.mkdir(parents=True, exist_ok=True)
    usage_path = usage_dir / f"{int(time.time())}-index-chunks.json"
    usage_path.write_text(json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f">>> usage log written to {usage_path}")


def main() -> None:
    """Run the full index-population pipeline once."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rag-dir", type=pathlib.Path, required=True)
    parser.add_argument("--file", action="append", default=None)
    parser.add_argument("--contributor", required=True)
    parser.add_argument("--dataset-version", required=True)
    args = parser.parse_args()
    files = args.file or ["judgements.jsonl", "statutes.jsonl"]

    started = time.perf_counter()
    records = load_records(args.rag_dir, files)
    indexable = select_records_for_indexing(records)

    chunks = []
    for record in indexable:
        if record.document_kind is DocumentKind.JUDGEMENT:
            chunks.extend(chunk_record(record, dataset_version=args.dataset_version))
        elif record.document_kind is DocumentKind.STATUTE:
            chunks.extend(chunk_statute_record(record, args.dataset_version))
        else:
            raise ValueError(f"unhandled document kind: {record.document_kind!r}")
    print(f">>> {len(indexable)} indexable records -> {len(chunks)} chunks")

    region = os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "ap-northeast-2"))
    model_id = os.environ.get("EMBEDDING_MODEL_ID", "global.cohere.embed-v4:0")
    dimension = int(os.environ.get("EMBEDDING_DIMENSION", "1536"))
    name = index_name(args.contributor)
    texts = [chunk.text for chunk in chunks]

    # Populated once each step actually completes, so a failure partway
    # through still leaves us able to report what quota was really spent.
    vectors = None
    embed_seconds = None
    success_count = 0
    errors = []

    try:
        bedrock_client = boto3.client("bedrock-runtime", region_name=region)
        budget = TokenBudget(limit_per_minute=300_000)

        embed_started = time.perf_counter()
        vectors = embed_batch(
            bedrock_client,
            texts,
            model_id=model_id,
            input_type="search_document",
            dimension=dimension,
            budget=budget,
        )
        embed_seconds = time.perf_counter() - embed_started
        print(f">>> embedded {len(vectors)} chunks in {embed_seconds:.1f}s")

        opensearch_client = build_client(
            url=os.environ.get("OPENSEARCH_URL", "http://localhost:9200"),
            profile=os.environ["AWS_PROFILE"],
            region=os.environ.get("AWS_REGION", "ap-northeast-2"),
        )
        actions = (
            {
                "_index": name,
                "_id": chunk.chunk_id,
                "_source": chunk_to_document(chunk, vector),
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        )
        success_count, errors = helpers.bulk(opensearch_client, actions, index=name)
        print(f">>> indexed {success_count} documents into {name}")
        if errors:
            print(f">>> {len(errors)} bulk errors (see usage log)")
    except Exception:
        # Real quota (embedding calls, tokens) may already be spent even
        # though this run is about to fail -- record whatever is known
        # rather than losing that record, then let the failure propagate.
        usage = {
            "dataset_version": args.dataset_version,
            "index": name,
            "records_indexed": len(indexable),
            "chunks_attempted": len(chunks),
            "embedding_model": model_id,
            "total_seconds": round(time.perf_counter() - started, 1),
            "status": "failed",
        }
        if vectors is not None:
            # Embedding finished (so the failure was in bulk indexing) --
            # the tokens/calls spent on the embed step are fully known.
            embedding_calls = math.ceil(len(texts) / BATCH_SIZE)
            estimated_tokens = sum(estimate_tokens(text) for text in texts)
            usage["embedding_calls"] = embedding_calls
            usage["estimated_tokens"] = estimated_tokens
            usage["estimated_cost_usd"] = round(
                estimated_tokens / 1_000_000 * COHERE_EMBED_V4_USD_PER_MILLION_TOKENS, 4
            )
            usage["embed_seconds"] = round(embed_seconds, 1)
        write_usage_log(usage)
        raise

    embedding_calls = math.ceil(len(texts) / BATCH_SIZE)
    estimated_tokens = sum(estimate_tokens(text) for text in texts)
    usage = {
        "dataset_version": args.dataset_version,
        "index": name,
        "records_indexed": len(indexable),
        "chunks_indexed": success_count,
        "embedding_model": model_id,
        "embedding_calls": embedding_calls,
        # estimate_tokens's docstring: conservative overestimate, not billing.
        "estimated_tokens": estimated_tokens,
        # Estimate derived from estimate_tokens's already-conservative
        # overestimate -- real cost is likely lower, since Cohere's real
        # subword tokenization produces fewer tokens than the 1-char-per-token
        # estimate. No official per-call cost is retrievable from shared
        # billing, which is the same reason this script self-instruments.
        "estimated_cost_usd": round(
            estimated_tokens / 1_000_000 * COHERE_EMBED_V4_USD_PER_MILLION_TOKENS, 4
        ),
        "embed_seconds": round(embed_seconds, 1),
        "total_seconds": round(time.perf_counter() - started, 1),
        "bulk_errors": len(errors),
    }
    write_usage_log(usage)


if __name__ == "__main__":
    main()
