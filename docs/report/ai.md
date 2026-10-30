# AI (판정·되묻기·분석 대화·모델 레지스트리·M2·리포트 서술)

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

- 구성: `analysis_agent/graph.py`(조립), `state.py`, `nodes/`(understand·retrieve·respond), `tools.py`(`RecordTools`, 호출마다 권한 재확인), `calculators.py`, `verification.py`, `templates.py`, `prompts.py`(`analysis@2`), `router.py`(SSE), `clients/learning_client.py`(learning 기록 조회 HTTP, #65)
- LLM 호출은 기존 `LlmClient` 사용(재시도·사용량 이벤트 `ANALYSIS`·대체 모델 유지). classify는 `generate`(구조화 출력), answer는 `stream`(일반 텍스트). LangGraph는 분기·상태·스트리밍만
- 도구 선택은 질문 유형 → 도구 표(6유형). 학생·기간은 LLM이 아니라 core가 확인한 `scope`만 사용

  | 질문 유형 | 조회 |
  |---|---|
  | 모든 유형 | `summary` |
  | 유형별 활동 | + `thinking-types` |
  | 아이가 쓴 생각 | + `attempts` 첫 페이지 8건 |
  | 전후 변화 | + `changes` 전체 페이지, `thinking-activities` |
  | 돌아보기 | + `attempts` 전체 페이지 (#66: 근거 작성 시각 `reflection.createdAt`이 attempts에만 있음) |
  | (#67 대조용, 그래프 미연결) | `evidence(answerIds)` — 삭제된 근거는 `available: false`·원문 null 그대로 |

- 수치는 learning이 P08로 계산한 값을 그대로 사용(대시보드·리포트와 일치). 분모 5 미만이면 비율 null, 건수 지표에는 분자·분모를 넘기지 않음
- #65 결정(사용자): 전후 변화 수(글자·문장·까닭을 잇는 말)는 ai가 다시 세지 않고 learning `changes.counts`를 그대로 사용. 이슈의 `calculators.change_counts`는 만들지 않고 class-diagram 5.2에서 제거. 까닭을 잇는 말 목록·문장 구분 규칙은 learning·report만 보유
- #65 API 문서 변경: api-spec 4.1 `thinking-activities` 호출자에 `ai` 추가(기존 구현이 이미 호출, 경로·응답 변경 없음). learning은 다른 학생 기록 조회와 같은 역할·학생 범위 검사(`requireStudentRecord`)를 적용하므로 공급자 변경 없음
- 대조 실패(숫자가 계산값·기록 수·기간 날짜에 없음, 한글 수 표현, 따옴표 인용 불일치, 레벨·등급·점수·사고력 표현) → `source: TEMPLATE`, `fallback.reason: VERIFICATION_FAILED`
- LLM 장애 → 규칙 응답(`AI_UNAVAILABLE`), 기록 부족 → 기간·기록 수만 안내(`fallback` null), 조회 실패 → `error`(빈 기록으로 대체하지 않음)
- 체크포인터 없음(이전 대화는 core가 `history`로 전달), 전체 마감 `ANALYSIS_DEADLINE` 110초(core 전체 120초 안). 첫 이벤트는 classify 시작 `status`라 core 첫 응답 20초 조건과 무관
- core와 확인할 계약: `result`의 `messageId`·`scope.changed`는 core가 붙임. `clarification` `{reason: OTHER_CHILD|DIFFERENT_PERIOD|UNCLEAR, message, current}`, `error` `{code, message, retryable}`(code: `RECORDS_UNAVAILABLE`·`RECORDS_NOT_READY`·`RECORDS_INVALID`·`FORBIDDEN`·`INTERNAL_ERROR`). 전후 변화 근거는 `answerVersion`·`submittedAt`이 null(core가 learning evidence 값으로 채움)
- 남은 작업: 유형별 대조 통과율 확인, 실제 learning 연동, core 대화 저장 연결

### #66 스트리밍·근거 계약 (2026-10-29)

결정(사용자 승인):

| 항목 | 결정 | 근거 |
|---|---|---|
| `delta` | answer LLM 답변을 조각마다 `delta {text}`로 전송(대조 전 임시 표시). 확정은 대조 통과 `result.answer`만 | api-spec 3.3·sequence 5. 기존 구현의 미전송을 설계에 맞춤 |
| 인용 식별 | answer는 일반 텍스트. 본문 큰따옴표 구간을 원문과 대조해 처음 들어맞는 원문을 근거로 연결, 같은 원문은 근거 하나 | 텍스트 스트리밍과 구조화 출력(citations) 병행 불가. core는 중복 `answerId` 근거를 거부 |
| 스트리밍 재시도 | 첫 조각 전 실패만 기존 재시도(1회, P12). 첫 조각 뒤 실패는 재시도 없이 `AI_UNAVAILABLE` 규칙 응답 | 이미 보낸 delta와 다른 답이 이어 붙지 않게 |
| 스트림 타임아웃 | LLM 1회 15초(`LLM_TIMEOUT`)를 요청 시작부터 다음 조각까지 적용, 마감이 가까우면 남은 시간 | 판정·되묻기와 같은 1회 한도 |
| 가명 토큰 | 학생 이름·ID와 시도·답변 ID를 LLM 요청에 넣지 않음. 원문은 `S1` 번호로만 표시하므로 토큰 생성·복원 불필요 | api-spec 4.2 문구 정리, 테스트로 미포함 보장 |
| 돌아보기 근거 | `kind: REFLECTION`, `attemptId`로 식별(`answerId`·`answerVersion` null), `submittedAt` = `reflection.createdAt` | 서비스 간 참조는 `attempt_id`·`answer_id`뿐(ERD 1장)이고 돌아보기는 시도당 하나(UK). learning API 변경 없음 |

API 변경(`docs/design/api-spec.md` 1장 Evidence·3.3·4.2, `contracts/openapi/ai-service.yaml`):
- `evidence[].kind: ANSWER | REFLECTION` 추가(필수)
- `delta` 전송으로 변경(이벤트 순서 `status* → delta* → result → done`)
- 소비 측(core #41) 변경 필요: `kind = REFLECTION` 근거는 `answerId` null 허용, 재조회는 `/internal/records/students/{studentId}/attempts/{attemptId}`의 `reflection`. `message_evidence.answer_id` 저장 방식은 #41에서 결정
- learning 변경 없음. ai의 돌아보기 질문 조회가 `thinking-activities` → `attempts` 전체 페이지로 바뀜(같은 P08 집계 대상)
- 안내 응답(기록 없음·비교 기록 부족·지원하지 않는 질문)의 `source`·`fallback`·`verification` 의미는 #67에서 정리(이번 변경 없음)

구현: `llm/base.py` `LlmClient.stream`(`LlmTextStream`, 제공자 `_stream`은 텍스트 조각 → `StreamEnd(모델·토큰)`), `llm/providers.py` Anthropic `beta.messages.stream`·OpenAI `stream=True`(`include_usage`). core 단절 시 Starlette(ASGI 2.3)가 응답 생성기를 취소 → 그래프·LLM 스트림 중단(`test_cancelled_stream_stops_graph_and_llm`).

#### 분기별 실제 SSE 응답 (2026-10-29)

- 실행: 로컬 `uvicorn app.main:app`(이 브랜치), 실제 LLM `LLM_PROVIDER=openai`·`gpt-6-luna`. learning은 대역(테스트 기록 `records_fixture`와 같은 데이터를 `/internal/records`로 응답, 학생 `s-1` 기록 있음·`s-empty` 기록 없음·`s-nochange` 되묻기 뒤 다시 쓴 시도 없음). 실제 learning·core 연결이 아님
- 조회 기간 2026-10-20~26. 줄임: delta는 앞 2개와 개수만, `result.metrics`는 label만 표시(실제 응답은 Metric 전체)
- RabbitMQ 없이 실행해 사용량 이벤트는 발행되지 않음(재시도 로그만, 응답 영향 없음)
- 참고: 같은 기록 없음 학생에 "이번 주에 몇 번 했어?"를 물으면 실행일(10-29) 기준 이번 주가 골라 둔 기간과 달라 `clarification(DIFFERENT_PERIOD)`로 끝남. 기간을 정하지 않는 질문으로 기록 없음 안내를 수집함
- 안내 응답(기록 없음·비교 기록 부족·지원하지 않는 질문)의 `verification: null`은 현재 core 검증에서 거부됨 → #67에서 정리

##### 정상 (전후 변화, LLM 답변 대조 통과)

학생 `s-1`, 질문 "질문을 받고 뭐가 달라졌어?"

```
event: status
data: {"state": "RUNNING", "message": "질문을 확인하는 중"}
event: status
data: {"state": "RUNNING", "message": "기록을 조회하는 중"}
event: status
data: {"state": "RUNNING", "message": "수치를 계산하는 중"}
event: status
data: {"state": "RUNNING", "message": "답변을 쓰는 중"}
event: delta
data: {"text": "이번"}
event: delta
data: {"text": " 기간"}
# … delta 103개 더 (총 105개)
event: status
data: {"state": "RUNNING", "message": "숫자와 인용을 기록과 맞춰 보는 중"}
event: result
data: {"answer": "이번 기간에는 학습 활동 3개가 기록되었고, 되묻기를 받은 활동 2개 중 1개에서 답을 보완했어요. 처음에는 “나는 찬성해.”라고 썼고, 다시 쓸 때는 “나는 찬성해. 왜냐하면 쉬는 시간이 길면 더 잘 놀 수 있어.”라고 이유를 덧붙였어요. 이 활동에서는 글자 수와 문장 수가 늘었고, 까닭을 잇는 말도 사용했어요.", "source": "LLM", "fallback": null, "scope": {"childId": "s-1", "from": "2026-10-20", "to": "2026-10-26"}, "metrics": ["학습한 활동", "되묻기 후 생각을 더한 활동", "글자 수가 늘어난 시도", "문장 수가 늘어난 시도", "까닭을 잇는 말이 늘어난 시도"], "evidence": [{"kind": "ANSWER", "attemptId": "t-1", "missionTitle": "쉬는 시간 토론", "answerId": "a-1", "answerVersion": null, "submittedAt": null, "quote": "나는 찬성해.", "available": true}, {"kind": "ANSWER", "attemptId": "t-1", "missionTitle": "쉬는 시간 토론", "answerId": "a-2", "answerVersion": null, "submittedAt": null, "quote": "나는 찬성해. 왜냐하면 쉬는 시간이 길면 더 잘 놀 수 있어.", "available": true}], "verification": {"numbersMatched": true, "quotesMatched": true, "contentAllowed": true}, "recordCount": 3, "versions": {"model": "gpt-6-luna", "prompt": "analysis@2"}}
event: done
data: {}
```

##### 범위 확인

학생 `s-1`, 질문 "지난달에는 몇 번 했어?"

```
event: status
data: {"state": "RUNNING", "message": "질문을 확인하는 중"}
event: clarification
data: {"reason": "DIFFERENT_PERIOD", "message": "질문한 기간이 골라 둔 조회 기간과 달라요. 어느 기간을 볼지 골라 주세요.", "current": {"childId": "s-1", "from": "2026-10-20", "to": "2026-10-26"}}
```

##### 기록 없음

학생 `s-empty`, 질문 "몇 번 했어?"

```
event: status
data: {"state": "RUNNING", "message": "질문을 확인하는 중"}
event: status
data: {"state": "RUNNING", "message": "기록을 조회하는 중"}
event: status
data: {"state": "RUNNING", "message": "수치를 계산하는 중"}
event: result
data: {"answer": "조회 기간은 2026-10-20부터 2026-10-26까지예요. 이 기간에 답변을 제출한 시도가 없어 분석할 기록이 없어요. 기간을 넓히거나 다른 내용을 물어봐 주세요.", "source": "TEMPLATE", "fallback": null, "scope": {"childId": "s-empty", "from": "2026-10-20", "to": "2026-10-26"}, "metrics": ["학습한 활동", "완료한 활동", "도움 없이 시작한 활동", "되묻기 후 생각을 더한 활동"], "evidence": [], "verification": null, "recordCount": 0, "versions": {"model": "gpt-6-luna", "prompt": "analysis@2"}}
event: done
data: {}
```

##### 비교 기록 부족

학생 `s-nochange`, 질문 "질문을 받고 뭐가 달라졌어?"

```
event: status
data: {"state": "RUNNING", "message": "질문을 확인하는 중"}
event: status
data: {"state": "RUNNING", "message": "기록을 조회하는 중"}
event: status
data: {"state": "RUNNING", "message": "수치를 계산하는 중"}
event: result
data: {"answer": "조회 기간은 2026-10-20부터 2026-10-26까지예요. 답변을 제출한 시도 3개 중 되묻기 뒤에 답변을 다시 쓴 시도가 없어 전후를 비교할 수 없어요. 기간을 넓히거나 다른 내용을 물어봐 주세요.", "source": "TEMPLATE", "fallback": null, "scope": {"childId": "s-nochange", "from": "2026-10-20", "to": "2026-10-26"}, "metrics": ["학습한 활동", "되묻기 후 생각을 더한 활동", "글자 수가 늘어난 시도", "문장 수가 늘어난 시도", "까닭을 잇는 말이 늘어난 시도"], "evidence": [], "verification": null, "recordCount": 3, "versions": {"model": "gpt-6-luna", "prompt": "analysis@2"}}
event: done
data: {}
```

##### 지원하지 않는 질문

학생 `s-1`, 질문 "수학 문제 풀이가 맞았는지 점검해 줘"

```
event: status
data: {"state": "RUNNING", "message": "질문을 확인하는 중"}
event: status
data: {"state": "RUNNING", "message": "기록을 조회하는 중"}
event: status
data: {"state": "RUNNING", "message": "수치를 계산하는 중"}
event: result
data: {"answer": "수학 풀이 점검은 아직 제공하지 않아요. 조회 기간은 2026-10-20부터 2026-10-26까지예요. 답변을 제출한 시도는 3개예요. 숫자, 생각 유형별 활동, 아이가 쓴 생각, 되묻기 전후 변화, 돌아보기에 대해 물어봐 주세요.", "source": "TEMPLATE", "fallback": null, "scope": {"childId": "s-1", "from": "2026-10-20", "to": "2026-10-26"}, "metrics": ["학습한 활동"], "evidence": [], "verification": null, "recordCount": 3, "versions": {"model": "gpt-6-luna", "prompt": "analysis@2"}}
event: done
data: {}
```

##### 돌아보기

학생 `s-1`, 질문 "돌아보기에 뭐라고 썼어?"

```
event: status
data: {"state": "RUNNING", "message": "질문을 확인하는 중"}
event: status
data: {"state": "RUNNING", "message": "기록을 조회하는 중"}
event: status
data: {"state": "RUNNING", "message": "수치를 계산하는 중"}
event: status
data: {"state": "RUNNING", "message": "답변을 쓰는 중"}
event: delta
data: {"text": "돌"}
event: delta
data: {"text": "아"}
# … delta 15개 더 (총 17개)
event: status
data: {"state": "RUNNING", "message": "숫자와 인용을 기록과 맞춰 보는 중"}
event: result
data: {"answer": "돌아보기에는 “근거 찾기가 어려웠어”라고 썼어요.", "source": "LLM", "fallback": null, "scope": {"childId": "s-1", "from": "2026-10-20", "to": "2026-10-26"}, "metrics": ["학습한 활동", "완료한 활동", "돌아보기를 쓴 활동", "난이도 어려웠어 돌아보기"], "evidence": [{"kind": "REFLECTION", "attemptId": "t-1", "missionTitle": "쉬는 시간 토론", "answerId": null, "answerVersion": null, "submittedAt": "2026-10-22T19:30:00+09:00", "quote": "근거 찾기가 어려웠어", "available": true}], "verification": {"numbersMatched": true, "quotesMatched": true, "contentAllowed": true}, "recordCount": 3, "versions": {"model": "gpt-6-luna", "prompt": "analysis@2"}}
event: done
data: {}
```


## 3. 모델 레지스트리·AI 사용량 (#43)

- 정책(사용자 결정): 평가 근거 필수, SERVICE_OPS의 명시적 사람 승인, 평가 범위 안에서만 활성화, 복귀는 원 승인 범위의 부분 집합, 자동 합격선·새 승인 상태 없음. 근거의 사실성·통계적 합격은 운영자 판단(서버가 평가를 실행했다고 주장하지 않음). NFR-AIQ-06 수치는 별도 정책
- 흐름: `PublicAuthFilter` → `AuthService` SERVICE_OPS 검사 → `ModelVersionService`. 같은 kind·name의 transaction advisory lock → 재조회 → 기존 ACTIVE를 INACTIVE → 대상 ACTIVE·범위·revision → 감사 행 → `OutboxWriter.append`가 한 트랜잭션. 부분 unique index가 ACTIVE 단일성을 최종 강제
- 감사는 공용 `AuditLogService`(미구현) 대신 `ModelVersionRepository.audit` 경로. 공용 감사 도입 시 통합 검토
- 사용량 조회: KST 양 끝 포함 최대 366일(사용자 결정), 범위 밖은 DB 조회 전 400. 미산정 비용이 섞이면 `costUsd` null + `unpricedCalls`
- scope 배열의 null 요소는 Kotlin 제네릭만으로 차단되지 않아 명시적으로 422
- 기존 NULL 평가 행은 목록에 null로 남기고 활성화·복귀는 422, 불완전한 기존 ACTIVE는 내부 snapshot에서 503 `MODEL_VERSION_STATE_INVALID`
- scoring은 #86에서 Pod별 큐 바인딩 → snapshot 조회 → 더 높은 revision 적용·재연결을 구현했다. ai 소비 흐름은 #68 후속이다. [scoring #86 검증](issue-86-scoring-model-events.md)을 참고한다.

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

## 5. 리포트 서술·저녁 질문 (#64)

- `POST /internal/report-narratives`(api-spec 4.2.1, `app/report_narrative/`). 서술·저녁 질문만 만들고 숫자 계산·대조·템플릿 전환은 report(class-diagram 5.2, P16). 사용량 `callType = REPORT_NARRATIVE`, 프롬프트 `report@1`(`/internal/versions`의 `reportNarrative`)
- API 변경: 요청 `quotes[]`에 `answerVersion` 추가(report `NarrativeGenerator`가 근거 링크 버전으로 채움). 응답 `citedQuotes[].answerVersion`을 ai가 알 수 없던 문제 해소. 3.4 상세 `quotes`·저장 payload는 그대로
- 인용: LLM이 `{후보 번호, 원문 구절}`을 고르고, 구절이 그 후보 원문의 부분 문자열이 아니거나 번호가 범위 밖이면 제외. ID·버전은 입력값. 서술 속 따옴표 문구와 `citedQuotes` 불일치는 report 대조에서 템플릿 전환
- 프롬프트 규칙은 report `ReportVerifier` 통과 범위에 맞춤: 입력 수치·전후 변화 값만 아라비아 숫자로, 한글 수사·미션 제목·답 속 숫자(인용 밖) 금지, 점수·등급·레벨·순위 낱말과 사고력 향상 단정 금지, 기록 없는 유형은 "확인된 기록 없음", 미작성 돌아보기는 "쓰지 않음"
- LLM 입력에는 수치·미션 제목·답변·돌아보기 원문만. 학생 이름·ID와 시도·답변 ID는 넣지 않음(인용은 후보 번호로 지칭, NFR-SEC-03). 로그에 원문 미기록

### 기준이 없어 정한 값

| 항목 | 값 | 근거 |
|---|---|---|
| 서술 | 학부모 대상 해요체 3~5문장, 600자 이내(프롬프트 지시, 코드 검사 없음) | 리포트 한 화면 분량 |
| 저녁 질문 | 1개, 아이에게 읽어 줄 친근한 반말 한 문장. 이번 주 미션·답에서 출발, 정답·평가·능력 암시 금지 | 기획서 저녁 식탁 대화 |
| 전체 마감 `NARRATIVE_DEADLINE` | 28초. LLM 1회 15초 + 대기 1초, 재시도는 남은 시간 안에서만 | report→ai 읽기 타임아웃 30초(report `http_read_timeout`)보다 짧게 |
| 돌아보기 난이도 | `EASY·NORMAL·HARD` 코드를 프롬프트에서 "쉬웠어·보통·어려웠어"로, 표시값이 오면 그대로 | report 저장 payload는 코드 유지 |
| 빈 서술·빈 저녁 질문 | 503 `AI_UNAVAILABLE`(`retryable: true`) | report는 AI 실패를 `FAILED`로 처리 |

- 후속: `model.version.activated` 수신 시 서술 프롬프트 버전 교체는 #68, 실제 LLM 연동 E2E는 report worker 생성기 조립 후

## 6. scoring 기동 모델 로딩 (#85)

`feature/scoring-model-registry`는 core 활성 snapshot 조회, 승인 scope·revision 검사, 실제 S3/MinIO 가중치 CPU 로딩 및 `/internal/versions`를 구현한다. 활성 모델이 없으면 준비 완료, 최초 조회·로딩 실패 시 준비 안 됨으로 재시도하며 프로세스는 유지한다. 같은 모델 교체 실패 시 기존 모델은 보존한다. 기동 이후 활성화 이벤트는 #86, M2 채점 API는 #87, M1 계약은 #88 범위다. 상세 증거는 [#85 검증](issue-85-scoring-model-registry.md)을 따른다.

## #67·#41 최종 응답 검증 후속

기준 develop dd8bbc8(PR #158/#145, #159/#66 포함), feature/ai-analysis-verification. 사용자가 기존 AI 검증/모델/템플릿/응답 노드, core 수신·저장·조회, 관련 계약/테스트 및 필요한 프론트 표시 변경을 승인했다. verification.py/templates.py를 재사용하며 이슈의 예정 파일명으로 중복 구현하지 않는다. 최종 응답 검사와 LLM 초안 실패값을 분리하고 notice로 정상 안내를 구분한다. 기존 REPORT 후속 브랜치는 별도 보존한다. 사용자가 돌아보기 참조 및 fallback/notice 저장의 DB 확장도 승인했다. 기존 ANSWER 참조를 유지하고 REFLECTION만 answer_id/version NULL을 허용하며 종류 CHECK를 추가한다. 별도 REPORT 브랜치의 V17과 충돌하지 않도록 V18을 사용한다. 구현·테스트를 마친 뒤 일괄 검증한다.

배포 순서: 별도 REPORT 브랜치의 V17을 먼저 통합·적용한 뒤 이 브랜치의 V18을 적용한다. V18을 먼저 적용한 환경에 나중에 낮은 번호 V17을 투입하는 방식은 사용하지 않는다. 최종 통합에서 두 migration의 공존을 검증한다. 기존 migration checksum은 유지한다. 최종 응답 검증 실패는 result 없이 error로 전달하며 기존 core의 수동 재시도/사용량 제한 정책을 유지한다.

V18의 kind는 임시 DEFAULT로 기존 행을 ANSWER로 채운 뒤 DEFAULT를 제거한다. 저장소의 DB 기본값 없음 규칙을 유지하며 새 쓰기는 core가 kind를 명시한다. verifier는 허용된 숫자 값·인용 원문·금지 표현을 검사한다. 자연어 문장 전체의 의미 정합성을 증명하거나 실제 모델 품질 향상을 측정한 것은 아니다.

### #67·#162 최종 검증 (2026-10-30)

#67은 AI 최종 verification·fallback.draftVerification·notice 생산을, #162는 core 수신·저장·근거 조회·DB·프론트·HTTP 연결을 담당한다. #47 관리자 기능은 별도 브랜치에서 진행한다.

사용자의 명시적 승인 후 InternalRestClientFactory에 선택적인 HTTP 버전 인자를 추가하고 AiClient 분석 스트림만 HTTP/1.1로 지정했다. 다른 서비스는 인자를 생략하므로 기존 JDK 기본 동작·토큰·타임아웃·재시도 정책을 유지한다. 실제 HTTP 테스트에서 AI 요청의 Upgrade·HTTP2-Settings 헤더 부재를 확인했다.

인계받은 최종 검증 산출물 기준:

- AI: pytest 226개, Ruff check/format 통과.
- core: HTTP/1.1 적용 후 전체 52클래스 333개 test, 실패·오류·생략 0, bootJar 통과.
- 프론트: test 114개, lint/build 통과.
- DB: 전체 migration cycle에서 core 42테이블/393컬럼, learning 19/160, report 8/56 대조. 63개 위반 입력, 75 CHECK 집합, 23 인덱스, 재적용 이력, report downgrade/upgrade 통과. V16 기존 답변 근거에 V18을 적용해 answerId/version 보존·kind=ANSWER·fallback/notice null·영구 기본값 없음을 확인했다. 별도 DB에서 REPORT V17→분석 V18 공존 검사도 통과했다.
- 실제 core→AI 그래프→learning 연결 9개 시나리오: 정상, 숫자/인용 불일치, 키 미설정, 기록 없음, 지원 외, 돌아보기, 범위 확인, 조회 장애 후 재시도 통과. 추가로 스트림 연결 해제 시 FAILED 및 부분 답변 미저장, 다른 자녀 403, 인증 없음 401을 확인했다.
- 브라우저: 규칙 응답 두 종류·지원 외 안내·돌아보기 근거·기록 없음 5개 시나리오, 실제 API 응답 28건, pageerror 0. 프론트 MSW 대역은 사용하지 않았다.

LLM은 테스트 dependency override 또는 실제 키 미설정 분기다. 실제 외부 유료 LLM 호출·모델 품질·배포·원격 CI 검증이 아니다. 자동 테스트와 연동 통과를 자연어 전체 의미의 정합성이나 모델 품질 향상으로 해석하지 않는다. 검증 로그·XML·실제 SSE 응답·브라우저 결과는 로컬 issue67-verification에 보존했다.

인계 후 마지막 스키마 보완을 포함해 `python -O -m unittest discover -s scripts/tests -v` 79개가 통과했다. core/AI OpenAPI 표준 검사와 `scripts/validate_analysis_contracts.py`의 실제 SSE 최종 응답 8종 검사도 통과했다. 최종 `git diff --check`를 확인했다. 실행 코드 변경 없이 보고서만 최신 결과로 정리했으므로 이미 통과한 AI·core·프론트·DB·브라우저 검증은 반복하지 않았다. 최종 파일의 SHA-256 목록은 로컬 검증 산출물에 갱신했다.

최신 origin/develop 640e0a2와 대조했다. 추가된 #146은 learning 신고 지원 조회·피드백 판정 ID 범위이며 이번 실행 코드 변경과 겹치지 않는다. 이 작업은 검증한 develop dd8bbc8 기반을 유지한다. REPORT V17을 먼저 통합·적용한 뒤 분석 V18을 적용하는 순서는 유지한다. PR의 base는 develop이며 PR은 사용자가 생성한다.

#47·#67·#162의 최신 develop 통합·관리자 실행·추가 브라우저 검증 결과는 [관리자 운영 통합 최종 검증](issue-47-admin-operations.md#통합-최종-검증)을 따른다. 이 절 이전의 dd8bbc8 결과는 기능 브랜치 검증 이력이다.
