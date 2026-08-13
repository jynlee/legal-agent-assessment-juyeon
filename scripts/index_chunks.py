"""Load default-corpus records, chunk them, embed them, and bulk-index them.

    uv run python scripts/index_chunks.py --rag-dir data --contributor jynlee \
        --dataset-version dataset-2026-08-11-v2.1

Requires the index to already exist (scripts/create_opensearch_index.py);
that is checked, along with the mapped embedding dimension, before the paid
embed step runs. Writes a per-run usage log (embedding calls, tokens,
latency) to reports/usage/, self-instrumented per SUBMISSION.md's Work
report requirement -- shared billing cannot attribute this by contributor.
"""

import argparse
import json
import os
import pathlib
import sys
import time
from typing import Any

import boto3
from opensearchpy import helpers

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from bedrock_embedding import embed_batch
from opensearch_client import build_client

from legal_agent_assessment.chunking import chunk_record, chunk_statute_record
from legal_agent_assessment.dataset import DocumentKind, SourceRecord
from legal_agent_assessment.embedding import EMBEDDING_DIMENSION, TokenBudget
from legal_agent_assessment.opensearch_index import chunk_to_document, index_name
from legal_agent_assessment.record_selection import select_records_for_indexing

# Cohere Embed v4 on Bedrock: $0.12 per 1,000,000 input tokens (AWS Bedrock
# published pricing, confirmed 2026-08-13).
COHERE_EMBED_V4_USD_PER_MILLION_TOKENS = 0.12

# The shared Bedrock quota is 300,000 tokens/minute (OPENSEARCH_ACCESS.md) and
# other contributors draw on the same pool. Pace at 80% of it: the real
# 7887-chunk run measured ~294,193 estimated tokens/minute, under 2% headroom,
# and `estimate_tokens` is an approximation that is not independently verified
# for Korean subword tokenization (see its docstring). 20% margin absorbs both.
TOKEN_BUDGET_PER_MINUTE = 240_000


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


def assert_index_ready(client: Any, name: str, *, dimension: int) -> None:
    """Fail before the paid embed step if the target index is missing or mismatched.

    The cluster runs with `auto_create_index: true`, so bulk-indexing into a
    missing index silently creates one from OpenSearch's dynamic mapping --
    `embedding` becomes a plain float array instead of a `knn_vector`, and the
    run still reports success. Checking here, rather than after embedding,
    means a forgotten `create_opensearch_index.py` costs nothing.
    """

    if not client.indices.exists(index=name):
        raise RuntimeError(
            f"index {name!r} does not exist -- create it first with\n"
            f"    uv run python scripts/create_opensearch_index.py "
            f"--contributor <id> --replicas <n>\n"
            "Indexing into a missing index would auto-create it with a dynamic "
            "mapping (embedding as a plain float array, not knn_vector)."
        )

    # `indices.get_mapping` returns {"<index>": {"mappings": {"properties": ...}}},
    # keyed by the resolved concrete index name -- confirmed read-only against
    # the real local OpenSearch 3.5 cluster.
    mappings = client.indices.get_mapping(index=name)
    properties = mappings[name]["mappings"]["properties"]
    live_dimension = properties.get("embedding", {}).get("dimension")
    if live_dimension != dimension:
        raise RuntimeError(
            f"index {name!r} maps embedding with dimension {live_dimension!r}, but this "
            f"run would request {dimension}-dimensional vectors. Recreate the index "
            "from the current mapping (scripts/create_opensearch_index.py) instead of "
            "paying for an embed run that cannot be indexed."
        )


def build_usage_dict(
    *,
    args: argparse.Namespace,
    name: str,
    model_id: str,
    records_indexed: int,
    chunks_attempted: int,
    chunks_indexed: int,
    embedding_calls: int,
    estimated_tokens: int,
    embed_seconds: float | None,
    total_seconds: float,
    status: str,
) -> dict[str, Any]:
    """Build one usage-log dict, so the success and failure paths cannot drift.

    `embedding_calls`/`estimated_tokens` come from the running totals the embed
    loop reports, so they are accurate even when embedding died partway
    through and only some batches were actually paid for.
    """

    return {
        "dataset_version": args.dataset_version,
        "index": name,
        "records_indexed": records_indexed,
        "chunks_attempted": chunks_attempted,
        "chunks_indexed": chunks_indexed,
        "embedding_model": model_id,
        "embedding_calls": embedding_calls,
        # estimate_tokens's docstring: an approximation for pacing, not billing.
        "estimated_tokens": estimated_tokens,
        # Derived from that same approximation. No official per-call cost is
        # retrievable from shared billing, which is the same reason this script
        # self-instruments (SUBMISSION.md's Work report requirement).
        "estimated_cost_usd": round(
            estimated_tokens / 1_000_000 * COHERE_EMBED_V4_USD_PER_MILLION_TOKENS, 4
        ),
        "embed_seconds": None if embed_seconds is None else round(embed_seconds, 1),
        "total_seconds": round(total_seconds, 1),
        "status": status,
    }


def write_usage_log(usage: dict[str, Any]) -> None:
    """Write one usage-log dict to `reports/usage/`, timestamped."""

    # Anchored to this file's location, not the caller's CWD: the log belongs to
    # the repo regardless of where the script was invoked from.
    usage_dir = pathlib.Path(__file__).resolve().parents[1] / "reports" / "usage"
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
    # A fixed project constraint (ASSIGNMENT.md: ingest and query share one
    # dimension), not a contributor knob. Read from the one constant the index
    # mapping is also built from, so the two can never drift apart.
    dimension = EMBEDDING_DIMENSION
    name = index_name(args.contributor)
    texts = [chunk.text for chunk in chunks]

    # Built and checked *before* the paid embed step, so a missing or
    # mismatched index costs nothing.
    opensearch_client = build_client(
        url=os.environ.get("OPENSEARCH_URL", "http://localhost:9200"),
        profile=os.environ["AWS_PROFILE"],
        region=os.environ.get("AWS_REGION", "ap-northeast-2"),
    )
    assert_index_ready(opensearch_client, name, dimension=dimension)
    print(f">>> index {name} exists with a matching embedding dimension ({dimension})")

    # Running totals, updated after every batch that actually returned, so a
    # failure partway through embedding still reports the quota really spent.
    embedding_calls = 0
    estimated_tokens = 0
    embed_seconds: float | None = None
    success_count = 0

    def record_batch(batch_tokens: int, calls_so_far: int) -> None:
        nonlocal embedding_calls, estimated_tokens
        embedding_calls = calls_so_far
        estimated_tokens += batch_tokens

    def usage_now(status: str) -> dict[str, Any]:
        """Snapshot the run's usage as of right now, for either outcome."""

        return build_usage_dict(
            args=args,
            name=name,
            model_id=model_id,
            records_indexed=len(indexable),
            chunks_attempted=len(chunks),
            chunks_indexed=success_count,
            embedding_calls=embedding_calls,
            estimated_tokens=estimated_tokens,
            embed_seconds=embed_seconds,
            total_seconds=time.perf_counter() - started,
            status=status,
        )

    try:
        bedrock_client = boto3.client("bedrock-runtime", region_name=region)
        budget = TokenBudget(limit_per_minute=TOKEN_BUDGET_PER_MINUTE)

        embed_started = time.perf_counter()
        vectors = embed_batch(
            bedrock_client,
            texts,
            model_id=model_id,
            input_type="search_document",
            dimension=dimension,
            budget=budget,
            on_batch_complete=record_batch,
        )
        embed_seconds = time.perf_counter() - embed_started
        print(f">>> embedded {len(vectors)} chunks in {embed_seconds:.1f}s")

        actions = (
            {
                "_index": name,
                "_id": chunk.chunk_id,
                "_source": chunk_to_document(chunk, vector),
            }
            for chunk, vector in zip(chunks, vectors, strict=True)
        )
        # raise_on_error stays at its default True, so any rejected document
        # raises BulkIndexError (handled below) rather than being returned in
        # the second element -- which is therefore always empty and not worth
        # reporting. Failing loud beats a partially populated index.
        success_count, _ = helpers.bulk(opensearch_client, actions, index=name)
        print(f">>> indexed {success_count} documents into {name}")
    except BaseException:
        # Real quota may already be spent even though this run is about to
        # fail -- record what was actually spent rather than losing it, then
        # let the failure propagate. BaseException, not Exception, so a Ctrl-C
        # partway through a long embed run still leaves the record behind; the
        # bare `raise` keeps the normal exit semantics for both.
        write_usage_log(usage_now("failed"))
        raise

    write_usage_log(usage_now("succeeded"))


if __name__ == "__main__":
    main()
