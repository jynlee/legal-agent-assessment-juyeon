"""Deterministic normalization and chunking for default-corpus judgements.

Turns one `SourceRecord` (from `legal_agent_assessment.dataset`) into the
`body` and `summary` chunks this project indexes, per the design decided in
reports/decisions/2026-08-11-normalization-and-chunking-design.md. Pure:
no filesystem, network, or CLI access, matching AGENTS.md's separation of
deterministic logic from I/O.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from legal_agent_assessment.dataset import DocumentKind, LawLinkage, StatuteUnitKind

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
    "split_paragraphs",
]
