"""Deterministic first-pass selection of aesthetic-domain precedents.

Discovery is intentionally broad. This module makes only decisions that can be
explained by stable, versioned rules: clear target-law noise is excluded, clear
aesthetic legal disputes are included, and ambiguity is preserved for review.
It never calls a model and never silently treats a search hit as corpus evidence.
"""

from enum import StrEnum

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel

PRECEDENT_SELECTION_POLICY_VERSION = "precedent-selection-v1"


class SelectionDecision(StrEnum):
    """Whether a collected candidate may enter the frozen corpus."""

    INCLUDE = "include"
    EXCLUDE = "exclude"
    REVIEW = "review"


class ReasonCode(StrEnum):
    """Stable explanations emitted by the first-pass policy."""

    TARGET_LAW_CORE = "TARGET_LAW_CORE"
    TARGET_LAW_CANDIDATE = "TARGET_LAW_CANDIDATE"
    TARGET_LAW_UNLINKED = "TARGET_LAW_UNLINKED"
    AESTHETIC_SUBJECT_MATCH = "AESTHETIC_SUBJECT_MATCH"
    AESTHETIC_SUBJECT_UNCLEAR = "AESTHETIC_SUBJECT_UNCLEAR"
    LEGAL_ISSUE_MATCH = "LEGAL_ISSUE_MATCH"
    LEGAL_ISSUE_UNCLEAR = "LEGAL_ISSUE_UNCLEAR"
    OUTSIDE_AESTHETIC_DOMAIN = "OUTSIDE_AESTHETIC_DOMAIN"
    MISSING_FULL_TEXT = "MISSING_FULL_TEXT"
    DUPLICATE_DECISION = "DUPLICATE_DECISION"


class PrecedentSelection(BaseModel):
    """One serializable row in the precedent selection ledger."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        alias_generator=to_camel,
        populate_by_name=True,
    )

    case_serial: str
    decision: SelectionDecision
    reason_codes: tuple[ReasonCode, ...]
    matched_laws: tuple[str, ...] = ()
    domain_signals: tuple[str, ...] = ()
    issue_signals: tuple[str, ...] = ()
    duplicate_of: str | None = None
    policy_version: str = PRECEDENT_SELECTION_POLICY_VERSION


_DOMAIN_TERMS = (
    "미용",
    "에스테틱",
    "피부관리",
    "성형",
    "피부과",
    "미용시술",
    "반영구",
    "문신",
    "제모",
    "안마",
    "마사지",
    "화장품",
    "레이저",
    "고주파",
    "초음파",
    "시술사진",
)

_ISSUE_TERMS = (
    "무면허 의료행위",
    "의료행위",
    "의료광고",
    "표시광고",
    "과대광고",
    "거짓광고",
    "광고",
    "위생관리",
    "영업신고",
    "업무범위",
    "자격",
    "개인정보",
    "민감정보",
    "얼굴정보",
    "효능",
    "판매",
)

_OUTSIDE_TERMS = (
    "숙박업",
    "숙박업소",
    "목욕장업",
    "세탁업",
    "위생관리용역업",
)

_SEARCHABLE_FIELDS = (
    "사건명",
    "판시사항",
    "판결요지",
    "참조조문",
    "content",
)


def _search_text(record: dict[str, object]) -> str:
    return "\n".join(str(record.get(field) or "") for field in _SEARCHABLE_FIELDS)


def _hits(text: str, vocabulary: tuple[str, ...]) -> tuple[str, ...]:
    return tuple(term for term in vocabulary if term in text)


def select_precedent(
    record: dict[str, object],
    *,
    linkage: str,
    matched_laws: tuple[str, ...],
    duplicate_of: str | None = None,
) -> PrecedentSelection:
    """Classify one collected candidate without inventing an ambiguous answer."""

    serial = str(record.get("판례일련번호") or "")
    if duplicate_of is not None:
        return PrecedentSelection(
            case_serial=serial,
            decision=SelectionDecision.EXCLUDE,
            reason_codes=(ReasonCode.DUPLICATE_DECISION,),
            matched_laws=matched_laws,
            duplicate_of=duplicate_of,
        )

    if not str(record.get("content") or "").strip():
        return PrecedentSelection(
            case_serial=serial,
            decision=SelectionDecision.EXCLUDE,
            reason_codes=(ReasonCode.MISSING_FULL_TEXT,),
            matched_laws=matched_laws,
        )

    if linkage == "unlinked" or not matched_laws:
        return PrecedentSelection(
            case_serial=serial,
            decision=SelectionDecision.EXCLUDE,
            reason_codes=(ReasonCode.TARGET_LAW_UNLINKED,),
        )
    if linkage not in {"core", "candidate"}:
        raise ValueError(f"unknown linkage: {linkage!r}")

    text = _search_text(record)
    domain_signals = _hits(text, _DOMAIN_TERMS)
    issue_signals = _hits(text, _ISSUE_TERMS)
    outside_signals = _hits(text, _OUTSIDE_TERMS)
    linkage_reason = (
        ReasonCode.TARGET_LAW_CORE if linkage == "core" else ReasonCode.TARGET_LAW_CANDIDATE
    )

    if outside_signals and not domain_signals:
        return PrecedentSelection(
            case_serial=serial,
            decision=SelectionDecision.EXCLUDE,
            reason_codes=(linkage_reason, ReasonCode.OUTSIDE_AESTHETIC_DOMAIN),
            matched_laws=matched_laws,
            issue_signals=issue_signals,
        )

    if domain_signals and issue_signals:
        return PrecedentSelection(
            case_serial=serial,
            decision=SelectionDecision.INCLUDE,
            reason_codes=(
                linkage_reason,
                ReasonCode.AESTHETIC_SUBJECT_MATCH,
                ReasonCode.LEGAL_ISSUE_MATCH,
            ),
            matched_laws=matched_laws,
            domain_signals=domain_signals,
            issue_signals=issue_signals,
        )

    reasons = [linkage_reason]
    if not domain_signals:
        reasons.append(ReasonCode.AESTHETIC_SUBJECT_UNCLEAR)
    if not issue_signals:
        reasons.append(ReasonCode.LEGAL_ISSUE_UNCLEAR)
    return PrecedentSelection(
        case_serial=serial,
        decision=SelectionDecision.REVIEW,
        reason_codes=tuple(reasons),
        matched_laws=matched_laws,
        domain_signals=domain_signals,
        issue_signals=issue_signals,
    )
