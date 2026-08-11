"""Map collected current-law articles and appendices to source-record-v2.

Usage:
    uv run python scripts/build_statute_records.py --raw data/v2/raw \
        --out data/v2/records/statutes.jsonl --acquired-at 2026-08-11T00:00:00Z
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path
from typing import Any

from legal_agent_assessment.collection import appendix_document_id, law_document_id
from legal_agent_assessment.dataset import (
    DocumentKind,
    SourceAdmission,
    SourceProvenance,
    SourceRecord,
    StatuteIdentity,
    StatuteUnitKind,
    TextExtraction,
    UsageDisposition,
)
from legal_agent_assessment.dataset_validation import content_hash

SOURCE_LABEL = "법제처 국가법령정보 공동활용(www.law.go.kr)"
PARSER_VERSION = "law-open-api-xml-v1"


def moment(value: str) -> dt.datetime:
    """Parse a required timezone-aware ISO-8601 acquisition time."""

    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("acquired-at must include a timezone")
    return parsed


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read one collected UTF-8 JSONL stream."""

    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def _required(row: dict[str, Any], key: str) -> str:
    value = str(row.get(key) or "").strip()
    if not value:
        raise ValueError(f"collected statute row is missing {key}")
    return value


def build(row: dict[str, Any], acquired_at: dt.datetime) -> SourceRecord:
    """Build one statute source record from one collected article or appendix."""

    law_name = _required(row, "법령명")
    law_id = _required(row, "법령ID")
    mst = _required(row, "MST")
    raw_path = _required(row, "rawArtifactPath")
    raw_hash = _required(row, "rawArtifactHash")
    common: dict[str, Any] = {
        "law_name": law_name,
        "law_id": law_id,
        "mst": mst,
        "instrument_kind": _required(row, "법령구분"),
        "responsible_ministry": _required(row, "소관부처"),
        "promulgated_on": _required(row, "공포일자"),
        "effective_on": _required(row, "시행일자"),
    }

    if row.get("doc_type") == "law_article":
        number = _required(row, "조문번호")
        branch = str(row.get("조문가지번호") or "").strip()
        text = _required(row, "content")
        identity = StatuteIdentity(
            **common,
            unit_kind=StatuteUnitKind.ARTICLE,
            unit_effective_on=str(row.get("조문시행일자") or common["effective_on"]),
            article_number=number,
            article_branch_number=branch,
            article_title=str(row.get("조문제목") or "").strip() or None,
        )
        document_id = law_document_id(law_id, number, branch)
        locator = f"제{int(number)}조" + (f"의{int(branch)}" if branch and int(branch) else "")
    elif row.get("doc_type") == "law_appendix":
        number = _required(row, "별표번호")
        branch = str(row.get("별표가지번호") or "").strip()
        text = _required(row, "contentCleaned")
        identity = StatuteIdentity(
            **common,
            unit_kind=StatuteUnitKind.APPENDIX,
            unit_effective_on=str(row.get("별표시행일자") or common["effective_on"]),
            appendix_number=number,
            appendix_branch_number=branch,
            appendix_title=str(row.get("별표제목") or "").strip() or None,
        )
        document_id = appendix_document_id(law_id, number, branch)
        locator = _required(row, "locator")
    else:
        raise ValueError(f"unsupported statute doc_type: {row.get('doc_type')!r}")

    return SourceRecord(
        document_id=document_id,
        document_kind=DocumentKind.STATUTE,
        title=f"{law_name} {locator}",
        text=text,
        content_hash=content_hash(text),
        identity=identity,
        provenance=SourceProvenance(
            provider="법제처",
            publisher_statement=SOURCE_LABEL,
            source_url=f"https://www.law.go.kr/법령/{law_name}",
            source_reference=f"국가법령정보센터 {law_name} {locator} (MST {mst})",
            acquired_at=acquired_at,
            extraction=TextExtraction(
                tool="legal-agent-assessment law.go.kr XML parser",
                output_format="text",
                performed_at=acquired_at,
                settings=(PARSER_VERSION,),
            ),
            raw_artifact_path=raw_path,
            raw_artifact_hash=raw_hash,
        ),
        admission=SourceAdmission.EXEMPT,
        attribution=SOURCE_LABEL,
        usage=UsageDisposition.INDEX_ELIGIBLE,
        linked_laws=(),
    )


def main() -> None:
    """Build a deterministic statute record stream."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--acquired-at", required=True)
    args = parser.parse_args()

    rows = read_jsonl(args.raw / "laws.jsonl") + read_jsonl(args.raw / "appendices.jsonl")
    if not rows:
        raise SystemExit("no collected law rows found")
    records = [build(row, moment(args.acquired_at)) for row in rows]
    ids = [record.document_id for record in records]
    if len(ids) != len(set(ids)):
        raise RuntimeError("statute conversion produced duplicate document IDs")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(record.model_dump_json(by_alias=True) + "\n")
    print(f">>> {len(records)} statute records -> {args.out}")


if __name__ == "__main__":
    main()
