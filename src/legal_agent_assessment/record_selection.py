"""Contributor-owned record-selection policy for what reaches the index.

MZO's dataset contract (`dataset.py`, `dataset_validation.py`) fixes what a
supplied record *is* and enforces the hard evaluation/restricted-material
boundary. It deliberately leaves record selection within the supplied
coverage to the contributor: "MZO fixes nothing downstream of that."
(DATASET_SCHEMA.md).

This module encodes this project's record-selection policy, decided in
`reports/decisions/2026-08-10-record-selection-and-document-kind-policy.md`:

- Records outside MZO's default corpus (`inDefaultCorpus: false`) are
  excluded. On the frozen 2026-08-09 release these are 109 records,
  dominated by tax and industrial-accident judgements that a full-text law
  search matched incidentally rather than records actually about the target
  domain.
- Within the default corpus, records missing every judgement summary field
  ("body-only") and records with no `core` law linkage are indexed like any
  other record, not filtered further. Neither condition affects citation
  validity: the citable text is `SourceRecord.text`, not the summary fields,
  and `linked_laws` strength describes a record's relevance grounds, not its
  eligibility for indexing. Downstream stages may still use
  `SourceRecord.linked_laws` and summary-field presence as signals; this
  module does not strip them.

`select_index_inputs` still runs last, so composing it after `default_corpus`
does not weaken its evaluation-leak boundary: a record can be inside the
default corpus and still have its raw artifact traced to an evaluation
artifact root, and that must still raise.

Decision 2 in the same note found that on the frozen 2026-08-09 release every
sentinel-valued record (placeholder `decidedOn`, literal `judgementType`
`"null"`) already falls inside the 109 records Decision 1 excludes, so no
separate sentinel-handling logic is needed *today*. `validate_release` still
reports sentinels as warnings rather than errors, because a sentinel outside
a contributor's indexed scope only describes the corpus. `default_corpus_sentinel_findings`
below is the check that keeps that a fact about this release instead of a
silent assumption about the next one.
"""

from collections.abc import Sequence

from legal_agent_assessment.dataset import SourceRecord, default_corpus
from legal_agent_assessment.dataset_validation import Finding, select_index_inputs

_SENTINEL_CODES = frozenset({"sentinel_decision_date", "sentinel_judgement_type"})


def select_records_for_indexing(
    records: Sequence[SourceRecord],
    *,
    evaluation_artifact_roots: Sequence[str] = (),
) -> tuple[SourceRecord, ...]:
    """Return the records this project indexes, or raise on a leak.

    Scopes to MZO's default corpus first, then applies the hard
    usage/admission/evaluation-artifact boundary from `select_index_inputs`.
    Body-only and no-core-linkage records inside the default corpus pass
    through unfiltered; see the module docstring for why.
    """

    return select_index_inputs(
        default_corpus(records),
        evaluation_artifact_roots=evaluation_artifact_roots,
    )


def default_corpus_sentinel_findings(
    records: Sequence[SourceRecord],
    findings: Sequence[Finding],
) -> tuple[Finding, ...]:
    """Sentinel findings whose record is inside this project's default corpus.

    `findings` is the output of `validate_release` for the same `records`.
    `validate_release` reports sentinels as warnings for the whole release,
    which is correct at the schema level: a sentinel outside a contributor's
    indexed scope is descriptive, not blocking. This project's policy is
    narrower — call the result non-empty and treat it as blocking, so a
    future release that puts a sentinel inside the default corpus cannot pass
    this check silently the way a generic warning count would.
    """

    in_scope = {record.document_id for record in default_corpus(records)}
    return tuple(
        finding
        for finding in findings
        if finding.code in _SENTINEL_CODES and finding.document_id in in_scope
    )


__all__ = ["default_corpus_sentinel_findings", "select_records_for_indexing"]
