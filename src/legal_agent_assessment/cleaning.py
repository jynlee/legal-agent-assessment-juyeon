"""Korean legal-text cleaning. Domain rules only; generic ones are in `textnorm`.

Ported from Peitho `scripts/clean_legal_raw.py` (baseline b38f308) so that a
delivered corpus survives re-processing on the Peitho side unchanged. Rules and
their reasons:

- [법령] strip `<개정/신설/전문개정 …>` history markers — articles amended together
  on one date get bound by the date text, which is vector noise, and the use case
  is a current-state query.
- [법령] deduplicate the 항/호/목 number the source API emits twice (once on its
  own line, once at the start of the body line).
- [common] `<img …>` -> '[이미지N]' index markers, same `src` sharing a number.
- [판례] clean the summary metadata fields too — summary-centric chunking makes
  those fields the chunk body.
- [판례] deduplicate by 사건번호, keeping the longest version — the same judgement
  is collected under different 판례일련번호.

Preserved (never touched): line-break structure (항 boundaries), 판례 section
markers 【…】, article headers, ASCII box-drawing tables.
"""

import re
from collections import Counter
from collections.abc import Callable
from html import unescape
from typing import Any

from legal_agent_assessment import textnorm
from legal_agent_assessment.textnorm import restore_item_breaks

NORMALIZATION_VERSION = "kit-clean-v2"
"""

Bump whenever a rule below changes the output. `SourceDocument.normalizationVersion`
records it, so a corpus can be told apart from one built under older rules.

"""

_AMEND_RE = re.compile(r"\s*<(?:개정|신설|전문개정)[^>]*>")
_DELETED_RE = re.compile(r"^제\d+조(의\d+)?\s*(\([^)]*\))?\s*삭제")
_PRECEDENT_META_FIELDS = ("판시사항", "판결요지", "참조조문", "참조판례")

# The source API emits each numbering token (항 ①-⑮, 호 "1.", 목 "가.") on its own
# line and again at the start of the body line. This matches a number-only line
# immediately followed by a line starting with the SAME token, and drops the
# number-only line (the body keeps its number). Requiring an exact repeat is what
# makes the wide [가-힣] class safe here.
_NUM_TOKEN = r"(?:[①-⑮]|\d{1,3}\.|[가-힣]\.)"
_DUP_NUMBER_RE = re.compile(rf"^(?P<tok>{_NUM_TOKEN})[ \t]*\n(?=(?P=tok))", re.MULTILINE)


def clean_law(content: str, stats: Counter[str]) -> str:
    """

    Clean one 법령 article: image index markers, amendment-history removal,
    character/whitespace normalization, numbering deduplication. Angle notation
    other than the amendment markers is left alone.

    """
    content, images = textnorm.index_image_markers(content)
    stats["images_indexed"] += images
    stats["amend_removed"] += len(_AMEND_RE.findall(content))
    content = _AMEND_RE.sub("", content)
    stats["dots_unified"] += textnorm.count_dot_variants(content)
    content = textnorm.normalize_whitespace(textnorm.normalize_chars(content))
    content, duplicates = _DUP_NUMBER_RE.subn("", content)
    stats["numbers_deduped"] += duplicates
    return content


def clean_instrument_body(content: str, stats: Counter[str]) -> str:
    """

    Clean a 별표 or 행정규칙 body, which arrives as one undivided instrument.

    This is the caller `textnorm.restore_item_breaks` was written for and did not
    have in Peitho: markers must be restored **before anything else touches the
    text**, because a citation locator is the 목 number. Cleaning otherwise
    follows the 법령 path.

    Restoration only handles markers already separated by a space, so ingestion
    must still assert that the expected 목 text arrived — see
    `docs/06_COLLECTION_RUNBOOK.md`.

    """
    return clean_law(restore_item_breaks(content), stats)


def clean_precedent(content: str, stats: Counter[str]) -> str:
    """

    Clean 판례 or sanction-decision text: image index markers, `<br>` to newline
    (paragraph boundaries preserved), residual-HTML safety net, entity decoding,
    character/whitespace normalization.

    """
    content, images = textnorm.index_image_markers(content)
    stats["images_indexed"] += images
    content, breaks = textnorm.replace_br(content)
    stats["br_replaced"] += breaks
    content, residual = textnorm.strip_html_tags(content)
    stats["residual_tags"] += residual
    # Entity decoding is the one rule this kit adds to the ported set. Peitho's
    # `corpus_stats.py` measures entities as an input to the clean spec, but the
    # production cleaner does not decode them yet, so decoded output is a
    # deliberate, counted difference to port back — not a silent divergence.
    # It runs after tag stripping so an encoded '&lt;b&gt;' cannot turn into a tag
    # that the safety net would then remove.
    decoded = unescape(content)
    stats["entities_unescaped"] += int(decoded != content)
    content = decoded
    stats["dots_unified"] += textnorm.count_dot_variants(content)
    return textnorm.normalize_whitespace(textnorm.normalize_chars(content))


def clean_precedent_record[RecordT: dict[str, Any]](
    record: RecordT, stats: Counter[str]
) -> RecordT:
    """

    Clean a 판례 record: `content` and every summary metadata field
    (판시사항/판결요지/참조조문/참조판례), because summary-centric chunking makes
    those fields the chunk body.

    """
    record["content"] = clean_precedent(record["content"], stats)
    for field in _PRECEDENT_META_FIELDS:
        if record.get(field):
            record[field] = clean_precedent(record[field], stats)
    return record


def is_deleted_article(content: str) -> bool:
    """

    Whether a cleaned article is a deleted shell ("제N조 삭제 <날짜>").

    A deleted 별표 or article is a short `삭제` body, not an absent record, so it
    looks like data until this check separates it.

    """
    return bool(_DELETED_RE.match(content.strip()))


def dedupe_precedents[RecordT: dict[str, Any]](
    records: list[RecordT], stats: Counter[str]
) -> tuple[list[RecordT], list[RecordT]]:
    """

    Deduplicate by 사건번호, keeping the longest `content` (ties keep the one
    collected first). Excluded records carry a 제외사유 and are returned
    separately rather than dropped.

    """
    best_by_case: dict[str, RecordT] = {}
    for record in records:
        case_number = record.get("사건번호", "")
        current = best_by_case.get(case_number)
        if current is None or len(record["content"]) > len(current["content"]):
            best_by_case[case_number] = record
    kept: list[RecordT] = []
    excluded: list[RecordT] = []
    for record in records:
        case_number = record.get("사건번호", "")
        if best_by_case.get(case_number) is record:
            kept.append(record)
            continue
        keeper = best_by_case[case_number]
        serial = keeper.get("판례일련번호", "?")
        record["제외사유"] = f"사건번호 중복(보존본: 판례일련번호 {serial})"
        excluded.append(record)
        stats["dup_removed"] += 1
    return kept, excluded


def verify_idempotent(
    cleaner: Callable[[str, Counter[str]], str],
    cleaned_contents: list[str],
    stats: Counter[str],
) -> int:
    """

    Assert that cleaning an already-cleaned body again changes nothing.

    A rule that is not idempotent silently rewrites the corpus on every re-run,
    which moves `contentHash` and therefore every derived identifier. Returns the
    violation count and records it in `stats`.

    """
    violations = 0
    for content in cleaned_contents:
        if cleaner(content, Counter()) != content:
            violations += 1
    stats["idempotency_violations"] += violations
    return violations


__all__ = [
    "NORMALIZATION_VERSION",
    "clean_instrument_body",
    "clean_law",
    "clean_precedent",
    "clean_precedent_record",
    "dedupe_precedents",
    "is_deleted_article",
    "restore_item_breaks",
    "verify_idempotent",
]
