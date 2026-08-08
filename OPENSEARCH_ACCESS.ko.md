# 관리형 OpenSearch 접근

> 한국어 번역본입니다. 정본은 [OPENSEARCH_ACCESS.md](OPENSEARCH_ACCESS.md)이며, 두 본이
> 어긋날 경우 영어 본문이 우선합니다.

시작할 때는 필요 없습니다. 평소 개발은 `docker-compose.yml`의 로컬 컨테이너로
충분하고, 인덱스는 언제든 다시 만들 수 있는 파생 데이터입니다. 관리형 도메인이
처음 필요해진 시점에 읽으십시오.

`<...>`로 표기된 값은 전부 승인된 별도 채널로 전달됩니다. 실제 계정 ID, 인스턴스
ID, 엔드포인트는 이 저장소에 들어가지 않습니다.

## 1. 자격증명과 허용 범위

기여자들은 **하나의 programmatic IAM 사용자를 공유**합니다. `.env`의
`AWS_PROFILE` 이름으로 boto3가 해석하며, 시간 제한이 있고 콘솔 로그인은
없습니다.

| 허용 | 불허 |
| --- | --- |
| 승인된 Bedrock 모델 invoke | RDS · Redis · S3 · Secrets Manager · CloudWatch Logs |
| 앱 EC2 경유 SSM 포트 포워딩 | SSH 및 모든 인바운드 포트 |
| **`legal-kit-*` 인덱스에 한한** OpenSearch 읽기/쓰기 | 그 외 모든 인덱스, 인프라 관리, IAM |

정책 경계는 2026-07-31 IAM 정책 시뮬레이터로 확인되었습니다.

| 경로 | 서명된 요청 |
| --- | --- |
| `legal-kit-*` 검색·색인·삭제·인덱스별 `_bulk` | 허용 |
| `_cat/indices`, `_cluster/health`, `/` | **implicit deny** |
| 전역 `_bulk` | **implicit deny** |
| `legal-kit-` 이외 인덱스 | **implicit deny** |

`OPENSEARCH_INDEX_PREFIX`가 `legal-kit-assessment`인 이유가 이것입니다.
`legal-kit-` 밖의 접두사를 쓰면 서명된 요청이 전부 실패하고, **로컬 컨테이너는
어떤 이름이든 받아주므로 그 실패는 늦게 드러납니다.**

## 2. 공유 도메인에서 작업하기

자격증명이 공유되므로 플랫폼도 CloudTrail도 기여자를 구분하지 못합니다. 여기서
규칙 셋이 따라 나오며, 이는 권고가 아니라 **과제의 일부**입니다.

**네임스페이스 하나를 소유하고 그 안에만 머무를 것.** 생성하는 모든 인덱스는
전달받은 기여자 ID로 `legal-kit-assessment-<contributor>-...` 형태를 갖습니다.
다른 사람의 ID가 붙은 인덱스는 읽지도, 쓰지도, 지우지도 마십시오.

**클러스터 전역 또는 와일드카드 파괴 연산을 절대 호출하지 말 것.**
`DELETE legal-kit-*`, 전역 `_bulk`, 클러스터 설정 변경 모두 금지입니다. 대부분은
정책이 이미 막지만, 막지 않는 것들은 **다른 기여자의 작업을 귀속도 복구도 불가능한
방식으로 파괴합니다.**

**자신의 사용량은 스스로 계량할 것.** 자격증명이 공유되므로 AWS 청구서도
CloudTrail도 어떤 호출이 누구 것인지 복원할 수 없습니다. 따라서 `SUBMISSION.md`가
요구하는 토큰·지연·비용 증거는 **첫 호출부터 직접 작성한 계측에서만** 나올 수
있습니다. 사후에 복원할 방법이 없습니다.

Bedrock 쿼터도 같은 방식으로 공유됩니다. Cohere Embed v4는 **계정 전체 기준 분당
300,000 토큰**이 상한이라, 한 기여자의 전체 코퍼스 임베딩이 다른 기여자가 쓸 몫을
그대로 소모합니다. 재시도에 기대지 말고 **토큰 예산으로 송신 속도를 스스로
조절**하십시오 — 해당 분의 예산을 다 쓴 뒤에는 재시도로 스로틀을 이길 수
없습니다. 다른 사람이 색인 중이면 스로틀을 각오해야 합니다.

## 3. 터널 열기

도메인은 프라이빗 서브넷에 있고 공인 엔드포인트도 인바운드 포트도 없으므로, 앱
EC2를 경유하는 SSM 터널로만 닿습니다.

사전 준비:

1. AWS CLI v2
2. **Session Manager plugin.** 별도 설치이며, CLI만으로는
   `SessionManagerPlugin is not found`로 실패합니다. 관리자 권한이 없으면 포터블
   zip을 풀어 그 안의 `bin/`을 `PATH` 앞에 두면 동작합니다.
3. 전달받은 액세스 키로 프로파일 구성:
   `aws configure --profile <profile>`, 리전 `ap-northeast-2`

터널을 열고, 세션이 유지되는 동안 이 창을 열어 둡니다.

```bash
aws ssm start-session --profile <profile> --region ap-northeast-2 \
  --target <app-ec2-instance-id> \
  --document-name AWS-StartPortForwardingSessionToRemoteHost \
  --parameters host=<opensearch-endpoint>,portNumber=443,localPortNumber=443
```

성공하면 `Port 443 opened for sessionId ...`와 `Waiting for connections...`가
출력됩니다. 창을 닫으면 세션이 끝나며, 남은 세션은
`aws ssm describe-sessions --state Active`로 확인하고
`aws ssm terminate-session --session-id <id>`로 정리합니다.

## 4. 처음에 반드시 밟는 실패 4가지

전부 스테이징 도메인에서 재현된 것들이며, **어느 것도 터널 고장이 아닙니다.**

**로컬 포트는 9200이 아니라 443으로 여십시오.** SigV4는 `Host` 헤더를 서명
대상에 포함합니다. `localPortNumber=9200`이면 클라이언트는 `endpoint:9200`으로
서명하는데 서버는 포트 없는 `endpoint`로 다시 계산하므로
`403 The request signature we calculated does not match the signature you
provided`가 납니다. 라이브러리 버그가 아니라 포트 불일치입니다. 443을 쓸 수 없는
사정이 있다면, 포트 없는 canonical URL로 서명하고 `Host` 헤더를 덮어써야 합니다.

**`localhost`로 접속하지 마십시오.** 인증서가 엔드포인트 이름으로 발급되어
있어 `https://localhost:443/`은 인증서 검증에 실패합니다(`curl` exit 60).
**검증을 끄지 말고** 클라이언트가 실제 엔드포인트 이름을 보게 하십시오.

```bash
curl --resolve <opensearch-endpoint>:443:127.0.0.1 \
     https://<opensearch-endpoint>/legal-kit-assessment-<contributor>/_search
```

Python이면 호스트만 `127.0.0.1`로 돌리고 URL·`Host`·TLS 검증에는 엔드포인트
이름을 그대로 씁니다.

**`GET /`과 `_cat/indices`는 정상 상태에서도 403입니다.** 정책 경계 밖이기
때문입니다. 연결 확인은 `GET legal-kit-assessment-<contributor>` 같은 인덱스
경로로 하십시오.

**`helpers.bulk()`는 기본값으로 실패합니다.** 전역 `POST /_bulk`를 호출하는데
그것이 거부되기 때문입니다. 인덱스를 명시해
`helpers.bulk(client, actions, index="legal-kit-assessment-...")`로 보내면
`legal-kit-*/_bulk`로 가서 통과합니다.

## 5. 첫 요청부터 서명하십시오

현재 도메인의 access policy는 터널만 뚫려 있으면 **서명하지 않은 요청도
통과**할 만큼 열려 있습니다. **여기에 기대지 마십시오.** 정책은 좁혀질 예정이며,
§1의 `legal-kit-*` 경계는 **서명한 요청에만** 적용됩니다.

서명 없는 클라이언트는 로컬에서도, 오늘의 스테이징 도메인에서도 통과한 뒤,
정책이 정상화되거나 다른 환경에서 재실행되는 순간 **모든 호출이 403**이 됩니다.
조용히, 그리고 늦게 실패합니다 — README의 「개발 시 유의점」이 말하는 바로 그
실패 형태입니다. 첫 요청부터 SigV4로 서명하십시오.

## 6. 평소 개발은 로컬에서

```powershell
docker compose up -d opensearch
```

인덱스는 파생 데이터입니다. 로컬에서 얼마든지 다시 만들되 **접두사는 로컬에서도
`legal-kit-assessment-`로 유지**해 이름이 그대로 옮겨지게 하고, 관리형 도메인은
파이프라인이 거기서 동작함을 입증해야 할 때만 사용하십시오.
