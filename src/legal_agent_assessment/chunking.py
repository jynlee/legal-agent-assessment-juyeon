"""Deterministic normalization and chunking for default-corpus judgements
and statutes.

Turns one `SourceRecord` (from `legal_agent_assessment.dataset`) into the
chunks this project indexes: `body`/`summary` chunks for judgements per
reports/decisions/2026-08-11-normalization-and-chunking-design.md (model
only -- no producer function exists for judgements yet), and `body` chunks
for statutes per reports/decisions/2026-08-12-statute-chunking-design.md
(`chunk_statute_record`). Pure: no filesystem, network, or CLI access,
matching AGENTS.md's separation of deterministic logic from I/O.
"""

import itertools
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from legal_agent_assessment.dataset import (
    DocumentKind,
    JudgementIdentity,
    LawLinkage,
    SourceRecord,
    StatuteIdentity,
    StatuteUnitKind,
)
from legal_agent_assessment.dataset_validation import content_hash

_BOX_DRAWING_RE = re.compile(r"[┌┬┐│└┴┘├┤┼─━]")

NORMALIZATION_VERSION = "norm-v1"
CHUNKING_VERSION = "chunk-v1"

# Soft target only: packing fills a chunk until the next paragraph would
# exceed this, then closes it. There is no enforced minimum — a short
# section legitimately produces a short chunk.
TARGET_MAX_CHARS = 1500

_PARAGRAPH_SEP = "<br/>"


class ChunkType(StrEnum):
    """What a chunk's text was derived from."""

    BODY = "body"
    SUMMARY_HEADNOTE = "summary-headnote"
    SUMMARY_HOLDING = "summary-holding"


def split_paragraphs(text: str) -> tuple[str, ...]:
    """Split on the corpus's literal paragraph marker, never on `\\n`.

    `\\n` is present in only a handful of judgement records and is not the
    paragraph boundary there; splitting on it would read most judgements as
    one unbroken line (DATASET_SCHEMA.md). Statute text uses `\\n` as its
    real line boundary instead — see `find_table_spans` and
    `split_statute_sections`, which split statute text on `\\n`, not this
    function.
    """

    return tuple(piece.strip() for piece in text.split(_PARAGRAPH_SEP) if piece.strip())


_SECTION_HEADER = re.compile(r"【([^】]*)】")


def split_sections(text: str) -> tuple[tuple[str, str], ...]:
    """Split on bracketed section headers, matched in place.

    Headers in this corpus are padded with inter-character spacing
    (`【이    유】`, not `【이유】`) as a typesetting convention. The bracket
    pattern here tolerates any internal whitespace and reports the
    normalized name, but matches against the original text so the split
    position is exact and no prose is mutated. See Decision 3 in
    reports/decisions/2026-08-11-normalization-and-chunking-design.md.
    """

    matches = list(_SECTION_HEADER.finditer(text))
    if not matches:
        return (("", text),)

    sections: list[tuple[str, str]] = []
    if matches[0].start() > 0:
        sections.append(("", text[: matches[0].start()]))

    for index, match in enumerate(matches):
        name = re.sub(r"\s+", "", match.group(1))
        content_start = match.end()
        content_end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        sections.append((name, text[content_start:content_end]))

    return tuple(sections)


_DIGIT_MARKER = re.compile(r"^(\d{1,2})\.(?!\d)(?!\s*\d{1,2}\.)\s*")
_HANGUL_MARKER = re.compile(r"^([가-힣])\.\s*")
_PAREN_MARKER = re.compile(r"^\((\d+)\)\s*")


def paragraph_marker(paragraph: str) -> tuple[str, str] | None:
    """Return (level, label) if a paragraph opens with a numbered marker.

    Matches only at the very start of the paragraph, so an ordinary sentence
    is never mistaken for a marker unless it literally opens with a single
    enumerator character (가/나/다/...) followed by a period, which is the
    convention this corpus uses for lettered sub-items.
    """

    for level, pattern in (
        ("digit", _DIGIT_MARKER),
        ("hangul", _HANGUL_MARKER),
        ("paren", _PAREN_MARKER),
    ):
        match = pattern.match(paragraph)
        if match:
            label = f"({match.group(1)})" if level == "paren" else match.group(1)
            return (level, label)
    return None


def _build_locator(
    section_name: str,
    digit: str | None,
    hangul: str | None,
    paren: str | None,
) -> str:
    return " > ".join(part for part in (section_name, digit, hangul, paren) if part)


def _tag_paragraphs(section_name: str, paragraphs: Sequence[str]) -> tuple[tuple[str, str], ...]:
    """Attach a locator path to each paragraph in one section.

    A digit marker resets any hangul/paren sub-labels seen so far (a new
    "2." starts a new sub-item, so the previous "가"/"나" no longer apply); a
    hangul marker resets any paren sub-label. This produces paths like
    "이유 > 1 > 가" that match the section's actual nesting as it is read
    top to bottom -- the same hierarchy-path approach the statute chunker
    uses (reports/decisions/2026-08-12-statute-chunking-design.md, Decision
    5), scoped per section rather than per record since a judgement's
    section boundary already prevents a "1" in 【주문】 colliding with a "1"
    in 【이유】.
    """

    digit_label: str | None = None
    hangul_label: str | None = None
    paren_label: str | None = None
    tagged: list[tuple[str, str]] = []

    for paragraph in paragraphs:
        marker = paragraph_marker(paragraph)
        if marker is not None:
            level, label = marker
            if level == "digit":
                digit_label, hangul_label, paren_label = label, None, None
            elif level == "hangul":
                hangul_label, paren_label = label, None
            else:
                paren_label = label
        tagged.append(
            (_build_locator(section_name, digit_label, hangul_label, paren_label), paragraph)
        )

    return tuple(tagged)


_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _split_oversized(text: str, target_max: int) -> tuple[str, ...]:
    """Split one paragraph that alone exceeds the target, by sentence.

    Falls back to a hard character cut only if a single sentence itself
    still exceeds the target -- an explicit last resort, not a silent one.
    """

    sentences = [piece for piece in _SENTENCE_SPLIT.split(text) if piece]
    pieces: list[str] = []
    current = ""

    for sentence in sentences:
        if len(sentence) > target_max:
            if current:
                pieces.append(current)
                current = ""
            for start in range(0, len(sentence), target_max):
                pieces.append(sentence[start : start + target_max])
            continue
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) > target_max and current:
            pieces.append(current)
            current = sentence
        else:
            current = candidate

    if current:
        pieces.append(current)
    return tuple(pieces)


def _pack_located(
    paragraphs: Sequence[tuple[str, str]], *, target_max: int = TARGET_MAX_CHARS
) -> tuple[tuple[str, str], ...]:
    """Greedily pack consecutive (locator, text) pairs up to target_max chars.

    No overlap: a paragraph belongs to exactly one output chunk. A chunk's
    locator is its first paragraph's locator. A single paragraph exceeding
    target_max is flushed on its own and split further by
    `_split_oversized`, never force-joined with a neighbour.
    """

    packed: list[tuple[str, str]] = []
    group_locator: str | None = None
    group_parts: list[str] = []
    group_len = 0

    def flush() -> None:
        nonlocal group_locator, group_parts, group_len
        if group_parts:
            packed.append((group_locator or "", "\n\n".join(group_parts)))
        group_locator, group_parts, group_len = None, [], 0

    for locator, text in paragraphs:
        if len(text) > target_max:
            flush()
            for piece in _split_oversized(text, target_max):
                packed.append((locator, piece))
            continue

        joined_len = group_len + len(text) + (2 if group_parts else 0)
        if joined_len > target_max and group_parts:
            flush()
        if not group_parts:
            group_locator = locator
        group_parts.append(text)
        group_len += len(text) + (2 if len(group_parts) > 1 else 0)

    flush()
    return tuple(packed)


_ISSUE_MARKER = re.compile(r"\[(\d+)\]\s*")


def _clean_issue_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace(_PARAGRAPH_SEP, " ")).strip()


def extract_issues(field_text: str) -> dict[int, str]:
    """Split headnote/holding/referencedProvisions/referencedPrecedents by [N].

    An unnumbered field is treated as a single issue numbered 1 -- the
    majority shape for headnote on the frozen v1 release (364/676, 53.8%),
    not an edge case (Decision 4). Applying this rule identically to all
    four fields is what makes issue-number metadata matching safe: 0
    mismatches across 671 default-corpus records once the same rule is used
    on both sides (verification basis in the chunking design note).

    Adjacent markers with nothing but whitespace between them (e.g.
    "[1][2] <citation>") share the text that follows -- a real shape in
    referencedPrecedents where one citation supports multiple issues. A
    number repeated later in the field (e.g. "[1] a ... [1] b") accumulates
    rather than overwrites. Both were silent citation-loss bugs on the real
    release before this fix (Decision 5 addendum,
    reports/decisions/2026-08-11-normalization-and-chunking-design.md).
    """

    stripped = field_text.strip()
    if not stripped:
        return {}

    matches = list(_ISSUE_MARKER.finditer(stripped))
    if not matches:
        return {1: _clean_issue_text(stripped)}

    group_starts = [0]
    for i in range(1, len(matches)):
        if stripped[matches[i - 1].end() : matches[i].start()].strip():
            group_starts.append(i)
    group_starts.append(len(matches))

    accumulated: dict[int, list[str]] = {}
    for g in range(len(group_starts) - 1):
        group_begin, group_end = group_starts[g], group_starts[g + 1]
        numbers = [int(matches[k].group(1)) for k in range(group_begin, group_end)]
        text_start = matches[group_end - 1].end()
        text_end = matches[group_end].start() if group_end < len(matches) else len(stripped)
        text = _clean_issue_text(stripped[text_start:text_end]).rstrip("/ ").rstrip()
        if not text:
            continue
        for number in numbers:
            accumulated.setdefault(number, []).append(text)

    return {number: "; ".join(parts) for number, parts in accumulated.items()}


def find_table_spans(text: str) -> tuple[tuple[int, int], ...]:
    """Return non-overlapping (start, end) offsets of contiguous table-formatted line runs.

    A line counts as table-formatted if it contains a box-drawing character.
    Only strictly contiguous table-formatted lines merge into one span; a
    non-table line always ends the current span. Splitting must never happen
    inside a returned span (see `split_statute_sections`).
    """

    spans: list[tuple[int, int]] = []
    pos = 0
    span_start: int | None = None
    lines = text.split("\n")
    for line in lines:
        line_end = pos + len(line)
        is_table_line = bool(_BOX_DRAWING_RE.search(line))
        if is_table_line and span_start is None:
            span_start = pos
        elif not is_table_line and span_start is not None:
            spans.append((span_start, pos - 1))
            span_start = None
        pos = line_end + 1  # account for the "\n" this split() consumed
    if span_start is not None:
        spans.append((span_start, len(text)))
    return tuple(spans)


_MARKER_RE = re.compile(
    r"(?:^|\n)(?:(?P<roman>[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)|(?P<digit>\d{1,3})|(?P<gana>[가나다라마바사아자차카타파하]))\.\s"
)

_MARKER_LEVELS = {"roman": 0, "digit": 1, "gana": 2}


def _marker_level_group_and_text(match: re.Match[str]) -> tuple[int, str, int]:
    """Return (level, marker text, start offset of the marker group itself).

    Exactly one of the three named groups matches per `_MARKER_RE` hit;
    `level` orders them roman (0, outermost) > digit (1) > gana (2,
    innermost), matching how Korean statute structure nests 별표 major
    sections, 호, and 목.
    """

    for name, level in _MARKER_LEVELS.items():
        text = match.group(name)
        if text is not None:
            return level, text, match.start(name)
    raise AssertionError("marker regex matched with no named group set")


@dataclass(frozen=True, slots=True)
class StatuteSection:
    """One piece of a statute record's text, in document order.

    `marker`, when set, is the full open marker-hierarchy path at this
    piece (e.g. "1 > 가"), not just the leaf marker character -- see
    `_split_gap`.
    """

    text: str
    marker: str | None
    is_table: bool


def split_statute_sections(
    text: str, table_spans: tuple[tuple[int, int], ...]
) -> tuple[StatuteSection, ...]:
    """Split `text` at 호/목/로마숫자 markers outside `table_spans`.

    `table_spans` must be sorted, non-overlapping offsets from
    `find_table_spans`. Each span is kept as its own whole, unsplit
    `StatuteSection` -- the marker search never runs on that text, so a
    marker inside a table row can never become a split point. Marker
    hierarchy state (see `_split_gap`) carries across a table span rather
    than resetting at it.
    """

    sections: list[StatuteSection] = []
    cursor = 0
    path: dict[int, str] = {}
    for start, end in table_spans:
        if start > cursor:
            gap_sections, path = _split_gap(text[cursor:start], path)
            sections.extend(gap_sections)
        sections.append(StatuteSection(text=text[start:end], marker=None, is_table=True))
        cursor = end
    if cursor < len(text):
        gap_sections, path = _split_gap(text[cursor:], path)
        sections.extend(gap_sections)
    return tuple(sections)


def _split_gap(gap: str, path: dict[int, str]) -> tuple[tuple[StatuteSection, ...], dict[int, str]]:
    """Split one table-free stretch of text at 호/목/로마숫자 markers.

    `path` is the caller's currently-open marker hierarchy (level -> marker
    text), carried across gaps and table spans so a marker path like
    "1 > 가" stays correct even when a table interrupts the text between
    "1." and "가.". Returns the updated path so the caller can pass it into
    the next gap.

    Piece boundaries are taken at the marker group's own start offset, not
    the whole match's start -- the match also consumes the "\\n" the
    `(?:^|\\n)` alternative matches for every marker after the first, which
    would leave a stray leading blank line on every piece but the first.
    Cutting at the marker itself and `.strip("\\n")`-ing each piece produces
    clean, directly embeddable text (these pieces become `Chunk.text`).
    """

    matches = list(_MARKER_RE.finditer(gap))
    if not matches:
        if gap.strip():
            return (StatuteSection(text=gap.strip("\n"), marker=None, is_table=False),), path
        return (), path

    group_starts = [_marker_level_group_and_text(match)[2] for match in matches]

    pieces: list[StatuteSection] = []
    if group_starts[0] > 0:
        preamble = gap[: group_starts[0]].strip("\n")
        if preamble.strip():
            pieces.append(StatuteSection(text=preamble, marker=None, is_table=False))

    for i, match in enumerate(matches):
        level, marker_text, piece_start = _marker_level_group_and_text(match)
        for open_level in [lvl for lvl in path if lvl > level]:
            del path[open_level]
        path[level] = marker_text
        marker_path = " > ".join(path[lvl] for lvl in sorted(path))

        piece_end = group_starts[i + 1] if i + 1 < len(matches) else len(gap)
        piece_text = gap[piece_start:piece_end].rstrip("\n")
        if piece_text.strip():
            pieces.append(StatuteSection(text=piece_text, marker=marker_path, is_table=False))

    return tuple(pieces), path


def pack_lines_to_budget(text: str, target_max_chars: int = TARGET_MAX_CHARS) -> tuple[str, ...]:
    """Pack `text` into pieces up to `target_max_chars`, never splitting a line.

    Lines are rejoined with "\\n". A single line longer than
    `target_max_chars` becomes its own oversized piece rather than being cut
    mid-line: this function guarantees line integrity, not a hard size cap.
    """

    lines = text.split("\n")
    pieces: list[str] = []
    current: list[str] = []
    current_len = 0
    for line in lines:
        added_len = len(line) + (1 if current else 0)
        if current and current_len + added_len > target_max_chars:
            pieces.append("\n".join(current))
            current = [line]
            current_len = len(line)
        else:
            current.append(line)
            current_len += added_len
    if current:
        pieces.append("\n".join(current))
    return tuple(pieces)


@dataclass(frozen=True, slots=True)
class JudgementChunkFields:
    """Judgement-only citation and grouping data for one chunk.

    Model only in this plan — no function constructs this yet.
    See reports/decisions/2026-08-11-normalization-and-chunking-design.md.
    """

    case_name: str
    court: str
    decided_on: str | None
    case_number: str
    referenced_provisions: str = ""
    referenced_precedents: str = ""
    issue_ordinal: int | None = None


@dataclass(frozen=True, slots=True)
class StatuteChunkFields:
    """Statute-only citation and grouping data for one chunk."""

    law_name: str
    unit_kind: StatuteUnitKind
    article_number: str | None = None
    appendix_number: str | None = None
    status: Literal["current", "repealed"] = "current"
    layout: Literal["text", "table"] = "text"


@dataclass(frozen=True, slots=True)
class Chunk:
    """One indexable unit, traceable back to exactly one `SourceRecord`.

    `title`/`source_uri`/`official_number` are populated at chunking time so
    a `contracts.Citation` can be built from a `Chunk` alone, without
    re-opening the source `SourceRecord` (see
    reports/decisions/2026-08-12-statute-chunking-design.md, Decision 4).
    """

    chunk_id: str
    document_id: str
    chunk_type: ChunkType
    ordinal: int
    text: str
    content_hash: str
    document_kind: DocumentKind
    dataset_version: str
    normalization_version: str
    chunking_version: str
    title: str
    source_uri: str | None
    official_number: str | None
    locator: str
    linked_laws: tuple[LawLinkage, ...]
    kind_fields: JudgementChunkFields | StatuteChunkFields


def _digit_group_key(section_name: str, locator: str) -> str:
    """The locator prefix up to and including the digit-level marker, if any.

    Paragraphs sharing this key belong to the same numbered sub-section per
    Decision 2 and must never be packed into one chunk across a change in
    it -- packing across it let a single chunk's locator name only its
    first paragraph while covering several numbered items' text (measured:
    37.9% of body chunks on the real release before this fix). Paragraphs
    sharing one digit (e.g. "이유 > 1 > 가" and "이유 > 1 > 나") still pack
    together; only a change in the digit component itself ends a group.
    """

    prefix = f"{section_name} > "
    if not locator.startswith(prefix):
        return section_name
    first_segment = locator[len(prefix) :].split(" > ", 1)[0]
    return f"{section_name} > {first_segment}" if first_segment.isdigit() else section_name


def _dedupe_locator(locator: str, counts: dict[str, int]) -> str:
    """Disambiguate a repeated locator with a per-locator occurrence count.

    Unconditional: applied to every chunk regardless of whether the
    upstream splitting/packing logic makes a collision look unlikely, so
    distinctness is an invariant this function enforces rather than a
    property that depends on every corpus shape being anticipated
    correctly -- the same reasoning as this function's predecessor in each
    chunker (reports/decisions/2026-08-12-statute-chunking-design.md,
    Decision 5 revised; reports/decisions/2026-08-11-normalization-and-chunking-design.md,
    Decision 6 addendum). `counts` is the caller's per-record occurrence
    map, mutated in place.
    """

    counts[locator] = counts.get(locator, 0) + 1
    count = counts[locator]
    return locator if count == 1 else f"{locator} ({count})"


def chunk_body(record: SourceRecord, *, dataset_version: str) -> tuple[Chunk, ...]:
    """Split one judgement record's `text` into structure-aware, non-overlapping chunks.

    Walks section headers, then <br/>-paragraphs tagged with their marker
    path, then packs to TARGET_MAX_CHARS. See Decisions 2 and 3 of
    reports/decisions/2026-08-11-normalization-and-chunking-design.md.
    """

    identity = record.identity
    if not isinstance(identity, JudgementIdentity):
        raise TypeError("chunk_body requires a JudgementIdentity")

    # Pack each section independently (not the flattened whole-document
    # paragraph stream): a chunk must not span two different top-level
    # 【...】 sections, since that would mix, e.g., 【주문】 and 【이유】 content
    # into one citation with a misleading locator.
    packed: list[tuple[str, str]] = []
    for section_name, section_text in split_sections(record.text):
        paragraphs = split_paragraphs(section_text)
        located = _tag_paragraphs(section_name, paragraphs)
        for _key, group in itertools.groupby(
            located, key=lambda pair: _digit_group_key(section_name, pair[0])
        ):
            packed.extend(_pack_located(tuple(group)))

    locator_counts: dict[str, int] = {}
    chunks: list[Chunk] = []
    for ordinal, (locator, text) in enumerate(packed):
        locator = _dedupe_locator(locator, locator_counts)

        chunks.append(
            Chunk(
                chunk_id=f"{record.document_id}#{ChunkType.BODY}-{ordinal:03d}",
                document_id=record.document_id,
                chunk_type=ChunkType.BODY,
                ordinal=ordinal,
                text=text,
                content_hash=content_hash(text),
                document_kind=record.document_kind,
                dataset_version=dataset_version,
                normalization_version=NORMALIZATION_VERSION,
                chunking_version=CHUNKING_VERSION,
                title=record.title,
                source_uri=record.provenance.source_url,
                official_number=identity.case_number,
                locator=locator,
                linked_laws=record.linked_laws,
                kind_fields=JudgementChunkFields(
                    case_name=identity.case_name,
                    court=identity.court,
                    decided_on=None if identity.has_sentinel_date else identity.decided_on,
                    case_number=identity.case_number,
                ),
            )
        )
    return tuple(chunks)


_SUMMARY_FIELDS: tuple[tuple[ChunkType, str], ...] = (
    (ChunkType.SUMMARY_HEADNOTE, "판시사항"),
    (ChunkType.SUMMARY_HOLDING, "판결요지"),
)


def chunk_summary(record: SourceRecord, *, dataset_version: str) -> tuple[Chunk, ...]:
    """One chunk per numbered issue in headnote and holding.

    referencedProvisions/referencedPrecedents are never embedded (they are
    citation lists, not prose) but are attached verbatim to the matching
    issue's chunk, keyed by the same issue number. See Decision 5 of
    reports/decisions/2026-08-11-normalization-and-chunking-design.md.
    """

    identity = record.identity
    if not isinstance(identity, JudgementIdentity):
        raise TypeError("chunk_summary requires a JudgementIdentity")

    provisions = extract_issues(identity.referenced_provisions)
    precedents = extract_issues(identity.referenced_precedents)

    chunks: list[Chunk] = []
    for chunk_type, locator_label in _SUMMARY_FIELDS:
        field_text = (
            identity.headnote if chunk_type is ChunkType.SUMMARY_HEADNOTE else identity.holding
        )
        issues = extract_issues(field_text)
        for ordinal, issue_number in enumerate(sorted(issues)):
            text = issues[issue_number]
            if not text:
                continue
            chunks.append(
                Chunk(
                    chunk_id=f"{record.document_id}#{chunk_type}-{ordinal:03d}",
                    document_id=record.document_id,
                    chunk_type=chunk_type,
                    ordinal=ordinal,
                    text=text,
                    content_hash=content_hash(text),
                    document_kind=record.document_kind,
                    dataset_version=dataset_version,
                    normalization_version=NORMALIZATION_VERSION,
                    chunking_version=CHUNKING_VERSION,
                    title=record.title,
                    source_uri=record.provenance.source_url,
                    official_number=identity.case_number,
                    locator=f"{locator_label} [{issue_number}]",
                    linked_laws=record.linked_laws,
                    kind_fields=JudgementChunkFields(
                        case_name=identity.case_name,
                        court=identity.court,
                        decided_on=None if identity.has_sentinel_date else identity.decided_on,
                        case_number=identity.case_number,
                        referenced_provisions=provisions.get(issue_number, ""),
                        referenced_precedents=precedents.get(issue_number, ""),
                        issue_ordinal=issue_number,
                    ),
                )
            )
    return tuple(chunks)


def chunk_record(record: SourceRecord, *, dataset_version: str) -> tuple[Chunk, ...]:
    """All chunks for one judgement record: body chunks, then summary chunks."""

    return chunk_body(record, dataset_version=dataset_version) + chunk_summary(
        record, dataset_version=dataset_version
    )


_REPEALED_RE = re.compile(r"^제\d+조(?:의\d+)?\s*삭제\b")


def _is_repealed_placeholder(text: str) -> bool:
    """True when `text` is a repeal placeholder like '제19조 삭제 <2011.3.30>'."""

    return bool(_REPEALED_RE.match(text.strip()))


def chunk_statute_record(record: SourceRecord, dataset_version: str) -> tuple[Chunk, ...]:
    """Turn one `statute` `SourceRecord` into one or more `Chunk`s.

    Implements reports/decisions/2026-08-12-statute-chunking-design.md.
    """

    identity = record.identity
    if not isinstance(identity, StatuteIdentity):
        raise TypeError("chunk_statute_record requires a StatuteIdentity")

    status: Literal["current", "repealed"] = (
        "repealed" if _is_repealed_placeholder(record.text) else "current"
    )

    if len(record.text) < TARGET_MAX_CHARS:
        prepared: list[StatuteSection] = [
            StatuteSection(text=record.text, marker=None, is_table=False)
        ]
    else:
        table_spans = find_table_spans(record.text)
        sections = split_statute_sections(record.text, table_spans)
        prepared = []
        for section in sections:
            if len(section.text) < TARGET_MAX_CHARS:
                prepared.append(section)
                continue
            packed_texts = pack_lines_to_budget(section.text)
            if len(packed_texts) == 1:
                prepared.append(
                    StatuteSection(
                        text=packed_texts[0], marker=section.marker, is_table=section.is_table
                    )
                )
            else:
                for i, packed_text in enumerate(packed_texts, start=1):
                    sub_marker = (
                        f"{section.marker} (조각 {i}/{len(packed_texts)})"
                        if section.marker is not None
                        else None
                    )
                    prepared.append(
                        StatuteSection(
                            text=packed_text, marker=sub_marker, is_table=section.is_table
                        )
                    )

    total = len(prepared)
    locator_counts: dict[str, int] = {}
    chunks: list[Chunk] = []
    for ordinal, piece in enumerate(prepared):
        if total == 1:
            locator = record.title
        elif piece.marker is not None:
            locator = f"{record.title} > {piece.marker}"
        else:
            locator = f"{record.title} (조각 {ordinal + 1}/{total})"
        locator = _dedupe_locator(locator, locator_counts)

        chunks.append(
            Chunk(
                chunk_id=f"{record.document_id}#{ChunkType.BODY}-{ordinal:03d}",
                document_id=record.document_id,
                chunk_type=ChunkType.BODY,
                ordinal=ordinal,
                text=piece.text,
                content_hash=content_hash(piece.text),
                document_kind=DocumentKind.STATUTE,
                dataset_version=dataset_version,
                normalization_version=NORMALIZATION_VERSION,
                chunking_version=CHUNKING_VERSION,
                title=record.title,
                source_uri=record.provenance.source_url,
                official_number=identity.mst,
                locator=locator,
                linked_laws=record.linked_laws,
                kind_fields=StatuteChunkFields(
                    law_name=identity.law_name,
                    unit_kind=identity.unit_kind,
                    article_number=identity.article_number,
                    appendix_number=identity.appendix_number,
                    status=status,
                    layout="table" if piece.is_table else "text",
                ),
            )
        )

    return tuple(chunks)


__all__ = [
    "CHUNKING_VERSION",
    "NORMALIZATION_VERSION",
    "TARGET_MAX_CHARS",
    "Chunk",
    "ChunkType",
    "JudgementChunkFields",
    "StatuteChunkFields",
    "StatuteSection",
    "chunk_body",
    "chunk_record",
    "chunk_statute_record",
    "chunk_summary",
    "extract_issues",
    "find_table_spans",
    "pack_lines_to_budget",
    "paragraph_marker",
    "split_paragraphs",
    "split_sections",
    "split_statute_sections",
]
