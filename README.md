# General Legal Agent 평가 템플릿

이 비공개 저장소는 2주짜리 General Legal Agent 구현을 각자 독립적으로 수행하기
위한 공통 출발점입니다. 모든 기여자는 동일한 Git 베이스라인과, 별도 비공개
저장소로 전달되는 바이트 단위로 동일한 동결 데이터셋 릴리스를 받습니다.

요구되는 수직 슬라이스는 다음과 같습니다.

```text
동결된 법률 데이터셋
-> 재현 가능한 OpenSearch 인덱스
-> 정량 측정된 검색 파이프라인
-> 근거에 기반한 Bedrock LLM 답변
-> 단일 턴 GeneralLegalAgent 애플리케이션 서비스
```

## 문서

| 영어 | 한국어 | 내용 |
| --- | --- | --- |
| [README.en.md](README.en.md) | [README.md](README.md) | 이 문서 |
| [ASSIGNMENT.md](ASSIGNMENT.md) | [ASSIGNMENT.ko.md](ASSIGNMENT.ko.md) | 목표, 고정 제약, 금지 사항 |
| [DATASET.md](DATASET.md) | [DATASET.ko.md](DATASET.ko.md) | 릴리스 전달, 허용 변환, 계보(lineage) |
| [DATASET_SCHEMA.md](DATASET_SCHEMA.md) | [DATASET_SCHEMA.ko.md](DATASET_SCHEMA.ko.md) | 전달 레코드의 형태, 결측 규약, 매니페스트, 검사 |
| [CONTRACT.md](CONTRACT.md) | [CONTRACT.ko.md](CONTRACT.ko.md) | 이식 가능한 애플리케이션 서비스 경계 |
| [SUBMISSION.md](SUBMISSION.md) | [SUBMISSION.ko.md](SUBMISSION.ko.md) | 제출에 필요한 증거 |
| [OPENSEARCH_ACCESS.md](OPENSEARCH_ACCESS.md) | [OPENSEARCH_ACCESS.ko.md](OPENSEARCH_ACCESS.ko.md) | 관리형 도메인 접근과 공유 자격증명 규칙 |
| [AGENTS.md](AGENTS.md) | — | 코딩 에이전트용 지침 ([CLAUDE.md](CLAUDE.md)가 이 파일을 가리킵니다) |

## 사전 요구사항

도구 두 개면 되고, **둘 다 Python이 아닙니다.**

**uv** 가 아래의 모든 명령을 실행합니다.
[공식 설치 안내](https://docs.astral.sh/uv/getting-started/installation/)를 따르십시오.

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Python은 직접 설치하지 마십시오.** `pyproject.toml`이 인터프리터를 3.12로 고정하고
있고, `uv sync`가 **시스템 Python이 무엇이든 상관없이** 그 버전을 내려받아 사용합니다.
`python`이 3.10인 머신에서도 시스템 설치를 건드리지 않고 3.12로 돌아갑니다. sync 후
`uv run python -V`로 확인하십시오.

**Docker Desktop** 이 `docker compose up -d opensearch`가 띄우는 로컬 OpenSearch 3.5
컨테이너를 제공합니다. 그 명령과 `smoke_opensearch.py` 실행 전에 **데몬이 떠 있어야
합니다.**

## 시작하기

1. [ASSIGNMENT.md](ASSIGNMENT.md)를 읽습니다.
2. [DATASET.md](DATASET.md)의 절차대로 전달받은 데이터셋을 검증합니다.
3. [CONTRACT.md](CONTRACT.md)의 이식 가능한 경계를 보존합니다.
4. [SUBMISSION.md](SUBMISSION.md)를 보고 필요한 증거 수집을 미리 계획합니다.
5. 승인된 별도 채널로 전달받은 전용 AWS CLI 프로파일을 설정한 뒤, `.env.example`을
   `.env`로 복사합니다. 액세스 키는 절대 `.env`에 넣지 않습니다. AWS SDK의
   자격증명 공급자가 `AWS_PROFILE` 이름으로 해석합니다.
6. 로컬 검사를 실행합니다.

```powershell
uv sync
docker compose up -d opensearch
uv run python scripts/smoke_opensearch.py
uv run python scripts/smoke_contract.py
uv run ruff check .
uv run ruff format --check .
uv run mypy src
uv run pytest
```

이 템플릿은 환경과 통합 경계를 고정할 뿐, 검색 설계를 고정하지 않습니다. 표준
청크, 인덱스 매핑, 검색 구현, 테스트셋, 관련성 라벨, 프롬프트, 합격 기준선은
**의도적으로 제공하지 않습니다.**

## 데이터셋과 그 출처

코퍼스의 원천은 두 가지입니다. 판례는 law.go.kr의 **법제처 국가법령정보 OPEN
API**에서, 대상 법령 네 개 — 의료법, 표시·광고의 공정화에 관한 법률, 소비자기본법,
안마사에 관한 규칙 — 를 본문 검색해 수집했습니다. 그 API가 본문 전문을 공개하지
않는 판례는 수집하지 않았습니다.

보건복지부·식품의약품안전처의 공식 가이드는 **내용으로는 승인되었으나 이용조건 때문에
철회**되었습니다. 한 건은 상업적 이용과 변형을 금지하는 조건으로 공개돼 있고, 다른 한
건은 조건을 확인하지 못했습니다. **둘 다 릴리스에 없습니다.** 추상적 요건이 특정 광고
문구에 대한 판단으로 바뀌는 지점이 가이드라인이므로, **판례만으로는 답할 수 없는 질의가
있을 것**을 예상하고 그런 경우에는 `insufficient_evidence`로 답하십시오.

MZO는 이를 **동결 릴리스**로 전달하며, **동결 릴리스가 측정 기준**입니다. 제출물은
릴리스를 기준으로 구축하고 측정하십시오. 그래야 MZO의 재실행이 여러분의 수치를
재현하고, 두 기여자 사이의 차이가 **누가 더 많이 모았는가가 아니라 설계의 차이**로
귀속됩니다.

**원천 자료를 직접 살펴보는 것은 허용됩니다.** 그래서 여기에 출처를 밝혀 둡니다.
레코드마다 원문 URL이 들어 있어 어떤 판례든 원본과 대조할 수 있습니다. API는 공개돼
있으나 `OC` id는 **개발자별로 발급**되므로, 직접 질의할 때는 본인이 발급받은 id를
쓰십시오.

커버리지가 잘못됐다고 판단되면 — 빠진 것이 있거나, 들어와서는 안 될 것이 들어와
있다면 — **gyro에게 설명하십시오. 커버리지는 변경 가능합니다.** 별도 리포트를
요구하지 않습니다. 분명한 설명이면 충분합니다. 곤란한 것은 릴리스를 우회해 조용히
따로 수집하는 경우입니다. 그러면 보고된 수치가 **아무도 갖고 있지 않은 코퍼스**를
서술하게 됩니다.

레코드마다 원천이 요구하는 발행 표기가 실려 있습니다. **답변에 드러내십시오.** 판례를
인용하면서 그 본문이 어디서 왔는지 밝히지 않으면 완전한 인용이 아닙니다. 라이선스
조건과 출처 표시 조건은 릴리스 매니페스트를 따릅니다.

### 릴리스를 어떻게 만들었고, 어떻게 확인하는가

릴리스를 만든 스크립트가 [scripts/](scripts/)에 있습니다. 판례는 수집된 JSONL을
매핑해 만들고, 매니페스트는 커버리지를 **타이핑이 아니라 레코드에서 세어** 기록합니다.
어떤 레코드가 왜 그렇게 생겼는지 알아보는 가장 빠른 방법은 이 코드를 읽는 것입니다.
가이드용 도구도 함께 두었는데, 이용허락이 나오면 가이드를 추가한 릴리스를 만들기
위한 것입니다.

**먼저 검증하십시오.** `scripts/verify_release.py`가 모든 콘텐츠 해시를 재계산하고,
파일과 커버리지를 매니페스트와 대조하며, 오류가 있으면 0이 아닌 코드로 종료합니다.
중요한 것은 이 검증입니다. **MZO가 서명하고 재실행의 기준으로 삼는 것이
매니페스트**이기 때문입니다.

다시 빌드해 보는 것은 **대조 수단이지 대체 수단이 아닙니다.** 레코드 파일은 같은 입력과
같은 명시적 타임스탬프에서 결정론적입니다.

```powershell
uv run python scripts/build_judgement_records.py --rag-dir <dir> `
    --out judgements.jsonl --acquired-at 2026-08-08T14:42:00Z
```

이 값은 **MZO가 원본을 받은 시각**입니다. 여러분 머신에 관한 사실이 아니라 **릴리스의
입력**이며, 레코드가 이 값을 담고 있기 때문에 반드시 넘겨야 합니다. 생략하면 빌드마다
파일 시각을 찍어 **만들어진 시각만 다른** 레코드가 나옵니다. 위 값을 주면 파일 해시가
매니페스트가 선언한 값과 일치합니다.

재빌드 결과가 매니페스트와 어긋나면 자기 산출물을 채택하지 말고 보고하십시오.

파싱·AWS 서비스 접근 권한은 별도 채널로 전달됩니다. **권한이 있다고 코퍼스가 넓어지는
것은 아닙니다.** 동결 릴리스가 측정 기준이며, 다시 빌드했다고 해서 다르게 빌드된
코퍼스가 비교 가능해지지는 않습니다.

## OpenSearch 3.5 베이스라인

이번 평가는 기존 OpenSearch 2.17 베이스라인을 **OpenSearch 3.5**로 변경합니다.
로컬 및 관리형 인덱스는 3.5와 호환되어야 합니다. 2.17의 매핑이나 가정을 그대로
복사하지 말고 3.5에서 다시 검증하십시오.

## 태그 기반 개별 저장소 생성

MZO는 데이터셋 릴리스, 모델 접근, smoke check가 준비되면 기여자 시작점을
`assessment-v1` 같은 불변 태그로 고정합니다. 이후 정확히 그 태그의 tree로
기여자별 private repo를 하나씩 생성합니다. 기여자들은 브랜치를 공유하지 않습니다.

각 기여자 repo의 초기 커밋에는 원본 태그와 commit을 기록합니다. 작업은 해당
repo의 `master`에서 계속하며 feature branch와 PR은 선택 사항입니다. 최종 제출은
정확한 commit SHA 하나로 식별합니다. 이후 베이스라인 수정이 필요하면 새 태그를
만들어 모든 활성 기여자에게 동시에 배포합니다.

```text
legal-agent-assessment-template @ assessment-v1
        |-- contributor-a private repository
        |-- contributor-b private repository
        `-- contributor-c private repository
```

태그 없이 움직이는 브랜치에서 기여자 repo를 만들지 않습니다.

## 개발 시 유의점: 계층

아래의 조용한 실패는 관련 없는 작업까지 무효로 만듭니다. 작업에 참조하시기 바랍니다.

| 실수 | 발견 시점 | 무효화되는 범위 |
| --- | --- | --- |
| 평가 쿼리·정답·관련성 라벨을 인덱스에 넣음 | MZO 재실행 | 모든 검색 지표 |
| 출처에서 파생된 근사 복제 테스트를 실사용 품질로 제시 | 리뷰 | 검색 평가 리포트 전체 |
| 청크 계보(lineage) 누락 | 인용 검증 시 | 모든 답변 — 출처를 붙일 수 없으면 `answered` 자체가 불가능 |
| 시간·토큰·비용을 그때그때 기록하지 않음 | 제출 시점 | Work report — IAM 사용자를 공유하므로 귀속 자체가 불가능해 사후 복원 불가 |
| 관리형 도메인에 서명(SigV4) 없이 개발 | 정책 정상화 또는 타 환경 재실행 | 모든 OpenSearch 호출 — 서명 없는 요청이 로컬에서도 현재 stg에서도 통과하므로 늦게 드러남 |

최소 탐지 기준:

- provenance/type이 평가 전용이거나 평가 artifact 경로에서 온 index input을 거부
- 모든 색인 record가 동결 corpus manifest에 속하는지 확인하고, 평가 질의·예상 답변
  text와 indexed chunk 사이의 동일·근사 중복 탐지
- ingest와 query가 동일한 versioned normalization·embedding 설정을 사용하도록 강제
- 필수 lineage 필드가 누락된 chunk 거부
- 모든 Bedrock 호출 시 model ID, token, latency, 비용 입력값을 즉시 append-only 기록


## 질문하기

**담당자: gyro (MZO).**

정의되지 않은 부분이 있으면 자유롭게 질문 주셔도 괜찮습니다.

좋은 질문은 다음을 담습니다.

1. 무엇이 막혔는가
2. 어떤 해석들이 가능한가
3. 어느 해석을 택하느냐에 따라 결과가 어떻게 달라지는가
4. 답이 오지 않으면 어떤 가정으로 진행할 것인가


평가에 영향을 주는 베이스라인 변경은 모든 활성 기여자에게 동시에 공지됩니다.
