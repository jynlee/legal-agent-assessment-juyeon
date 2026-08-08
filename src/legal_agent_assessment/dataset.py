"""Frozen dataset release contract: supplied source records and the manifest.

MZO owns everything in this module. It fixes what one supplied record *is* —
identity, provenance, citation coordinates, admission, and usage disposition —
so that a submission can be reproduced and so the comparison does not become an
exercise in parsing heterogeneous files.

It deliberately stops there. Normalization, chunking, index mapping, retrieval,
test sets, and metrics are contributor-owned outputs and appear nowhere below.
Every indexed chunk must be traceable to exactly one `SourceRecord`, but the
shape of that chunk is not this contract's business.

Wire format is English ``camelCase`` per the Kit data contract; source-native
Korean keys are mapped at the collector boundary. Python attributes stay
``snake_case``, so both conventions hold at once.
"""

import re
from collections.abc import Iterable
from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic.alias_generators import to_camel

# Missing values arrive in three distinct shapes. Only the first announces
# itself; the other two are type-valid and read as present. See DATASET_SCHEMA.md.
EMPTY = ""
SENTINEL_DATE = "00010101"
SENTINEL_NULL_TEXT = "null"

DOCUMENT_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
SHA256_PATTERN = re.compile(r"^sha256:[0-9a-f]{64}$")
# YYYYMMDD exactly as delivered. Deliberately permissive: the placeholder
# 00010101 must survive the release unchanged, and is reported instead of
# rejected. See `JudgementIdentity.has_sentinel_date`.
COMPACT_DATE_PATTERN = re.compile(r"^\d{8}$")
# A guide states the precision its colophon actually carries. "2024. 12." is
# `2024-12`; padding it to a day would invent a source fact. Unlike the
# judgement date above this is transcribed by MZO rather than supplied by an
# API, so a zero month or day is a transcription error and is refused here.
PARTIAL_DATE_PATTERN = re.compile(r"^\d{4}(-(0[1-9]|1[0-2])(-(0[1-9]|[12]\d|3[01]))?)?$")


class DatasetModel(BaseModel):
    """Strict, hashable, camelCase-on-the-wire base for release contracts."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )


class DocumentKind(StrEnum):
    """Kinds that actually occur in the release.

    A new kind is a schema change, not a new enum value smuggled into a
    delivery: each kind carries its own required citation identity below.
    """

    JUDGEMENT = "judgement"
    OFFICIAL_GUIDE = "official_guide"


class UsageDisposition(StrEnum):
    """Whether a record may be indexed at all."""

    INDEX_ELIGIBLE = "index_eligible"
    EVALUATION_ONLY = "evaluation_only"


class SourceAdmission(StrEnum):
    """Collection gate carried forward so the release can be audited.

    `restricted` never reaches an index. It exists as a value because
    evaluation-only material can be restricted, and a schema that could not
    express that would push the fact into prose.
    """

    EXEMPT = "exempt"
    LICENSED = "licensed"
    RESTRICTED = "restricted"


class LinkageStrength(StrEnum):
    """How a supplied record relates to one target law.

    `core` means the law is an actual ground of the decision; `candidate` and
    `unlinked` mean the record surfaced through full-text search and mentions
    the law without deciding on it. Filtering on the law alone therefore does
    not give a set of decisions about that law.
    """

    CORE = "core"
    CANDIDATE = "candidate"
    UNLINKED = "unlinked"


class GuideNumberScheme(StrEnum):
    """Which official numbering system a guide's number belongs to.

    The two approved guides are numbered by different authorities under
    different systems, so the number alone does not identify what it is.
    """

    PUBLICATION_REGISTRATION = "publication_registration"
    GUIDANCE_DOCUMENT = "guidance_document"


class LawLinkage(DatasetModel):
    """One target law and this record's relationship to it."""

    law_name: str = Field(min_length=1)
    strength: LinkageStrength


class SourceProvenance(DatasetModel):
    """Where the supplied text came from and what was retained."""

    provider: str = Field(min_length=1)
    publisher_statement: str = Field(min_length=1)
    source_url: str | None = None
    source_reference: str = Field(min_length=1)
    acquired_at: datetime
    raw_artifact_path: str | None = None
    raw_artifact_hash: str | None = None

    @model_validator(mode="after")
    def validate_artifact_pair(self) -> "SourceProvenance":
        """Keep the retained-artifact claim checkable.

        Retaining the response bytes is a separate decision from recording
        where the text came from, so the pair is optional. A path without a
        hash reads as "artifact retained" while being uncheckable.
        """

        if (self.raw_artifact_path is None) != (self.raw_artifact_hash is None):
            raise ValueError("rawArtifactPath and rawArtifactHash are set together or not at all")
        if self.raw_artifact_hash is not None and not SHA256_PATTERN.match(self.raw_artifact_hash):
            raise ValueError("rawArtifactHash must be sha256:<64 lowercase hex>")
        return self


class JudgementIdentity(DatasetModel):
    """Citation coordinates for one court decision, as delivered.

    Values are preserved exactly as supplied, including the sentinels. The
    release does not repair them, because deciding what a missing decision date
    should become is a normalization choice this contract leaves open.
    """

    document_kind: Literal[DocumentKind.JUDGEMENT] = DocumentKind.JUDGEMENT
    case_serial: str = Field(min_length=1)
    case_name: str = Field(min_length=1)
    case_number: str = Field(min_length=1)
    court: str = Field(min_length=1)
    case_category: str = Field(min_length=1)
    decided_on: str = Field(pattern=COMPACT_DATE_PATTERN.pattern)
    judgement_type: str
    headnote: str = EMPTY
    holding: str = EMPTY
    referenced_provisions: str = EMPTY
    referenced_precedents: str = EMPTY

    @property
    def has_sentinel_date(self) -> bool:
        """True when the decision date is the placeholder, not a real date."""

        return self.decided_on == SENTINEL_DATE

    @property
    def has_sentinel_judgement_type(self) -> bool:
        """True when the disposition is the four-character string ``null``."""

        return self.judgement_type.strip().lower() == SENTINEL_NULL_TEXT


class GuideIdentity(DatasetModel):
    """Citation coordinates for one official guide.

    A guide has no case number, court, or decision date; it has an issuing
    authority, an official number under a named scheme, an edition, and pages.
    Both approved guides state in their own text that they carry no legal
    force, so `legally_binding` is fixed rather than supplied.
    """

    document_kind: Literal[DocumentKind.OFFICIAL_GUIDE] = DocumentKind.OFFICIAL_GUIDE
    issuing_authority: str = Field(min_length=1)
    issuing_division: str | None = None
    official_number: str = Field(min_length=1)
    official_number_scheme: GuideNumberScheme
    edition: str | None = None
    issued_on: str = Field(pattern=PARTIAL_DATE_PATTERN.pattern)
    page_count: int = Field(ge=1)
    legally_binding: Literal[False] = False
    non_binding_statement: str = Field(min_length=1)


SourceIdentity = Annotated[
    JudgementIdentity | GuideIdentity,
    Field(discriminator="document_kind"),
]


class SourceRecord(DatasetModel):
    """One supplied, independently citable source record.

    One record is one whole source document. A guide is delivered as a single
    record with its full text; splitting it into citable units is chunking, and
    chunking is contributor-owned.

    `source_group_id` is split safety, not identity. The corpus registers some
    decisions twice under different serial numbers, with text that is identical
    or near-identical. Records that are the same underlying decision share a
    group, so an evaluation split cannot put one of a pair in the test set and
    the other in the index and score the near-copy match as recall. It is
    optional because MZO assigns it during release preparation; a record
    without one is asserting nothing about grouping.
    """

    document_id: str = Field(pattern=DOCUMENT_ID_PATTERN.pattern)
    source_group_id: str | None = None
    document_kind: DocumentKind
    title: str = Field(min_length=1)
    text: str = Field(min_length=1)
    content_hash: str = Field(pattern=SHA256_PATTERN.pattern)
    identity: SourceIdentity
    provenance: SourceProvenance
    admission: SourceAdmission
    attribution: str | None = None
    usage: UsageDisposition
    linked_laws: tuple[LawLinkage, ...] = ()
    limitations: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_record(self) -> "SourceRecord":
        """Reject the combinations that would be unsafe or unreadable later."""

        if self.document_kind is not self.identity.document_kind:
            raise ValueError("documentKind must match the supplied citation identity")

        names = [linkage.law_name for linkage in self.linked_laws]
        if len(names) != len(set(names)):
            raise ValueError("linkedLaws must not repeat a law name")

        if (
            self.admission is SourceAdmission.RESTRICTED
            and self.usage is not UsageDisposition.EVALUATION_ONLY
        ):
            raise ValueError("restricted material cannot be index-eligible")
        if self.admission is SourceAdmission.LICENSED and not self.attribution:
            raise ValueError("licensed material requires an attribution")

        return self

    @property
    def core_laws(self) -> tuple[str, ...]:
        """Laws that are an actual ground of this record, not a mention."""

        return tuple(
            linkage.law_name
            for linkage in self.linked_laws
            if linkage.strength is LinkageStrength.CORE
        )

    @property
    def is_index_eligible(self) -> bool:
        """Whether this record may reach an embedding call or an index."""

        return self.usage is UsageDisposition.INDEX_ELIGIBLE


class ReleaseFile(DatasetModel):
    """One delivered file and the values that prove it arrived intact."""

    path: str = Field(min_length=1)
    sha256: str = Field(pattern=SHA256_PATTERN.pattern)
    byte_size: int = Field(ge=0)
    record_count: int = Field(ge=0)


class CoverageEntry(DatasetModel):
    """One counted slice of the release."""

    key: str = Field(min_length=1)
    record_count: int = Field(ge=0)


class DispositionNote(DatasetModel):
    """One inclusion or exclusion decision and the reason behind it."""

    subject: str = Field(min_length=1)
    included: bool
    reason: str = Field(min_length=1)


class LicenceNote(DatasetModel):
    """One licence or restricted-use condition attached to the release."""

    subject: str = Field(min_length=1)
    terms: str = Field(min_length=1)
    attribution_required: bool = False
    restricted_use: bool = False


class ReleaseManifest(DatasetModel):
    """The authoritative description of one frozen dataset release.

    This is what wins over examples, planning notes, and prose — including over
    every number written in this repository's documentation.
    """

    dataset_version: str = Field(min_length=1)
    schema_version: str = Field(min_length=1)
    frozen_at: datetime
    delivery_id: str = Field(min_length=1)
    delivered_by: str = Field(min_length=1)
    files: tuple[ReleaseFile, ...] = Field(min_length=1)
    coverage_by_document_kind: tuple[CoverageEntry, ...] = Field(min_length=1)
    coverage_by_provider: tuple[CoverageEntry, ...] = Field(min_length=1)
    coverage_by_usage: tuple[CoverageEntry, ...] = Field(min_length=1)
    dispositions: tuple[DispositionNote, ...] = ()
    licences: tuple[LicenceNote, ...] = ()
    known_gaps: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_manifest(self) -> "ReleaseManifest":
        """Reject a manifest that cannot be checked against the delivery."""

        paths = [file.path for file in self.files]
        if len(paths) != len(set(paths)):
            raise ValueError("files must not repeat a path")

        for label, entries in (
            ("coverageByDocumentKind", self.coverage_by_document_kind),
            ("coverageByProvider", self.coverage_by_provider),
            ("coverageByUsage", self.coverage_by_usage),
        ):
            keys = [entry.key for entry in entries]
            if len(keys) != len(set(keys)):
                raise ValueError(f"{label} must not repeat a key")

        for label, entries, allowed in (
            ("coverageByDocumentKind", self.coverage_by_document_kind, set(DocumentKind)),
            ("coverageByUsage", self.coverage_by_usage, set(UsageDisposition)),
        ):
            unknown = {entry.key for entry in entries} - {str(value) for value in allowed}
            if unknown:
                raise ValueError(f"{label} has unknown keys: {sorted(unknown)}")

        return self

    def total_records(self) -> int:
        """Records the manifest claims across every delivered file."""

        return sum(file.record_count for file in self.files)


def coverage_total(entries: Iterable[CoverageEntry]) -> int:
    """Sum one coverage breakdown."""

    return sum(entry.record_count for entry in entries)
