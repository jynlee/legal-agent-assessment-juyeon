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

import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from legal_agent_assessment.dataset import (
    DocumentKind,
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


_DIGIT_MARKER = re.compile(r"^(\d+)\.(?!\d)\s*")
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
    decided_on: str
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
    seen_locators: set[str] = set()
    chunks: list[Chunk] = []
    for ordinal, piece in enumerate(prepared):
        if total == 1:
            locator = record.title
        elif piece.marker is not None:
            locator = f"{record.title} > {piece.marker}"
        else:
            locator = f"{record.title} (조각 {ordinal + 1}/{total})"
        if locator in seen_locators:
            locator = f"{locator} #{ordinal + 1}"
        seen_locators.add(locator)

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
    "chunk_statute_record",
    "find_table_spans",
    "pack_lines_to_budget",
    "paragraph_marker",
    "split_paragraphs",
    "split_sections",
    "split_statute_sections",
]
