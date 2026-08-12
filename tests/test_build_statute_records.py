"""Mapping collected law rows to source-record-v2."""

import importlib.util
from datetime import UTC, datetime
from pathlib import Path

_PATH = Path(__file__).parents[1] / "scripts" / "build_statute_records.py"
_SPEC = importlib.util.spec_from_file_location("build_statute_records", _PATH)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)
build = _MODULE.build

ACQUIRED = datetime(2026, 8, 11, tzinfo=UTC)
HASH = "sha256:" + "0" * 64


def common() -> dict[str, object]:
    return {
        "법령명": "공중위생관리법",
        "법령구분": "법률",
        "소관부처": "보건복지부",
        "공포일자": "20260101",
        "시행일자": "20260701",
        "법령ID": "001234",
        "MST": "999999",
        "rawArtifactPath": "source-native/law/example.xml",
        "rawArtifactHash": HASH,
    }


def test_builds_one_article_record() -> None:
    row = common() | {
        "doc_type": "law_article",
        "조문번호": "10",
        "조문가지번호": "0",
        "조문제목": "영업자의 준수사항",
        "조문시행일자": "20260701",
        "content": "제10조 영업자는 위생관리 기준을 지켜야 한다.",
    }

    record = build(row, ACQUIRED)

    assert record.document_kind == "statute"
    assert record.identity.article_number == "10"
    assert record.title == "공중위생관리법 제10조"


def test_builds_one_appendix_record_from_cleaned_text() -> None:
    row = common() | {
        "doc_type": "law_appendix",
        "별표번호": "0005",
        "별표가지번호": "00",
        "별표제목": "준수사항",
        "별표시행일자": "20260701",
        "locator": "별표 5",
        "content": "glued raw text",
        "contentCleaned": "가. 복원된 항목",
    }

    record = build(row, ACQUIRED)

    assert record.identity.appendix_number == "0005"
    assert record.text == "가. 복원된 항목"
    assert record.title == "공중위생관리법 별표 5"
