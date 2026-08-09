"""Write the release manifest for a built set of source-record files.

MZO release tooling.

    uv run python scripts/build_release_manifest.py --rag-dir data/rag \
        --file judgements.jsonl --file guides.jsonl \
        --dataset-version dataset-v1 --delivery-id delivery-0001 \
        --out release-manifest.json

Coverage is counted from the records rather than typed in, so the manifest
cannot drift from the files it describes. The dispositions, licence notes and
known gaps below are MZO decisions and are written here deliberately: this file
is where a reader learns what was left out and why, and where the corpus is
known to fall short.
"""

import argparse
import collections
import datetime as dt
import hashlib
import pathlib

from legal_agent_assessment.dataset import (
    CoverageEntry,
    DispositionNote,
    LicenceNote,
    ReleaseFile,
    ReleaseManifest,
    SourceRecord,
)

DISPOSITIONS = (
    DispositionNote(
        subject="법제처 국가법령정보 판례 (의료법·표시광고법·소비자기본법·안마사에 관한 규칙)",
        included=True,
        reason="출처 표기가 완전하고 질의 도메인과 맞아 주 검색 데이터로 사용한다",
    ),
    DispositionNote(
        subject="승인된 공식 가이드 2건 (보건복지부 의료광고, 식약처 화장품 표시·광고)",
        included=True,
        reason=(
            "조문과 판례 사이의 판단 기준을 사례로 제공한다. "
            "법령이 아니라 해석이므로 문서 종류를 구분해 색인한다"
        ),
    ),
    DispositionNote(
        subject="본문 전문이 공개되지 않은 판례 후보",
        included=False,
        reason="서지정보만 제공되어 인용 가능한 근거가 되지 못한다",
    ),
    DispositionNote(
        subject="산재·지방세 등 도메인 무관 판례",
        included=True,
        reason=(
            "릴리스에는 포함하되 inDefaultCorpus=false로 표시한다. "
            "포함 여부는 기여자의 레코드 선택 결정이다"
        ),
    ),
    DispositionNote(
        subject="AI Hub 452 (법률 문서 요약)",
        included=False,
        reason="사건번호·법원명·선고일자·원문 URL이 없어 출처를 표시할 수 없다",
    ),
    DispositionNote(
        subject="AI Hub 71874 (의학지식 발췌)",
        included=False,
        reason=(
            "출처가 없고 대부분 피부과 의학지식이라 도메인이 다르다. "
            "제한적 사용 조건 확인 후 평가 전용으로만 검토한다"
        ),
    ),
    DispositionNote(
        subject="전달 PDF 법령 6건",
        included=False,
        reason="법제처 API 수집분과 중복이며, PDF는 그 시점 개정본으로 고정되어 최신본과 충돌한다",
    ),
    DispositionNote(
        subject="의료광고가이드라인(2판) PDF",
        included=False,
        reason="「건강한 의료광고, 우리가 함께 만들어요」와 본문이 사실상 같은 문서이다",
    ),
    DispositionNote(
        subject="약사법 관련 판례",
        included=False,
        reason="대상 법령 범위를 4개 법령으로 닫았다",
    ),
)

LICENCES = (
    LicenceNote(
        subject="법제처 국가법령정보 공동활용 판례",
        terms="레코드마다 실린 발행 표기를 답변에 드러내야 한다. 출처를 밝히면 재이용할 수 있다",
        attribution_required=True,
    ),
    LicenceNote(
        subject="보건복지부 「건강한 의료광고, 우리가 함께 만들어요」 2판",
        terms=(
            "발행 기관 게시물에 공공누리 표시가 추가된 것으로 확인되나 유형은 미확인이다. "
            "발행기관 확인 전까지 출처 표시를 전제로 사용한다"
        ),
        attribution_required=True,
    ),
    LicenceNote(
        subject="식품의약품안전처 「화장품 표시·광고 관리 지침(민원인 안내서)」",
        terms="이용 조건 미확인. 발행기관 확인 전까지 출처 표시를 전제로 사용한다",
        attribution_required=True,
    ),
)

KNOWN_GAPS = (
    "가이드의 위반 사례 광고 이미지는 텍스트가 아니라 마크다운 이미지 참조로만 남는다. "
    "해당 사례의 증거물은 인용할 수 없다",
    "의료광고 가이드 표지의 발간등록번호는 파서가 표지 디자인으로 보아 본문에 넣지 않았다. "
    "identity 필드에서만 확인된다",
    "일부 판례는 선고일자가 자리표시자 00010101이고 판결유형이 문자열 'null'이다. "
    "형식은 유효하므로 날짜 필터가 조용히 제외한다",
    "일부 판례는 판시사항·판결요지·참조조문·참조판례가 모두 비어 있어 본문만 제공된다",
    "같은 판결이 서로 다른 판례일련번호로 두 번 수록된 경우가 있다. "
    "sourceGroupId를 공유하므로 평가 분할에서 갈라놓지 말아야 한다",
    "linkedLaws는 본문 검색 결과이며 core가 아닌 연계는 그 법령에 관한 판단이 아니다",
    "화장품 표시·광고 관리 지침은 클라이언트가 전달한 문서를 그대로 사용한다. "
    "이후 개정본이 존재할 수 있으며 릴리스는 전달본 기준이다",
    "식품의약품안전처 안내서는 발행기관 페이지가 조회 시 응답하지 않아 sourceUrl을 기록하지 않았다",
)


def read(path: pathlib.Path) -> tuple[list[SourceRecord], ReleaseFile]:
    """Parse one record file and describe it for the manifest."""

    raw = path.read_bytes()
    records = [
        SourceRecord.model_validate_json(line)
        for line in raw.decode("utf-8").splitlines()
        if line.strip()
    ]
    return records, ReleaseFile(
        path=path.name,
        sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
        record_count=len(records),
    )


def coverage(values: collections.Counter[str]) -> tuple[CoverageEntry, ...]:
    """Turn counted values into manifest coverage entries."""

    return tuple(
        CoverageEntry(key=key, record_count=count) for key, count in sorted(values.items())
    )


def main() -> None:
    """Count the built records and write the manifest beside them."""

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rag-dir", type=pathlib.Path, required=True)
    parser.add_argument("--file", action="append", required=True, dest="files")
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--schema-version", default="source-record-v1")
    parser.add_argument("--delivery-id", required=True)
    parser.add_argument("--delivered-by", default="MZO")
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()

    records: list[SourceRecord] = []
    files: list[ReleaseFile] = []
    for name in args.files:
        parsed, described = read(args.rag_dir / name)
        records.extend(parsed)
        files.append(described)
        print(f"{name:20s} {len(parsed):5d} records  {described.byte_size:>12,} bytes")

    manifest = ReleaseManifest(
        dataset_version=args.dataset_version,
        schema_version=args.schema_version,
        frozen_at=dt.datetime.now(dt.UTC).replace(microsecond=0),
        delivery_id=args.delivery_id,
        delivered_by=args.delivered_by,
        files=tuple(files),
        coverage_by_document_kind=coverage(
            collections.Counter(str(record.document_kind) for record in records)
        ),
        coverage_by_provider=coverage(
            collections.Counter(record.provenance.provider for record in records)
        ),
        coverage_by_usage=coverage(collections.Counter(str(record.usage) for record in records)),
        dispositions=DISPOSITIONS,
        licences=LICENCES,
        known_gaps=KNOWN_GAPS,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(manifest.model_dump_json(by_alias=True, indent=2) + "\n", encoding="utf-8")
    print(f"\ntotal records: {manifest.total_records()}")
    print(f"wrote manifest -> {args.out} ({args.out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
