# AI (판정·되묻기·분석 대화·모델 레지스트리·M2)

통합 원본: ai-judgment-followup, analysis-agent, issue-43-model-registry, m2-api-alignment

계약은 [API 명세 4.2·4.3·5.2·4.6](../design/api-spec.md)과 [ai OpenAPI](../../contracts/openapi/ai-service.yaml).

## 1. 판정·되묻기 (#6)

### 설계와 다르게 정한 부분

| 항목 | 결정 | 근거 |
|---|---|---|
| 미검증 요소 보류 | 기본 꺼짐, `JUDGE_REQUIRE_VERIFIED=true`로 켬 | 사람 검증(P11)이 없어 켜면 모든 서술 판정이 보류됨 |
| 보류 시 요소 결과 | `HELD`면 `elements` 빈 배열 | 보류가 낮은 수준으로 기록되지 않게 (FN-JDG-04) |
| 결과 결정 위치 | `judgment/service.py` | 업무 판단은 service, `verifier.py`는 원문 대조만 |
| `versions.model` | M2 미활성 판정·되묻기는 LLM 모델 ID, M2 활성 판정은 M2 버전, 규칙 판정은 null | 제공자를 바꿔도 결과를 만든 모델을 남김 |
| 되묻기 요청 `grade` 필수 | 누락 시 400 | 선택값이면 빠뜨려도 드러나지 않고 학년에 맞지 않는 말투가 됨 |
| 사용량 이벤트 `traceparent` | null | 공통 `UsagePublisher`가 받지 않음(미정) |

### 기준이 없어 정한 값 (`app/config.py`, 환경 변수로 변경 가능)

| 항목 | 값 | 이유 |
|---|---|---|
| 판정 결과 | 필수 요소(`goodThought=false`) 모두 충족 `CORRECT`, 충족 배점 0 `RETHINK`, 그 외 `PARTIAL` | state-diagram 3 |
| 보류 판단 순서 | `TOO_SHORT` → `UNVERIFIED_SCOPE` → `INSUFFICIENT_EVIDENCE` → `QUOTE_MISMATCH` | 앞의 둘은 LLM 호출 전에 걸러 비용 절약 |
| `TOO_SHORT` | 공백 제외 10자 미만 | "몰라요" 같은 답 |
| 원문 대조 허용 | 유니코드 NFC, 연속 공백 하나로, 앞뒤 공백 제거 | 띄어쓰기 차이만 허용 |
| 되묻기 유형 | `CORRECT`→`ONE_STEP_MORE`, `PARTIAL`·`HELD`→`TELL_MORE`, `RETHINK`→`LOOK_AGAIN` | 보류는 생각을 더 말하도록 |
| 예시 답 | LLM에 보내지 않고 유출 검사에만 사용. 12자 이상 겹치면 유출, 학생이 이미 쓴 말은 제외 | 학생 말을 되받는 질문을 유출로 오판하던 문제 수정 |
| 되묻기 전체 마감 | 33초 | 첫 생성 + 재생성 최악 62초가 learning→ai 35초(P12)를 넘음. 재생성은 남은 시간 안에서만, 못 하면 질문 은행 |

- learning 연동: 되묻기 `question`이 null이고 `leakCheck.passed=false`면 같은 `type`의 질문 은행 질문을 `source = BANK`로 저장(P16). `elementId`는 `rubric_element.id`
- 판정 최악 31초·되묻기 33초로 learning→ai 35초 안

### OpenAI 전환

- 기본 제공자 `LLM_PROVIDER=openai`, `OPENAI_MODEL=gpt-6.1-terra`(`config.py`·`compose.yaml`·`.env.example`). Claude는 `LLM_PROVIDER=anthropic`으로 계속 사용 가능. 제공자별 클래스로 Claude 전용 기능(추론 강도·대체 모델·스키마 강제) 유지
- 실제 호출 확인: 판정 근거 추출·되묻기 모두 JSON 스키마 통과, LLM 1회 15초(P12) 안
- 수정한 버그: compose가 빈 `OPENAI_BASE_URL`을 넘기면 SDK가 빈 주소를 사용 → 주소가 비면 `https://api.openai.com/v1`을 직접 전달
- 남은 확인: `gpt-6.1-terra`와 Claude의 판정 결과 유형·되묻기 4유형 비교(현재 1건씩만 확인)

## 2. 분석 대화 에이전트 (LangGraph)

```
START → classify ─(범위 불명확·충돌)→ END [clarification]
              └→ retrieve ─(조회 실패)→ END [error]
                        └→ compute ─(기록 부족)→ insufficient → END
                                   ├(수학 점검·기록 밖 질문)→ unsupported → END
                                   ├(LLM 장애)→ fallback → END
                                   └→ answer ─(LLM 장애)→ fallback → END
                                             └→ check ─(대조 실패)→ fallback → END
                                                      └(통과)→ END [result: LLM]
```

- 구성: `analysis_agent/graph.py`(조립), `state.py`, `nodes/`(understand·retrieve·respond), `records.py`(learning 기록 도구, 호출마다 권한 재확인), `metrics.py`, `verification.py`, `templates.py`, `prompts.py`(`analysis@1`), `router.py`(SSE)
- LLM 호출은 기존 `LlmClient` 사용(재시도·사용량 이벤트 `ANALYSIS`·대체 모델 유지). LangGraph는 분기·상태·스트리밍만
- 도구 선택은 질문 유형 → 도구 표(6유형). 학생·기간은 LLM이 아니라 core가 확인한 `scope`만 사용

  | 질문 유형 | 조회 |
  |---|---|
  | 모든 유형 | `summary` |
  | 유형별 활동 | + `thinking-types` |
  | 아이가 쓴 생각 | + `attempts` 첫 페이지 8건 |
  | 전후 변화 | + `changes` 전체 페이지, `thinking-activities` |
  | 돌아보기 | + `thinking-activities` |

- 수치는 learning이 P08로 계산한 값을 그대로 사용(대시보드·리포트와 일치). 분모 5 미만이면 비율 null, 건수 지표에는 분자·분모를 넘기지 않음
- 대조 실패(숫자가 계산값·기록 수·기간 날짜에 없음, 한글 수 표현, 따옴표 인용 불일치, 레벨·등급·점수·사고력 표현) → `source: TEMPLATE`, `fallback.reason: VERIFICATION_FAILED`
- LLM 장애 → 규칙 응답(`AI_UNAVAILABLE`), 기록 부족 → 기간·기록 수만 안내(`fallback` null), 조회 실패 → `error`(빈 기록으로 대체하지 않음)
- `delta` 미전송(대조 통과 후에만 표시), 체크포인터 없음(이전 대화는 core가 `history`로 전달), 전체 마감 `ANALYSIS_DEADLINE` 110초
- core와 확인할 계약: `result`의 `messageId`·`scope.changed`는 core가 붙임. `clarification` `{reason: OTHER_CHILD|DIFFERENT_PERIOD|UNCLEAR, message, current}`, `error` `{code, message, retryable}`(code: `RECORDS_UNAVAILABLE`·`RECORDS_NOT_READY`·`RECORDS_INVALID`·`FORBIDDEN`·`INTERNAL_ERROR`). 돌아보기·전후 변화 근거는 `answerId`·`answerVersion`이 null일 수 있음
- 남은 작업: 유형별 대조 통과율 확인, 실제 learning 연동, core 대화 저장 연결, 리포트 서술 API(api-spec 4.2.1)

## 3. 모델 레지스트리·AI 사용량 (#43)

- 정책(사용자 결정): 평가 근거 필수, SERVICE_OPS의 명시적 사람 승인, 평가 범위 안에서만 활성화, 복귀는 원 승인 범위의 부분 집합, 자동 합격선·새 승인 상태 없음. 근거의 사실성·통계적 합격은 운영자 판단(서버가 평가를 실행했다고 주장하지 않음). NFR-AIQ-06 수치는 별도 정책
- 흐름: `PublicAuthFilter` → `AuthService` SERVICE_OPS 검사 → `ModelVersionService`. 같은 kind·name의 transaction advisory lock → 재조회 → 기존 ACTIVE를 INACTIVE → 대상 ACTIVE·범위·revision → 감사 행 → `OutboxWriter.append`가 한 트랜잭션. 부분 unique index가 ACTIVE 단일성을 최종 강제
- 감사는 공용 `AuditLogService`(미구현) 대신 `ModelVersionRepository.audit` 경로. 공용 감사 도입 시 통합 검토
- 사용량 조회: KST 양 끝 포함 최대 366일(사용자 결정), 범위 밖은 DB 조회 전 400. 미산정 비용이 섞이면 `costUsd` null + `unpricedCalls`
- scope 배열의 null 요소는 Kotlin 제네릭만으로 차단되지 않아 명시적으로 422
- 기존 NULL 평가 행은 목록에 null로 남기고 활성화·복귀는 422, 불완전한 기존 ACTIVE는 내부 snapshot에서 503 `MODEL_VERSION_STATE_INVALID`
- 미구현: ai·scoring의 Pod별 큐 바인딩 → snapshot 조회 → 더 높은 revision만 적용하는 소비 흐름(브로커 fan-out 검증만 완료)

## 4. M2 모델과 API 정렬 (#4)

2026-10-29 로컬 #87 후속 기준: 받은 2.0 모델은 핵심어 입력·score_cuts 보정·rawScores 반환을 적용한다. [#87 구현·검증](issue-87-scoring-m2.md)과 [API 4.3](../design/api-spec.md#43-scoring-service-호출-ai)을 따른다. scoring 이벤트 소비는 #86에 구현되어 있으며, AI #69의 실제 scoring 호출은 별도 후속이다. 아래 #4 기록을 새 모델의 반올림·핵심어 개수 대체 규칙으로 해석하지 않는다.

- `grade`(3~6)는 scoring이 `초{grade}`로 바꿔 모델 입력에 사용(모델은 `[학년] 초5` 문자열로 학습, 데이터에 중학생도 있어 정수로 재학습 불가). 학습 데이터 학년(초5·6) 밖은 활성 범위 밖. 변환을 빠뜨리면 오류 없이 성능만 떨어짐
- 응답 점수: 총점 1~4점(데이터에 5점 없음)·8개 항목 1~5점
- 모델 버전 규칙: `uq_model_version_active`가 `(kind, name)` 단위라 서술·논술 모델을 `name`으로 분리

  | 항목 | 규칙 |
  |---|---|
  | name | 서술형 `m2-klue-narrative`, 논술형 `m2-klue-essay` (`inputType`과 1:1) |
  | version | `X.Y`. 입력·출력 형식이 바뀌면 X, 같은 형식 재학습이면 Y |
  | artifact_uri | `s3://<버킷>/models/{name}/{version}/` |
  | 활성화 | 두 모델을 따로 활성화·롤백 |

- 미정: 논술 답변 `essay{claim, reasons[], rebuttal}`을 scoring 입력 `text`로 합치는 규칙(scoring 연동 전 결정)
