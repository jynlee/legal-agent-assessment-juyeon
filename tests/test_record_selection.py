"""This project's record-selection policy: what actually reaches the index.

Every example here is synthetic, matching the shapes described in
reports/decisions/2026-08-10-record-selection-and-document-kind-policy.md.
Real dataset payloads are never committed.
"""

from datetime import UTC, datetime

import pytest

from legal_agent_assessment import (
    CoverageEntry,
    DocumentKind,
    EvaluationLeakError,
    Finding,
    JudgementIdentity,
    LawLinkage,
    LinkageStrength,
    ReleaseFile,
    ReleaseManifest,
    Severity,
    SourceAdmission,
    SourceProvenance,
    SourceRecord,
    UsageDisposition,
    content_hash,
    validate_release,
)
from legal_agent_assessment.record_selection import (
    default_corpus_sentinel_findings,
    select_records_for_indexing,
)

ACQUIRED = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)

DEFAULT_LINKED_LAWS = (LawLinkage(law_name="의료법", strength=LinkageStrength.CORE),)


def judgement(
    document_id: str = "precedent-000001",
    text: str = "【주 문】 원심판결을 파기한다.",
    in_default_corpus: bool = True,
    linked_laws: tuple[LawLinkage, ...] = DEFAULT_LINKED_LAWS,
    headnote: str = "판시사항 예시",
    holding: str = "판결요지 예시",
    referenced_provisions: str = "의료법 제27조",
    referenced_precedents: str = "",
    raw_artifact_path: str | None = None,
    decided_on: str = "20990101",
    judgement_type: str = "판결",
) -> SourceRecord:
    identity = JudgementIdentity(
        case_serial=document_id,
        case_name="의료법위반",
        case_number="2099도1111",
        court="대법원",
        case_category="형사",
        decided_on=decided_on,
        judgement_type=judgement_type,
        headnote=headnote,
        holding=holding,
        referenced_provisions=referenced_provisions,
        referenced_precedents=referenced_precedents,
    )
    provenance_fields: dict[str, object] = {
        "provider": "대법원",
        "publisher_statement": "법제처 국가법령정보 공동활용(www.law.go.kr)",
        "source_reference": "국가법령정보센터 판례 000000",
        "acquired_at": ACQUIRED,
    }
    if raw_artifact_path is not None:
        provenance_fields["raw_artifact_path"] = raw_artifact_path
        provenance_fields["raw_artifact_hash"] = "sha256:" + "a" * 64

    return SourceRecord(
        document_id=document_id,
        document_kind=DocumentKind.JUDGEMENT,
        title="의료법위반",
        text=text,
        content_hash=content_hash(text),
        identity=identity,
        provenance=SourceProvenance(**provenance_fields),
        admission=SourceAdmission.EXEMPT,
        attribution="법제처 국가법령정보 공동활용",
        usage=UsageDisposition.INDEX_ELIGIBLE,
        in_default_corpus=in_default_corpus,
        linked_laws=linked_laws,
    )


def manifest(document_id: str = "precedent-000001") -> ReleaseManifest:
    return ReleaseManifest(
        dataset_version="dataset-v1",
        schema_version="source-record-v1",
        frozen_at=ACQUIRED,
        delivery_id="delivery-0001",
        delivered_by="MZO",
        files=(
            ReleaseFile(
                path="judgements.jsonl",
                sha256="sha256:" + "0" * 64,
                byte_size=1024,
                record_count=1,
            ),
        ),
        coverage_by_document_kind=(CoverageEntry(key="judgement", record_count=1),),
        coverage_by_provider=(CoverageEntry(key="대법원", record_count=1),),
        coverage_by_usage=(CoverageEntry(key="index_eligible", record_count=1),),
    )


def test_records_outside_the_default_corpus_are_excluded() -> None:
    inside = judgement(document_id="precedent-000001")
    outside = judgement(document_id="precedent-000002", in_default_corpus=False)

    result = select_records_for_indexing([inside, outside])

    assert result == (inside,)


def test_body_only_records_inside_the_default_corpus_are_still_indexed() -> None:
    body_only = judgement(
        headnote="",
        holding="",
        referenced_provisions="",
        referenced_precedents="",
    )

    assert select_records_for_indexing([body_only]) == (body_only,)


def test_no_core_linkage_records_are_indexed_with_their_linkage_preserved() -> None:
    unlinked_only = judgement(
        linked_laws=(LawLinkage(law_name="소비자기본법", strength=LinkageStrength.UNLINKED),),
    )

    result = select_records_for_indexing([unlinked_only])

    assert result == (unlinked_only,)
    assert result[0].core_laws == ()
    assert result[0].linked_laws[0].strength is LinkageStrength.UNLINKED


def test_an_evaluation_artifact_leak_inside_the_default_corpus_still_raises() -> None:
    """default_corpus() narrows scope; it must not weaken the leak boundary."""

    leaking = judgement(raw_artifact_path="evaluation/queries/000001.json")

    with pytest.raises(EvaluationLeakError, match="evaluation tree"):
        select_records_for_indexing([leaking], evaluation_artifact_roots=("evaluation",))


def test_todays_release_shape_has_no_sentinel_inside_the_default_corpus() -> None:
    """Decision 2: on the frozen 2026-08-09 release, every sentinel-valued
    record falls inside the 109 excluded by Decision 1, so today this must be
    empty. This pins that fact down as a synthetic regression case rather
    than leaving it as an unchecked claim in the decision note."""

    sentinel_but_out_of_scope = judgement(
        document_id="precedent-000002",
        in_default_corpus=False,
        decided_on="00010101",
        judgement_type="null",
    )

    findings = validate_release([sentinel_but_out_of_scope], manifest("precedent-000002"))

    assert default_corpus_sentinel_findings([sentinel_but_out_of_scope], findings) == ()


def test_a_future_sentinel_inside_the_default_corpus_is_not_silent() -> None:
    """The regression case Decision 2 exists to guard against: a later
    release could put a sentinel-valued record inside the default corpus.
    validate_release alone would not stop that (sentinels are warnings, by
    design, since they only describe the corpus in general). This is the
    check that must catch it instead."""

    sentinel_in_scope = judgement(decided_on="00010101", judgement_type="null")

    findings = validate_release([sentinel_in_scope], manifest())
    caught = default_corpus_sentinel_findings([sentinel_in_scope], findings)

    assert {finding.code for finding in caught} == {
        "sentinel_decision_date",
        "sentinel_judgement_type",
    }
    assert all(finding.document_id == "precedent-000001" for finding in caught)


def test_unrelated_default_corpus_findings_are_not_flagged_as_sentinels() -> None:
    inside = judgement()
    unrelated = Finding(
        severity=Severity.WARNING,
        code="body_only_judgement",
        message="every summary field is empty",
        document_id=inside.document_id,
    )

    assert default_corpus_sentinel_findings([inside], [unrelated]) == ()
