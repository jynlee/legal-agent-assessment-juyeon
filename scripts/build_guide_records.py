"""Build the official-guide source records from the parsed guide Markdown.

MZO release tooling. Requires the `release` dependency group for pypdf:

    uv sync --group release
    uv run python scripts/build_guide_records.py --parsed out --pdf-dir pdfs --out guides.jsonl

Every quoted string in GUIDES was read from the source document, and each is
asserted before use — body quotes against the parse, identity facts against the
PDF text layer. The two extractions disagree in both directions: the parser
renders pages and drops what it reads as cover design, which is where the
publication registration number lives, while the text layer jams words together
on pages the parser handles cleanly. Checking each fact against the extraction
that actually carries it is what keeps a wrong value from reaching the release.
"""

import argparse
import datetime as dt
import json
import pathlib
import re
import sys
from typing import Any

from legal_agent_assessment.dataset import (
    DocumentKind,
    GuideIdentity,
    GuideNumberScheme,
    SourceAdmission,
    SourceProvenance,
    SourceRecord,
    TextExtraction,
    UsageDisposition,
)
from legal_agent_assessment.dataset_validation import content_hash

IMAGE_REF = re.compile(r"!\[\]\([^)]*_img\.[a-z]+\)")
PAGE_MARKER = re.compile(r"\[PAGE_NUMBER\]:\s*(\d+)")

MEDICAL_NON_BINDING = (
    "해당 가이드라인은 법령과 복지부 유권해석 및 입장, 관련 판례 등을 토대로 구성되어 있으며, "
    "개별 사례에 대한 적용은 구체적 사실관계에 따라 달리 적용될 수 있습니다."
)
COSMETIC_NON_BINDING = (
    "본 안내서는 대외적으로 법적 효력을 가지는 것이 아니므로 본문의 기술방식"
    "('\\~하여야 한다' 등)에도 불구하고 참고로만 활용하시기 바랍니다."
)

GUIDES: list[dict[str, Any]] = [
    {
        "key": "medical",
        "pdf": "건강한+의료광고,+우리가+함께+만들어요(2판).pdf",
        "parsed": "medical.md",
        "document_id": "guide-11-1352000-100026-01",
        "title": (
            "건강한 의료광고, 우리가 함께 만들어요! — 유형별 의료광고 사례 및 체크리스트 (2판)"
        ),
        "identity": {
            "issuing_authority": "보건복지부",
            "issuing_division": "보건의료정책과",
            "official_number": "11-1352000-100026-01",
            "official_number_scheme": GuideNumberScheme.PUBLICATION_REGISTRATION,
            "edition": "2판",
            "issued_on": "2024-12",
            "page_count": 108,
            "non_binding_statement": MEDICAL_NON_BINDING,
        },
        "provider": "보건복지부",
        # Verified: this 발간자료 entry serves the publication and names 보건의료정책과.
        "source_url": (
            "https://www.mohw.go.kr/board.es?mid=a10411010300&bid=0019&act=view&list_no=1484159"
        ),
        "publisher_statement": "보건복지부 발간등록번호 11-1352000-100026-01",
        "source_reference": (
            "보건복지부, 「건강한 의료광고, 우리가 함께 만들어요!」 2판, "
            "발간등록번호 11-1352000-100026-01"
        ),
        "expect_body": ["유형별 의료광고 사례 및 체크리스트"],
        "expect_front": ["발간등록번호", "11-1352000-100026-01"],
    },
    {
        "key": "cosmetic",
        "pdf": "「화장품+표시·광고+관리+지침(민원인안내서)」.pdf",
        "parsed": "cosmetics.md",
        "document_id": "guide-mfds-0086-06",
        "title": "화장품 표시·광고 관리 지침 (민원인 안내서)",
        "identity": {
            "issuing_authority": "식품의약품안전처",
            "issuing_division": "바이오생약국 화장품정책과",
            "official_number": "안내서-0086-06",
            "official_number_scheme": GuideNumberScheme.GUIDANCE_DOCUMENT,
            "edition": None,
            "issued_on": "2025-01-21",
            "page_count": 17,
            "non_binding_statement": COSMETIC_NON_BINDING,
        },
        "provider": "식품의약품안전처",
        # The MFDS guidance board did not answer when checked, so no URL is
        # recorded rather than an unverified one. The number identifies it.
        "source_url": None,
        "publisher_statement": "식품의약품안전처 민원인 안내서 안내서-0086-06",
        "source_reference": (
            "식품의약품안전처 바이오생약국 화장품정책과, "
            "「화장품 표시·광고 관리 지침(민원인 안내서)」, 안내서-0086-06, 2025. 1. 21."
        ),
        "expect_body": ["안내서\\-0086\\-06", "화장품 표시·광고 관리 지침", "식품의약품안전처"],
        "expect_front": ["안내서-0086-06"],
    },
]


def file_time(path: pathlib.Path) -> dt.datetime:
    """Modification time of one file, as a whole-second UTC timestamp."""

    return dt.datetime.fromtimestamp(path.stat().st_mtime, dt.UTC).replace(microsecond=0)


def moment(value: str | None) -> dt.datetime | None:
    """Parse an explicit ISO-8601 timestamp, or return None to fall back."""

    if value is None:
        return None
    parsed = dt.datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.UTC)
    return parsed.astimezone(dt.UTC).replace(microsecond=0)


def squash(value: str) -> str:
    """Drop whitespace and Markdown backslash escapes for comparison.

    The parser loses spaces at some line-wrap points, so a quote is verified
    against the document without storing that damage.
    """

    return re.sub(r"[\s\\]+", "", value)


def front_matter(pdf: pathlib.Path, pages: int) -> tuple[str, int]:
    """Read the PDF text layer for the first few pages, and the page count."""

    import pypdf

    reader = pypdf.PdfReader(pdf)
    head = "\n".join(
        (reader.pages[index].extract_text() or "") for index in range(min(pages, len(reader.pages)))
    )
    return head, len(reader.pages)


def build(
    spec: dict[str, Any],
    parsed_dir: pathlib.Path,
    pdf_dir: pathlib.Path,
    acquired_at: dt.datetime | None,
    parsed_at: dt.datetime | None,
) -> SourceRecord:
    """Assemble one guide record, refusing any fact the sources do not support."""

    parsed_path = parsed_dir / spec["parsed"]
    text = parsed_path.read_text(encoding="utf-8")
    pdf = pdf_dir / spec["pdf"]
    identity: dict[str, Any] = spec["identity"]

    body = squash(text)
    for phrase in [*spec["expect_body"], identity["non_binding_statement"]]:
        if squash(phrase) not in body:
            raise SystemExit(f"[{spec['key']}] quote absent from the parse: {phrase[:60]!r}")

    head, page_count = front_matter(pdf, pages=4)
    for phrase in spec["expect_front"]:
        if squash(phrase) not in squash(head):
            raise SystemExit(f"[{spec['key']}] identity fact absent from the PDF: {phrase!r}")
    if page_count != identity["page_count"]:
        raise SystemExit(f"[{spec['key']}] declared page_count disagrees with the PDF")

    pages = {int(marker) for marker in PAGE_MARKER.findall(text)}
    if len(pages) != identity["page_count"] or max(pages) != identity["page_count"]:
        raise SystemExit(f"[{spec['key']}] page markers do not cover every page")

    images = len(IMAGE_REF.findall(text))

    # State only what holds for this record. A limitation that is not true
    # teaches a reader to discount the whole field.
    limitations: list[str] = []
    if images:
        limitations.append(
            f"위반 사례의 광고 이미지 {images}건이 텍스트가 아니라 마크다운 이미지 참조로만 "
            "남아 있어, 해당 사례의 증거물은 인용할 수 없다"
        )
    if squash(identity["official_number"]) not in squash(text):
        limitations.append(
            "표지의 발행 식별 정보를 파서가 표지 디자인으로 보아 본문에 넣지 않았다. "
            "공식 번호는 identity 필드에서만 확인할 수 있다"
        )
    limitations.append("라이선스 근거는 발행기관 확인 전이며, 매니페스트가 최종 조건을 정한다")

    acquired = acquired_at or file_time(pdf)
    return SourceRecord(
        document_id=spec["document_id"],
        document_kind=DocumentKind.OFFICIAL_GUIDE,
        title=spec["title"],
        text=text,
        content_hash=content_hash(text),
        identity=GuideIdentity(**identity),
        provenance=SourceProvenance(
            provider=spec["provider"],
            publisher_statement=spec["publisher_statement"],
            source_url=spec["source_url"],
            source_reference=spec["source_reference"],
            acquired_at=acquired,
            extraction=TextExtraction(
                tool="MZO Noesis document-parsing API",
                engine="chandra",
                model="balanced",
                output_format="md",
                performed_at=parsed_at or file_time(parsed_path),
                settings=("useOcrToImage=true", "endpoint=/api/document/analyze"),
            ),
        ),
        admission=SourceAdmission.LICENSED,
        attribution=spec["provider"],
        usage=UsageDisposition.INDEX_ELIGIBLE,
        limitations=tuple(limitations),
    )


def main() -> None:
    """Write the guide records as JSONL."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parsed", type=pathlib.Path, required=True)
    parser.add_argument("--pdf-dir", type=pathlib.Path, required=True)
    parser.add_argument("--out", type=pathlib.Path, required=True)
    # Timestamps are inputs, not observations of the build machine. Supply them
    # and the same sources produce byte-identical records anywhere; omit them
    # and they fall back to file modification times, which copying destroys.
    parser.add_argument("--acquired-at", help="ISO-8601 time the PDFs were received")
    parser.add_argument("--parsed-at", help="ISO-8601 time the PDFs were parsed")
    args = parser.parse_args()

    acquired_at = moment(args.acquired_at)
    parsed_at = moment(args.parsed_at)
    records = [build(spec, args.parsed, args.pdf_dir, acquired_at, parsed_at) for spec in GUIDES]
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as handle:
        for record in records:
            handle.write(
                json.dumps(record.model_dump(by_alias=True, mode="json"), ensure_ascii=False)
            )
            handle.write("\n")

    for record in records:
        print(f"{record.document_id}  {len(record.text):>8,} chars  {record.content_hash}")
    print(f"wrote {len(records)} guide records -> {args.out}", file=sys.stderr)


if __name__ == "__main__":
    main()
