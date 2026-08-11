"""Label precedents by whitelist-statute linkage.

Ported from Peitho `scripts/filter_precedents.py` (baseline b38f308).

The 법제처 API has **no statute-to-precedent linkage endpoint** (measured
2026-07-13: statute bodies carry zero precedent references, and precedent search
takes no statute parameter). Linkage is therefore inferred from each precedent's
`참조조문` against the whitelist.

Labels:

- `core`      — a whitelist statute is cited in 참조조문 (the court rested on it,
                so relevance is established)
- `candidate` — not in 참조조문 but present in the body (needs a second look)
- `excluded`  — nowhere (keyword-collection noise)

Filtering before indexing is **not optional**: broad keyword collection has
measured domain precision around 10%, so an unfiltered corpus is mostly noise.

Usage:

    uv run python scripts/filter_precedents.py --cleaned data/cleaned
"""

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

# Whitelist statute names (docs/06_COLLECTION_RUNBOOK.md §3, corpus scope).
WHITELIST_LAWS: tuple[str, ...] = (
    "약사법",
    "의료법",
    "개인정보 보호법",
    "의료기기법",
    "표시ㆍ광고의 공정화에 관한 법률",
    "화장품법",
    "공중위생관리법",
    "안마사에 관한 규칙",
)

# Extract a statute name at a "법령명 (개정이력?) 제N조" boundary. Names end in
# '법'/'법률'/'규칙', optionally followed by a parenthesised amendment note, then
# '제N조'. The leading boundary is string start or a non-Hangul character, which
# stops a preceding particle ("피고인은") being absorbed into the name. A leading
# '구 ' (pre-amendment notation) is excluded from the capture.
_LAW_NAME_RE = re.compile(
    r"(?:^|[\s,/])(?:구\s+)?"
    r"([가-힣ㆍ·][가-힣ㆍ·\s]*?(?:법률|법|규칙))"
    r"\s*(?:\([^)]*\))?\s*제\d+조"
)

_DOT_RE = re.compile(r"[·ᆞ‧∙•・ㆍ]")


def _canonical(text: str) -> str:
    """

    Fold middle-dot variants and drop spaces for matching, so "표시ㆍ광고" /
    "표시·광고" and "의료기사 등에 관한 법률" / "의료기사등에관한법률" compare equal.

    """
    return _DOT_RE.sub("ㆍ", text).replace(" ", "")


_CANONICAL_WHITELIST = tuple((law, _canonical(law)) for law in WHITELIST_LAWS)


def extract_law_names(text: str) -> list[str]:
    """

    Statute names appearing in a "법령명 + 제N조" pattern in free text.

    """
    return [match.group(1).strip() for match in _LAW_NAME_RE.finditer(text or "")]


def _matches(canonical_name: str, canonical_law: str) -> bool:
    """

    Whether an extracted name is the whitelist statute.

    An exact match counts, as does a suffix match where a particle precedes the
    name. A suffix whose prefix ends in '법'/'률'/'칙' is refused, so
    "의료기사등에관한법률" does not match "약사법" by its tail.

    """
    if canonical_name == canonical_law:
        return True
    if canonical_name.endswith(canonical_law):
        prefix = canonical_name[: -len(canonical_law)]
        return not prefix.endswith(("법", "률", "칙"))
    return False


def cited_laws(text: str) -> list[str]:
    """

    Whitelist statutes cited in the text, deduplicated, under their real names.

    """
    extracted = {_canonical(name) for name in extract_law_names(text)}
    return [
        law
        for law, canonical_law in _CANONICAL_WHITELIST
        if any(_matches(name, canonical_law) for name in extracted)
    ]


def label_precedent(record: dict[str, Any]) -> tuple[str, list[str]]:
    """

    Label one precedent. 참조조문 outranks the body: what the court cited is more
    reliable than what the text happens to mention.

    **An absent 참조조문 is not a negative signal.** Measured 2026-08-05 over 169
    full-text records: 참조조문 is populated for 77 of 78 대법원 records (99%) but
    for only 26 of 91 lower-court records (29%). Treating "no 참조조문" the same as
    "참조조문 names none of ours" made the pipeline 대법원-only by accident, and
    lower-court judgments carrying full reasoning are exactly what the
    commissioned Categories are short of. So the two cases are separated:

    - 참조조문 **populated** but naming none of ours — the court cited statutes and
      ours were not among them. Real weak evidence: `candidate`.
    - 참조조문 **absent** — nothing is known about what the court cited, so the body
      is the only evidence there is and carries full weight: `core`.

    """
    references = (record.get("참조조문") or "").strip()
    reference_hits = cited_laws(references)
    if reference_hits:
        return "core", reference_hits
    body_hits = cited_laws(record.get("content", ""))
    if not body_hits:
        return "excluded", []
    return ("candidate" if references else "core"), body_hits


def label_all(records: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Counter[str]]:
    """

    Label a list of records in place and count the outcome.

    """
    counts: Counter[str] = Counter()
    for record in records:
        label, hits = label_precedent(record)
        record["domain_label"] = label
        record["matched_laws"] = hits
        counts[label] += 1
    return records, counts


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")


def main() -> None:
    parser = argparse.ArgumentParser(description="Label precedents by statute linkage")
    parser.add_argument("--cleaned", type=Path, default=Path("data/cleaned"))
    arguments = parser.parse_args()

    records = load_jsonl(arguments.cleaned / "precedents.jsonl")
    if not records:
        print(f"[filter] {arguments.cleaned}/precedents.jsonl not found — nothing to do")
        return
    labeled, counts = label_all(records)

    by_label: dict[str, list[dict[str, Any]]] = {"core": [], "candidate": [], "excluded": []}
    for record in labeled:
        by_label[record["domain_label"]].append(record)
    for label, subset in by_label.items():
        write_jsonl(arguments.cleaned / f"precedents_{label}.jsonl", subset)
        print(f"  {label}: {len(subset)}")
    print(f">>> labelled {counts.total()} precedents in {arguments.cleaned}")


if __name__ == "__main__":
    main()
