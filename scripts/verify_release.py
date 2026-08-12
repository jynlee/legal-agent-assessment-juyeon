"""Check a built release against its manifest and report every finding.

Useful to MZO before delivery and to a contributor after it — the checks are
the same ones DATASET_SCHEMA.md describes.

    uv run python scripts/verify_release.py --rag-dir data/rag \
        --file judgements.jsonl --file guides.jsonl --manifest release-manifest.json

Exits non-zero when the release carries an error. Warnings describe the corpus
and are printed with counts, not treated as failures.
"""

import argparse
import pathlib
import sys

from legal_agent_assessment.chunking import ChunkType, chunk_record, chunk_statute_record
from legal_agent_assessment.dataset import DocumentKind, ReleaseManifest, SourceRecord
from legal_agent_assessment.dataset_validation import (
    content_hash,
    errors,
    select_index_inputs,
    summarize,
    validate_release,
)


def main() -> None:
    """Load the release, validate it, and summarize what it contains."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rag-dir", type=pathlib.Path, required=True)
    parser.add_argument("--file", action="append", required=True, dest="files")
    parser.add_argument("--manifest", type=pathlib.Path, required=True)
    args = parser.parse_args()

    records: list[SourceRecord] = []
    for name in args.files:
        path = args.rag_dir / name
        parsed = [
            SourceRecord.model_validate_json(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        records.extend(parsed)
        print(f"{name:20s} {len(parsed):5d} records")

    manifest = ReleaseManifest.model_validate_json(args.manifest.read_text(encoding="utf-8"))
    print(f"manifest {manifest.dataset_version} / {manifest.schema_version}")

    mismatched = [r.document_id for r in records if r.content_hash != content_hash(r.text)]
    print(f"\ncontentHash mismatches: {len(mismatched)}")

    findings = validate_release(records, manifest)
    blocking = errors(findings)
    print(f"findings: {len(findings)}  errors: {len(blocking)}")
    for code, count in summarize(findings).items():
        severity = next(f.severity for f in findings if f.code == code)
        print(f"  [{severity}] {code}: {count}")
    for finding in blocking[:20]:
        print(f"  ERROR {finding.code}: {finding.message}")

    indexable = select_index_inputs(records)
    baseline = [record for record in records if record.in_default_corpus]
    guides = [r for r in records if r.document_kind is DocumentKind.OFFICIAL_GUIDE]
    judgements = [r for r in records if r.document_kind is DocumentKind.JUDGEMENT]

    print(f"\nmay be indexed          : {len(indexable)}")
    print(f"default corpus          : {len(baseline)}")
    print(f"outside default corpus  : {len(records) - len(baseline)}")
    with_extraction = sum(1 for r in guides if r.provenance.extraction)
    print(f"guides with extraction  : {with_extraction}/{len(guides)}")
    print(
        "judgements with artifact: "
        f"{sum(1 for r in judgements if r.provenance.raw_artifact_path)}/{len(judgements)}"
    )

    statute_records = [r for r in records if r.document_kind is DocumentKind.STATUTE]
    all_chunks = [
        chunk
        for record in judgements
        for chunk in chunk_record(record, dataset_version=manifest.dataset_version)
    ] + [
        chunk
        for record in statute_records
        for chunk in chunk_statute_record(record, manifest.dataset_version)
    ]
    body_chunks = [c for c in all_chunks if c.chunk_type is ChunkType.BODY]
    summary_chunks = [c for c in all_chunks if c.chunk_type is not ChunkType.BODY]
    print(f"\nchunks produced          : {len(all_chunks)}")
    print(f"  judgement records chunked: {len(judgements)}")
    print(f"  statute records chunked  : {len(statute_records)}")
    print(f"  body                    : {len(body_chunks)}")
    print(f"  summary                 : {len(summary_chunks)}")

    if blocking or mismatched:
        raise SystemExit(f"release is not deliverable: {len(blocking) + len(mismatched)} error(s)")
    print("\nno blocking errors", file=sys.stderr)


if __name__ == "__main__":
    main()
