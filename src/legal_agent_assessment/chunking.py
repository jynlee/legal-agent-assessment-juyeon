"""Deterministic normalization and chunking for default-corpus judgements.

Turns one `SourceRecord` (from `legal_agent_assessment.dataset`) into the
`body` and `summary` chunks this project indexes, per the design decided in
reports/decisions/2026-08-11-normalization-and-chunking-design.md. Pure:
no filesystem, network, or CLI access, matching AGENTS.md's separation of
deterministic logic from I/O.
"""

from dataclasses import dataclass
from enum import StrEnum

from legal_agent_assessment.dataset import DocumentKind, LawLinkage

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

    `\\n` is present in only a handful of records and is not the paragraph
    boundary; splitting on it would read most judgements as one unbroken
    line (DATASET_SCHEMA.md).
    """

    return tuple(piece.strip() for piece in text.split(_PARAGRAPH_SEP) if piece.strip())


@dataclass(frozen=True, slots=True)
class Chunk:
    """One indexable unit, traceable back to exactly one `SourceRecord`."""

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
    case_name: str
    court: str
    decided_on: str
    case_number: str
    locator: str
    linked_laws: tuple[LawLinkage, ...]
    issue_ordinal: int | None = None
    referenced_provisions: str = ""
    referenced_precedents: str = ""


__all__ = [
    "CHUNKING_VERSION",
    "NORMALIZATION_VERSION",
    "TARGET_MAX_CHARS",
    "Chunk",
    "ChunkType",
    "split_paragraphs",
]
