"""Promote the 15 gyro-approved LLM candidates into a v2.1 selection."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

APPROVED_SERIALS = frozenset(
    {
        "206364",
        "206398",
        "110389",
        "184694",
        "172444",
        "172449",
        "173261",
        "173233",
        "144508",
        "94170",
        "168622",
        "606509",
        "606747",
        "80695",
        "191857",
    }
)
APPROVED_BY = "gyro (MZO)"
APPROVAL_BASIS = "explicit human approval after evidence-checked LLM review"


def apply_human_approval(decision: dict[str, Any], llm_review: dict[str, Any]) -> dict[str, Any]:
    """Record the explicit human decision and the model review it considered."""

    promoted = dict(decision)
    promoted["decision"] = "include"
    promoted["selectionStage"] = "llm_human_approved"
    promoted["approvedBy"] = APPROVED_BY
    promoted["approvalBasis"] = APPROVAL_BASIS
    promoted["llmReview"] = llm_review
    return promoted


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--deterministic-ledger", type=Path, required=True)
    parser.add_argument("--llm-ledger", type=Path, required=True)
    parser.add_argument("--selected", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    args = parser.parse_args()

    candidates = read_jsonl(args.candidates)
    deterministic = {row["caseSerial"]: row for row in read_jsonl(args.deterministic_ledger)}
    llm = {row["caseSerial"]: row for row in read_jsonl(args.llm_ledger)}
    missing = APPROVED_SERIALS - deterministic.keys() | APPROVED_SERIALS - llm.keys()
    if missing:
        raise ValueError(f"approved serials missing from ledgers: {sorted(missing)}")

    selected: list[dict[str, Any]] = []
    final_ledger: list[dict[str, Any]] = []
    for record in candidates:
        serial = str(record["판례일련번호"])
        decision = dict(deterministic[serial])
        if serial in APPROVED_SERIALS:
            decision = apply_human_approval(decision, llm[serial])
        final_ledger.append(decision)
        if decision["decision"] != "include":
            continue
        reasons = set(decision.get("reasonCodes", []))
        linkage = "candidate" if "TARGET_LAW_CANDIDATE" in reasons else "core"
        enriched = dict(record)
        matched_laws = decision.get("matchedLaws", [])
        enriched["ragTargets"] = matched_laws
        enriched["linkage"] = {law: linkage for law in matched_laws}
        selected.append(enriched)

    if len(selected) != 182:
        raise ValueError(f"expected 182 selected precedents, got {len(selected)}")
    write_jsonl(args.selected, selected)
    write_jsonl(args.ledger, final_ledger)
    print(f">>> selected {len(selected)} precedents; promoted {len(APPROVED_SERIALS)}")


if __name__ == "__main__":
    main()
