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
import os
import pathlib
import sys
import time

import boto3
from opensearchpy import helpers

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from bedrock_embedding import embed_batch
from opensearch_client import build_client

from legal_agent_assessment.chunking import chunk_record, chunk_statute_record
from legal_agent_assessment.dataset import DocumentKind, SourceRecord
from legal_agent_assessment.embedding import TokenBudget
from legal_agent_assessment.opensearch_index import chunk_to_document, index_name
from legal_agent_assessment.record_selection import select_records_for_indexing


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


def main() -> None:
    """Run the full index-population pipeline once."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rag-dir", type=pathlib.Path, required=True)
    parser.add_argument("--file", action="append", default=["judgements.jsonl", "statutes.jsonl"])
    parser.add_argument("--contributor", required=True)
    parser.add_argument("--dataset-version", required=True)
    args = parser.parse_args()

    started = time.perf_counter()
    records = load_records(args.rag_dir, args.file)
    indexable = select_records_for_indexing(records)

    chunks = []
    for record in indexable:
        if record.document_kind is DocumentKind.JUDGEMENT:
            chunks.extend(chunk_record(record, dataset_version=args.dataset_version))
        elif record.document_kind is DocumentKind.STATUTE:
            chunks.extend(chunk_statute_record(record, args.dataset_version))
    print(f">>> {len(indexable)} indexable records -> {len(chunks)} chunks")

    region = os.environ.get("BEDROCK_REGION", os.environ.get("AWS_REGION", "ap-northeast-2"))
    model_id = os.environ.get("EMBEDDING_MODEL_ID", "global.cohere.embed-v4:0")
    dimension = int(os.environ.get("EMBEDDING_DIMENSION", "1536"))
    bedrock_client = boto3.client("bedrock-runtime", region_name=region)
    budget = TokenBudget(limit_per_minute=300_000)

    texts = [chunk.text for chunk in chunks]
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

    name = index_name(args.contributor)
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

    total_chars = sum(len(text) for text in texts)
    usage = {
        "dataset_version": args.dataset_version,
        "index": name,
        "records_indexed": len(indexable),
        "chunks_indexed": success_count,
        "embedding_model": model_id,
        # estimate_tokens's docstring: conservative overestimate, not billing.
        "estimated_tokens": total_chars,
        "embed_seconds": round(embed_seconds, 1),
        "total_seconds": round(time.perf_counter() - started, 1),
        "bulk_errors": len(errors),
    }
    usage_dir = pathlib.Path("reports/usage")
    usage_dir.mkdir(parents=True, exist_ok=True)
    usage_path = usage_dir / f"{int(time.time())}-index-chunks.json"
    usage_path.write_text(json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f">>> usage log written to {usage_path}")


if __name__ == "__main__":
    main()
