"""Collect 별표 bodies from the 법제처 OPEN API.

`collect_legal_raw.py` collects 조문 only and says so at its
`fetch_law_articles` docstring: 별표 bodies arrive in the *same* `target=law`
response under `<별표단위 …>` and were left uncollected. This script adds that
path. It is the gap `docs/06_COLLECTION_RUNBOOK.md` §1 calls "the work" —
화장품법 시행규칙 별표 5 제2호 is a prohibited-expression list enacted as law and
is a curated ground for **three** of the four commissioned Categories
(`profiles/false-exaggeration.yaml`, `medicinal-confusion.yaml`,
`substantiation.yaml`), all declaring `state: 본문취득` against a body that is
not on disk.

Usage:

    # Parse a saved response. No network, no OC.
    python scripts/collect_law_appendices.py --offline RESPONSE.xml

    # Probe one statute and report what came back, writing nothing.
    python scripts/collect_law_appendices.py --oc YOUR_ID --law "화장품법 시행규칙" --probe

    # Collect the whitelist into data/raw/appendices.jsonl
    python scripts/collect_law_appendices.py --oc YOUR_ID --out data/raw

`OC` is the per-developer law.go.kr account id; there is no shared default
(`docs/06_COLLECTION_RUNBOOK.md` §1). Pass `--oc` or set `LAW_OC`.

Every trap in §2 is handled here and named at the site that handles it. A
partial or empty result is raised, never written: "Empty or partial output is
never silent success" (§5).
"""

import argparse
import json
import os
import sys
import xml.etree.ElementTree as ElementTree
from collections import Counter
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collect_legal_raw import (
    LAW_WHITELIST,
    SERVICE_URL,
    SOURCE_LABEL,
    _publish_artifact,
    http_get,
    parse_xml,
    resolve_law,
)

from legal_agent_assessment.cleaning import clean_instrument_body, is_deleted_article
from legal_agent_assessment.collection import (
    artifact_hash,
    assert_expected_text,
    assert_item_markers_begin_lines,
)

# TRAP (§2) — 별표 and 서식 reuse the same numbering under `별표구분`, so matching
# on the number alone silently ingests a 서식. The runbook records the field but
# not its encoding, so both the code and the label are accepted and **any other
# value raises**: a silently dropped 별표 and a silently ingested 서식 are the two
# failures this whole script exists to avoid. Correct this set from the first
# live run rather than widening it to make a run pass.
APPENDIX_KIND_VALUES = frozenset({"1", "별표"})
NON_APPENDIX_KIND_VALUES = frozenset({"2", "3", "4", "서식", "별지", "별지서식"})

# The runbook requires asserting the expected legal text: "The request returned
# 200" is not "the right body arrived" (§2). Keyed by (법령명, 별표 locator).
EXPECTED_TEXT: dict[tuple[str, str], tuple[str, ...]] = {
    ("화장품법 시행규칙", "별표 5"): ("화장품 표시ㆍ광고의 범위 및 준수사항",),
}

# A citation locator *is* the 목 number (`제2호 가목`), so a marker that stayed
# glued to the preceding sentence makes every profile locator resolve to
# nothing. These are the 목 the three profiles actually cite.
EXPECTED_ITEM_MARKERS: dict[tuple[str, str], tuple[str, ...]] = {
    ("화장품법 시행규칙", "별표 5"): ("가.", "나.", "라.", "마.", "바.", "사.", "아."),
}


def appendix_locator(number: str, branch: str) -> str:
    """

    Build a citation locator from the two separate number fields.

    TRAP (§2) — 별표번호 and 별표가지번호 are separate fields of 4 and 2 digits,
    **not** one zero-padded 6-digit number. 별표 5 is `별표번호=0005` plus
    `별표가지번호=00`; a branch of `02` is 별표 5의2, a different instrument.

    """
    stripped = (number or "").strip().lstrip("0") or "0"
    branch_stripped = (branch or "").strip().lstrip("0")
    if branch_stripped:
        return f"별표 {stripped}의{branch_stripped}"
    return f"별표 {stripped}"


def appendix_body(unit: ElementTree.Element, stats: Counter[str]) -> tuple[str, str]:
    """

    Join a 별표's content into one body and return `(extracted, cleaned)`.

    Both are kept because §7 requires the text-preservation chain: `extractedText`
    is what parsing produced and is never overwritten, `normalizedText` is its
    cleaned derivative. Cleaning in place here would destroy the first one, and
    the assertions need the second one, so the collector emits both.

    TRAP (§2) — `<별표내용>` is a *sequence* of CDATA sections, not one string,
    and reading only the first one is the silent way to ingest a truncated
    별표. Consecutive CDATA inside a single element does merge into `.text`
    under ElementTree, so that specific regex-era failure does not reproduce
    here; the two shapes that still truncate are **repeated `<별표내용>`
    elements** and **markup nested inside one**. `findall` plus `itertext`
    covers all three. Measured lengths differ by roughly 2-3x depending on
    whether markers are stripped and whitespace normalized, so this returns the
    combined text and leaves normalization to the cleaning stage.

    An absent `<별표내용>` yields an empty body rather than a guessed fallback
    tag. Whether a 별표 arrives inline or only as an attachment link is not
    recorded in the runbook, so the caller counts and reports the empty ones and
    the first live run settles it.

    """
    parts = ["".join(content.itertext()) for content in unit.findall("별표내용")]
    joined = "\n".join(part for part in parts if part.strip())
    if not joined.strip():
        return "", ""
    # `clean_instrument_body` is the 별표 path and already orders the steps
    # correctly: `restore_item_breaks` runs **before anything else touches the
    # text**, because a citation locator is the 목 number. It restores only
    # markers already separated by whitespace and deliberately leaves a fully
    # glued Korean marker alone, which is why `assert_item_markers_begin_lines`
    # remains a required backstop rather than a redundant check.
    return joined, clean_instrument_body(joined, stats)


# TRAP (§2) — "Deleted shells look like data": a deleted 별표 is a ~37-character
# `삭제` body, not an absent record. The runbook points at
# `cleaning.is_deleted_article`, but that regex is 조문-shaped
# (`^제\d+조(의\d+)?…삭제`) and cannot match a 별표 shell, so the length-bounded
# check the runbook describes is applied here as well.
DELETED_APPENDIX_MAX_CHARS = 60


def is_deleted_appendix(body: str) -> bool:
    """

    Whether a 별표 body is a deleted shell rather than content.

    """
    stripped = body.strip()
    if "삭제" not in stripped:
        return False
    if is_deleted_article(stripped):
        return True
    return len(stripped) <= DELETED_APPENDIX_MAX_CHARS


def is_appendix_unit(kind: str, *, source_reference: str) -> bool:
    """

    Whether a 별표단위 is a 별표 rather than a 서식.

    An unrecognized `별표구분` raises instead of guessing, so a new encoding
    surfaces as a failed run rather than as a corpus that quietly gained
    forms or quietly lost appendices.

    """
    value = (kind or "").strip()
    if value in APPENDIX_KIND_VALUES:
        return True
    if value in NON_APPENDIX_KIND_VALUES:
        return False
    raise RuntimeError(
        f"unrecognized 별표구분 {value!r} in {source_reference}; "
        "confirm the encoding against the response before widening "
        "APPENDIX_KIND_VALUES in scripts/collect_law_appendices.py"
    )


def parse_appendices(root: ElementTree.Element, meta: dict[str, str]) -> list[dict[str, Any]]:
    """

    Parse every 별표 in one `target=law` response into records.

    TRAP (§2) — `<별표단위>` carries attributes (`별표키=…`). A matcher written as
    the bare tag against raw XML returns **zero** rows from a response full of
    them, which is exactly what produced the earlier conclusion that 별표 bodies
    were unavailable. ElementTree matches on tag name and is immune, so the
    parsing here is by element, never by regex over the response text.

    TRAP (§2) — deleted shells look like data: a deleted 별표 is a ~37-character
    `삭제` body, not an absent record. They are counted and dropped.

    """
    records: list[dict[str, Any]] = []
    skipped: Counter[str] = Counter()
    stats: Counter[str] = Counter()
    for unit in root.iter("별표단위"):
        number = (unit.findtext("별표번호") or "").strip()
        branch = (unit.findtext("별표가지번호") or "").strip()
        locator = appendix_locator(number, branch)
        reference = f"{meta.get('법령명', '')} {locator}".strip()

        if not is_appendix_unit(unit.findtext("별표구분") or "", source_reference=reference):
            skipped["서식"] += 1
            continue

        extracted, body = appendix_body(unit, stats)
        if not body.strip():
            skipped["본문없음"] += 1
            continue
        if is_deleted_appendix(body):
            skipped["삭제"] += 1
            continue

        record = dict(meta)
        record.update(
            {
                "doc_type": "law_appendix",
                "별표번호": number,
                "별표가지번호": branch,
                "별표구분": (unit.findtext("별표구분") or "").strip(),
                "별표제목": (unit.findtext("별표제목") or "").strip(),
                "별표시행일자": (unit.findtext("별표시행일자") or "").strip(),
                "locator": locator,
                # §7: extracted stays pre-cleaning, cleaned is its derivative.
                "content": extracted,
                "contentCleaned": body,
                "source": SOURCE_LABEL,
            }
        )
        records.append(record)
    if skipped:
        print(f"  [DROPPED] {dict(skipped)}")
    if stats:
        print(f"  [CLEANED] {dict(stats)}")
    return records


def law_metadata(root: ElementTree.Element, mst: str) -> dict[str, str]:
    """

    Read the 기본정보 block a 별표 record inherits from its parent statute.

    """
    info = root.find("기본정보")

    def basic(tag: str) -> str:
        return (info.findtext(tag) or "").strip() if info is not None else ""

    return {
        "법령명": basic("법령명_한글"),
        "법령구분": basic("법종구분"),
        "소관부처": basic("소관부처"),
        "공포일자": basic("공포일자"),
        "시행일자": basic("시행일자"),
        "법령ID": basic("법령ID"),
        "MST": mst,
    }


def verify_expected(records: list[dict[str, Any]], law_name: str) -> list[str]:
    """

    Assert the known text of every 별표 this kit cites, returning what was checked.

    """
    checked: list[str] = []
    for record in records:
        key = (law_name, record["locator"])
        expected = EXPECTED_TEXT.get(key)
        if expected:
            assert_expected_text(
                record["contentCleaned"],
                expected,
                source_reference=f"{law_name} {record['locator']}",
            )
            checked.append(f"{key[1]} text")
        markers = EXPECTED_ITEM_MARKERS.get(key)
        if markers:
            assert_item_markers_begin_lines(
                record["contentCleaned"],
                markers,
                source_reference=f"{law_name} {record['locator']}",
            )
            checked.append(f"{key[1]} markers")
    return checked


def fetch_appendices(
    oc: str, mst: str, *, artifact_path: Path | None = None
) -> tuple[list[dict[str, Any]], dict[str, str]]:
    """

    Fetch one statute and parse its 별표 units.

    """
    text = http_get(
        SERVICE_URL,
        {"OC": oc, "target": "law", "type": "XML", "MST": mst},
        artifact_path=artifact_path,
    )
    root = parse_xml(text)
    if root is None:
        raise RuntimeError(f"law response was not XML (MST={mst})")
    meta = law_metadata(root, mst)
    return parse_appendices(root, meta), meta


def run_offline(path: Path) -> int:
    """

    Parse a saved response so the parser can be exercised without an OC.

    """
    root = parse_xml(path.read_text(encoding="utf-8"))
    if root is None:
        raise RuntimeError(f"{path} is not XML")
    meta = law_metadata(root, mst="(offline)")
    records = parse_appendices(root, meta)
    report(records, meta)
    checked = verify_expected(records, meta.get("법령명", ""))
    for item in checked:
        print(f"  [ASSERTED] {item}")
    return len(records)


def report(records: list[dict[str, Any]], meta: dict[str, str]) -> None:
    """

    Print what a response actually contained, including the raw 별표구분 values.

    The runbook records the field but not its encoding, so the first live run
    is what settles it. Printing the distribution makes that a fact rather than
    an assumption.

    """
    print(f"  법령명 {meta.get('법령명', '(unknown)')}  시행일자 {meta.get('시행일자', '')}")
    print(f"  별표 records: {len(records)}")
    kinds = Counter(record["별표구분"] for record in records)
    if kinds:
        print(f"  별표구분 values: {dict(kinds)}")
    for record in records:
        body = record["contentCleaned"]
        lines = body.count("\n") + 1
        print(
            f"    {record['locator']:>12}  {len(body):>7} chars  "
            f"{lines:>4} lines  {record['별표제목'][:44]}"
        )


def collect(oc: str, out_dir: Path, *, only: str | None) -> int:
    """

    Collect 별표 for the whitelist statutes, or for one named statute.

    A statute that does not resolve exactly is skipped and makes the run fail,
    matching `collect_legal_raw.collect_laws`: a fuzzy fallback silently loads
    an unrelated instrument.

    """
    # A whitelist entry is named and must resolve. Its 시행령 and 시행규칙 are
    # *derived* names, and not every 법률 has both — 표시ㆍ광고의 공정화에 관한 법률
    # and 개인정보 보호법 resolved no 시행규칙 on 2026-08-05. §5 requires that an
    # exact-name miss never be replaced by a guess; it does not require an
    # instrument that does not exist. So a derived miss is reported and skipped,
    # and only a named miss fails the run.
    targets: list[tuple[str, str | None, bool]] = []
    if only:
        targets.append((only, None, True))
    else:
        for name, gubun in LAW_WHITELIST:
            targets.append((name, gubun, True))
            if gubun == "법률":
                targets.append((f"{name} 시행령", "대통령령", False))
                targets.append((f"{name} 시행규칙", None, False))

    out_path = out_dir / "appendices.jsonl"
    out_dir.mkdir(parents=True, exist_ok=True)
    total = 0
    unresolved: list[str] = []
    with TemporaryDirectory(prefix=".appendices-", dir=out_dir) as temporary:
        staging = Path(temporary)
        staged_path = staging / out_path.name
        artifacts: list[tuple[Path, Path, str]] = []
        with staged_path.open("w", encoding="utf-8", newline="\n") as handle:
            for name, gubun, required in targets:
                mst, resolved = resolve_law(oc, name, gubun, strict=True)
                if not mst:
                    kind = "whitelist entry" if required else "derived name, may not exist"
                    print(f"  [SKIP] no exact match: {name} ({kind})")
                    if required:
                        unresolved.append(name)
                    continue
                staged_artifact = staging / "pending" / f"law-{len(artifacts)}.xml"
                records, meta = fetch_appendices(oc, mst, artifact_path=staged_artifact)
                raw_hash = artifact_hash(staged_artifact.read_bytes())
                relative = Path("source-native") / "law" / f"{raw_hash.removeprefix('sha256:')}.xml"
                artifacts.append((staged_artifact, relative, raw_hash))
                for check in verify_expected(records, meta.get("법령명", "")):
                    print(f"  [ASSERTED] {resolved} {check}")
                for record in records:
                    record["rawArtifactPath"] = relative.as_posix()
                    record["rawArtifactHash"] = raw_hash
                    handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                total += len(records)
                print(f"  [OK] {resolved:34s} MST={mst} 별표 {len(records)}")
        if unresolved:
            raise RuntimeError(
                "appendix collection was partial; unresolved entries: " + ", ".join(unresolved)
            )
        for staged_artifact, relative, raw_hash in artifacts:
            _publish_artifact(staged_artifact, out_dir, relative, raw_hash)
        staged_path.replace(out_path)
    print(f">>> {total} 별표 records -> {out_path}")
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--oc", default=os.environ.get("LAW_OC"), help="law.go.kr account id")
    parser.add_argument("--offline", type=Path, help="parse a saved XML response instead")
    parser.add_argument("--law", help="collect one statute by exact name")
    parser.add_argument("--probe", action="store_true", help="report findings, write nothing")
    parser.add_argument("--out", type=Path, default=Path("data/raw"))
    args = parser.parse_args()

    if args.offline:
        run_offline(args.offline)
        return 0

    if not args.oc:
        parser.error(
            "no OC. Pass --oc or set LAW_OC; there is no shared key "
            "(docs/06_COLLECTION_RUNBOOK.md §1). Use --offline to parse a saved response."
        )

    if args.probe:
        name = args.law or "화장품법 시행규칙"
        mst, resolved = resolve_law(args.oc, name, None, strict=True)
        if not mst:
            raise SystemExit(f"[SKIP] no exact match: {name}")
        records, meta = fetch_appendices(args.oc, mst)
        print(f"[PROBE] {resolved} MST={mst}")
        report(records, meta)
        for check in verify_expected(records, meta.get("법령명", "")):
            print(f"  [ASSERTED] {check}")
        return 0

    collect(args.oc, args.out, only=args.law)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
