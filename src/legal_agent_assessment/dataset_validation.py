"""Deterministic checks over a supplied release. No filesystem, no network.

Two jobs, kept apart on purpose.

`validate_release` reports. It answers "did this delivery arrive intact and does
it describe itself honestly", and it returns findings rather than raising, so a
caller sees every problem at once instead of the first one.

`select_index_inputs` refuses. It is the boundary between supplied material and
anything that reaches an embedding call or an index, and it raises, because a
caller that ignored a warning here would be indexing evaluation material and
scoring the leakage as recall.
"""

import hashlib
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum

from legal_agent_assessment.dataset import (
    CoverageEntry,
    JudgementIdentity,
    ReleaseManifest,
    SourceAdmission,
    SourceRecord,
    UsageDisposition,
    coverage_total,
)


class Severity(StrEnum):
    """Whether a finding blocks the release or describes it."""

    ERROR = "error"
    WARNING = "warning"


@dataclass(frozen=True, slots=True)
class Finding:
    """One deterministic observation about a release."""

    severity: Severity
    code: str
    message: str
    document_id: str | None = None


class EvaluationLeakError(RuntimeError):
    """Raised when material that must never be indexed reached the boundary."""


def content_hash(text: str) -> str:
    """Hash supplied text exactly as delivered, in the manifest's format."""

    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"


def _counts(entries: Iterable[CoverageEntry]) -> dict[str, int]:
    return {entry.key: entry.record_count for entry in entries}


def _compare_coverage(
    label: str,
    claimed: Sequence[CoverageEntry],
    actual: Counter[str],
) -> list[Finding]:
    findings: list[Finding] = []
    claimed_counts = _counts(claimed)
    for key in sorted(set(claimed_counts) | set(actual)):
        expected = claimed_counts.get(key, 0)
        observed = actual.get(key, 0)
        if expected != observed:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    code="coverage_mismatch",
                    message=(
                        f"{label} claims {expected} record(s) for {key!r}, "
                        f"but the supplied records contain {observed}"
                    ),
                )
            )
    return findings


def _record_findings(record: SourceRecord) -> list[Finding]:
    findings: list[Finding] = []

    if record.content_hash != content_hash(record.text):
        findings.append(
            Finding(
                severity=Severity.ERROR,
                code="content_hash_mismatch",
                message="contentHash does not match the supplied text",
                document_id=record.document_id,
            )
        )

    identity = record.identity
    if isinstance(identity, JudgementIdentity):
        if identity.has_sentinel_date:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    code="sentinel_decision_date",
                    message=(
                        f"decidedOn is the placeholder {identity.decided_on!r}; "
                        "it parses as a valid date and will pass a date filter silently"
                    ),
                    document_id=record.document_id,
                )
            )
        if identity.has_sentinel_judgement_type:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    code="sentinel_judgement_type",
                    message=(
                        f"judgementType is the literal string {identity.judgement_type!r}; "
                        "it is non-empty and would render into a citation as written"
                    ),
                    document_id=record.document_id,
                )
            )
        if not any(
            (
                identity.headnote,
                identity.holding,
                identity.referenced_provisions,
                identity.referenced_precedents,
            )
        ):
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    code="body_only_judgement",
                    message=(
                        "every summary and cross-reference field is empty; "
                        "only the full text is available for this record"
                    ),
                    document_id=record.document_id,
                )
            )

    if record.linked_laws and not record.core_laws:
        findings.append(
            Finding(
                severity=Severity.WARNING,
                code="no_core_linkage",
                message=(
                    "no linked law is a ground of this record; it matched full-text "
                    "search without deciding on any target law"
                ),
                document_id=record.document_id,
            )
        )

    return findings


def _duplicate_decision_findings(records: Sequence[SourceRecord]) -> list[Finding]:
    """Report decisions registered more than once under different serials.

    A shared case number, court, and decision date is the same decision, not a
    reused label: the corpus carries such pairs with identical or near-identical
    text. Splitting a pair across the index and the test set makes a near-copy
    match score as recall, which is why they must share a `sourceGroupId`.
    """

    findings: list[Finding] = []
    clusters: dict[tuple[str, str, str], list[SourceRecord]] = {}

    for record in records:
        identity = record.identity
        if isinstance(identity, JudgementIdentity):
            key = (identity.case_number, identity.court, identity.decided_on)
            clusters.setdefault(key, []).append(record)

    for (case_number, court, decided_on), cluster in sorted(clusters.items()):
        if len(cluster) < 2:
            continue

        listed = ", ".join(sorted(record.document_id for record in cluster))
        groups = {record.source_group_id for record in cluster}

        if None in groups or len(groups) > 1:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    code="ungrouped_duplicate_decision",
                    message=(
                        f"{len(cluster)} records share caseNumber {case_number!r}, "
                        f"court {court!r} and decidedOn {decided_on!r} without one "
                        f"sourceGroupId: {listed}. An evaluation split can separate "
                        "them and score the near-copy match as recall"
                    ),
                )
            )
        else:
            findings.append(
                Finding(
                    severity=Severity.WARNING,
                    code="duplicate_decision",
                    message=(
                        f"{len(cluster)} records are the same decision "
                        f"({case_number!r}) and share a sourceGroupId: {listed}. "
                        "Keep them on the same side of any evaluation split"
                    ),
                )
            )

    return findings


def validate_release(
    records: Sequence[SourceRecord],
    manifest: ReleaseManifest,
) -> tuple[Finding, ...]:
    """Check a supplied release against its manifest and report every finding.

    Errors mean the delivery cannot be trusted and must be reported to MZO
    rather than repaired locally. Warnings describe the corpus: they are the
    documented shapes a contributor has to decide how to handle.
    """

    findings: list[Finding] = []

    seen: Counter[str] = Counter(record.document_id for record in records)
    for document_id, count in sorted(seen.items()):
        if count > 1:
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    code="duplicate_document_id",
                    message=f"documentId appears {count} times; it must be unique",
                    document_id=document_id,
                )
            )

    findings.extend(_duplicate_decision_findings(records))

    for record in records:
        findings.extend(_record_findings(record))

    total = manifest.total_records()
    if total != len(records):
        findings.append(
            Finding(
                severity=Severity.ERROR,
                code="record_count_mismatch",
                message=(
                    f"manifest claims {total} record(s) across its files, "
                    f"but {len(records)} were supplied"
                ),
            )
        )

    findings.extend(
        _compare_coverage(
            "coverageByDocumentKind",
            manifest.coverage_by_document_kind,
            Counter(str(record.document_kind) for record in records),
        )
    )
    findings.extend(
        _compare_coverage(
            "coverageByProvider",
            manifest.coverage_by_provider,
            Counter(record.provenance.provider for record in records),
        )
    )
    findings.extend(
        _compare_coverage(
            "coverageByUsage",
            manifest.coverage_by_usage,
            Counter(str(record.usage) for record in records),
        )
    )

    for label, entries in (
        ("coverageByDocumentKind", manifest.coverage_by_document_kind),
        ("coverageByUsage", manifest.coverage_by_usage),
    ):
        if coverage_total(entries) != len(records):
            findings.append(
                Finding(
                    severity=Severity.ERROR,
                    code="coverage_total_mismatch",
                    message=(
                        f"{label} totals {coverage_total(entries)}, "
                        f"but {len(records)} record(s) were supplied"
                    ),
                )
            )

    return tuple(findings)


def errors(findings: Iterable[Finding]) -> tuple[Finding, ...]:
    """The subset that blocks a release."""

    return tuple(finding for finding in findings if finding.severity is Severity.ERROR)


def select_index_inputs(
    records: Sequence[SourceRecord],
    *,
    evaluation_artifact_roots: Sequence[str] = (),
) -> tuple[SourceRecord, ...]:
    """Return the records that may be embedded and indexed, or raise.

    This raises rather than filtering. Silently dropping an evaluation-only
    record would let a pipeline that was wired wrong keep producing plausible
    numbers, and the resulting recall would be measuring leakage.
    """

    leaks: list[str] = []
    eligible: list[SourceRecord] = []

    for record in records:
        reasons: list[str] = []
        if record.usage is not UsageDisposition.INDEX_ELIGIBLE:
            reasons.append(f"usage is {record.usage}")
        if record.admission is SourceAdmission.RESTRICTED:
            reasons.append("admission is restricted")

        path = record.provenance.raw_artifact_path
        if path is not None:
            for root in evaluation_artifact_roots:
                if path == root or path.startswith(root.rstrip("/") + "/"):
                    reasons.append(f"raw artifact is under the evaluation tree {root!r}")
                    break

        if reasons:
            leaks.append(f"{record.document_id}: {'; '.join(reasons)}")
        else:
            eligible.append(record)

    if leaks:
        listed = "\n  ".join(leaks)
        raise EvaluationLeakError(f"{len(leaks)} record(s) must never be indexed:\n  {listed}")

    return tuple(eligible)


def assert_supplied_by_manifest(
    records: Sequence[SourceRecord],
    manifest: ReleaseManifest,
) -> None:
    """Refuse to proceed when the records and the manifest disagree.

    Use this before indexing. `validate_release` reports the same disagreement
    without raising, which is what a delivery-inspection report wants.
    """

    blocking = errors(validate_release(records, manifest))
    if blocking:
        listed = "\n  ".join(f"[{finding.code}] {finding.message}" for finding in blocking)
        raise EvaluationLeakError(
            f"records do not match release {manifest.dataset_version}:\n  {listed}"
        )


def summarize(findings: Iterable[Finding]) -> dict[str, int]:
    """Count findings by code, for a delivery-inspection report."""

    return dict(sorted(Counter(finding.code for finding in findings).items()))


__all__ = [
    "EvaluationLeakError",
    "Finding",
    "Severity",
    "assert_supplied_by_manifest",
    "content_hash",
    "errors",
    "select_index_inputs",
    "summarize",
    "validate_release",
]
