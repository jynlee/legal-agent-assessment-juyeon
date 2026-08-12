"""Build the reproducible external dataset-v2 delivery archive."""

from __future__ import annotations

import argparse
import collections
import datetime as dt
import gzip
import hashlib
import json
import shutil
import tarfile
import zipfile
from pathlib import Path

from build_release_manifest import (
    V2_DISPOSITIONS,
    V2_KNOWN_GAPS,
    V2_LICENCES,
    describe_artifacts,
    describe_metadata,
    read,
)

from legal_agent_assessment.dataset import (
    CoverageEntry,
    ReleaseManifest,
    SourceRecord,
)

OPTIONAL_METADATA_FILES = ("llm-review.jsonl", "llm-review-calls.jsonl")


def sha256(path: Path) -> str:
    """Hex SHA-256 of one delivery file."""

    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def coverage(values: collections.Counter[str]) -> tuple[CoverageEntry, ...]:
    return tuple(
        CoverageEntry(key=key, record_count=count) for key, count in sorted(values.items())
    )


def deterministic_tar(source: Path, output: Path, timestamp: int) -> int:
    """Archive every raw artifact with stable metadata and entry order."""

    files = sorted(path for path in source.rglob("*") if path.is_file())
    with (
        output.open("wb") as raw_output,
        gzip.GzipFile(filename="", mode="wb", fileobj=raw_output, mtime=timestamp) as compressed,
        tarfile.open(fileobj=compressed, mode="w") as archive,
    ):
        for path in files:
            relative = path.relative_to(source.parent).as_posix()
            info = archive.gettarinfo(str(path), arcname=relative)
            info.mtime = timestamp
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            with path.open("rb") as handle:
                archive.addfile(info, handle)
    return len(files)


def deterministic_zip(
    source: Path, output: Path, frozen_at: dt.datetime, names: tuple[str, ...]
) -> None:
    """Write one stable ZIP from the fixed delivery file list."""

    stamp = frozen_at.astimezone(dt.UTC)
    zip_time = (stamp.year, stamp.month, stamp.day, stamp.hour, stamp.minute, stamp.second)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name in names:
            payload = (source / name).read_bytes()
            info = zipfile.ZipInfo(name, date_time=zip_time)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16
            archive.writestr(info, payload, compresslevel=9)


def delivery_document(
    dataset_version: str,
    delivery_id: str,
    statute_count: int,
    judgement_count: int,
    candidate_count: int,
    review_count: int,
) -> str:
    """Human verification and scope instructions shipped inside the archive."""

    return f"""# Dataset release `{dataset_version}`

Delivery `{delivery_id}`, from MZO. Schema `source-record-v2`.

The signed `release-manifest.json` is authoritative for coverage, files,
licence notes, dispositions, and known gaps. This archive contains
{statute_count:,} current statute article/appendix records and
{judgement_count:,} selected aesthetic-domain judgement records. Selection is
deterministic except for 15 review candidates explicitly approved by gyro after
an evidence-checked LLM review; `selectionStage` records that human decision.

The selection ledger covers {candidate_count:,} collected precedent candidates;
{review_count:,} remain `review` and are not corpus records. Raw API responses
are retained for every collected candidate, including excluded and review rows.

## Files

| File | Contents |
| --- | --- |
| `statutes.jsonl` | Current laws, decrees, rules, and appendices |
| `judgements.jsonl` | Deterministically selected court decisions |
| `precedent-decisions.jsonl` | Include/exclude/review audit ledger; never index it |
| `source-native.tar.gz` | Retained law.go.kr XML responses |
| `release-manifest.json` | Authoritative frozen release description |
| `SHA256SUMS` | Per-file SHA-256 values |

## Verify

Verify the ZIP hash supplied alongside this archive before extraction. Then
verify the inner files with `SHA256SUMS` and run:

```powershell
tar -xzf source-native.tar.gz
uv run python scripts/verify_release.py --rag-dir . `
    --file statutes.jsonl --file judgements.jsonl `
    --manifest release-manifest.json
```

Do not index `precedent-decisions.jsonl`, excluded candidates, review candidates,
or raw XML directly. Every index input must come from the two record files and
must remain traceable to this manifest.

This release contains current law only. A judgement may have applied an older
version of a provision; consumers must not silently present the current text as
the historical text applied by the court.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--delivery-id", required=True)
    parser.add_argument("--frozen-at", required=True)
    args = parser.parse_args()

    frozen_at = dt.datetime.fromisoformat(args.frozen_at.replace("Z", "+00:00"))
    if frozen_at.tzinfo is None:
        raise ValueError("frozen-at must include a timezone")
    timestamp = int(frozen_at.timestamp())
    delivery = args.work_dir / "delivery"
    if delivery.exists():
        raise FileExistsError(f"refusing to overwrite existing delivery: {delivery}")
    delivery.mkdir(parents=True)

    for name in ("statutes.jsonl", "judgements.jsonl"):
        shutil.copyfile(args.work_dir / "records" / name, delivery / name)
    shutil.copyfile(
        args.work_dir / "selection" / "precedent-decisions.jsonl",
        delivery / "precedent-decisions.jsonl",
    )
    included_optional: list[str] = []
    for name in OPTIONAL_METADATA_FILES:
        source = args.work_dir / "selection" / name
        if source.exists():
            shutil.copyfile(source, delivery / name)
            included_optional.append(name)

    artifact_count = deterministic_tar(
        args.work_dir / "raw" / "source-native",
        delivery / "source-native.tar.gz",
        timestamp,
    )
    records: list[SourceRecord] = []
    files = []
    for name in ("statutes.jsonl", "judgements.jsonl"):
        parsed, described = read(delivery / name)
        records.extend(parsed)
        files.append(described)
    files.append(describe_metadata(delivery / "precedent-decisions.jsonl"))
    for name in included_optional:
        files.append(describe_metadata(delivery / name))
    files.append(describe_artifacts(delivery / "source-native.tar.gz", artifact_count))

    ledger_rows = [
        json.loads(line)
        for line in (delivery / "precedent-decisions.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
        if line.strip()
    ]
    review_count = sum(row["decision"] == "review" for row in ledger_rows)
    statute_count = sum(record.document_kind == "statute" for record in records)
    judgement_count = sum(record.document_kind == "judgement" for record in records)
    (delivery / "DELIVERY.md").write_text(
        delivery_document(
            args.dataset_version,
            args.delivery_id,
            statute_count,
            judgement_count,
            len(ledger_rows),
            review_count,
        ),
        encoding="utf-8",
    )
    files.append(describe_metadata(delivery / "DELIVERY.md"))

    manifest = ReleaseManifest(
        dataset_version=args.dataset_version,
        schema_version="source-record-v2",
        frozen_at=frozen_at,
        delivery_id=args.delivery_id,
        delivered_by="MZO",
        files=tuple(files),
        coverage_by_document_kind=coverage(
            collections.Counter(str(record.document_kind) for record in records)
        ),
        coverage_by_provider=coverage(
            collections.Counter(record.provenance.provider for record in records)
        ),
        coverage_by_usage=coverage(collections.Counter(str(record.usage) for record in records)),
        dispositions=V2_DISPOSITIONS,
        licences=V2_LICENCES,
        known_gaps=V2_KNOWN_GAPS,
    )
    (delivery / "release-manifest.json").write_text(
        manifest.model_dump_json(by_alias=True, indent=2) + "\n",
        encoding="utf-8",
    )

    checksum_names = (
        "statutes.jsonl",
        "judgements.jsonl",
        "precedent-decisions.jsonl",
        *included_optional,
        "source-native.tar.gz",
        "release-manifest.json",
        "DELIVERY.md",
    )
    (delivery / "SHA256SUMS").write_text(
        "".join(f"{sha256(delivery / name)}  {name}\n" for name in checksum_names),
        encoding="ascii",
    )

    archive = args.work_dir / f"{args.dataset_version}.zip"
    zip_names = tuple(
        name
        for name in (
            "statutes.jsonl",
            "judgements.jsonl",
            "precedent-decisions.jsonl",
            *included_optional,
            "source-native.tar.gz",
            "release-manifest.json",
            "SHA256SUMS",
            "DELIVERY.md",
        )
    )
    deterministic_zip(delivery, archive, frozen_at, zip_names)
    (args.work_dir / f"{archive.name}.sha256").write_text(
        f"{sha256(archive)}  {archive.name}\n",
        encoding="ascii",
    )
    print(f">>> records {len(records)} · artifacts {artifact_count} · archive {archive}")
    print(f">>> sha256 {sha256(archive)}")


if __name__ == "__main__":
    main()
