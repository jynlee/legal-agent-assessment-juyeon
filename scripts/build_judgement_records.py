"""Map the collected precedent JSONL onto the source-record contract.

MZO release tooling.

    uv run python scripts/build_judgement_records.py --rag-dir data/rag --out judgements.jsonl

Source-native Korean keys are translated here and nowhere else. Nothing is
repaired on the way through: the placeholder decision date and the literal
"null" disposition are carried exactly as collected and declared on the record,
because deciding what a missing decision date should become is a normalization
choice that belongs to the contributor.
"""

import argparse
import datetime as dt
import hashlib
import json
import pathlib
from collections import defaultdict
from typing import Any

from legal_agent_assessment.dataset import (
    SENTINEL_DATE,
    SENTINEL_NULL_TEXT,
    DocumentKind,
    JudgementIdentity,
    LawLinkage,
    LinkageStrength,
    SourceAdmission,
    SourceProvenance,
    SourceRecord,
    UsageDisposition,
)
from legal_agent_assessment.dataset_validation import content_hash

# Providers whose subject matter sits away from this agent's questions. They
# stay in the release; including them is a contributor decision.
OUTSIDE_DEFAULT = frozenset({"근로복지공단산재판례", "지방세법령정보시스템"})

# Verified against a sample from every provider: the page resolves and contains
# the record's own case number, while a nonexistent id returns a short shell.
SOURCE_URL = "https://www.law.go.kr/precInfoP.do?precSeq={serial}"


def load(path: pathlib.Path) -> list[dict[str, Any]]:
    """Read the collected rows."""

    rows = []
    for line in path.open(encoding="utf-8"):
        if line.strip():
            rows.append(json.loads(line))
    return rows


def group_ids(rows: list[dict[str, Any]]) -> dict[str, str]:
    """Give one group to every serial that names the same decision.

    A case number that repeats also repeats its court and decision date: those
    rows are one decision registered twice, with text that is identical or
    nearly so. Sharing a group is what stops an evaluation split from putting
    one of a pair in the test set and the other in the index.
    """

    clusters: dict[tuple[str, str, str], list[str]] = defaultdict(list)
    for row in rows:
        clusters[(row["사건번호"], row["법원명"], row["선고일자"])].append(row["판례일련번호"])
    return {
        serial: f"group-{min(serials, key=int)}"
        for serials in clusters.values()
        for serial in serials
    }


def moment(value: str | None) -> dt.datetime | None:
    """Parse an explicit ISO-8601 timestamp, or return None to fall back."""

    if value is None:
        return None
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC).replace(microsecond=0)


def build(
    row: dict[str, Any],
    group: str,
    native: pathlib.Path,
    acquired_at: dt.datetime | None,
) -> SourceRecord:
    """Assemble one judgement record from one collected row."""

    serial = row["판례일련번호"]
    text = row["content"]
    artifact = native / f"{serial}.xml"
    payload = artifact.read_bytes()

    identity = JudgementIdentity(
        case_serial=serial,
        case_name=row["사건명"],
        case_number=row["사건번호"],
        court=row["법원명"],
        case_category=row["사건종류명"],
        decided_on=row["선고일자"],
        judgement_type=row["판결유형"],
        headnote=row["판시사항"],
        holding=row["판결요지"],
        referenced_provisions=row["참조조문"],
        referenced_precedents=row["참조판례"],
    )

    limitations: list[str] = []
    if identity.has_sentinel_date:
        limitations.append(
            f"선고일자가 자리표시자 {SENTINEL_DATE}이며 실제 선고일이 아니다. "
            "날짜 필터가 이 레코드를 조용히 제외한다"
        )
    if identity.has_sentinel_judgement_type:
        limitations.append(f"판결유형이 문자열 {SENTINEL_NULL_TEXT!r}이며 실제 심급 표기가 아니다")
    if not any(
        (
            identity.headnote,
            identity.holding,
            identity.referenced_provisions,
            identity.referenced_precedents,
        )
    ):
        limitations.append("판시사항·판결요지·참조조문·참조판례가 모두 비어 있어 본문만 제공된다")

    linkage = row["linkage"]
    return SourceRecord(
        document_id=f"precedent-{serial}",
        source_group_id=group,
        document_kind=DocumentKind.JUDGEMENT,
        title=row["사건명"],
        text=text,
        content_hash=content_hash(text),
        identity=identity,
        provenance=SourceProvenance(
            provider=row["데이터출처명"],
            publisher_statement=row["source"],
            source_url=SOURCE_URL.format(serial=serial),
            source_reference=f"국가법령정보 판례일련번호 {serial} ({row['사건번호']})",
            acquired_at=acquired_at
            or dt.datetime.fromtimestamp(artifact.stat().st_mtime, dt.UTC).replace(microsecond=0),
            raw_artifact_path=f"source-native/{serial}.xml",
            raw_artifact_hash="sha256:" + hashlib.sha256(payload).hexdigest(),
        ),
        admission=SourceAdmission.EXEMPT,
        attribution=row["source"],
        usage=UsageDisposition.INDEX_ELIGIBLE,
        in_default_corpus=row["데이터출처명"] not in OUTSIDE_DEFAULT,
        linked_laws=tuple(
            LawLinkage(law_name=law, strength=LinkageStrength(linkage[law]))
            for law in row["ragTargets"]
        ),
        limitations=tuple(limitations),
    )


def main() -> None:
    """Write the judgement records as JSONL."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rag-dir", type=pathlib.Path, required=True)
    parser.add_argument("--source", default="precedents.jsonl")
    parser.add_argument("--native", default="source-native")
    parser.add_argument("--out", type=pathlib.Path, required=True)
    # Supply this and the same sources produce byte-identical records on any
    # machine; omit it and each record falls back to its artifact's
    # modification time, which copying the tree destroys.
    parser.add_argument("--acquired-at", help="ISO-8601 time the precedents were collected")
    args = parser.parse_args()

    rows = load(args.rag_dir / args.source)
    groups = group_ids(rows)
    native = args.rag_dir / args.native
    acquired_at = moment(args.acquired_at)
    records = [build(row, groups[row["판례일련번호"]], native, acquired_at) for row in rows]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(
                json.dumps(record.model_dump(by_alias=True, mode="json"), ensure_ascii=False)
            )
            handle.write("\n")

    outside = sum(1 for record in records if not record.in_default_corpus)
    shared = len(records) - len({record.source_group_id for record in records})
    print(f"records                    : {len(records)}")
    print(f"outside the default corpus : {outside}")
    print(f"serials sharing a decision : {shared}")
    print(f"wrote -> {args.out}")


if __name__ == "__main__":
    main()
