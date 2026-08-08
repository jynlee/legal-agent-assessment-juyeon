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
| [CONTRACT.md](CONTRACT.md) | [CONTRACT.ko.md](CONTRACT.ko.md) | 이식 가능한 애플리케이션 서비스 경계 |
| [SUBMISSION.md](SUBMISSION.md) | [SUBMISSION.ko.md](SUBMISSION.ko.md) | 제출에 필요한 증거 |
| [AGENTS.md](AGENTS.md) | — | 코딩 에이전트용 지침 ([CLAUDE.md](CLAUDE.md)가 이 파일을 가리킵니다) |

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

## OpenSearch 3.5 베이스라인

이번 평가는 기존 OpenSearch 2.17 베이스라인을 **OpenSearch 3.5**로 변경합니다.
로컬 및 관리형 인덱스는 3.5와 호환되어야 합니다. 2.17의 매핑이나 가정을 그대로
복사하지 말고 3.5에서 다시 검증하십시오.

## 태그 기반 개별 저장소 생성

MZO는 데이터셋 릴리스, 모델 접근, smoke check가 준비되면 기여자 시작점을
`assessment-v1` 같은 불변 태그로 고정합니다. 이후 정확히 그 태그의 tree로
기여자별 private repo를 하나씩 생성합니다. 기여자들은 브랜치를 공유하지 않고
서로의 작업을 볼 수 없습니다.

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

## 개발 시 유의점: 계층 C

아래의 조용한 실패는 관련 없는 작업까지 무효로 만듭니다. 전체 파이프라인을 만들기
전에 각 항목을 드러낼 수 있는 값싼 탐지기를 추가하십시오.

| 실수 | 발견 시점 | 무효화되는 범위 |
| --- | --- | --- |
| 평가 쿼리·정답·관련성 라벨을 인덱스에 넣음 | MZO 재실행 | 모든 검색 지표 |
| 출처에서 파생된 근사 복제 테스트를 실사용 품질로 제시 | 리뷰 | 검색 평가 리포트 전체 |
| ingest와 query의 임베딩 또는 전처리가 어긋남 | 끝까지 발견 못 할 수 있음 | 모든 검색 결과 |
| 청크 계보(lineage) 누락 | 인용 검증 시 | 모든 답변 — 출처를 붙일 수 없으면 `answered` 자체가 불가능 |
| 시간·토큰·비용을 그때그때 기록하지 않음 | 제출 시점 | Work report — 사후 복원 불가 |

최소 탐지 기준:

- provenance/type이 평가 전용이거나 평가 artifact 경로에서 온 index input을 거부
- 모든 색인 record가 동결 corpus manifest에 속하는지 확인하고, 평가 질의·예상 답변
  text와 indexed chunk 사이의 동일·근사 중복 탐지
- ingest와 query가 동일한 versioned normalization·embedding 설정을 사용하도록 강제
- 필수 lineage 필드가 누락된 chunk 거부
- 모든 Bedrock 호출 시 model ID, token, latency, 비용 입력값을 즉시 append-only 기록

CI가 초록불이라는 사실만으로 위 조건이 충족됐다고 볼 수 없습니다.

## 질문하기

**담당자: gyro (MZO).**

정의되지 않은 부분이 있으면 질문하십시오. **질문은 당연하며 감점 요소가
아닙니다.** 이 템플릿은 설계 결정을 의도적으로 비워 두었으므로, 무엇을 모르는지
식별하고 정리하는 능력 자체가 검토 대상입니다. **좋은 질문 하나가 조용한 가정보다
가치 있습니다.**

좋은 질문은 다음을 담습니다.

1. 무엇이 막혔는가
2. 어떤 해석들이 가능한가
3. 어느 해석을 택하느냐에 따라 결과가 어떻게 달라지는가
4. 답이 오지 않으면 어떤 가정으로 진행할 것인가

**답을 기다리며 멈추지 마십시오.** 제때 답이 올 수 없다면 명시한 가정으로
진행하고, 질문과 가정을 모두 [SUBMISSION.md](SUBMISSION.md)가 요구하는 블로커
로그에 기록하십시오.

평가에 영향을 주는 베이스라인 변경은 모든 활성 기여자에게 동시에 공지됩니다.
