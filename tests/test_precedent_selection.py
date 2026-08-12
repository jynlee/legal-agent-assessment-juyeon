"""Deterministic precedent selection for the fixed aesthetic-domain boundary."""

from legal_agent_assessment.precedent_selection import (
    PRECEDENT_SELECTION_POLICY_VERSION,
    ReasonCode,
    SelectionDecision,
    select_precedent,
)


def precedent(**overrides: object) -> dict[str, object]:
    """Return a synthetic collected precedent."""

    row: dict[str, object] = {
        "판례일련번호": "000001",
        "사건명": "의료법위반",
        "사건번호": "2099도1111",
        "법원명": "대법원",
        "선고일자": "20990101",
        "content": "피부관리실 운영자가 레이저 시술을 하여 무면허 의료행위로 기소되었다.",
    }
    row.update(overrides)
    return row


def test_clear_aesthetic_legal_issue_is_included() -> None:
    result = select_precedent(
        precedent(),
        linkage="core",
        matched_laws=("의료법",),
    )

    assert result.decision is SelectionDecision.INCLUDE
    assert result.policy_version == PRECEDENT_SELECTION_POLICY_VERSION
    assert ReasonCode.AESTHETIC_SUBJECT_MATCH in result.reason_codes
    assert ReasonCode.LEGAL_ISSUE_MATCH in result.reason_codes


def test_unlinked_keyword_noise_is_excluded() -> None:
    result = select_precedent(precedent(), linkage="unlinked", matched_laws=())

    assert result.decision is SelectionDecision.EXCLUDE
    assert result.reason_codes == (ReasonCode.TARGET_LAW_UNLINKED,)


def test_obvious_other_public_hygiene_business_is_excluded() -> None:
    result = select_precedent(
        precedent(content="숙박업소 객실의 위생관리 기준 위반에 관한 사건이다."),
        linkage="core",
        matched_laws=("공중위생관리법",),
    )

    assert result.decision is SelectionDecision.EXCLUDE
    assert ReasonCode.OUTSIDE_AESTHETIC_DOMAIN in result.reason_codes


def test_ambiguous_law_linked_case_goes_to_review() -> None:
    result = select_precedent(
        precedent(content="의료법 제27조의 적용 범위가 문제되었다."),
        linkage="core",
        matched_laws=("의료법",),
    )

    assert result.decision is SelectionDecision.REVIEW
    assert ReasonCode.AESTHETIC_SUBJECT_UNCLEAR in result.reason_codes


def test_duplicate_is_excluded_before_subject_classification() -> None:
    result = select_precedent(
        precedent(),
        linkage="core",
        matched_laws=("의료법",),
        duplicate_of="precedent-000000",
    )

    assert result.decision is SelectionDecision.EXCLUDE
    assert result.duplicate_of == "precedent-000000"
    assert result.reason_codes == (ReasonCode.DUPLICATE_DECISION,)
