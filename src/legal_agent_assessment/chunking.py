"""Deterministic normalization and chunking for default-corpus judgements.

Turns one `SourceRecord` (from `legal_agent_assessment.dataset`) into the
`body` and `summary` chunks this project indexes, per the design decided in
reports/decisions/2026-08-11-normalization-and-chunking-design.md. Pure:
no filesystem, network, or CLI access, matching AGENTS.md's separation of
deterministic logic from I/O.
"""

import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from legal_agent_assessment.dataset import DocumentKind, LawLinkage, StatuteUnitKind

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
    r"(?:^|\n)(?P<marker>\d{1,3}|[가나다라마바사아자차카타파하]|[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)\.\s"
)


@dataclass(frozen=True, slots=True)
class StatuteSection:
    """One piece of a statute record's text, in document order."""

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
    marker inside a table row can never become a split point.
    """

    sections: list[StatuteSection] = []
    cursor = 0
    for start, end in table_spans:
        if start > cursor:
            sections.extend(_split_gap(text[cursor:start]))
        sections.append(StatuteSection(text=text[start:end], marker=None, is_table=True))
        cursor = end
    if cursor < len(text):
        sections.extend(_split_gap(text[cursor:]))
    return tuple(sections)


def _split_gap(gap: str) -> tuple[StatuteSection, ...]:
    """Split one table-free stretch of text at 호/목/로마숫자 markers.

    Piece boundaries are taken at `match.start("marker")`, not
    `match.start()` -- the latter includes the "\\n" the `(?:^|\\n)`
    alternative consumes for every marker after the first, which would leave
    a stray leading blank line on every piece but the first. Cutting at the
    marker itself and `.strip("\\n")`-ing each piece produces clean,
    directly embeddable text at the cost of not reproducing the original
    text byte-for-byte via concatenation (the marker-to-marker line breaks
    are dropped, not preserved) -- an accepted trade-off, since these pieces
    become `Chunk.text` and must read cleanly.
    """

    matches = list(_MARKER_RE.finditer(gap))
    if not matches:
        if gap.strip():
            return (StatuteSection(text=gap, marker=None, is_table=False),)
        return ()

    pieces: list[StatuteSection] = []
    first_marker_start = matches[0].start("marker")
    if first_marker_start > 0:
        preamble = gap[:first_marker_start].strip("\n")
        if preamble.strip():
            pieces.append(StatuteSection(text=preamble, marker=None, is_table=False))
    for i, match in enumerate(matches):
        piece_start = match.start("marker")
        piece_end = matches[i + 1].start("marker") if i + 1 < len(matches) else len(gap)
        piece_text = gap[piece_start:piece_end].rstrip("\n")
        if piece_text.strip():
            pieces.append(
                StatuteSection(text=piece_text, marker=match.group("marker"), is_table=False)
            )
    return tuple(pieces)


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


__all__ = [
    "CHUNKING_VERSION",
    "NORMALIZATION_VERSION",
    "TARGET_MAX_CHARS",
    "Chunk",
    "ChunkType",
    "JudgementChunkFields",
    "StatuteChunkFields",
    "StatuteSection",
    "find_table_spans",
    "pack_lines_to_budget",
    "split_paragraphs",
    "split_statute_sections",
]
