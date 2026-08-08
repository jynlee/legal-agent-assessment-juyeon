"""Deterministic behavior of the source-record and release-manifest contract.

Every example here is synthetic. Real dataset payloads are never committed, but
the shapes are the ones the candidate corpus actually contains: placeholder
dates, a literal ``"null"`` disposition, a case number shared by two records,
and two guides numbered under different official schemes.
"""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from legal_agent_assessment import (
    CoverageEntry,
    DocumentKind,
    EvaluationLeakError,
    GuideIdentity,
    GuideNumberScheme,
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
    errors,
    select_index_inputs,
    summarize,
    validate_release,
)

ACQUIRED = datetime(2026, 8, 1, 9, 0, tzinfo=UTC)


def provenance(provider: str = "대법원", **overrides: object) -> SourceProvenance:
    fields: dict[str, object] = {
        "provider": provider,
        "publisher_statement": "법제처 국가법령정보 공동활용(www.law.go.kr)",
        "source_url": "https://www.law.go.kr/precInfoP.do?precSeq=000000",
        "source_reference": "국가법령정보센터 판례 000000",
        "acquired_at": ACQUIRED,
    }
    fields.update(overrides)
    return SourceProvenance.model_validate(fields)


def judgement(
    document_id: str = "precedent-000001",
    text: str = "【주 문】 원심판결을 파기한다.",
    **identity_overrides: object,
) -> SourceRecord:
    identity: dict[str, object] = {
        "case_serial": "000001",
        "case_name": "의료법위반",
        "case_number": "2099도1111",
        "court": "대법원",
        "case_category": "형사",
        "decided_on": "20990101",
        "judgement_type": "판결",
        "headnote": "판시사항 예시",
        "holding": "판결요지 예시",
        "referenced_provisions": "의료법 제27조",
        "referenced_precedents": "",
    }
    identity.update(identity_overrides)
    return SourceRecord(
        document_id=document_id,
        document_kind=DocumentKind.JUDGEMENT,
        title="의료법위반",
        text=text,
        content_hash=content_hash(text),
        identity=JudgementIdentity.model_validate(identity),
        provenance=provenance(),
        admission=SourceAdmission.EXEMPT,
        attribution="법제처 국가법령정보 공동활용",
        usage=UsageDisposition.INDEX_ELIGIBLE,
        linked_laws=(LawLinkage(law_name="의료법", strength=LinkageStrength.CORE),),
    )


def guide(
    document_id: str = "guide-000001",
    text: str = "이 안내서는 참고용입니다.",
    **overrides: object,
) -> SourceRecord:
    identity: dict[str, object] = {
        "issuing_authority": "보건복지부",
        "issuing_division": "보건의료정책과",
        "official_number": "00-0000000-000000-01",
        "official_number_scheme": GuideNumberScheme.PUBLICATION_REGISTRATION,
        "edition": "2판",
        "issued_on": "2099-12",
        "page_count": 108,
        "non_binding_statement": "이 가이드라인은 해설서이며 법적 효력을 가지지 않습니다.",
    }
    identity.update(overrides)
    return SourceRecord(
        document_id=document_id,
        document_kind=DocumentKind.OFFICIAL_GUIDE,
        title="유형별 의료광고 사례 및 체크리스트",
        text=text,
        content_hash=content_hash(text),
        identity=GuideIdentity.model_validate(identity),
        provenance=provenance(provider="보건복지부"),
        admission=SourceAdmission.LICENSED,
        attribution="보건복지부",
        usage=UsageDisposition.INDEX_ELIGIBLE,
        limitations=(
            "위반 사례 상당수가 본문이 아니라 이미지로 실려 있어 텍스트로 추출되지 않는다",
        ),
    )


def manifest(
    records: int = 2,
    kinds: tuple[tuple[str, int], ...] = (("judgement", 1), ("official_guide", 1)),
    providers: tuple[tuple[str, int], ...] = (("대법원", 1), ("보건복지부", 1)),
    usage: tuple[tuple[str, int], ...] = (("index_eligible", 2),),
) -> ReleaseManifest:
    return ReleaseManifest(
        dataset_version="dataset-v1",
        schema_version="source-record-v1",
        frozen_at=datetime(2026, 8, 9, 0, 0, tzinfo=UTC),
        delivery_id="delivery-0001",
        delivered_by="MZO",
        files=(
            ReleaseFile(
                path="records.jsonl",
                sha256="sha256:" + "0" * 64,
                byte_size=1024,
                record_count=records,
            ),
        ),
        coverage_by_document_kind=tuple(
            CoverageEntry(key=key, record_count=count) for key, count in kinds
        ),
        coverage_by_provider=tuple(
            CoverageEntry(key=key, record_count=count) for key, count in providers
        ),
        coverage_by_usage=tuple(CoverageEntry(key=key, record_count=count) for key, count in usage),
    )


class TestSourceRecord:
    def test_camel_case_round_trip_preserves_the_record(self) -> None:
        record = judgement()

        wire = record.model_dump(by_alias=True, mode="json")

        assert "documentId" in wire
        assert "document_id" not in wire
        assert wire["identity"]["caseSerial"] == "000001"
        assert SourceRecord.model_validate(wire) == record

    def test_identity_must_agree_with_the_declared_kind(self) -> None:
        with pytest.raises(ValidationError):
            SourceRecord.model_validate(
                judgement().model_dump(by_alias=True, mode="json")
                | {"documentKind": "official_guide"}
            )

    def test_restricted_material_cannot_be_index_eligible(self) -> None:
        with pytest.raises(ValidationError, match="restricted material cannot be index-eligible"):
            SourceRecord.model_validate(
                guide().model_dump(by_alias=True, mode="json") | {"admission": "restricted"}
            )

    def test_licensed_material_requires_an_attribution(self) -> None:
        with pytest.raises(ValidationError, match="licensed material requires an attribution"):
            SourceRecord.model_validate(
                guide().model_dump(by_alias=True, mode="json") | {"attribution": None}
            )

    def test_unknown_fields_are_refused(self) -> None:
        with pytest.raises(ValidationError):
            SourceRecord.model_validate(
                judgement().model_dump(by_alias=True, mode="json") | {"extra": "value"}
            )

    def test_a_law_may_be_linked_once(self) -> None:
        with pytest.raises(ValidationError, match="must not repeat a law name"):
            SourceRecord.model_validate(
                judgement().model_dump(by_alias=True, mode="json")
                | {
                    "linkedLaws": [
                        {"lawName": "의료법", "strength": "core"},
                        {"lawName": "의료법", "strength": "unlinked"},
                    ]
                }
            )

    def test_core_laws_exclude_mere_mentions(self) -> None:
        record = SourceRecord.model_validate(
            judgement().model_dump(by_alias=True, mode="json")
            | {
                "linkedLaws": [
                    {"lawName": "의료법", "strength": "core"},
                    {"lawName": "소비자기본법", "strength": "candidate"},
                    {"lawName": "표시광고법", "strength": "unlinked"},
                ]
            }
        )

        assert record.core_laws == ("의료법",)

    def test_a_retained_artifact_needs_both_path_and_hash(self) -> None:
        with pytest.raises(ValidationError, match="set together or not at all"):
            provenance(raw_artifact_path="source-native/000001.xml")

    def test_guide_carries_its_numbering_scheme(self) -> None:
        cosmetics = guide(
            document_id="guide-000002",
            official_number="안내서-0000-06",
            official_number_scheme=GuideNumberScheme.GUIDANCE_DOCUMENT,
            issuing_authority="식품의약품안전처",
            issuing_division="화장품정책과",
            edition=None,
            issued_on="2099-01-21",
            page_count=17,
        )

        assert isinstance(cosmetics.identity, GuideIdentity)
        assert cosmetics.identity.official_number_scheme is GuideNumberScheme.GUIDANCE_DOCUMENT
        assert cosmetics.identity.legally_binding is False

    def test_a_guide_publication_date_keeps_the_precision_its_source_states(self) -> None:
        assert guide(issued_on="2099").identity.issued_on == "2099"
        assert guide(issued_on="2099-12").identity.issued_on == "2099-12"

        with pytest.raises(ValidationError):
            guide(issued_on="2099-12-00")


class TestMissingValueConventions:
    """Three ways of saying "absent". Only the first one looks absent."""

    def test_empty_string_is_the_absent_value_not_a_missing_key(self) -> None:
        record = judgement(headnote="", holding="", referenced_provisions="")

        assert isinstance(record.identity, JudgementIdentity)
        assert record.identity.headnote == ""
        assert not record.identity.has_sentinel_date

    def test_placeholder_decision_date_is_detected(self) -> None:
        record = judgement(decided_on="00010101")

        assert isinstance(record.identity, JudgementIdentity)
        assert record.identity.has_sentinel_date

        findings = validate_release(
            [record],
            manifest(
                records=1,
                kinds=(("judgement", 1),),
                providers=(("대법원", 1),),
                usage=(("index_eligible", 1),),
            ),
        )

        assert "sentinel_decision_date" in summarize(findings)
        assert not errors(findings), "a placeholder describes the corpus; it does not block it"

    def test_literal_null_disposition_is_detected(self) -> None:
        record = judgement(judgement_type="null")

        assert isinstance(record.identity, JudgementIdentity)
        assert record.identity.has_sentinel_judgement_type
        assert record.identity.judgement_type, "the sentinel is non-empty, which is the whole trap"

    def test_a_record_with_only_full_text_is_reported(self) -> None:
        record = judgement(
            headnote="",
            holding="",
            referenced_provisions="",
            referenced_precedents="",
        )

        findings = validate_release(
            [record],
            manifest(
                records=1,
                kinds=(("judgement", 1),),
                providers=(("대법원", 1),),
                usage=(("index_eligible", 1),),
            ),
        )

        assert "body_only_judgement" in summarize(findings)


class TestReleaseValidation:
    def test_a_consistent_release_produces_no_errors(self) -> None:
        findings = validate_release([judgement(), guide()], manifest())

        assert errors(findings) == ()

    def test_content_hash_is_recomputed_from_the_supplied_text(self) -> None:
        tampered = SourceRecord.model_validate(
            judgement().model_dump(by_alias=True, mode="json") | {"text": "본문이 교체되었습니다."}
        )

        findings = validate_release([tampered, guide()], manifest())

        assert [finding.code for finding in errors(findings)] == ["content_hash_mismatch"]

    def test_duplicate_document_ids_block_the_release(self) -> None:
        findings = validate_release(
            [judgement(), judgement()],
            manifest(kinds=(("judgement", 2),), providers=(("대법원", 2),)),
        )

        codes = [finding.code for finding in errors(findings)]

        assert "duplicate_document_id" in codes

    def test_the_same_decision_under_two_serials_is_reported_without_blocking(self) -> None:
        findings = validate_release(
            [judgement(document_id="precedent-000001"), judgement(document_id="precedent-000002")],
            manifest(kinds=(("judgement", 2),), providers=(("대법원", 2),)),
        )

        assert "ungrouped_duplicate_decision" in summarize(findings)
        assert errors(findings) == (), "a duplicate describes the corpus; it does not block it"

    def test_a_shared_source_group_answers_the_duplicate(self) -> None:
        pair = [
            SourceRecord.model_validate(
                judgement(document_id=document_id).model_dump(by_alias=True, mode="json")
                | {"sourceGroupId": "group-2099do1111"}
            )
            for document_id in ("precedent-000001", "precedent-000002")
        ]

        codes = summarize(
            validate_release(pair, manifest(kinds=(("judgement", 2),), providers=(("대법원", 2),)))
        )

        assert "ungrouped_duplicate_decision" not in codes
        assert codes["duplicate_decision"] == 1

    def test_a_reused_case_number_across_courts_is_not_a_duplicate(self) -> None:
        findings = validate_release(
            [
                judgement(document_id="precedent-000001"),
                judgement(document_id="precedent-000002", court="서울고등법원"),
            ],
            manifest(kinds=(("judgement", 2),), providers=(("대법원", 2),)),
        )

        assert "ungrouped_duplicate_decision" not in summarize(findings)

    def test_manifest_record_count_must_match_what_was_supplied(self) -> None:
        findings = validate_release(
            [judgement()],
            manifest(
                records=2,
                kinds=(("judgement", 1),),
                providers=(("대법원", 1),),
                usage=(("index_eligible", 1),),
            ),
        )

        assert "record_count_mismatch" in [finding.code for finding in errors(findings)]

    def test_provider_coverage_must_match_what_was_supplied(self) -> None:
        findings = validate_release(
            [judgement(), guide()],
            manifest(providers=(("대법원", 2),)),
        )

        mismatches = [
            finding for finding in errors(findings) if finding.code == "coverage_mismatch"
        ]

        assert {finding.message.split("for ")[1].split(",")[0] for finding in mismatches} == {
            "'대법원'",
            "'보건복지부'",
        }

    def test_manifest_refuses_an_unknown_coverage_key(self) -> None:
        with pytest.raises(ValidationError, match="unknown keys"):
            manifest(kinds=(("statute", 2),))

    def test_manifest_refuses_a_repeated_file_path(self) -> None:
        base = manifest()
        with pytest.raises(ValidationError, match="must not repeat a path"):
            ReleaseManifest.model_validate(
                base.model_dump(by_alias=True, mode="json")
                | {
                    "files": [
                        base.files[0].model_dump(by_alias=True, mode="json"),
                        base.files[0].model_dump(by_alias=True, mode="json"),
                    ]
                }
            )

    def test_findings_carry_the_record_they_describe(self) -> None:
        findings = validate_release(
            [judgement(decided_on="00010101"), guide()],
            manifest(),
        )
        sentinel = next(f for f in findings if f.code == "sentinel_decision_date")

        assert sentinel.document_id == "precedent-000001"
        assert sentinel.severity is Severity.WARNING


class TestIndexInputBoundary:
    def test_eligible_records_pass_through(self) -> None:
        records = [judgement(), guide()]

        assert select_index_inputs(records) == tuple(records)

    def test_evaluation_only_material_cannot_be_indexed(self) -> None:
        evaluation_only = SourceRecord.model_validate(
            guide().model_dump(by_alias=True, mode="json")
            | {"usage": "evaluation_only", "admission": "restricted"}
        )

        with pytest.raises(EvaluationLeakError, match="must never be indexed"):
            select_index_inputs([judgement(), evaluation_only])

    def test_the_boundary_raises_instead_of_filtering(self) -> None:
        """A filtered pipeline keeps producing plausible numbers. A raised one stops."""

        evaluation_only = SourceRecord.model_validate(
            guide().model_dump(by_alias=True, mode="json") | {"usage": "evaluation_only"}
        )

        with pytest.raises(EvaluationLeakError) as caught:
            select_index_inputs([evaluation_only])

        assert "guide-000001" in str(caught.value)
        assert "usage is evaluation_only" in str(caught.value)

    def test_records_from_the_evaluation_tree_are_refused(self) -> None:
        from_evaluation = SourceRecord.model_validate(
            judgement().model_dump(by_alias=True, mode="json")
            | {
                "provenance": provenance(
                    raw_artifact_path="evaluation/queries/000001.json",
                    raw_artifact_hash="sha256:" + "a" * 64,
                ).model_dump(by_alias=True, mode="json")
            }
        )

        with pytest.raises(EvaluationLeakError, match="evaluation tree"):
            select_index_inputs([from_evaluation], evaluation_artifact_roots=("evaluation",))

    def test_a_sibling_directory_is_not_the_evaluation_tree(self) -> None:
        neighbour = SourceRecord.model_validate(
            judgement().model_dump(by_alias=True, mode="json")
            | {
                "provenance": provenance(
                    raw_artifact_path="evaluation-notes/000001.json",
                    raw_artifact_hash="sha256:" + "a" * 64,
                ).model_dump(by_alias=True, mode="json")
            }
        )

        assert select_index_inputs([neighbour], evaluation_artifact_roots=("evaluation",))
