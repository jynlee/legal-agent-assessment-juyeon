"""Collect raw legal corpus data from the 법제처 OPEN API.

Ported from Peitho `scripts/collect_legal_raw.py` (baseline b38f308). Statutes
(law + decree + rules) are downloaded per article, precedents per case.
One JSONL line is one record.

- statute bodies: `lawService.do` (MST) -> 조문내용 plus 항/호 text, merged
- precedent bodies: `lawService.do` (ID). `데이터출처명` names the **publisher**,
  not the court, and does not predict whether a body exists — see the measurement
  at `_PRECEDENT_PUBLISHER_DENYLIST`. A row qualifies when 판례내용 comes back
  non-empty, which `fetch_precedent` decides.

Usage:

    uv run python scripts/collect_legal_raw.py --oc YOUR_ID
    uv run python scripts/collect_legal_raw.py --oc YOUR_ID --laws-only
    uv run python scripts/collect_legal_raw.py --oc YOUR_ID --prec-only --limit 20

`OC` is not a secret — it is the law.go.kr account id you register — but it is
**per developer** and there is no shared default: the originally handed-over key
stopped passing user validation on 2026-07-08. Apply for your own and pass it
via `--oc` or the `LAW_OC` environment variable. See
`docs/06_COLLECTION_RUNBOOK.md` §1.

The output directory is gitignored. Raw artifacts are delivered outside Git.
"""

import argparse
import json
import os
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ElementTree
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from legal_agent_assessment.collection import artifact_hash

SEARCH_URL = "http://www.law.go.kr/DRF/lawSearch.do"
SERVICE_URL = "http://www.law.go.kr/DRF/lawService.do"
SLEEP_SECONDS = 0.3
MAX_RETRY = 3
PAGE_SIZE = 100  # Requested value; the API returns ~20 rows regardless (§1).
MAX_PAGES = 200
SOURCE_LABEL = "법제처 국가법령정보 공동활용(www.law.go.kr)"

# Aesthetic-domain whitelist: (법령명, 법령구분). Each statute is collected with
# its enforcement decree and rules. Ingesting all law hurts retrieval precision.
LAW_WHITELIST: tuple[tuple[str, str], ...] = (
    ("약사법", "법률"),
    ("의료법", "법률"),
    ("개인정보 보호법", "법률"),
    ("의료기기법", "법률"),
    ("표시ㆍ광고의 공정화에 관한 법률", "법률"),
    ("화장품법", "법률"),
    ("공중위생관리법", "법률"),
    ("안마사에 관한 규칙", "보건복지부령"),
)

# `데이터출처명` is the **publisher**, not the court. 대법원 종합법률정보 publishes
# lower-court judgements in full — a fetched 서울행법 2024구합70616 carried 판시사항,
# 판결요지, 참조조문 and a 7,800-character body (`docs/06_COLLECTION_RUNBOOK.md` §8,
# measured 2026-08-05). Keeping only `대법원` therefore silently discarded every
# 지방법원·고등법원·행정법원 judgement, which is most of the domain's case law.
#
# The runbook goes on to name 국세법령정보시스템 and 근로복지공단산재판례 as the rows
# to drop instead. **Half of that is wrong.** Measured 2026-08-07 over 「소비자기본법」,
# six bodies fetched per publisher:
#
#     대법원              6/6 bodies   5,451-14,170 chars   대법원·대구고법·서울행법
#     지방세법령정보시스템   6/6 bodies  12,221-57,075 chars   인천지법·서울중앙지법 …
#     근로복지공단산재판례   6/6 bodies   2,004-5,893 chars   서울고법·서울행법 …
#     국세법령정보시스템     0/6 bodies                        (metadata only)
#
# So 근로복지공단산재판례 syndicates real judgements and dropping it loses them, while
# 지방세법령정보시스템 — which the runbook never mentions — carries the longest bodies
# in the sample. A publisher name does not predict whether a body exists.
#
# The real criterion is the body itself, and `fetch_precedent` already applies it:
# it returns None when 판례내용 is empty. Filtering by publisher here would only
# save requests, and it has now twice cost us records instead. Rows are therefore
# kept at search time and dropped at fetch time on the evidence.
_PRECEDENT_PUBLISHER_DENYLIST: frozenset[str] = frozenset()

# Precedent full-text search keywords. Collect broadly and narrow with
# `filter_precedents.py`: the API has no statute-to-precedent linkage endpoint.
# Broad keywords are deliberate — measured 2026-07-13, '화장품' returns 528 hits
# against 208 for '화장품법', so naming the statute loses related cases.
PRECEDENT_KEYWORDS: tuple[str, ...] = (
    "약사법",
    "의료법",
    "개인정보 보호법",
    "의료기기법",
    "표시광고",
    "화장품",
    "공중위생관리법",
    "안마사",
    "미용",
    "과대광고",
    "무면허 의료행위",
)


def _artifact_relative_path(kind: str, raw_hash: str) -> Path:
    return Path("source-native") / kind / f"{raw_hash.removeprefix('sha256:')}.xml"


def _publish_artifact(staged: Path, out_dir: Path, relative_path: Path, raw_hash: str) -> None:
    destination = out_dir / relative_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists():
        if artifact_hash(destination.read_bytes()) != raw_hash:
            raise RuntimeError(f"content-addressed artifact path is corrupted: {relative_path}")
        return
    staged.replace(destination)


def http_get(url: str, params: dict[str, str], *, artifact_path: Path | None = None) -> str:
    """

    GET one API response, retrying transient failures.

    """
    full_url = f"{url}?{urllib.parse.urlencode(params)}"
    last_error: Exception | None = None
    for attempt in range(MAX_RETRY):
        try:
            with urllib.request.urlopen(full_url, timeout=30) as response:
                payload = response.read()
                text: str = payload.decode("utf-8")
                if artifact_path is not None:
                    artifact_path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = artifact_path.with_name(f".{artifact_path.name}.tmp")
                    temporary.write_bytes(payload)
                    temporary.replace(artifact_path)
                return text
        except Exception as error:  # Network and HTTP errors both retry.
            last_error = error
            time.sleep(SLEEP_SECONDS * (attempt + 1))
    raise RuntimeError(f"GET failed ({full_url}): {last_error}")


def parse_xml(text: str) -> ElementTree.Element | None:
    """

    Parse a response, or return None when the API answered with an error page.

    An error response is HTML or plain prose, not XML, so a parse failure here is
    an expected outcome rather than a bug.

    """
    try:
        return ElementTree.fromstring(text)
    except ElementTree.ParseError:
        return None


def resolve_law(
    oc: str, name: str, gubun: str | None = None, *, strict: bool = False
) -> tuple[str | None, str]:
    """

    Resolve a 법령명 to its MST (법령일련번호).

    MST is resolved per run and never stored as a permanent key — it changes with
    each amendment. Exact name-and-kind matches win, then exact name; `strict`
    refuses a loose fallback so a wrong statute cannot be ingested silently.

    """
    text = http_get(
        SEARCH_URL,
        {"OC": oc, "target": "law", "type": "XML", "query": name, "numOfRows": "20"},
    )
    root = parse_xml(text)
    time.sleep(SLEEP_SECONDS)
    if root is None:
        raise RuntimeError(f"law search response was not XML (query={name!r})")

    def normalize(value: str | None) -> str:
        return (value or "").replace(" ", "").strip()

    target = normalize(name)
    candidates: list[tuple[str, str, str]] = []
    for law in root.findall("law"):
        mst = (law.findtext("법령일련번호") or "").strip()
        if not mst:
            continue
        candidates.append(
            (
                mst,
                (law.findtext("법령명한글") or "").strip(),
                (law.findtext("법령구분명") or "").strip(),
            )
        )

    if gubun:
        for mst, matched_name, matched_gubun in candidates:
            if normalize(matched_name) == target and matched_gubun == gubun:
                return mst, matched_name
    for mst, matched_name, _ in candidates:
        if normalize(matched_name) == target:
            return mst, matched_name
    if not strict and candidates:
        return candidates[0][0], candidates[0][1]
    return None, name


def fetch_law_articles(
    oc: str, mst: str, *, artifact_path: Path | None = None
) -> list[dict[str, Any]]:
    """

    Fetch one statute and parse it into article records.

    Only `조문여부 == 조문` units become records; the response also carries
    non-article units. 별표 bodies arrive in the same response under
    `<별표단위 …>` and are collected by `scripts/collect_law_appendices.py`,
    which fetches the same MST and parses that element instead. Keeping the two
    passes separate costs one extra request per statute and keeps this
    function's record shape to one kind.

    """
    text = http_get(
        SERVICE_URL,
        {"OC": oc, "target": "law", "type": "XML", "MST": mst},
        artifact_path=artifact_path,
    )
    time.sleep(SLEEP_SECONDS)
    root = parse_xml(text)
    if root is None:
        raise RuntimeError(f"law response was not XML (MST={mst})")

    info = root.find("기본정보")

    def basic(tag: str) -> str:
        return (info.findtext(tag) or "").strip() if info is not None else ""

    meta = {
        "법령명": basic("법령명_한글"),
        "법령구분": basic("법종구분"),
        "소관부처": basic("소관부처"),
        "공포일자": basic("공포일자"),
        "시행일자": basic("시행일자"),
        "법령ID": basic("법령ID"),
        "MST": mst,
    }

    records: list[dict[str, Any]] = []
    for unit in root.iter("조문단위"):
        if (unit.findtext("조문여부") or "").strip() != "조문":
            continue
        parts: list[str] = []
        body = unit.find("조문내용")
        if body is not None and body.text:
            parts.append(body.text.strip())
        for hang in unit.findall("항"):
            hang_text = "".join(hang.itertext()).strip()
            if hang_text:
                parts.append(hang_text)
        content = "\n".join(part for part in parts if part)
        if not content:
            continue
        record = dict(meta)
        record.update(
            {
                "doc_type": "law_article",
                "조문번호": (unit.findtext("조문번호") or "").strip(),
                "조문가지번호": (unit.findtext("조문가지번호") or "").strip(),
                "조문제목": (unit.findtext("조문제목") or "").strip(),
                "조문시행일자": (unit.findtext("조문시행일자") or "").strip(),
                "content": content,
                "source": SOURCE_LABEL,
            }
        )
        records.append(record)
    if not records:
        raise RuntimeError(f"law response contained no article bodies (MST={mst})")
    return records


def collect_laws(oc: str, out_dir: Path) -> int:
    """

    Collect every whitelist statute with its decree and rules.

    A statute that does not resolve exactly is **skipped, never guessed**: a
    fuzzy fallback here silently loads an unrelated statute into the corpus.

    """
    out_path = out_dir / "laws.jsonl"
    total = 0
    unresolved: list[str] = []
    with TemporaryDirectory(prefix=".laws-", dir=out_dir) as temporary:
        staging = Path(temporary)
        staged_path = staging / out_path.name
        artifacts: list[tuple[Path, Path, str]] = []
        with staged_path.open("w", encoding="utf-8", newline="\n") as handle:
            for name, gubun in LAW_WHITELIST:
                # A whitelist entry is named and must resolve. Its 시행령 and
                # 시행규칙 are *derived* names and not every 법률 has both —
                # 표시ㆍ광고의 공정화에 관한 법률 and 개인정보 보호법 resolved no
                # 시행규칙 on 2026-08-05, which failed the whole run. §5 forbids
                # replacing an exact-name miss with a guess; it does not require
                # an instrument that does not exist.
                queries: list[tuple[str, str | None, bool]] = [(name, gubun, True)]
                if gubun == "법률":
                    queries.append((f"{name} 시행령", "대통령령", False))
                    queries.append((f"{name} 시행규칙", None, False))
                for query_name, query_gubun, required in queries:
                    mst, resolved = resolve_law(oc, query_name, query_gubun, strict=True)
                    if not mst:
                        kind = "whitelist entry" if required else "derived name, may not exist"
                        print(f"  [SKIP] no exact match: {query_name} ({kind})")
                        if required:
                            unresolved.append(query_name)
                        continue
                    staged_artifact = staging / "pending" / f"law-{len(artifacts)}.xml"
                    articles = fetch_law_articles(oc, mst, artifact_path=staged_artifact)
                    raw_hash = artifact_hash(staged_artifact.read_bytes())
                    artifact_relative = _artifact_relative_path("law", raw_hash)
                    artifacts.append((staged_artifact, artifact_relative, raw_hash))
                    for record in articles:
                        record["rawArtifactPath"] = artifact_relative.as_posix()
                        record["rawArtifactHash"] = raw_hash
                        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                    total += len(articles)
                    print(f"  [OK] {resolved:34s} MST={mst} articles {len(articles)}")
        if unresolved:
            raise RuntimeError(
                "law collection was partial; unresolved whitelist entries: " + ", ".join(unresolved)
            )
        for staged_artifact, artifact_relative, raw_hash in artifacts:
            _publish_artifact(staged_artifact, out_dir, artifact_relative, raw_hash)
        staged_path.replace(out_path)
    print(f">>> {total} statute articles -> {out_path}")
    return total


def search_precedents_with_publisher(oc: str, keyword: str) -> list[tuple[str, str]]:
    """

    Page through a full-text precedent search, returning (일련번호, 데이터출처명).

    The publisher is only available here — the detail endpoint omits it — so it
    is returned alongside rather than fetched again later.

    Pagination cannot trust `numOfRows`: the API returns roughly 20 rows per page
    regardless, so the loop runs until `totalCnt` is covered.

    """
    results: list[tuple[str, str]] = []
    for page in range(1, MAX_PAGES + 1):
        text = http_get(
            SEARCH_URL,
            {
                "OC": oc,
                "target": "prec",
                "type": "XML",
                "query": keyword,
                "search": "2",
                "numOfRows": str(PAGE_SIZE),
                "page": str(page),
            },
        )
        time.sleep(SLEEP_SECONDS)
        root = parse_xml(text)
        if root is None:
            raise RuntimeError(
                f"precedent search response was not XML (keyword={keyword!r}, page={page})"
            )
        blocks = root.findall("prec")
        if not blocks:
            break
        for precedent in blocks:
            publisher = (precedent.findtext("데이터출처명") or "").strip()
            if publisher in _PRECEDENT_PUBLISHER_DENYLIST:
                continue
            serial = (precedent.findtext("판례일련번호") or "").strip()
            if serial:
                results.append((serial, publisher))
        total_count = int((root.findtext("totalCnt") or "0").strip() or 0)
        if page * len(blocks) >= total_count:
            break
    return results


def search_precedents(oc: str, keyword: str) -> list[str]:
    """Serial numbers alone, for callers that do not record provenance."""
    return [serial for serial, _publisher in search_precedents_with_publisher(oc, keyword)]


def fetch_precedent(
    oc: str,
    serial: str,
    *,
    artifact_path: Path | None = None,
    publisher: str = "",
) -> dict[str, Any] | None:
    """

    Fetch one precedent, or None when no full text is published for it.

    `publisher` is the search response's 데이터출처명, which the detail endpoint
    does not return. Pass it through to keep provenance; omit it and the field
    is left absent rather than guessed.

    """
    text = http_get(
        SERVICE_URL,
        {"OC": oc, "target": "prec", "type": "XML", "ID": serial},
        artifact_path=artifact_path,
    )
    time.sleep(SLEEP_SECONDS)
    root = parse_xml(text)
    if root is None:
        raise RuntimeError(f"precedent response was not XML (ID={serial})")

    def field(tag: str) -> str:
        element = root.find(tag)
        return "".join(element.itertext()).strip() if element is not None else ""

    content = field("판례내용")
    if not content:
        return None
    return {
        "doc_type": "precedent",
        "판례일련번호": serial,
        "사건명": field("사건명"),
        "사건번호": field("사건번호"),
        "선고일자": field("선고일자"),
        "법원명": field("법원명"),
        "사건종류명": field("사건종류명"),
        "판결유형": field("판결유형"),
        "판시사항": field("판시사항"),
        "판결요지": field("판결요지"),
        "참조조문": field("참조조문"),
        "참조판례": field("참조판례"),
        "content": content,
        "source": SOURCE_LABEL,
        # The publisher is **not** in the detail response — measured 2026-08-07,
        # `lawService.do?target=prec` returns 판례정보일련번호 … 판례내용 and no
        # 데이터출처명. Only the search response carries it.
        #
        # Hardcoding 대법원 here was the same misreading as the old search filter:
        # it stamped every lower-court judgement as a Supreme Court one. Defaulting
        # to any other constant would repeat the mistake with a different word, so
        # the caller passes through what the search actually said, and a record
        # collected without that context leaves the field absent rather than
        # inventing one.
        **({"데이터출처명": publisher} if publisher else {}),
    }


def load_seen(out_path: Path) -> set[str]:
    """

    Serials already collected, so a run resumes instead of restarting.

    """
    seen: set[str] = set()
    if not out_path.exists():
        return seen
    with out_path.open(encoding="utf-8") as handle:
        for number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                raise ValueError(f"{out_path}: invalid JSON on line {number}") from error
            serial = str(record.get("판례일련번호", "")).strip()
            if not serial:
                raise ValueError(f"{out_path}: missing 판례일련번호 on line {number}")
            seen.add(serial)
    return seen


def collect_precedents(oc: str, out_dir: Path, limit: int | None = None) -> int:
    """

    Collect Supreme Court precedent full texts, appending and deduplicating.

    """
    out_path = out_dir / "precedents.jsonl"
    seen = load_seen(out_path)
    total = 0
    stopped = False
    with TemporaryDirectory(prefix=".precedents-", dir=out_dir) as temporary:
        staging = Path(temporary)
        staged_path = staging / out_path.name
        artifacts: list[tuple[Path, Path, str]] = []
        if out_path.exists():
            staged_path.write_bytes(out_path.read_bytes())
        with staged_path.open("a", encoding="utf-8", newline="\n") as handle:
            for keyword in PRECEDENT_KEYWORDS:
                found = search_precedents_with_publisher(oc, keyword)
                serials = [serial for serial, _publisher in found]
                publishers = {serial: publisher for serial, publisher in found}
                fresh = [serial for serial in serials if serial not in seen]
                print(f"  [{keyword}] {len(serials)} Supreme Court cases ({len(fresh)} new)")
                for serial in fresh:
                    if limit is not None and total >= limit:
                        print(f"  [LIMIT] reached {limit}, stopping")
                        stopped = True
                        break
                    staged_artifact = staging / "pending" / f"precedent-{len(artifacts)}.xml"
                    record = fetch_precedent(
                        oc,
                        serial,
                        artifact_path=staged_artifact,
                        publisher=publishers.get(serial, ""),
                    )
                    seen.add(serial)
                    if record:
                        raw_hash = artifact_hash(staged_artifact.read_bytes())
                        artifact_relative = _artifact_relative_path("precedent", raw_hash)
                        artifacts.append((staged_artifact, artifact_relative, raw_hash))
                        record["rawArtifactPath"] = artifact_relative.as_posix()
                        record["rawArtifactHash"] = raw_hash
                        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
                        total += 1
                if stopped:
                    break
        for staged_artifact, artifact_relative, raw_hash in artifacts:
            _publish_artifact(staged_artifact, out_dir, artifact_relative, raw_hash)
        staged_path.replace(out_path)
    print(f">>> {total} new precedents -> {out_path}")
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Collect raw legal data from the 법제처 API")
    parser.add_argument(
        "--oc",
        default=os.environ.get("LAW_OC"),
        help="your law.go.kr account id (or set LAW_OC). There is no shared default.",
    )
    parser.add_argument("--out", type=Path, default=Path("data/raw"), help="output directory")
    parser.add_argument("--laws-only", action="store_true")
    parser.add_argument("--prec-only", action="store_true")
    parser.add_argument("--limit", type=int, default=None, help="cap precedents (smoke test)")
    arguments = parser.parse_args()

    if not arguments.oc:
        parser.error(
            "no OC supplied. Apply for your own at law.go.kr -> 공동활용 -> OPEN API 활용신청 "
            "and pass --oc or set LAW_OC (docs/06_COLLECTION_RUNBOOK.md §1)."
        )

    arguments.out.mkdir(parents=True, exist_ok=True)
    print(f"OC={arguments.oc}  OUT={arguments.out.resolve()}")

    if not arguments.prec_only:
        print("\n[statutes]")
        collect_laws(arguments.oc, arguments.out)
    if not arguments.laws_only:
        print("\n[precedents]")
        collect_precedents(arguments.oc, arguments.out, limit=arguments.limit)

    print("\ndone.")


if __name__ == "__main__":
    main()
