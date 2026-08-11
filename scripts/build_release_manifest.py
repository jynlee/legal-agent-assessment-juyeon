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
    ReleaseFileKind,
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
        subject="공식 가이드 2건 (보건복지부 의료광고, 식약처 화장품 표시·광고)",
        included=False,
        reason=(
            "보건복지부 간행물은 게시물 항목별로 공공누리 제4유형"
            "(출처표시+상업적이용금지+변경금지)이 지정되어 있어, 상용 서비스 색인과 "
            "정규화·청킹에 의한 변형이 이용조건과 맞지 않는다. 식약처 안내서는 "
            "이용조건을 확인하지 못했고, 미확인 라이선스는 licensed가 아니다. "
            "별도 이용허락을 받으면 재편입한다"
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
        subject="보건복지부 「건강한 의료광고, 우리가 함께 만들어요」 2판 (릴리스 제외)",
        terms=(
            "공공누리 제4유형: 출처표시 + 상업적이용금지 + 변경금지. "
            "기관 기본 정책은 제1유형이나 이 간행물에 항목별로 제4유형이 지정되어 있다"
        ),
        attribution_required=True,
        restricted_use=True,
    ),
    LicenceNote(
        subject="식품의약품안전처 「화장품 표시·광고 관리 지침(민원인 안내서)」 (릴리스 제외)",
        terms="이용 조건 미확인. 확인될 때까지 코퍼스에 들어가지 않는다",
        attribution_required=True,
        restricted_use=True,
    ),
)

KNOWN_GAPS = (
    "공식 가이드가 들어 있지 않다. 조문과 판례 사이를 메우는 판단 기준 — 「의학적 효능 오인」 "
    "같이 조문에 없고 가이드라인 사례에만 있는 것들 — 은 이 릴리스에 근거가 없다. "
    "이용조건 때문이며 자료가 없어서가 아니다",
    "일부 판례는 선고일자가 자리표시자 00010101이고 판결유형이 문자열 'null'이다. "
    "형식은 유효하므로 날짜 필터가 조용히 제외한다",
    "일부 판례는 판시사항·판결요지·참조조문·참조판례가 모두 비어 있어 본문만 제공된다",
    "같은 판결이 서로 다른 판례일련번호로 두 번 수록된 경우가 있다. "
    "sourceGroupId를 공유하므로 평가 분할에서 갈라놓지 말아야 한다",
    "linkedLaws는 본문 검색 결과이며 core가 아닌 연계는 그 법령에 관한 판단이 아니다",
)

V2_DISPOSITIONS = (
    DispositionNote(
        subject="핵심 8개 법령의 현행 법률·시행령·시행규칙·별표",
        included=True,
        reason="gyro가 승인한 dataset-v2 법령 범위이며 조문·별표 단위로 제공한다",
    ),
    DispositionNote(
        subject="핵심 8개 법령과 피부미용·에스테틱 도메인의 교집합 판례",
        included=True,
        reason=(
            "deterministic selection policy가 include로 판정한 판례와, 그 review 후보 중 "
            "LLM 근거 검증 뒤 gyro가 명시적으로 승인한 15건의 전문 공개 판례를 제공한다"
        ),
    ),
    DispositionNote(
        subject="판례 selection의 review 및 exclude 후보",
        included=False,
        reason="raw artifact와 selection ledger에는 보존하지만 corpus 및 index에는 넣지 않는다",
    ),
    DispositionNote(
        subject="의료기사 등에 관한 법률·전자상거래법·법령해석례·행정규칙·공식 가이드",
        included=False,
        reason="2026-08-11 gyro가 고정한 dataset-v2 범위 밖이며 후속 release 후보로 남긴다",
    ),
    DispositionNote(
        subject="과거 연혁 법령",
        included=False,
        reason="dataset-v2는 수집 시점의 현행 법령만 제공한다",
    ),
)

V2_LICENCES = (
    LicenceNote(
        subject="법제처 국가법령정보 공동활용 법령 및 판례",
        terms="레코드의 법제처 출처 표기를 답변과 재사용 산출물에 드러낸다",
        attribution_required=True,
    ),
)

V2_KNOWN_GAPS = (
    "현행 법령만 제공하므로 판례 선고 당시 적용된 과거 조문과 다를 수 있다",
    (
        "review 판례는 자동 편입하지 않는다. LLM 검토 결과도 사람의 명시적 승인 "
        "없이는 corpus record가 아니다"
    ),
    "법령해석례·고시·예규·훈령 및 공식 가이드는 dataset-v2 범위에 포함되지 않는다",
    "법제처가 전문을 제공하지 않는 판례 검색 결과는 인용 가능한 corpus record가 아니다",
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


def describe_artifacts(path: pathlib.Path, contained: int) -> ReleaseFile:
    """Describe a retained-artifact archive so it is not an unlisted file.

    Records point at these bytes through `rawArtifactPath`. Delivering them
    without listing them would trip the check DATASET.md asks contributors to
    run; listing them as records would inflate the record count.
    """

    raw = path.read_bytes()
    return ReleaseFile(
        path=path.name,
        kind=ReleaseFileKind.ARTIFACTS,
        sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
        record_count=contained,
    )


def describe_metadata(path: pathlib.Path) -> ReleaseFile:
    """Describe a line-oriented audit file that is not corpus evidence."""

    raw = path.read_bytes()
    rows = sum(bool(line.strip()) for line in raw.decode("utf-8").splitlines())
    return ReleaseFile(
        path=path.name,
        kind=ReleaseFileKind.METADATA,
        sha256="sha256:" + hashlib.sha256(raw).hexdigest(),
        byte_size=len(raw),
        record_count=rows,
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
    parser.add_argument(
        "--artifact-archive",
        help="retained source artifacts referenced by rawArtifactPath, e.g. source-native.tar.gz",
    )
    parser.add_argument("--artifact-count", type=int, help="all raw artifacts in the archive")
    parser.add_argument("--metadata-file", action="append", default=[])
    parser.add_argument("--dataset-version", required=True)
    parser.add_argument("--schema-version", default="source-record-v1")
    parser.add_argument("--delivery-id", required=True)
    parser.add_argument("--delivered-by", default="MZO")
    parser.add_argument("--frozen-at", help="fixed ISO-8601 timestamp; defaults to the build time")
    parser.add_argument("--out", type=pathlib.Path, required=True)
    args = parser.parse_args()

    records: list[SourceRecord] = []
    files: list[ReleaseFile] = []
    for name in args.files:
        parsed, described = read(args.rag_dir / name)
        records.extend(parsed)
        files.append(described)
        print(f"{name:20s} {len(parsed):5d} records  {described.byte_size:>12,} bytes")

    if args.artifact_archive:
        retained = {
            record.provenance.raw_artifact_path
            for record in records
            if record.provenance.raw_artifact_path
        }
        contained = args.artifact_count if args.artifact_count is not None else len(retained)
        archive = describe_artifacts(args.rag_dir / args.artifact_archive, contained)
        files.append(archive)
        print(f"{archive.path:20s} {contained:5d} artifacts {archive.byte_size:>11,} bytes")

    for name in args.metadata_file:
        described = describe_metadata(args.rag_dir / name)
        files.append(described)
        print(f"{name:20s} {described.record_count:5d} metadata rows")

    is_v2 = args.schema_version == "source-record-v2"
    frozen_at = (
        dt.datetime.fromisoformat(args.frozen_at.replace("Z", "+00:00"))
        if args.frozen_at
        else dt.datetime.now(dt.UTC).replace(microsecond=0)
    )

    manifest = ReleaseManifest(
        dataset_version=args.dataset_version,
        schema_version=args.schema_version,
        frozen_at=frozen_at,
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
        dispositions=V2_DISPOSITIONS if is_v2 else DISPOSITIONS,
        licences=V2_LICENCES if is_v2 else LICENCES,
        known_gaps=V2_KNOWN_GAPS if is_v2 else KNOWN_GAPS,
    )

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(manifest.model_dump_json(by_alias=True, indent=2) + "\n", encoding="utf-8")
    print(f"\ntotal records: {manifest.total_records()}")
    print(f"wrote manifest -> {args.out} ({args.out.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()
