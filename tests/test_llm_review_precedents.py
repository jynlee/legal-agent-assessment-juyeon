"""Evidence validation for second-pass LLM review."""

import importlib.util
from pathlib import Path


def module():  # type: ignore[no-untyped-def]
    path = Path(__file__).parents[1] / "scripts" / "llm_review_precedents.py"
    spec = importlib.util.spec_from_file_location("llm_review_precedents", path)
    assert spec is not None and spec.loader is not None
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    return loaded


def source() -> dict[str, str]:
    return {
        "caseSerial": "1",
        "caseName": "의료법위반",
        "headnote": "",
        "holding": "",
        "referencedProvisions": "의료법 제27조",
        "body": "피부관리실에서 레이저 시술을 하였다.",
    }


def test_high_include_requires_exact_source_evidence() -> None:
    loaded = module()
    result = loaded.validate_result(
        {
            "decision": "include",
            "confidence": "high",
            "evidence": [{"field": "body", "quote": "피부관리실에서 레이저 시술"}],
        },
        source(),
    )

    assert result["usableCandidate"] is True


def test_invented_evidence_demotes_include_to_review() -> None:
    loaded = module()
    result = loaded.validate_result(
        {
            "decision": "include",
            "confidence": "high",
            "evidence": [{"field": "body", "quote": "존재하지 않는 문구"}],
        },
        source(),
    )

    assert result["decision"] == "review"
    assert result["usableCandidate"] is False


def test_human_promotion_records_approval_provenance() -> None:
    scripts = Path(__file__).parents[1] / "scripts"
    promote_path = scripts / "promote_llm_candidates.py"
    spec = importlib.util.spec_from_file_location("promote_llm_candidates", promote_path)
    assert spec is not None and spec.loader is not None
    promote = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(promote)

    llm_review = {"caseSerial": "206364", "decision": "include"}
    promoted = promote.apply_human_approval(
        {"caseSerial": "206364", "decision": "review"}, llm_review
    )

    assert promoted["selectionStage"] == "llm_human_approved"
    assert promoted["approvedBy"] == "gyro (MZO)"
    assert promoted["approvalBasis"] == (
        "explicit human approval after evidence-checked LLM review"
    )
    assert promoted["llmReview"] == llm_review
