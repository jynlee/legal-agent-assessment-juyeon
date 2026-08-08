# 이식 가능한 애플리케이션 서비스 컨트랙트

> 한국어 번역본입니다. 정본은 [CONTRACT.md](CONTRACT.md)이며, 두 본이 어긋날 경우
> 영어 본문이 우선합니다.

요구되는 경계는 `src/legal_agent_assessment/contracts.py`의 Pydantic 모델과
프로토콜로 정의됩니다.

```python
class GeneralLegalAgent(Protocol):
    async def answer(
        self,
        request: GeneralLegalRequest,
    ) -> GeneralLegalResponse:
        ...
```

이 서비스는 다음 성질을 갖습니다.

- **단일 턴:** 호출 한 번에 독립적인 질문 하나
- **무상태:** 호출 사이에 대화 기억이 필요하지 않음
- 공개 경계에서 **데이터베이스에 의존하지 않음**
- **비동기**이며, 호출자가 타임아웃·취소를 걸 수 있음
- 타입이 정의되고 **JSON 직렬화 가능**
- Peitho, FastAPI, ORM, DI, `ITool`에 **의존하지 않음**
- 교체 가능한 OpenSearch·Bedrock 어댑터로 뒷받침됨

응답은 다음 상태를 구분합니다.

- `answered` — 답변 텍스트가 반환된 하나 이상의 인용으로 뒷받침됨
- `insufficient_evidence` — 제공된 근거로는 답변을 뒷받침할 수 없음
- `out_of_scope` — 질문이 지원 범위 밖의 법률 영역임
- `dependency_unavailable` — 필요한 외부 의존성이 실패함

`answered`에는 인용이 필수입니다. **`answered`가 아닌 상태는 답변 텍스트나 출처를
지어내서는 안 됩니다.** 모든 응답은 사용된 데이터셋·인덱스·임베딩·생성 모델·프롬프트
버전을 노출합니다. 내부 검색 진단 정보는 소비자에게 안전한 텍스트와 분리해 반환할
수 있습니다.

내부 필드와 모델은 추가할 수 있으나, **공개 컨트랙트를 조용히 바꾸지 마십시오.**
현재 경계로 필요한 동작을 표현할 수 없다면, 호환성 설명과 함께 컨트랙트 변경을
제안하십시오.
