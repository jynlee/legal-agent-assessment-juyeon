"""Select collected precedent candidates and write an auditable ledger.

The input is the broad raw `precedents.jsonl` written by collect_legal_raw.py.
Only deterministic `include` decisions reach the selected output. Review and
excluded rows remain represented in the ledger and their raw XML stays intact.
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from filter_precedents import label_precedent

from legal_agent_assessment.precedent_selection import (
    PrecedentSelection,
    SelectionDecision,
    select_precedent,
)


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    """Read a non-empty UTF-8 candidate stream."""

    with path.open(encoding="utf-8") as handle:
        records = [json.loads(line) for line in handle if line.strip()]
    if not records:
        raise ValueError(f"no precedent candidates in {path}")
    return records


def decision_key(record: dict[str, Any]) -> tuple[str, str, str]:
    """Coordinates used to group repeated publications of one decision."""

    return tuple(str(record.get(key) or "").strip() for key in ("법원명", "사건번호", "선고일자"))


def _representative_rank(record: dict[str, Any]) -> tuple[int, int, int, str]:
    structured = sum(
        bool(str(record.get(key) or "").strip())
        for key in ("판시사항", "판결요지", "참조조문", "참조판례")
    )
    preferred = int(str(record.get("데이터출처명") or "") in {"대법원", "국가법령정보센터"})
    body_length = len(str(record.get("content") or ""))
    serial = str(record.get("판례일련번호") or "")
    return preferred, structured, body_length, serial


def duplicate_map(records: list[dict[str, Any]]) -> dict[str, str]:
    """Map duplicate serials to the deterministic representative serial."""

    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        key = decision_key(record)
        if not all(key):
            continue
        grouped[key].append(record)

    duplicates: dict[str, str] = {}
    for cluster in grouped.values():
        if len(cluster) < 2:
            continue
        representative = max(cluster, key=_representative_rank)
        representative_serial = str(representative["판례일련번호"])
        for record in cluster:
            serial = str(record["판례일련번호"])
            if serial != representative_serial:
                duplicates[serial] = f"precedent-{representative_serial}"
    return duplicates


def select_all(
    records: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[PrecedentSelection]]:
    """Return selected converter inputs and one ledger row per candidate."""

    duplicates = duplicate_map(records)
    selected: list[dict[str, Any]] = []
    ledger: list[PrecedentSelection] = []
    for record in records:
        serial = str(record.get("판례일련번호") or "")
        linkage, matched_laws = label_precedent(record)
        decision = select_precedent(
            record,
            linkage=linkage,
            matched_laws=tuple(matched_laws),
            duplicate_of=duplicates.get(serial),
        )
        ledger.append(decision)
        if decision.decision is SelectionDecision.INCLUDE:
            enriched = dict(record)
            enriched["ragTargets"] = matched_laws
            enriched["linkage"] = {law: linkage for law in matched_laws}
            selected.append(enriched)
    return selected, ledger


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write UTF-8 JSONL with stable source order."""

    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> None:
    """Run deterministic precedent selection."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--selected", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args()

    selected, ledger = select_all(read_jsonl(args.input))
    write_jsonl(args.selected, selected)
    write_jsonl(
        args.ledger,
        [row.model_dump(by_alias=True, mode="json") for row in ledger],
    )
    counts = {decision.value: 0 for decision in SelectionDecision}
    for row in ledger:
        counts[row.decision.value] += 1
    print(f">>> candidates {len(ledger)} · decisions {counts} · selected {len(selected)}")


if __name__ == "__main__":
    main()
