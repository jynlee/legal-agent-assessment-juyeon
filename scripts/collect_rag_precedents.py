"""Collect precedents for the four RAG-scope statutes from the 법제처 OPEN API.

    uv run python scripts/collect_rag_precedents.py --oc YOUR_ID
    uv run python scripts/collect_rag_precedents.py --oc YOUR_ID --limit 20
    uv run python scripts/collect_rag_precedents.py --report      # counts only

The 2026-08-07 scope change moved the project from category curation to a
retrieval system measured on provenance. Its corpus is **four statutes**, which
is a different set from the aesthetic-domain whitelist in `collect_legal_raw.py`.
Rather than widening that whitelist — which would relabel precedents for the
already-delivered categories — this script carries its own target list and
reuses the other module's transport, throttling and artifact handling.

## Why keyword search and then a linkage check

The API has no statute-to-precedent linkage endpoint (`filter_precedents.py`),
so a precedent is found by full-text search and then verified against its
참조조문. Measured 2026-08-07 with `search=2`:

    의료법                          939
    소비자기본법                     427
    표시ㆍ광고의 공정화에 관한 법률    104
    안마사                           47      (안마사에 관한 규칙 alone: 18)
    표시광고                       1,278      ← the abbreviation, not the statute

The last line is why aliases are kept narrow. 「표시광고」 matches four times as
much as the statute does, and the surplus is other statutes' cases that merely
use the word. Aliases here exist to *find* candidates; `linkage` records whether
the court actually rested on the statute.

Each record carries `linkage`:

    core       the statute is cited in 참조조문 — the court rested on it
    candidate  not in 참조조문 but named in the body — needs a second look
    unlinked   found by keyword alone

`unlinked` rows are kept rather than dropped: the statistics task must report
what a keyword corpus actually looks like, and dropping them here would hide the
precision cost from the sizing estimate.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import collect_legal_raw as raw
from filter_precedents import _canonical, _matches, extract_law_names

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "rag"
OUT_PATH = OUT_DIR / "precedents.jsonl"

# (표시명, 정식 법령명, 검색 별칭). The 정식 법령명 is what `참조조문` is matched
# against; the aliases are only how candidates are found.
RAG_TARGETS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("의료법", "의료법", ("의료법",)),
    # 「안마사법」이라는 법률은 없다. 안마사 자격·업무는 의료법 제82조의 위임을
    # 받은 「안마사에 관한 규칙」(보건복지부령)이 정한다. 규칙 이름만으로는 18건
    # 이라 「안마사」를 함께 넣어 후보를 넓히고, linkage 로 실제 근거를 가린다.
    ("안마사법", "안마사에 관한 규칙", ("안마사에 관한 규칙", "안마사")),
    (
        "표시광고법",
        "표시ㆍ광고의 공정화에 관한 법률",
        ("표시ㆍ광고의 공정화에 관한 법률",),
    ),
    ("소비자기본법", "소비자기본법", ("소비자기본법",)),
)


def _linkage(record: dict[str, Any], canonical_law: str) -> str:
    """How firmly one precedent rests on the target statute."""
    referenced = {_canonical(name) for name in extract_law_names(record.get("참조조문", ""))}
    if any(_matches(name, canonical_law) for name in referenced):
        return "core"
    body = {_canonical(name) for name in extract_law_names(record.get("content", ""))}
    if any(_matches(name, canonical_law) for name in body):
        return "candidate"
    return "unlinked"


def discover(oc: str) -> tuple[dict[str, list[str]], dict[str, str]]:
    """Serials per target, plus each serial's publisher.

    The publisher comes from the search response because the detail endpoint
    does not return it (measured 2026-08-07).
    """
    found: dict[str, list[str]] = {}
    publishers: dict[str, str] = {}
    for label, _statute, aliases in RAG_TARGETS:
        serials: list[str] = []
        seen: set[str] = set()
        for alias in aliases:
            for serial, publisher in raw.search_precedents_with_publisher(oc, alias):
                if serial not in seen:
                    seen.add(serial)
                    serials.append(serial)
                    publishers.setdefault(serial, publisher)
        found[label] = serials
        print(f"  {label:<12} {len(serials):>5} candidates")
    return found, publishers


def collect(oc: str, limit: int | None = None) -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    artifacts = OUT_DIR / "source-native"
    artifacts.mkdir(parents=True, exist_ok=True)

    print("탐색")
    discovered, publishers = discover(oc)

    # One precedent can rest on more than one of the four. It is written once,
    # with every target it belongs to, so the file has no duplicate bodies and
    # the per-statute counts can still be recovered.
    targets_by_serial: dict[str, list[str]] = {}
    for label, serials in discovered.items():
        for serial in serials:
            targets_by_serial.setdefault(serial, []).append(label)

    order = list(targets_by_serial)
    if limit is not None:
        order = order[:limit]

    statute_of = {label: statute for label, statute, _ in RAG_TARGETS}
    written = 0
    no_body = 0
    print(f"\n본문 취득 — {len(order)}건")
    with OUT_PATH.open("w", encoding="utf-8") as handle:
        for index, serial in enumerate(order, 1):
            staged = artifacts / f"{serial}.xml"
            record = raw.fetch_precedent(
                oc, serial, artifact_path=staged, publisher=publishers.get(serial, "")
            )
            if record is None:
                no_body += 1
                continue
            labels = targets_by_serial[serial]
            record["ragTargets"] = labels
            record["linkage"] = {
                label: _linkage(record, _canonical(statute_of[label])) for label in labels
            }
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
            written += 1
            if index % 100 == 0:
                print(f"    {index}/{len(order)}")

    print(f"\n수집 {written}건 · 본문 없음 {no_body}건")
    print(f"→ {OUT_PATH}")
    return written


def report(oc: str) -> None:
    print("검색 건수만 확인합니다 (본문 취득 없음)\n")
    discover(oc)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oc", default=os.environ.get("LAW_OC", ""))
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--report", action="store_true")
    args = parser.parse_args()
    if not args.oc:
        parser.error("--oc or LAW_OC is required")
    if args.report:
        report(args.oc)
        return
    collect(args.oc, args.limit)


if __name__ == "__main__":
    main()
