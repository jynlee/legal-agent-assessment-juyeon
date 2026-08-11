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

from legal_agent_assessment.dataset import DocumentKind, ReleaseManifest, SourceRecord
from legal_agent_assessment.dataset_validation import (
    content_hash,
    errors,
    select_index_inputs,
    summarize,
    validate_release,
)
from legal_agent_assessment.record_selection import default_corpus_sentinel_findings


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

    # Generic sentinel findings are warnings (they describe the corpus in
    # general); this project's policy is stricter for the records it actually
    # indexes. See reports/decisions/2026-08-10-record-selection-and-document-kind-policy.md.
    default_corpus_sentinels = default_corpus_sentinel_findings(records, findings)
    print(f"\nsentinels inside default corpus: {len(default_corpus_sentinels)}")
    for finding in default_corpus_sentinels[:20]:
        print(f"  BLOCKING {finding.code}: {finding.message}")

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

    if blocking or mismatched or default_corpus_sentinels:
        problems = len(blocking) + len(mismatched) + len(default_corpus_sentinels)
        raise SystemExit(f"release is not deliverable: {problems} error(s)")
    print("\nno blocking errors", file=sys.stderr)


if __name__ == "__main__":
    main()
