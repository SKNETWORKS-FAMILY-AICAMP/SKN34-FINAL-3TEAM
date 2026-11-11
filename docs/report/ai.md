# AI (판정·되묻기·분석 대화·모델 레지스트리·M2·교차 확인·리포트 서술)

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
| 사용량 이벤트 `traceparent` | 요청 context 값 | `publisher.py`가 `context.traceparent`를 전달 |

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

- 기본 제공자 `LLM_PROVIDER=openai`, `OPENAI_MODEL=gpt-6-luna`(`config.py`·`compose.yaml`·`.env.example`). Claude는 `LLM_PROVIDER=anthropic`으로 계속 사용 가능. 제공자별 클래스로 Claude 전용 기능(추론 강도·대체 모델·스키마 강제) 유지
- 실제 호출 확인: 판정 근거 추출·되묻기 모두 JSON 스키마 통과, LLM 1회 15초(P12) 안
- 수정한 버그: compose가 빈 `OPENAI_BASE_URL`을 넘기면 SDK가 빈 주소를 사용 → 주소가 비면 `https://api.openai.com/v1`을 직접 전달
- 남은 확인: `gpt-6-luna`와 Claude의 판정 결과 유형·되묻기 4유형 비교(현재 1건씩만 확인)

### 판정 품질 평가 도구 (#199)

- 러너 [`evaluation/runners/judgment_eval.py`](../../evaluation/runners/judgment_eval.py), 자료 형식 [`evaluation/datasets/judgment/`](../../evaluation/datasets/judgment/README.md). `/internal/judgments`를 그대로 호출하고 테스트는 `tests/test_judgment_eval_runner.py`(대역 LLM)
- 지표: 결과 QWK(RETHINK<PARTIAL<CORRECT, 사람 결과는 평가자 요소 표시에 서비스 `_result` 규칙 적용), 요소 일치율·kappa, 보류 비율·사유, 인용 불일치 보류 비율. 사람-AI 일치도는 평가자 2명 각각과 비교한 평균이며 HELD는 빼고 따로 셈(FN-JDG-04)
- 묶음: 전체·범위 키별·미션별(기준 미달 미션은 판정하지 않고 기록, 기능명세 3.5)·미션/요소별 일치율(검증 통과 요소만 충족 표시, NFR-AIQ-01 → `judgeVerified` 결정 근거)
- 출력: 버전별 요약 JSON(학생 원문 없음, 학년·유형 묶음 키 `judgment/grade-N/<inputType>`), `--baseline`으로 이전 결과와 차이, 모델 레지스트리 `evaluation` 9개 필드(api-spec 5.2). `evaluatedScopes`는 판정 프롬프트 등록·활성화 범위 `ai/judgment`(api-spec 4.2, #313)
- 정한 값: 계산 정확성은 "해당 없음"(판정은 계산 없음), 학습·평가 분리는 "학습 없는 프롬프트, 평가 답안은 프롬프트에 미포함"으로 기록
- 남은 일(#199는 종료됐으나 기준선은 미실행): 실제 평가 자료(P11, 5미션×20답안×평가자 2명) 준비 담당·일정, 평가 미션 범위·QWK 허용 기준(NFR-AIQ-06, 11/22) 확인 후 `judge@2` 실제 기준선 1회 실행·이 절에 결과 추가

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

- P25(#392, [서비스 기획 방향](service-direction.md)): 일일 리포트 고정 대화는 core가 범위(그날)와 리포트 요약을 요청에 넣는다. ai는 report를 직접 호출하지 않고 기존 흐름을 그대로 쓴다
- 구성: `analysis_agent/graph.py`(조립), `service.py`(`AnalysisService`: 범위·기한·프롬프트 선택, 그래프 실행·최종 상태 → 이벤트, #253), `state.py`, `context.py`(`AgentContext`), `nodes/`(understand·retrieve·respond), `tools.py`(`RecordTools`, 호출마다 권한 재확인), `calculators.py`, `verification.py`, `templates.py`, `prompts.py`(`analysis@4`, #454), `router.py`(SSE), `clients/learning_client.py`(learning 기록 조회 HTTP, #65)
- LLM 호출은 기존 `LlmClient` 사용(재시도·사용량 이벤트 `ANALYSIS`·대체 모델 유지). classify는 `generate`(구조화 출력), answer는 `stream`(일반 텍스트). LangGraph는 분기·상태·스트리밍만
- 도구 선택은 질문 유형 → 도구 표(6유형). 학생·기간은 LLM이 아니라 core가 확인한 `scope`만 사용

  | 질문 유형 | 조회 |
  |---|---|
  | 모든 유형 | `summary` |
  | 유형별 활동 | + `thinking-types` |
  | 아이가 쓴 생각 | + `attempts` 첫 페이지 8건 |
  | 전후 변화 | + `changes` 전체 페이지, `thinking-activities` |
  | 돌아보기 | + `attempts` 전체 페이지 (#66: 근거 작성 시각 `reflection.createdAt`이 attempts에만 있음) |

- 수치는 learning이 P08로 계산한 값을 그대로 사용(대시보드·리포트와 일치). 분모 5 미만이면 비율 null, 건수 지표에는 분자·분모를 넘기지 않음
- #65 결정(사용자): 전후 변화 수(글자·문장·까닭을 잇는 말)는 ai가 다시 세지 않고 learning `changes.counts`를 그대로 사용. 이슈의 `calculators.change_counts`는 만들지 않고 class-diagram 5.2에서 제거. 까닭을 잇는 말 목록·문장 구분 규칙은 learning·report만 보유
- #65 API 문서 변경: api-spec 4.1 `thinking-activities` 호출자에 `ai` 추가(기존 구현이 이미 호출, 경로·응답 변경 없음). learning은 다른 학생 기록 조회와 같은 역할·학생 범위 검사(`requireStudentRecord`)를 적용하므로 공급자 변경 없음
- 대조 실패(숫자가 계산값·기록 수·기간 날짜에 없음, 한글 수 표현, 따옴표 인용 불일치, 레벨·등급·점수·사고력 표현) → `source: TEMPLATE`, `fallback.reason: VERIFICATION_FAILED`
- LLM 장애 → 규칙 응답(`AI_UNAVAILABLE`), 기록 부족 → 기간·기록 수만 안내(`fallback` null), 조회 실패 → `error`(빈 기록으로 대체하지 않음)
- 체크포인터 없음(이전 대화는 core가 `history`로 전달), 전체 마감 `ANALYSIS_DEADLINE` 110초(core 전체 120초 안). 첫 이벤트는 classify 시작 `status`라 core 첫 응답 20초 조건과 무관
- core 계약(#41에서 반영): `result`의 `messageId`·`scope.changed`는 core가 붙임. `clarification` `{reason: OTHER_CHILD|DIFFERENT_PERIOD|UNCLEAR, message, current}`, `error` `{code, message, retryable}`(code: `RECORDS_UNAVAILABLE`·`RECORDS_NOT_READY`·`RECORDS_INVALID`·`FORBIDDEN`·`INTERNAL_ERROR`). 전후 변화 근거는 `answerVersion`·`submittedAt`이 null(core가 learning evidence 값으로 채움)
- 남은 작업: 유형별 대조 통과율 확인(실제 learning 연동·core 대화 저장은 #41·#65에서 완료)

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
- 소비 측(core #41) 반영: `kind = REFLECTION` 근거는 `answerId` null 허용, 재조회는 `/internal/records/students/{studentId}/attempts/{attemptId}`의 `reflection`. `message_evidence.answer_id`는 nullable로 저장(#41)
- learning 변경 없음. ai의 돌아보기 질문 조회가 `thinking-activities` → `attempts` 전체 페이지로 바뀜(같은 P08 집계 대상)
- 안내 응답(기록 없음·비교 기록 부족·지원하지 않는 질문)의 `source`·`fallback`·`verification` 의미는 #67에서 정리(이번 변경 없음)

구현: `llm/base.py` `LlmClient.stream`(`LlmTextStream`, 제공자 `_stream`은 텍스트 조각 → `StreamEnd(모델·토큰)`), `llm/providers.py` Anthropic `beta.messages.stream`·OpenAI `stream=True`(`include_usage`). core 단절 시 Starlette(ASGI 2.3)가 응답 생성기를 취소 → 그래프·LLM 스트림 중단(`test_cancelled_stream_stops_graph_and_llm`).

#### SSE 응답 예시 (정상 분기, 10/29 실제 LLM)

delta는 앞 2개와 개수만, `result`는 줄여서 표시. 범위 확인·기록 없음·비교 기록 부족·지원하지 않는 질문·돌아보기 분기는 같은 순서에서 `clarification` 또는 규칙 `result`로 끝남.

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

### #67·#162 최종 응답 검증

- 최종 응답 검사와 LLM 초안 실패값을 분리하고 notice로 정상 안내를 구분(`verification.py`/`templates.py` 재사용). 최종 응답 검증 실패는 result 없이 error로 전달하며 core의 수동 재시도·사용량 정책 유지
- 돌아보기 참조·fallback/notice 저장을 위해 core V18: 기존 ANSWER 참조 유지, REFLECTION만 answer_id/version NULL 허용, 종류 CHECK. kind는 임시 DEFAULT로 기존 행을 ANSWER로 채운 뒤 DEFAULT 제거(새 쓰기는 core가 kind 명시)
- verifier는 허용된 숫자 값·인용 원문·금지 표현을 검사. 자연어 문장 전체의 의미 정합성을 증명하지는 않음
- core `AiClient` 분석 스트림만 HTTP/1.1 고정(InternalRestClientFactory에 선택적 HTTP 버전 인자)

## 3. 모델 레지스트리·AI 사용량 (#43)

- 정책(사용자 결정): 평가 근거 필수, SERVICE_OPS의 명시적 사람 승인, 평가 범위 안에서만 활성화, 복귀는 원 승인 범위의 부분 집합, 자동 합격선·새 승인 상태 없음. 근거의 사실성·통계적 합격은 운영자 판단(서버가 평가를 실행했다고 주장하지 않음). NFR-AIQ-06 수치는 별도 정책
- 흐름: `PublicAuthFilter` → `AuthService` SERVICE_OPS 검사 → `ModelVersionService`. 같은 kind·name의 transaction advisory lock → 재조회 → 기존 ACTIVE를 INACTIVE → 대상 ACTIVE·범위·revision → 감사 행 → `OutboxWriter.append`가 한 트랜잭션. 부분 unique index가 ACTIVE 단일성을 최종 강제
- 감사는 공용 `AuditLogService`(미구현) 대신 `ModelVersionRepository.audit` 경로. 공용 감사 도입 시 통합 검토
- 사용량 조회: KST 양 끝 포함 최대 366일(사용자 결정), 범위 밖은 DB 조회 전 400. 미산정 비용이 섞이면 `costUsd` null + `unpricedCalls`
- scope 배열의 null 요소는 Kotlin 제네릭만으로 차단되지 않아 명시적으로 422
- 기존 NULL 평가 행은 목록에 null로 남기고 활성화·복귀는 422, 불완전한 기존 ACTIVE는 내부 snapshot에서 503 `MODEL_VERSION_STATE_INVALID`
- scoring은 #86에서 Pod별 큐 바인딩 → snapshot 조회 → 더 높은 revision 적용·재연결을 구현했다. ai 소비 흐름은 #68에서 구현했다(7장). [scoring #86 검증](scoring.md#2-활성-버전-이벤트롤백-86)을 참고한다.

### 3.1 등록·활성화 절차 개선 설계안 (#301, 설계 검토)

> 상태: 공동 담당자(kty2001) 검토를 반영한 설계안이다. 코드·API·DB는 바꾸지 않았다. 2026-11-05 kty2001 답변과 팀 확인으로 정한 항목은 `[결정]`으로 표시한다.
> 배경: #185 AWS 배포 때 서술 3.0·논술 3.1을 관리자 화면으로 등록하면서 등록 자료를 화면에 반복 전사해야 했다. 두 버전은 이후 11/03 AWS 데모 검증용으로 같은 화면에서 활성화되었다(3.1.2 대조 결과).

이 절의 모든 안은 #301의 원칙을 따른다. 파일 업로드·등록·사전 검사만으로 활성화하지 않는다. 파일 무결성·로딩 성공을 품질 승인으로 표시하지 않는다. 사람 승인과 감사 이력을 유지하고 임시 경계·평가 범위 제한·미검증 사항을 화면에 드러낸다. api-spec 5.2의 "새 승인 상태 enum 없음"도 유지한다.

#### 3.1.1 현재 흐름 (코드 기준)

1. 등록: 관리자 `models` 화면(`ModelRegistry.tsx`) → `POST /api/v1/admin/model-versions` → `ModelVersionService.register`가 필수 근거·범위 형식만 검사하고 `REGISTERED`로 저장, 감사 `MODEL_REGISTER`
2. 승인·활성화: 버전 카드의 "활성화" → `POST /{id}/activate` `{approved:true,scopes,reason,reanalysisPlanned}` → `scopes ⊆ evaluatedScopes`이면 기존 ACTIVE를 INACTIVE로 바꾸고 대상 ACTIVE·`approval`·`activeScopes`·revision 저장, 감사 `MODEL_ACTIVATE`, Outbox `model.version.activated`가 한 트랜잭션
3. 로딩: scoring 각 Pod가 이벤트·snapshot(`GET /internal/model-versions/active`)을 받아 `ModelRegistry.load` → S3 다운로드 → `validate_metadata`(train_info.json·score_cuts.json)·`num_labels` 확인 → 메모리 교체. 실패하면 기존 모델을 유지하고 오류 유형만 로그에 남긴다
4. 추론: `M2Service`가 요청마다 scope `judgment/grade-{N}/{narrative|essay}`가 활성 scope에 있는지 확인한다

core는 3·4의 결과를 모른다. 로딩된 버전은 scoring `GET /internal/versions`(name·version·revision)로만 보이며 core·화면은 이를 호출하지 않는다. 그래서 화면의 `ACTIVE`는 "core에서 활성화됨"까지만 뜻한다.

**화면 수동 입력 항목**

| 화면 항목 | 저장 위치 | 등록 | 활성화 | 복귀 | 코드에서 확인한 문제 |
|---|---|---|---|---|---|
| 종류 | `model_version.kind` | 사용 | - | - | 기본값이 `PROMPT`라 M2 등록 때 `MODEL`로 바꾸지 않으면 다른 종류로 등록된다 |
| 이름 | `name` | 사용 | - | - | 자유 입력. scoring은 `m2-klue-narrative`·`m2-klue-essay`만 쓰므로 오타 이름도 등록·활성화는 되지만 쓰이지 않는다 |
| 버전 | `version` | 사용 | - | - | `X.Y` 규칙(4장)을 검사하지 않는다 |
| 기준표 원본 UUID | `ref_id` | RUBRIC만 | - | - | - |
| 아티팩트 주소 (선택) | `artifact_uri` | 사용 | - | - | `MODEL`에도 선택이다. 빈 값으로 활성화하면 scoring 계약 검사(`model_versions.py`, `artifactUri` 필수)에서 거부된다. 이름·버전과 경로 일치도 검사하지 않는다 |
| 평가 근거 8개 (평가셋 ID·버전, 비교 기준 버전, 비교 보고서, 학습·평가 분리, 인용·계산 정확성, 사람 검토 기록) | `eval_result.evidence.*` | 사용 | 완전성 재확인 | 완전성 재확인 | 8칸을 모두 손으로 옮긴다 |
| 적용 범위 (상단) | 아래 설명 | `evidence.evaluatedScopes` | `approval.scopes`·`activeScopes` | `activeScopes` | 한 입력이 세 의미로 쓰인다 |
| 변경 사유 (상단) | 활성화: `approval.reason`·감사 `detail.reason` / 복귀: 감사만 | - | 필수 | 필수 | 등록에는 쓰이지 않는데 등록 폼 밖 상단에 있다 |
| 승인 체크 (상단) | 요청 `approved`. 저장은 `approval` 생성으로 간접 기록 | - | 필수 | - | 모든 카드가 같은 체크 하나를 공유한다 |
| 재분석 계획 (상단) | 감사 `detail.reanalysisPlanned`만 | - | 사용 | 사용 | 작업을 실행하지 않는다 |

자동으로 채워지는 값: `id`·`status`·`createdAt`, 승인자 `approvedBy`(로그인 계정), `approvedAt`·`activatedAt`·`revision`.

**"적용 범위"의 실제 의미**: 상단 textarea 하나(`scopeText`)를 모든 요청이 공유한다.

- 등록 폼은 이 값을 `evaluatedScopes`, 즉 "평가 근거가 확보된 범위"로 보낸다. 등록 폼 안에는 범위 입력이 없고, 비어 있으면 "버전 등록" 버튼이 이유 표시 없이 비활성화된다
- 활성화 버튼은 같은 값을 승인·서비스 적용 범위로 보낸다. 서버는 문자열 집합 포함(`evaluatedScopes.containsAll`)만 확인한다
- 복귀 버튼은 같은 값을 복귀 범위로 보낸다. 서버는 원 승인 범위의 부분 집합인지 확인한다
- 결과: 등록 직후 같은 값으로 활성화하면 평가 범위와 활성 범위가 늘 같아져 "평가는 했지만 적용하지 않은 범위"를 표현하기 어렵다. 다른 카드의 버튼도 같은 값을 쓰므로 서술 범위를 입력한 상태에서 논술 카드의 버튼을 누르면 422가 난다
- 활성화·복귀 버튼이 꺼지는 조건 6가지(근거 없음, 범위 형식, 사유 없음, 처리 중, 상태, 승인 체크)를 화면이 알려 주지 않는다

#### 3.1.2 등록용 JSON 계약과 자동 입력 범위

**실제 제공 자료(기준)**: M2 담당 수빈 님이 11/03에 준 두 파일이다. 둘 다 저장소에는 없다(manifest의 "JSON도 저장소에 넣을지는 팀 결정"에 따름).

- `registration_1103.json`(v1.0.0): 등록 API 본문을 그대로 담은 파일이다. 최상위는 설명 키(`title`·`version`·`date`·`author`·`주의`·`<버킷>`)와 `requests[]`이고, 각 항목은 `{kind,name,version,artifactUri,evaluation}`(api-spec 5.2)과 같다. 서술 3.0·논술 3.1 두 항목, `evaluation` 9칸이 모두 채워져 있다
- `manifest.json`(v1.1.0): 모델별 `name`·`version`·`inputType`·`scope`·`num_labels`·`outputs`·`주의`와 6개 파일의 `file`·`bytes`·`sha256`을 담은 scoring 로딩용 파일 목록이다
- 최상위 `주의`: "품질 승인 근거가 아니라 현재 평가 기록. 허용 기준은 11/22 확정(NFR-AIQ-06) 전이라 활성화 범위는 팀 결정". manifest 논술 `주의`: train_info.json의 score_cuts는 null이라 별도 score_cuts.json을 써야 하고 경계는 임시값이다
- `artifactUri`는 `s3://<버킷>/models/{name}/{version}/` 형태로, 버킷 이름을 운영자가 바꿔 넣게 되어 있다

2026-11-05 로컬 대조(읽기만, S3·core 호출 없음):

- 받은 12개 파일의 크기·sha256이 manifest와 모두 일치
- `registration`과 `manifest`의 이름·버전·`evaluatedScopes`↔`scope`가 두 모델 모두 일치. `evaluation` 9칸에 빈 값 없음
- train_info.json·config.json 주요 값이 4.1 계약과 같음: 서술 `dataset=descriptive`·`with_keyword=True`·9출력, 논술 `dataset=essay545`·14출력·`use_outputs=[org,cont,exp]`·train_info.json의 score_cuts는 null, 둘 다 `regression`·512토큰. scoring `validate_metadata` 자체는 이 PC에 실행 환경이 없어 돌리지 못했다(같은 파일의 로딩은 #228·PR #288에서 확인됨)

**계약(실제 형식 기준으로 수정)**: 처음 초안(`schema`·`items`·`artifact.files`를 한 파일에 둔 형식)은 버리고 두 파일을 그대로 받는다.

| 파일 | 필수 | 웹이 쓰는 부분 | 쓰지 않는 부분 |
|---|---|---|---|
| registration | 필수 | `requests[]` 각 항목을 그대로 POST 본문으로 사용 | 최상위 설명 키는 미리보기 상단에 원문 표시만 |
| manifest | 선택(사전 검사 때 필수) | 모델별 `files[]`의 `file`·`bytes`·`sha256`, `scope`, `주의` | `input`·`score_rule`·`where` 등 설명 값은 표시만 |

| 구분 | 항목 | 처리 |
|---|---|---|
| JSON에서 자동 입력 | kind·name·version·artifactUri·evaluation 9칸 | 미리보기에 그대로 표시. 수정하면 수정 표시를 남긴다 |
| 운영자가 확인·수정 | `artifactUri`의 `<버킷>` | 환경(local·AWS)마다 버킷이 다르다. 웹에서 버킷을 한 번 입력하면 모든 항목에 치환하고, 치환 전에는 등록을 막는다 |
| 운영자가 확인 | `limitations` | 최상위 `주의`와 manifest 모델별 `주의`를 후보로 채워 보이고 운영자가 확인·수정한다 |
| JSON에 넣지 않음 | 승인 여부, 활성화 범위, 변경 사유, 재분석 계획, 승인자 | 사람이 활성화 단계에서 직접 정한다. `requests[]` 항목에 있으면 거부한다 |

- `[결정]` 파싱 위치: 브라우저에서 JSON을 읽어 기존 `POST /admin/model-versions`를 항목별로 호출한다(API 변경 없음). 실제 파일이 이미 POST 본문 형식이라 변환이 거의 없다. 검토한 대안: core JSON 업로드 API
- `[결정]` `limitations`(임시 경계·미검증 사항): `evidence`에 선택 필드 `limitations: string[]`를 추가한다. jsonb라 마이그레이션은 없고 Kotlin `EvaluationEvidence`(기본값 빈 목록)·api-spec 5.2·OpenAPI·웹 타입을 바꾼다. 기존 행은 빈 목록으로 읽힌다. 검토한 대안: `comparisonReport` 문장에 함께 기록
- `[결정]` 여러 모델: 모델별 미리보기 카드와 개별 "등록" 버튼, 부분 실패는 항목별로 표시한다. 검토한 대안: 일괄 등록 API
- `requests[]` 항목은 엄격하게 본다. API에 없는 필드는 거부한다. 최상위 설명 키는 사람이 읽는 메모라 거부하지 않고 원문을 보인다
- `[결정]` `주의`를 `limitations`로 옮기는 방식: 웹이 최상위 `주의`와 manifest 모델별 `주의`를 `limitations` 후보로 채우고, 운영자가 확인·수정한 뒤 등록한다. 지금 받은 파일을 그대로 쓴다. 나중에 `requests[]` 항목에 `evaluation.limitations`가 있으면 그 값을 쓰고 `주의`로는 채우지 않는다. 검토한 대안: M2 담당자가 처음부터 `evaluation.limitations`를 직접 넣는 방식(제공 형식이 바뀌어 이번에는 쓰지 않음)
- `[결정]` 이미 운영에 등록된 3.0·3.1 레코드를 이 파일과 대조한다. 운영 core 목록(`GET /api/v1/admin/model-versions?kind=MODEL`)을 읽기만 해서 칸별로 비교한다. 다르면 레코드를 고치지 않고(평가 근거 보존 원칙) 새 버전명(예: 3.0.1)으로 다시 등록한다
- 대조 결과(2026-11-05, AWS 데모 core 목록 읽기): 두 레코드 모두 `kind`·`name`·`version`, `artifactUri`의 버킷 뒤 경로, `evidence` 9칸이 파일과 글자까지 같다. 다시 등록할 필요는 없다. 두 레코드는 11/03에 이미 `ACTIVE`이고 `revision` 1이다. 승인 범위는 서술 3.0이 초5·6 서술형(평가 범위 전체), 논술 3.1이 초5·6 논술형이다. 논술 3.1의 초4는 평가했지만 적용하지 않았다. 두 레코드 모두 `limitations`는 없고, 논술 승인 사유에 "평가 한계와 임시 점수 경계 유지"를 적었다
- manifest의 `bytes`·`sha256`은 현재 저장할 곳이 없다. 사전 검사(3.1.4)에서 쓰고 감사 detail에 남기는 안을 3.1.5에 적었다

#### 3.1.3 평가 범위와 활성화 범위 분리

API는 이미 `evaluatedScopes`(등록)와 `scopes`(활성화·복귀)를 나눠 받으므로 **1단계는 화면만 바꾼다.**

- 상단 공용 영역을 없앤다. 평가 범위는 등록 폼·JSON 미리보기 안에 두고, JSON에서 왔으면 읽기 전용으로 보인다(수정하면 경고)
- 활성화·복귀 입력은 각 버전 카드 안으로 옮기고 카드마다 상태를 따로 둔다(범위·사유·승인 체크)
- 활성화 범위는 해당 버전의 `evaluatedScopes`를 체크박스로 보여 주고 직접 입력하지 않는다. 복귀는 원 `approval.scopes`만 보여 준다
- 범위를 고를 때 같은 카드에 평가셋 ID·버전, 비교 보고서, 사람 검토 기록, `limitations`를 함께 보인다. 평가 범위 중 고르지 않은 범위는 "평가했지만 적용하지 않음"으로 표시한다
- 기본값은 아무것도 선택하지 않는다. 평가 범위 전체를 미리 선택하는 대안은 사람이 범위를 고르는 의미가 약해져 추천하지 않는다
- `[결정]` 범위 후보 목록: 웹 domain에 알려진 소비자 scope 상수(M2 `judgment/grade-{4,5,6}/{narrative,essay}`, ai 7장 여섯 개)를 두고 목록 밖 값은 **경고만** 한다(새 소비자 등록을 막지 않음). 검토한 대안: core scope 목록 API, 자유 입력만 유지

#### 3.1.4 등록 전 검증과 오류 표시

| 검증 | 위치 | 결과 | 현재 |
|---|---|---|---|
| JSON 형식·`schema`·알 수 없는 필드 | 브라우저 | 차단 | 없음 |
| 필수 문자열 9개 공백 | 브라우저 + core | 차단 | core 422 (어느 필드인지 안 알려 줌) |
| 범위 키 형식·중복·빈 배열 | 브라우저 + core | 차단 | 있음 |
| 범위 키가 알려진 목록 밖 | 브라우저 | 경고 | 없음 |
| `(kind,name,version)` 중복 | 브라우저(목록 대조) + core | 차단 | core 409 |
| `MODEL`인데 `artifactUri` 없음 | core | 차단 | 없음 (scoring에서 거부) |
| `artifactUri`에 `<버킷>` 같은 자리표시자가 남음 | 브라우저 | 차단 | 없음 |
| manifest의 name·version·`scope`가 registration과 다름 | 브라우저 | 차단 | 없음 |
| `m2-`·`m1-` 이름이 scoring이 아는 이름이 아님, 버전이 `X.Y`가 아님 | 브라우저 | 경고 | 없음 |
| `artifactUri`가 `.../models/{name}/{version}/`와 다름 | 브라우저 | `[결정]` 경고 | 없음 |
| S3 6개 파일 존재·sha256 일치 | 사전 검사 | 차단 | 없음 (활성화 후 로딩 때 처음 알게 됨) |
| train_info.json·score_cuts.json·출력 수가 이름과 맞는지 | 사전 검사 | 차단 | 활성화 후 로딩 때만 |

- `[결정]` 사전 검사 위치: core 관리자 API가 scoring 내부 API(가칭 `POST /internal/models/preflight`)를 **동기 HTTP**로 중계한다. scoring이 이미 가진 S3 읽기 권한과 `validate_metadata`를 재사용한다. 검토한 대안: core에 S3 SDK 추가, 운영자 CLI
  - 지금은 core→scoring 호출 경로가 없다. core에 scoring 클라이언트가 없고, NetworkPolicy도 scoring은 ai에게서만 받고 core egress에 scoring이 없다(`environments/local/scoring-service.yaml`·`core-service.yaml`, prod도 같은 구성 확인 필요). 4단계에 core 클라이언트·시간 제한·양쪽 NetworkPolicy 변경이 들어간다
  - 동기 응답 안에 끝나도록 가중치는 받지 않는다. 6개 파일은 존재·크기·해시만, 내용은 작은 JSON 3개(config.json·train_info.json·score_cuts.json)만 읽는다
- 사전 검사 통과는 "파일·형식 확인"으로만 표시한다. 품질 승인이나 활성화 가능 상태로 표시하지 않고, 통과해도 자동으로 다음 단계로 넘기지 않는다. 전체 가중치 로딩은 활성화 뒤 로딩 확인에서 본다
- `[결정]` 오류 표시: 공통 오류 형식(RFC 9457, api-spec 1.3)은 바꾸지 않는다. 바꾸면 모든 서비스에 영향이 간다. 필드 검사는 화면에서 먼저 하고(`items[1].evaluation.humanReview` 같은 경로와 원인을 입력 옆·미리보기 카드에 표시), 서버 409·422는 웹이 오류 코드로 해당 위치에 연결한다
  - 409 `MODEL_VERSION_CONFLICT`(중복)는 이름·버전 칸에 연결한다. 422 `MODEL_APPROVAL_REJECTED`는 등록·활성화의 여러 원인이 한 코드라 필드를 특정할 수 없으므로 폼 상단에 서버 메시지를 보인다. 화면 사전 검사가 같은 규칙을 모두 다뤄 422가 드물게 하는 것을 전제로 한다. 나중에 더 나눠야 하면 공통 형식은 두고 오류 코드만 세분한다
- 비활성 버튼에는 부족한 조건을 문장으로 붙인다. 예: "변경 사유가 없습니다", "선택 범위 `judgment/grade-4/narrative`가 평가 범위 밖입니다", "최초 등록 버전이 아니므로 되돌리기를 사용하세요"

#### 3.1.5 상태 안내와 승인·감사 이력

화면은 버전마다 다섯 단계와 현재 위치, 다음 작업, 진행할 수 없는 이유를 보인다. 상태 enum은 늘리지 않고 아래 값에서 계산한다.

| 단계 | 판단 근거 | 비고 |
|---|---|---|
| 등록 | `status = REGISTERED` | - |
| 사전 검사 | 사전 검사 기록 (2단계 후) | 통과해도 승인 아님 |
| 승인·활성화 | `approval` 존재, `status = ACTIVE` | 사람 승인 체크 + 사유 필수 유지 |
| 로딩 확인 | scoring에 같은 name·revision이 로딩됨 | 1차는 안내만 (아래 결정) |
| 추론 확인 | 운영자가 점검 요청으로 확인 | 자동 판정하지 않고 확인 방법만 안내 |

- `[결정]` 로딩 확인 출처: 1차에는 화면에 "core 활성화 완료, 로딩은 scoring에서 확인"이라는 안내와 확인 방법만 표시한다. scoring은 레플리카마다 따로 로딩하므로 Service를 한 번 호출하면 Pod 하나만 보기 때문이다. Pod별 로딩 보고(이벤트를 core가 모아 표시)는 후속 이슈로 둔다. 검토한 대안: core가 `/internal/versions`를 한 번 조회해 "일부 Pod 기준"으로 표시
- 승인 확인: 활성화 전 확인 창에 승인 범위, 평가셋 ID·버전, 사람 검토 기록, `limitations`를 요약해 보이고 사유를 받는다. 승인자는 계속 로그인 계정에서 정한다
- 감사 유지: `MODEL_REGISTER`·`MODEL_ACTIVATE`·`MODEL_ROLLBACK`과 `evalResult`(원 근거·최초 승인 덮어쓰기 금지)는 그대로 둔다. 추가 안:
  - 등록 감사 detail에 `source`(`MANUAL`·`JSON_IMPORT`), 가져온 JSON의 sha256, 운영자가 바꾼 필드 이름 목록, 산출물 파일 해시
  - 사전 검사 결과는 `evidence`가 아닌 별도 감사 action(가칭 `MODEL_PREFLIGHT`, `result` SUCCESS·FAILURE)으로 남긴다
  - 감사 화면은 지금 action·대상만 보인다. `MODEL_VERSION` detail(범위·사유·재분석 계획·이전 버전)을 펼쳐 볼 수 있게 한다
- `[결정]` 거부된 시도(409·422) 감사: 이번 범위에서 제외한다. 지금은 같은 트랜잭션이 롤백되어 남지 않으며, 기록하려면 별도 트랜잭션 설계가 필요하다

#### 3.1.6 구현 단계와 후속 이슈 단위

크기: S ≈ 반나절~1일, M ≈ 2~3일, L ≈ 4일 이상(검토·검증 포함 대략치).

| 단계 | 내용 | 영향 | 크기 | 선행 |
|---|---|---|---|---|
| 1 | 화면 범위 분리(카드별 활성화·복귀 입력, 평가 범위 체크박스), 비활성 이유 표시, `MODEL` 기본 종류 안내 | web만, API 변경 없음 | S~M | 없음 |
| 2 | registration·manifest 가져오기, 버킷 치환, 모델별 미리보기·개별 등록, 계약 문서(api-spec 5.2) | web + 문서 | M | 없음 (실제 JSON 확인 완료) |
| 3 | core 등록 검증 강화(`MODEL` artifactUri 필수), 감사 detail `source`·해시, `limitations` 필드, 웹의 오류 코드→입력 위치 연결 | core·api-spec·OpenAPI·web | M | 2의 계약 |
| 4 | scoring 사전 검사 API와 core 동기 중계·화면 연결 | scoring·core·web, core scoring 클라이언트, core→scoring NetworkPolicy(local·prod), S3 읽기 권한(#212 AWS 설정과 조율) | M~L | 3 |
| 5 | Pod별 로딩 확인 보고와 화면 표시 (후속 이슈로 결정) | scoring·core 이벤트·web | L | 1단계 안내 |
| 6 | 감사 화면 detail 표시 (거부된 시도 기록은 제외) | core·web | S | 없음 |

- 1·6은 서로 독립이라 먼저 진행할 수 있다. 2→3→4는 순서대로다. 5는 별도 후속 이슈로 연다
- 이미 등록된 서술 3.0·논술 3.1은 새 절차와 무관하게 지금 레코드를 그대로 쓴다
- `[결정]` 후속 이슈는 4개로 나눴다(2026-11-05 발행, 담당자는 각 이슈에서 정한다): 1·6단계 #366, 2·3단계 #367, 4단계 #368, 5단계 #370
- 3.0·3.1은 11/03 AWS 데모에서 지금 화면으로 이미 활성화했으므로(3.1.2 대조 결과) 활성화 시점은 정하지 않는다

**결정 현황 (2026-11-05)**: kty2001 답변으로 JSON 파싱 위치·`limitations`·여러 모델 등록(3.1.2), 범위 후보 목록(3.1.3), 경로 불일치·사전 검사 위치·오류 표시(3.1.4), 로딩 확인 출처·거부된 시도 감사(3.1.5)를 정했다. 실제 등록용 JSON은 11/05 받아 계약을 그 형식으로 고쳤고, `주의`→`limitations` 옮기는 방식과 기존 3.0·3.1 레코드 대조도 정했다(3.1.2). 대조 결과 두 레코드는 파일과 같고 11/03에 이미 활성화되어 있다. 구현은 후속 이슈 #366·#367·#368·#370으로 나눴다(3.1.6). 남은 `[결정 필요]` 항목은 없다.

## 4. M2 모델과 API 정렬 (#4)

2026-11-02 #228: 서술 3.0(9출력)·논술 3.1(14출력 중 앞 3영역)을 적용한다. 담당자 답변에 따라 논술도 `scores`(0~3 정수)와 `rawScores`(소수 원점수)를 함께 반환한다. [API 4.3](../design/api-spec.md#43-scoring-service-호출-ai), [#228 구현·검증](ai.md#41-서술-30논술-31-서비스-호환-228)이 현재 계약이며 [#87](scoring.md#3-m2-채점-api-87)의 2.0 결과는 과거 검증 이력이다.

- 서술 활성 학년은 초5·6, 논술은 초4·5·6. 서술 학습 데이터는 초5~중3이지만 서비스 범위를 중학생까지 확장하지 않는다.
- 새 모델 입력에서 지시문 제외. 서술 `[학년] 초N [핵심어] ...`(쉼표+공백), 논술 `[학년] 초N [글 종류] ...`와 학생 글을 사용한다.
- 서술은 기존 9항목 scores(hol 1~4, 그 외 1~5)·rawScores, 논술은 org·cont·exp의 scores(0~3)·rawScores. 원점수는 반올림·범위 자르기를 하지 않는다. 임시 score_cuts는 모델 담당자 제공값만 사용하며 경계 변경 시 재검증한다.
- 2026-11-03 사용자가 전달한 담당자 후속 답변에서도 논술 3.1과 기존 score_cuts.json 유지가 확정됐다. 경계는 임시이며 담당자의 변경 통지 시 교체·재검증한다. PR #261의 두 JSON 파일 자동 저장은 담당자가 실제 학습에서도 확인했다고 보고했다(4.1). 화면 표시와 #69 판정 소비는 별도다.
- 모델 버전 규칙: `uq_model_version_active`가 `(kind, name)` 단위라 서술·논술 모델을 `name`으로 분리

  | 항목 | 규칙 |
  |---|---|
  | name | 서술형 `m2-klue-narrative`, 논술형 `m2-klue-essay` (`inputType`과 1:1) |
  | version | `X.Y`. 입력·출력 형식이 바뀌면 X, 같은 형식 재학습이면 Y |
  | artifact_uri | `s3://<버킷>/models/{name}/{version}/` |
  | 활성화 | 두 모델을 따로 활성화·롤백 |

- 논술 답변 `essay{claim, reasons[], rebuttal}`을 scoring 입력 `text`로 합치는 규칙은 api-spec 4.2.2의 `answerText` 기준

### 4.1 서술 3.0·논술 3.1 서비스 호환 (#228)

기존 scoring은 두 입력 유형을 모두 9출력으로 해석해 논술 3.1의 14출력을 로딩하지 못했음. 담당자 답변: 서술 3.0·논술 3.1, 논술 14개 중 앞 3개만 사용, 소수와 변환 정수를 함께 전달. 11/03 후속 답변으로 논술 3.1과 기존 score_cuts.json 유지 확정, `train_545.py`의 score_cuts.json·train_info.json 자동 저장도 담당자 실제 학습에서 확인([PR #261](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/pull/261)).

| 항목 | 서술 3.0 | 논술 3.1 |
|---|---|---|
| 이름 | m2-klue-narrative | m2-klue-essay |
| 모델 출력 | 9 | 14 (앞 3개만 사용) |
| 첫 문장 | `[학년] 초N [핵심어] ` + 쉼표·공백으로 연결한 핵심어 | `[학년] 초N [글 종류] {essayType}` |
| 두 번째 문장 | 학생 text | 학생 text |
| 활성 학년 | 5·6 | 4·5·6 |
| 응답 키 | hol·task_1·content_1~3·organization_1~2·expression_1~2 | org·cont·exp (구성·내용·표현) |
| scores | 경계 bisect_right + 1; hol 1~4, 나머지 1~5 | 경계 bisect_right; 0~3, +1 없음 |
| rawScores | 유한 소수 원점수 그대로 | 유한 소수 원점수 그대로; 임의 반올림·범위 자르기 없음 |

- ESSAY 요청은 essayType(설명글·글짓기·주장·찬성반대·대안제시) 필수, 누락·잘못된 값은 400. prompt는 기존 필드로 유지하되 새 모델 입력에서 제외
- 이전 2.0 메타데이터는 기존 지시문 입력·9항목 반환 경로로 처리, 이전 논술 모델은 4학년을 승인했더라도 비활성
- 산출물 6개 파일(config.json, model.safetensors, tokenizer.json, tokenizer_config.json, train_info.json, score_cuts.json). 원본 tar의 논술 score_cuts 누락은 담당자가 별도로 준 값으로 보완: `{"org":[0.5,2.15,2.55],"cont":[0.5,2.15,2.5],"exp":[0.5,2.1,2.55]}`. 학습 주제 검증 글로 정한 **임시 기준**이며 변경 파일을 받으면 해시를 남기고 로딩·점수 변환 재검증
- 공통 메타데이터 검사(모델 이름·데이터셋·입력 플래그·출력 순서·출력 수·최대 길이·경계 키/개수/유한성/정렬)를 로딩·추론에서 동일하게 사용. 잘못된 체크포인트는 활성 snapshot에 넣지 않음
- 지원하지 않는 학년·미승인 scope·서술 핵심어 없음은 비활성, 추론 장애는 503. 비활성에서 추론·사용량 이벤트를 만들지 않음
- 실제 MinIO·core·scoring 검증: 두 모델 12개 파일 업로드·등록·활성화·로딩, 서술 5·6·논술 4·5·6 `active:true`, 응답 rawScores에 파일 경계를 적용한 값이 scores와 일치

```powershell
docker build -t local/scoring228:<tag> backend/scoring-service
uv run --frozen python ../../scripts/verify_scoring_m2.py --archive <m2_models.tar> --core-root <최신 core 저장소> --output <외부 결과 폴더> --image local/scoring228:<tag> --new-models --essay-cuts <담당자 score_cuts.json>
```

### 4.2 서술 content_3 선택 보정 (기본 꺼짐)

서술 적절성 점수에 핵심어 포함 비율을 결합하는 후보 규칙. 기준 자료는 M2 담당 제공 `content3_rule_1103.json`·`content3_rule_1103.py`(11/03 v1.0.0). 계수 `(w0, w_model, w_ratio) = (0.9724, 0.197, 2.8891)`은 코드에 고정하며 계수·규칙을 바꾸면 규칙 버전도 올리고 재검증.

- `M2_CONTENT3_RULE_ENABLED=true`이면서 활성 모델이 정확히 `m2-klue-narrative@3.0`이고 NARRATIVE 초5·6 승인 scope일 때만 적용. 다른 서술 버전·모든 논술은 기존 계산
- 계산: `mixed = clip(0.9724 + 0.197 * 모델 content_3 원점수 + 2.8891 * 핵심어 포함 비율, 1, 5)`, `rawScores.content_3 = round(mixed, 4)`, `scores.content_3 = floor(mixed + 0.5)`. 정수는 소수 4자리 반올림 전에 계산(예: 2.49996 → raw 2.5, score 2). 보정된 content_3에 score_cuts를 적용하지 않음
- 핵심어는 배열 원소 하나당 묶음 하나. 참고 구현은 배열을 연결한 뒤 괄호 밖 쉼표로 묶음을 구분하므로 `['환경, 보호']`도 두 묶음. 각 묶음은 본래 핵심어·괄호 안 대체어 중 하나라도 text에 있으면 1(공백 무시 부분 문자열, 괄호 안 쉼표·슬래시는 대체어 구분자)
- Settings·`.env.example`·Compose 기본값 false. 허용 기준 확정·품질 승인 후에만 켜고 scoring 재시작. 원복은 false로 바꾸고 재시작(저장된 결과 소급 변경 없음). `app.bootstrap` INFO 로그에 `enabled`·`rule_version=1.0.0`
- 한계: 담당자 보고 QWK 0.897→0.945는 재평가하지 않음. 계수는 처음 보는 주제 예측으로 맞춘 값이며 핵심어를 다른 말로 풀어 쓴 답의 점수가 낮아질 수 있음

### 4.3 판정 모델 교차 확인 (#69)

계약은 [api-spec 4.2.2](../design/api-spec.md#422-판정-모델-교차-확인-69-2026-11-03). 11/03 담당자 확정:

| 항목 | 결정 |
|---|---|
| 불일치 기준 | M2 `scores` 평균과 LLM 결과 비교. `CORRECT`인데 평균이 낮은 경계 이하, `RETHINK`인데 높은 경계 이상이면 불일치. `PARTIAL`은 불일치 아님. 경계는 설정값(서술 2.0/4.0, 논술 1.0/2.0), M2 담당 확인 전 임시값 |
| 보류 적용 | `M2_CROSS_CHECK_ENABLED` 기본 false. 켜면 `HELD(MODEL_DISAGREEMENT)`·`HELD(LOW_CONFIDENCE)`. 꺼져 있으면 scoring을 부르지 않음(#305, 4.3.1) |
| scoring 장애 | LLM 판정만 200(#305, 4.3.1, 이전에는 503), `modelScores.skipped`에 `SCORING_UNAVAILABLE`(5xx·시간 초과·연결 실패) 또는 `SCORING_REJECTED`(4xx·계약 밖 응답). 비활성(`{active:false}`)과 구분 |
| 입력 출처 | `question`은 mission_version.question, `keywords`·`essayType`은 learning V9 `rubric_version` 새 칸(채점 입력이라 기준표와 함께 바뀌고 검토·게시됨) |
| 점수 저장 | ai 응답 `modelScores`를 learning이 `judgment.model_scores`에 그대로 저장, 학생 화면 비노출 |
| M1 | 비활성 유지. ai 호출 분기와 대역 테스트만, `M1_CHECK_ENABLED` 기본 false, learning은 M1 입력 미전송 |

- ai: `ScoringClient`(`{active:false}`만 비활성, 점수 키가 입력 방식과 다르면 계약 밖), `judgment/cross_check.py`(요청 구성·평균·불일치), `judgment/service.py`(LLM 판정이 보류가 아닐 때만 scoring 호출, 활성 응답이면 `versions.model`을 `"{name}@{version}"`으로)
- learning: 관리자 기준표 `PUT /internal/admin/missions/{id}/rubric`에 `keywords`(100개·각 200자)·`essayType`(5종). 관리자 웹 입력 칸은 아직 없어 입력 전까지 서술·논술 M2는 호출되지 않음. 데모 시드에는 핵심어·글 종류 없음

시간 배분(P12, learning→ai 35초 안, M2·M1 입력이 있는 판정):

| 구간 | 설정 | 최악 시간 |
|---|---|---:|
| LLM 1회 | `LLM_TIMEOUT=15` | 15초 |
| 재시도 전 대기 | `LLM_RETRY_BACKOFF=1` | 1초 |
| LLM 재시도 | LLM 마감(33 - 3 = 30초)까지 남은 시간 | 14초 |
| LLM 소계 | `JUDGE_DEADLINE - SCORING_RESERVE` | 30초 |
| scoring 몫 | `SCORING_RESERVE=3`, 한도 `min(SCORING_TIMEOUT=10, 남은 시간)` | 3초 이상 |
| 판정 마감 | `JUDGE_DEADLINE=33` | 33초 |
| learning 35초 대비 여유 | 네트워크·직렬화 | 2초 |

- 3초 몫은 M2 예열 후 HTTP 포함 최대 1.68초([scoring](scoring.md) 3장)의 약 1.8배. 첫 요청 8.4초가 다시 나오거나 남은 시간이 1초 미만이면 scoring을 건너뛰고 `skipped: SCORING_UNAVAILABLE`로 LLM 판정만 씀(#305, 4.3.1. 이전에는 503). 교차 확인 입력이 없는 판정은 LLM이 33초 전체 사용
- 실제 모델 전체 측정(로컬 Docker, 서술 3.0·논술 3.1, learning 피드백 요청 기준): 예열 후 대역 LLM 최대 0.34초, 실제 OpenAI LLM 중앙값 3.8~7.3초·최대 9.0초, LLM 최악 경로(첫 요청 시간 초과 → 재시도) 약 29.8초로 모두 200·`model_scores` 저장. 배포 환경·동시 요청 부하에서는 재측정 필요


### 4.3.1 scoring 실패 격리 (#305, 2026-11-04)

문제: ai가 scoring 장애·시간 초과·5xx와 400(M2 입력 토큰 한도 초과)을 모두 `503 SCORING_UNAVAILABLE`로 바꿨다. learning `AiClient`는 판정·되묻기가 함께 쓰는 서킷 `ai`(20건·50%·30초)에서 ai 5xx를 실패로 센다. 그래서 keywords가 긴 미션 하나나 scoring 장애가 scoring과 무관한 LLM 단독 판정·되묻기까지 모든 학생에게 30초 동안 막았다. 또 `M2_CROSS_CHECK_ENABLED=false`(기본)여도 scoring을 불렀다([감사](audit.md) 6.3 A20·B36).

담당자 결정(11/04):

| 항목 | 결정 | 근거 |
|---|---|---|
| 플래그 꺼짐 | `M2_CROSS_CHECK_ENABLED=false`면 M2를 부르지 않음. M1은 기존 `M1_CHECK_ENABLED`(기본 false)로만 결정 | 꺼진 기능이 장애 경로가 되지 않게 함. 꺼진 동안 LLM은 판정 마감 33초 전체 사용 |
| scoring 장애·5xx·시간 초과 | 503 대신 LLM 판정만으로 200, `modelScores.skipped = "SCORING_UNAVAILABLE"`. 남은 시간 1초 미만으로 부르지 못한 경우도 같음 | learning `ai` 서킷에 집계되지 않음(아키텍처 1.3 구간 독립, 1.1 scoring 분리) |
| scoring 400 등 4xx·계약 밖 응답 | 같은 방식, `skipped = "SCORING_REJECTED"` | 다시 불러도 같은 결과라 판정을 막을 이유가 없음. 장애와 입력 문제를 구분해 운영에서 찾을 수 있게 둘로 나눔 |
| 표시 위치 | `modelScores` 안에 `skipped` 추가(정상이면 null) | 판정 응답·learning DB에 생략 상태 값이 없었음. learning은 `modelScores`를 해석하지 않고 `judgment.model_scores`(jsonb)에 그대로 저장하므로 migration·learning 코드 변경 없음. 학생 화면 비노출 유지 |
| learning keywords 제한 | 바꾸지 않음(`AdminMissionController` 100개·각 200자 유지) | 이번 범위 밖. 아래 한계로 남김 |

구현: ai `judgment/service.py`(플래그 꺼짐이면 M2 본문을 만들지 않음, `ScoringUnavailable`을 `retryable`에 따라 `skipped` 값으로 바꾸고 경고 로그), `judgment/models.py`(`CrossCheckSkipped`), 계약 [api-spec 4.2.2](../design/api-spec.md#422-판정-모델-교차-확인-69-2026-11-03)·`contracts/openapi/ai-service.yaml` `ModelScores.skipped`. `ScoringClient`의 응답 분류(5xx·전송 오류 retryable, 그 밖 비-200·계약 밖 응답 not retryable)는 그대로 쓴다. learning 코드 변경 없음.

한계·후속:

- 교차 확인을 켠 상태에서 scoring이 실패하면, 불일치였다면 `HELD(MODEL_DISAGREEMENT)`로 걸렸을 답도 LLM 결과로 확정된다. 생략된 판정을 나중에 다시 확인하지 않는다.
- scoring 장애가 판정 실패로 드러나지 않는다. ai 경고 로그와 `judgment.model_scores->>'skipped'` 조회로만 보이며 지표·알림은 없다(scoring 자체의 503은 scoring 쪽에서 그대로 보임).
- keywords가 M2 토큰 한도를 넘는 미션은 판정마다 `SCORING_REJECTED`로 교차 확인이 생략된다. 관리자 화면에는 알리지 않는다. learning 입력 제한을 scoring 한도에 맞출지는 별도 결정이다.
- 플래그를 끈 동안 M2 점수·불일치 관찰 기록이 쌓이지 않는다. 불일치 경계(임시값) 보정이나 플래그 활성화 판단에 쓸 자료는 켠 기간이나 별도 평가([판정 품질 평가 도구](#판정-품질-평가-도구-199))로 모아야 한다.
- 로컬 이관 체험 Compose가 scoring을 함께 띄우도록 바꾼 [로컬 플랫폼](local-platform.md) 결정은 그대로 둔다(플래그 꺼짐이면 판정이 scoring을 부르지 않으므로 필수 의존은 아님).

#### 검증 (#305)

- ai pytest: 플래그 꺼짐이면 scoring 미호출·LLM 마감 전체 사용, M2·M1 실패(retryable true/false)와 남은 시간 부족이 `skipped`와 함께 LLM 판정(CORRECT·RETHINK) 유지, HTTP 경로에서 scoring 503·500·시간 초과·400이 200 + `skipped`, 기존 일치·불일치(HELD)·비활성·입력 없음 경로 유지
- learning: `AiClientTest` 생략 응답 20건 뒤에도 서킷 CLOSED·실패 0건·되묻기 호출 가능, `FeedbackFacadeTest` 생략 판정이 DONE·LLM 모델 버전·`model_scores.skipped`로 저장
- 루트 계약 테스트: `ModelScores.skipped` enum과 ai `CrossCheckSkipped` 대조

## 5. 리포트 서술·저녁 질문 (#64)

- `POST /internal/report-narratives`(api-spec 4.2.1, `app/report_narrative/`). 서술·저녁 질문만 만들고 숫자 계산·대조·템플릿 전환은 report(class-diagram 5.2, P16). 사용량 `callType = REPORT_NARRATIVE`, 프롬프트 `report@1`(`/internal/versions`의 `reportNarrative`)
- API 변경: 요청 `quotes[]`에 `answerVersion` 추가(report `NarrativeGenerator`가 근거 링크 버전으로 채움). 응답 `citedQuotes[].answerVersion`을 ai가 알 수 없던 문제 해소. 3.4 상세 `quotes`·저장 payload는 그대로
- 인용: LLM이 `{후보 번호, 원문 구절}`을 고르고, 구절이 그 후보 원문의 부분 문자열이 아니거나 번호가 범위 밖이면 제외. ID·버전은 입력값. 서술 속 따옴표 문구와 `citedQuotes` 불일치는 report 대조에서 템플릿 전환
- 프롬프트 규칙은 report `ReportVerifier` 통과 범위에 맞춤: 입력 수치·전후 변화 값만 아라비아 숫자로, 한글 수사·미션 제목·답 속 숫자(인용 밖) 금지, 점수·등급·레벨·순위 낱말과 사고력 향상 단정 금지, 기록 없는 유형은 "확인된 기록 없음", 미작성 돌아보기는 "쓰지 않음"
- LLM 입력에는 수치·미션 제목·답변·돌아보기 원문만. 학생 이름·ID와 시도·답변 ID는 넣지 않음(인용은 후보 번호로 지칭, NFR-SEC-03). 로그에 원문 미기록
- P24(#391): 일일 리포트는 템플릿만 써 이 API를 호출하지 않는다(주간 리포트만 서술·저녁 질문)

### 기준이 없어 정한 값

| 항목 | 값 | 근거 |
|---|---|---|
| 서술 | 학부모 대상 해요체 3~5문장, 600자 이내(프롬프트 지시, 코드 검사 없음) | 리포트 한 화면 분량 |
| 저녁 질문 | 1개, 아이에게 읽어 줄 친근한 반말 한 문장. 이번 주 미션·답에서 출발, 정답·평가·능력 암시 금지 | 기획서 저녁 식탁 대화 |
| 전체 마감 `NARRATIVE_DEADLINE` | 28초. LLM 1회 15초 + 대기 1초, 재시도는 남은 시간 안에서만 | report→ai 읽기 타임아웃 30초(report `http_read_timeout`)보다 짧게 |
| 돌아보기 난이도 | `EASY·NORMAL·HARD` 코드를 프롬프트에서 "쉬웠어·보통·어려웠어"로, 표시값이 오면 그대로 | report 저장 payload는 코드 유지 |
| 빈 서술·빈 저녁 질문 | 503 `AI_UNAVAILABLE`(`retryable: true`) | report는 AI 실패를 `FAILED`로 처리 |

- `model.version.activated` 수신 시 서술 프롬프트 버전 교체는 #68에서 구현(7장). 실제 LLM 연동은 [learning 19절](learning.md#19-실행-모델-가상-스레드-비활성-201)·[report 19절](report.md#19-판정-요소-지표-연결-344)에서 확인

## 6. scoring 기동 모델 로딩 (#85)

[scoring](scoring.md) 1장.

## 7. AI 활성 프롬프트 버전 수신 (#68)

core #43의 `GET /internal/model-versions/active`와 `model.version.activated.v1` data는 같은 `id·kind·name·version·refId·artifactUri·scopes·revision·activatedAt` 필드를 사용한다. 이벤트에만 `previousVersionId`가 추가된다. 이미 있는 스키마를 재작성하지 않는다. core는 kind·name별 revision을 증가시키므로 ai는 정해진 `PROMPT` 이름(#437 이후 아래 표 일곱 개)만 골라 높은 revision을 적용하고 각 기능의 승인 scope를 정확히 검사한다. 형식 오류 이벤트는 원문·URI 없이 경고하고 ACK하여 재시도하지 않는다.

| name | 승인 scope | ai 이미지에 포함된 기본 본문·버전 |
|---|---|---|
| `judgment` | `ai/judgment` | `judgment/prompts.py`, `judge@2` |
| `followup` | `ai/followup` | `followup/prompts.py`, `followup@4` |
| `analysis` | `ai/analysis` | `analysis_agent/prompts.py`, `analysis@4` (#454) |
| `reportNarrative` | `ai/report-narrative` | `report_narrative/prompts.py`, `report@1` |
| `reportTemplate` | `ai/report-template` | `analysis_agent/template_prompts.py`, `analysis-template@1` (#280) |
| `missionDraft` | `ai/mission-draft` | `mission_draft/prompts.py`, `mission-draft@1` (#354) |
| `themeDraft` | `ai/theme-draft` | `theme_draft/prompts.py`, `theme-draft@1`(생성·검토 프롬프트 한 묶음, #437) |

각 버전은 실제 system 문구와 user 본문 구성 함수를 이미지 코드에 함께 넣은 뒤에만 활성화할 수 있다. 현재 이미지는 위 기본 버전의 본문만 보유한다. core snapshot에 해당 활성 항목이 없으면 기본 버전을 사용한다. 보유하지 않은 활성 버전은 다른 본문에 새 버전명만 붙이지 않고 해당 기능 요청과 `/internal/versions`를 `503 AI_PROMPT_VERSION_UNAVAILABLE`로 거부한다. 구독·core snapshot·이벤트 조정 또는 본문 준비가 되지 않으면 `/health/ready`의 `versions`는 DOWN이다. 요청 시작 때 본문·버전 참조를 잡아 분석의 분류/답변 두 LLM 호출과 되묻기 재생성까지 같은 버전을 사용한다.

기동·재연결마다 Pod 고유의 exclusive·auto-delete 큐를 `events.topic`의 `model.version.*`에 먼저 바인딩하고 소비를 시작한다. 그 다음 기존 `internal_client`로 core snapshot을 조회한다. 조회 중 이벤트를 이름별 최신 revision으로 보존했다가 snapshot에 조정한다. 최초 조회 실패는 백그라운드에서 재시도하며 프로세스는 유지한다. health 요청은 메모리 상태만 확인한다. 새 production 패키지나 core API·이벤트 스키마 변경은 없다.

배포 연결 요구: ai HTTP 내부 포트 `8000`과 `/health/live`·`/health/ready` 경로는 그대로다. `CORE_URL`·`INTERNAL_TOKEN`으로 core 내부 조회가 가능해야 하고 RabbitMQ `events.topic` 접근과 Pod별 임시 큐 선언 권한이 필요하다. #171 chart·NetworkPolicy는 ai→core HTTP와 ai→RabbitMQ를 열고, `versions=DOWN`인 Pod는 Ready로 취급하지 않아야 한다. AI 계측은 #171 이후 `langfuse`·OTLP 의존성과 `LANGFUSE_*` 설정으로 추가됐다(기본 비활성, local 관측 chart는 Langfuse 제외).

### 계층 분리 (#254)

`app/versions.py`와 소비자에 섞여 있던 처리를 scoring(`model_versions`·`model_registry`·`model_startup`·`versions`)과 같은 구조로 `app/prompt_versions/`에 나눴다. `models.py`는 활성 버전 계약·`PromptChoice`, `registry.py`는 이미지 본문과 `ActiveVersions`(revision 규칙), `service.py`의 `PromptSync`는 snapshot 조회·재시도와 snapshot 전 이벤트의 이름별 최신 revision 보존·재적용, `router.py`는 `GET /internal/versions`다. `messaging/consumer.py`는 구독·재연결, 봉투 검증, `PromptSync.offer`, ACK만 맡는다. 응답 모양·경로·이벤트 계약·readiness·OpenAPI는 바꾸지 않았고 `versions.py`는 남기지 않았다.

## 8. 리포트 표시 설정 변경안 (#209)

`POST /internal/analysis/report-template`은 현재 설정과 학부모 요청만 받아 구조화한 변경안 또는 확인 질문을 반환한다. 학습 원문·학생 ID를 이 요청에 넣지 않는다. 학생 공개 설정·섹션 숨김·메모·계산식 변경은 허용하지 않는다. 저장과 확인 토큰 검증은 core가 소유한다. 실제 UI/서비스 간 연동 및 #206 공개 차단 검증은 [report](report.md) 17장을 따른다. 합성 LLM 테스트 통과는 실제 모델의 모든 자연어 해석 정확도를 보장하지 않는다.

### 프롬프트 레지스트리 등록과 core 서킷 (#280)

- 설정 제안 본문을 `analysis_agent/template_prompts.py`(`SYSTEM`·`build_user`·`PROMPT_VERSION = "analysis-template@1"`)로 옮기고 `prompt_versions`에 이름 `reportTemplate`, 승인 scope `ai/report-template`로 등록했다. `AnalysisService.propose_template`은 PARENT 확인 뒤 `ActiveVersions.prompt("reportTemplate")`로 본문·버전을 한 번 골라 LLM 호출에 그대로 쓴다. 버전 문자열은 바꾸지 않아 사용량 기록의 `promptVersion`은 이전과 같다.
- 영향: `/internal/versions` 응답에 `reportTemplate` 키가 추가된다(OpenAPI `required` 갱신). 미보유 활성 버전이면 설정 제안·`/internal/versions`가 `503 AI_PROMPT_VERSION_UNAVAILABLE`이고 readiness `versions`는 DOWN이다. core 관리자 모델 레지스트리는 이름·scope를 자유 입력으로 받으므로 core·웹 변경 없이 `PROMPT`/`reportTemplate`/`ai/report-template`으로 활성화·롤백할 수 있다. core는 `/internal/versions`를 호출하지 않는다.
- core `AiClient.reportTemplate`에는 분석 스트림 `ai-analysis`와 분리한 `ai-report-template` 서킷(최근/최소 10건·실패율 50%·30초·half-open 1건)을 두었다. 공유하면 설정 제안 실패가 분석 대화를 막고, 설정 제안은 호출량이 적어 20건 창으로는 거의 열리지 않기 때문이다. 4xx는 성공, 전송 오류·시간 초과·5xx·빈 본문은 실패로 센다. 기준은 아키텍처 1.3.
- 검증: ai `tests/test_active_versions.py`(활성 본문 선택·미보유 503), `tests/test_versions.py`, core `AiClientTest`(서킷 열림·HTTP 미호출·half-open 회복·4xx 미집계, `ai-analysis` 서킷 유지).

## 9. 미션 초안 생성·자동 검사 (#336 설계, #354 구현)

기획서 6.2 ②·③(성취기준·성취수준 문장으로 LLM 초안 → 자동 검사 → 실패 사유를 붙여 재생성)과 FAC-18의 ai 쪽 설계. 결정·근거·구현 인계 전체는 [learning 보고서](learning.md) 21절, 계약은 api-spec 4.2 `POST /internal/mission-drafts`, 구조는 class-diagram 5.4. 구현 담당은 기획서 7장 기준 최성욱(초안 생성)이다.

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 호출 단위 | 요청 1번에 LLM 생성 1회 + 검사, 반복하지 않음 | 반복을 ai 안에서 하면 `LlmClient` 최악 31초(15 + 1 + 15, `config.py`)가 3번이라 learning→ai 35초(P12)를 넘음. 반복은 learning 주기 작업이 이전 실패 사유(`previousFailures`)를 넣어 다시 부름 |
| 마감 | 63초, LLM 60초 1회(#353에서 되묻기와 같은 33초 → 63초, 9.2) | 설계 때는 `followup_deadline` 선례로 learning→ai 35초 안. 실제 성취기준 실측 뒤 미션 초안만 P12 예외로 늘림 |
| ai 검사 | `REQUIRED`(필수 항목·입력 방식별 선택지·정답 키·예시 답), `QUESTION_LENGTH`(학년별 길이), `LEAK`(질문·안내·생각 열기 질문 속 정답 키·금지어, 안내·생각 열기 질문 속 예시 답) | 기획서 6.2 ③ "판정 엔진의 질문 검사 재사용" → `followup/leak_guard.find_leaks`를 학생 답 없이 씀(`reason`은 `ANSWER_KEY`·`FORBIDDEN_TERM`·`EXAMPLE_ANSWER` 그대로) |
| learning 검사 | 성취기준 실재·요소 code 규칙·요소 `standardCode`·입력 방식 모양 | 성취기준 표와 게시 검사 규칙이 learning에 있음. ai가 표를 따로 들고 있지 않게 |
| 입력 | 성취기준 문장, (있으면) 성취수준 문장, 생각 유형, 그 유형 표준 요소 코드·공통 설명(learning이 FN 1.5에서 채움), 학년, 입력 방식 | 학생 정보·학생 답 없음(이슈 지침). 성취수준 문장은 이용 조건 확인 전까지 없음 |
| 출력 | 정해진 형식(`draft`)으로 질문·안내·장면 메모·선택지·정답 키·예시 답·금지어·생각 열기 질문·요소 | 기획서 6.2 ② 항목. 형식에 맞는 초안을 못 만들면 502(learning은 AI 호출 실패로 셈), 임의 내용으로 성공 처리하지 않음(FAC-18) |
| 프롬프트 | 내장 `mission-draft@1`, #68 레지스트리 이름 `missionDraft`·scope `ai/mission-draft`, `/internal/versions`에 추가 | 7절 규칙 그대로. `/internal/versions`를 읽는 core 코드는 없어 core 변경 없음 |
| 사용량 | `callType = MISSION_DRAFT` | 호출 종류가 이벤트 스키마·core enum·core CHECK에 고정돼 core와 같이 추가(learning 보고서 21절 core 인계) |

- 학년별 질문 길이 값은 P19(김동섭)가 정한다. 확정 전에는 아래 9.1의 기준안(전 학년 200자)을 쓴다. 생성 시간 실측도 9.1

### 9.1 ai 구현 (#354)

`app/mission_draft/`(모델·프롬프트·검사·서비스·라우터), `POST /internal/mission-drafts`, OpenAPI `MissionDraft*` 스키마. 9절 설계를 그대로 따랐고 아래만 정하거나 바꿨다.

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 질문 길이 상한 | `mission_draft_question_max_chars` 기본 `{3:200, 4:200, 5:200, 6:200}`, `gradeMin` 학년 값으로 검사(`TOO_LONG`). 설정에 없는 학년은 가장 작은 값 | P19 확정 전 기준안. 데모 시드 질문이 초3 67~156자 … 초6 92~185자라 200자면 지금 미션을 막지 않음. 학년 범위 미션은 어린 학년에 맞춤 |
| 생각 열기 질문 | 필수(`REQUIRED HINTS`), 노출 검사 대상 | 학생에게 보이는 글이라 질문·안내와 같이 봄 |
| 정답 키 노출 | 고르기는 정답 선택지 이름, 풀이는 최종 답을 글로 비교. 숫자뿐인 최종 답은 숫자 경계로 비교(정답 30이 "300원"에 걸리지 않게). 순서·분류는 비교하지 않음 | 순서·분류 정답은 한 낱말로 나타낼 수 없음 |
| 예시 답 노출 | 질문은 예시 답과 비교하지 않고, 안내·생각 열기 질문은 질문에 이미 있는 글을 빼고 비교 | 실측에서 풀이 예시 답이 질문 조건("가로 8cm, 세로 3cm인 직사각형")을 옮겨 써 12글자 겹침으로 떨어진 오탐. 되묻기가 학생 답에 있는 글을 빼는 것과 같은 방식. 정답 키·금지어는 질문도 계속 검사 |
| 들어가면 좋은 생각 | 생각 미션(서술·풀이 단계·논술)은 유형별로 정함(프롬프트 `요소 규칙`, `prompts.ELEMENT_RULE`). 분석하기 `ANALYZE_REASON`, 따져 보기 `EVALUATE_PERSPECTIVE`, 새로 만들기 `CREATE_CONNECT`, 문제 해결하기 `SOLVE_CHECK`, 돌아보기 `REFLECT_CONNECT`가 들어가면 좋은 생각이고 나머지 유형 요소는 필수. 따져 보기 논술은 세 요소 모두 필수. 정답형·정답 요소는 false | 설계에는 개수·종류 규칙이 없다(functional-spec 1.5 "미션 요소마다 정한다"). 0~1개를 LLM에 맡기면 실측 12건 모두 0개, "더 깊은 생각 1개"로 두면 논술 반론을 들어가면 좋은 생각으로 정하는 등 시드와 달랐다. 그래서 데모 시드 20문항의 유형별 지정을 기본값으로 삼았다(새로 만들기 4개·문제 해결하기 3개 모두 같고, 돌아보기 4개 중 3개·따져 보기 서술 2개·분석하기 서술 1개가 같음. 논술 12번은 세 요소 필수, 17번은 세 요소 필수에 넷째 고유 요소만 들어가면 좋은 생각이며 초안은 고유 요소를 만들지 않음). 들어가면 좋은 생각은 판정에서 필수가 아니므로(`judgment/service.py` `_result`) 시드처럼 질문이 묻는 요소일 수도 있다. 관리자가 검토에서 바꿀 수 있음 |
| 노출 검사 공유 | `followup/leak_guard.find_leaks`가 새 `find_text_leaks`(기준표 객체 없이 글 하나 검사)에 위임, 되묻기 동작은 같음 | 이슈 지침 "새 공통 라이브러리 만들지 않음" |
| 실패 응답 | 형식 밖 출력(`LLM_INVALID_OUTPUT`)은 `502 AI_BAD_RESPONSE`, 그 밖 LLM 실패는 `503 AI_UNAVAILABLE`, 둘 다 `retryable=true` | 기존 `AI_*` 코드. learning은 둘 다 AI 호출 실패로 셈 |
| 출력 상한 | `mission_draft_max_tokens` 8192(#353에서 4096 → 8192) | `gpt-6.1-terra` 출력 673~1,465토큰, `gpt-6-luna`는 최대 3,514토큰으로 4096에 가까움(9.2) |

- 이슈와 다른 점: 예시 답 노출 검사 범위와 들어가면 좋은 생각 규칙(위 표)은 실측 뒤 정했다. 들어가면 좋은 생각 규칙은 시드 작성 기준을 따른 기본값이라, 기준표 내용 담당이 정하면 `ELEMENT_RULE`만 바꾸면 된다. 나머지 계약은 api-spec 4.2 그대로다.
- 사용량 `MISSION_DRAFT`: core 이벤트 스키마·enum·CHECK에 아직 없어(#355) core 소비자가 거부하고 DLQ에 남는다. 초안 생성 자체는 막지 않는다. #355 반영 뒤 DLQ 메시지는 다시 넣을 수 있다. → #355에서 core가 받도록 반영([learning 23절](learning.md#23-core-성취기준미션-초안-프록시와-사용량-mission_draft-355)).
- 검증: `tests/mission_draft/`(검사별 실패·통과, 학생 정보 없는 입력, 이전 실패 사유 반영, 형식 밖 502·그 밖 503, 응답 필드 이름), `tests/test_versions.py`, `scripts/tests/test_ai_openapi.py`(경로 7개).

#### 생성 시간 실측 (2026-11-04, 로컬, OpenAI `gpt-6.1-terra`)

입력 방식 6가지(고르기·순서·분류·서술·풀이 단계·논술)를 3번씩, 이어서 생각 유형 5가지가 모두 들어간 생각 미션 6건, 합쳐 요청 24건·LLM 호출 27번. 입력은 성취기준 문장·유형 요소·학년·입력 방식뿐이다(학생 정보 없음). 설정은 기본값(LLM 1회 15초, 재시도 1번, 마감 33초).

| 항목 | 값 |
|---|---|
| 성공한 호출 시간 | 9.2~14.8초, 가운데 12.3초 (23번) |
| 15초 시간 초과 | 27번 중 4번(고르기 2·분류 1·풀이 1). 분류·풀이 2건은 재시도로 성공 |
| 요청 실패 | 24건 중 1건(고르기, 15초 초과 2번, 31.8초 뒤 `503`) |
| 토큰 | 입력 1,132~1,276, 출력 673~1,176 |
| 검사 | 수정 전 1건 `LEAK EXAMPLE_ANSWER` 오탐(위 표), 수정 뒤 12건 모두 통과 |
| 들어가면 좋은 생각 | 유형별 규칙 뒤 생각 미션 6건 모두 위 표대로(논술은 0개) |
| 질문 길이 | 31~109자 |

- 출력이 15초에 거의 붙어 있어 호출 일곱에 하나꼴로 시간 초과가 난다. 기본 설정을 그대로 두고 learning 반복(상한 3회)으로 받는다. 요청이 실패할 확률을 이번 비율(24건 중 1건)로 보면 3번 모두 실패할 확률은 매우 낮다. 대신 시간 초과로 버려지는 호출이 생긴다.
- 실패가 잦거나 비용이 문제가 되면 이 호출만 LLM 대기를 30초 1회(재시도 없음, 33초 마감 안)로 바꾸는 방법이 있다. P12를 바꾸는 일이라 팀 확인이 필요하다.
- **이 실측은 짧은 가짜 성취기준 문장으로 쟀다.** 실제 성취기준으로 다시 재서 시간 설정을 바꿨다(9.2).

### 9.2 미션 초안 시간 설정 변경 (#353)

#353 로컬 실연(learning 주기 작업 → 실제 ai)에서 논술 초안이 3번 모두 `AI_CALL`(`AI_UNAVAILABLE`) 실패로 `FAILED`가 됐다. 9.1 실측은 짧은 가짜 성취기준 문장이었고, 실제 2022 개정 성취기준 문장(`achievement_standard.statement`)을 넣으면 출력이 길어져 LLM 1회 15초를 넘었다(ai 직접 호출도 2번 모두 15초 초과 2번 = 31초 뒤 503).

실측(2026-11-05, 로컬, LLM 시간 제한을 풀고 1회씩, 입력 방식 6가지 × 2와 성취기준 2개짜리 논술·풀이 각 1, 같은 14건):

| | `gpt-6.1-terra` | `gpt-6-luna`(기본 모델) |
|---|---|---|
| 걸린 시간 | 10.5~18.8초, 가운데 14.0초 | 15.0~31.7초, 가운데 22.3초 |
| 30초 넘음 | 0건 | 4건(논술 30.5·30.5·31.5초, 분류 31.7초) |
| 입력·출력 토큰 | 입력 약 1,165, 출력 791~1,245 | 입력 약 1,165, 출력 1,024~3,514 |
| 검사 실패 | 0건 | 2건(금지어 노출 1, 질문 길이 초과 1. learning이 다시 생성) |

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| LLM 대기 | 미션 초안만 60초 1회(재시도 없음). `LlmClient.generate`에 호출별 `timeout`·`max_retries`를 두고 설정 `mission_draft_llm_timeout=60`·`mission_draft_llm_retries=0`. 다른 호출 종류는 15초·1회 그대로 | 초안은 learning 주기 작업이라 기다리는 사람이 없음. Luna 최대 31.7초에 여유. 30초 1회는 Luna에서 4/14가 넘음 |
| 마감 | 63초 | LLM 60초 + 검사 |
| learning→ai | 초안 ai 클라이언트만 70초(`app.mission-draft.ai-read-timeout`). 생성 리스 90초 안 | 다른 내부 호출은 35초 그대로 |
| 출력 상한 | 8192 | Luna 출력 최대 3,514토큰이 4096에 가까워 잘리면 형식 밖 출력(502)이 됨 |

- 비용: 바꾸기 전에는 논술에서 ai 1번에 LLM 호출 2번이 모두 시간 초과, learning 3번 반복으로 호출 6번에 결과가 없었다. 바꾼 뒤에는 보통 호출 1번에 끝난다. 시간 초과 호출의 과금 여부는 우리 사용량 기록(토큰 없음)으로는 알 수 없다
- P12 예외라 팀 확인이 필요하다(이슈 #353 확인 필요)
- 확인: 바꾼 뒤 로컬에서 learning 주기 작업으로 `gpt-6-luna` 입력 방식 6가지 초안이 모두 첫 시도에 `READY`(learning.md 22절). ai 테스트 `test_call_can_override_timeout_and_retries_without_changing_defaults`·`test_mission_draft_waits_60_seconds_once_with_63_second_deadline`

## 10. 일일 리포트 고정 대화 리포트 요약 입력 (#392)

2026-11-06 결정 P25(FN-RPT-16)의 ai 몫. core가 메시지마다 고정 판을 읽어 넘긴 리포트 요약을 분석 에이전트 입력에 더한다. ai는 report를 직접 호출하지 않는다(core 쪽은 [core 보고서 12장](core-gateway.md#12-일일-리포트-고정-대화-392)).

### 구현

| 영역 | 내용 |
|---|---|
| 요청 | `AnalysisRequest.report: ReportSummary \| None`(`reportId`, `revision ≥ 1`, `date`, `metrics[{label, count}]`, `problems[{title, context, judgment, elements[{label, satisfied}]}]`). 있으면 `scope.from = scope.to = date`가 아니면 400 |
| 프롬프트 | `analysis@3`. 답변 user 본문에 `[고정 리포트] {날짜} 일일 리포트, 문제 N개` + 지표·문제 JSON(판정·맥락은 웹 학부모 화면과 같은 한글 문구). `ANSWER_SYSTEM` 규칙 1에 `[고정 리포트]` 숫자 허용, 규칙 6에 판정 문구를 능력 평가로 바꾸지 않기. 일반 대화는 블록이 없다 |
| 대조 | `verification.report_numbers`: 리포트 지표 개수·문제 수·문제 제목 속 숫자를 `compute` 노드에서 `Computation.extra_numbers`에 더한다. 인용 대조는 그대로 learning `[원문]`만 |
| 범위 확인 | 고정 대화에서 `DIFFERENT_PERIOD`면 "이 대화는 {날짜} 일일 리포트로 고정돼 있어요. 다른 날은 새 대화에서 물어봐 주세요."(`PINNED_PERIOD_MESSAGE`). `current`는 고정 범위 그대로 |

### 결정

1. **리포트 인용은 받지 않음**: 요약에 원문을 넣으면 근거(`Evidence`) 구조와 core 근거 ID 저장을 바꿔야 한다. 인용은 그날 learning 기록으로 충분해 개수·판정만 받는다(사용자 확인)
2. **프롬프트 버전 올림**: 모듈 규칙대로 `analysis@2 → analysis@3`. 어떤 환경에서 `analysis@2`를 활성 버전으로 지정해 두었다면 이 이미지에서는 `503 AI_PROMPT_VERSION_UNAVAILABLE`이 되므로 배포 때 `analysis@3`으로 바꾸거나 활성 항목을 지운다

### 검증

- `uv run pytest`: 고정 리포트 요약이 답변 프롬프트에 들어가고 요약 숫자가 대조를 통과(`test_router`), 같은 답변이 일반 대화에서는 규칙 응답, 하루가 아닌 범위 400, 고정 대화의 다른 기간 안내 문구(`test_nodes`)

### 10.1 상대 날짜 질문 분류 (#454)

2026-11-10 kind 실서버 확인(#424)에서 2026-11-10 일일 리포트로 고정된 대화에 "오늘 우리 아이가 어떤 생각을 했는지 알려 줘"처럼 물으면 `clarification` `DIFFERENT_PERIOD`로 끝났다. 날짜 표현이 없는 같은 질문은 정상 답변했다. 분류 user 본문에 `[골라 둔 범위]`만 있고 현재 날짜가 없어 LLM이 "오늘·어제·이번 주"가 언제인지 알 수 없었다. 되묻기도 분석 대화 사용 1회로 차감되므로 잘못된 되묻기가 하루 30회 한도를 쓴다. 일반 분석 대화(기간 선택)에도 같은 영향이 있었다.

| 영역 | 내용 |
|---|---|
| 오늘 날짜 | ai가 요청 시작 때 직접 계산한다. `AnalysisService.stream`이 `kst_today`(`context.py`, UTC+9 고정 오프셋. 한국은 서머타임이 없어 `tzdata` 불필요)로 정한 날짜를 `AgentContext.today`에 넣고, 분류·되묻기까지 같은 값을 쓴다. 시계는 `AnalysisService(clock=...)`로 주입해 테스트에서 고정한다 |
| 프롬프트 | `analysis@4`. 분류 user 본문 맨 앞에 `[오늘] 2026-11-10(화)`를 넣고 `[골라 둔 범위]`에도 요일을 붙인다. `CLASSIFY_SYSTEM`에 상대 표현(오늘·어제·그제·이번 주·지난주·이번 달·지난달)을 `[오늘]` 기준 실제 날짜 범위로 바꿔 비교하고, 한 주는 월~일, 같으면 `NONE`·다르면 `DIFFERENT_PERIOD`라는 규칙과 예시를 더했다. 답변 프롬프트는 바꾸지 않았다 |

#### 결정

1. **core 요청에 날짜를 넣지 않음**: 요청 시각 기준 한국 날짜는 ai가 계산할 수 있어 api-spec 4.2·OpenAPI·core 변경이 필요 없다. core와 ai의 시계 차이는 자정 전후 몇 초 범위라 영향이 작다
2. **프롬프트 버전 올림**: 이미지는 이름마다 본문 한 개만 보유하고 본문을 바꾸면 `PROMPT_VERSION`을 올리는 모듈 규칙(10장 결정 2와 같은 방식)에 따라 `analysis@3 → analysis@4`. core 활성 버전 시드에는 `analysis` 항목이 없어(기본 버전 사용) 시드 변경은 없다. 어떤 환경에서 `analysis@3`을 활성 버전으로 지정해 두었다면 이 이미지에서는 `503 AI_PROMPT_VERSION_UNAVAILABLE`이 되므로 배포 때 `analysis@4`로 바꾸거나 활성 항목을 지운다. `/internal/versions`의 `analysis` 값은 `analysis@4`
3. **범위 안의 더 좁은 기간도 다른 기간으로 봄**: 일반 대화에서 한 주를 골라 두고 "오늘"을 물으면 계산은 한 주 전체로 하므로, 같은 범위가 아니면 `DIFFERENT_PERIOD`로 기간을 다시 고르게 한다(이슈 기준 "같으면 NONE, 다르면 DIFFERENT_PERIOD")

#### 검증

- `uv run pytest`: 고정 범위가 오늘(2026-11-10)·어제(2026-11-09)일 때 분류 입력에 `[오늘] 2026-11-10(화)`와 요일 붙은 범위가 들어가고 규칙이 system에 있음(`test_nodes`), KST 자정 경계(`test_kst_today_uses_korean_date`), 주입한 시계가 UTC 15시 이후면 다음 날로 들어감(`test_router`), `/internal/versions` `analysis@4`(`test_versions`)
- 실제 LLM으로 "오늘 …" 질문이 되묻기 없이 답변되는지는 머지 후 kind에서 확인한다(이슈 완료 조건)

## 11. 모델 등록 API (#367)

### 11.1 백엔드 등록 계약 구현 (2026-11-09)

기존 등록 API에 EvaluationEvidence.limitations(기본 [])와 registration 출처 메타데이터를 추가했다. MODEL의 artifactUri 누락은 등록 시 422로 거부한다. 기존 evaluation JSONB를 사용하므로 DB 마이그레이션은 없다. 기존 행은 limitations=[]로 읽히고 평가 근거를 덮어쓰지 않는다.

MODEL_REGISTER 감사 detail에 source·jsonSha256·manifestSha256·modifiedFields·artifactFiles를 기록한다. 원본 파일을 서버에 업로드하지 않으므로 해시/크기는 클라이언트 신고로 취급하며 파일·품질 검증 성공으로 간주하지 않는다. 등록 요청의 승인 관련 값·알 수 없는 필드는 거부하며 기존 사람 승인·활성화·복귀와 이벤트 계약은 유지한다.

프론트 전달 내용(11.2~11.7)에 원본 바이트 해시 방식, 요청 예시, 응답 위치, 오류와 각 담당 범위를 정리했다. 후속 통합에서 PR #409의 프론트와 연결해 등록 출처 메타데이터도 함께 전달한다. 검증 결과는 [11.9 통합 검증 결과](#119-통합-검증-결과)를 기준으로 본다.

검증: core ModelVersionHttpTest·ModelVersionRepositoryTest·ModelVersionMessagingTest 총 23개 및 bootJar 통과. 등록/목록의 limitations, 구버전 JSONB, MANUAL 기본값, JSON_IMPORT 감사·인증 사용자, 중복 시 원본 유지, 자동 활성화 없음, 필수 경로·해시·파일 크기·상대 경로·알 수 없는 필드 거부와 기존 활성화·복귀를 확인했다. 계약 검증기 전체 187개 통과. 이는 최초 백엔드 단독 검증 기록이다. 후속 프론트 통합 결과는 [11.9 통합 검증 결과](#119-통합-검증-결과)을 참고한다. GitHub CI와 운영 품질 승인은 로컬 검증과 구분한다.

### 11.2 작업 범위와 연결 기준

통합 브랜치: `feature/367-model-registration-backend`. develop `8defa1f3`와 PR #409의 프론트 구현을 통합했다. 등록과 감사 출처 저장을 연결하며 운영 활성화는 별도 승인이다.

- API: `POST /api/v1/admin/model-versions`, SERVICE_OPS 관리자 Bearer 인증
- 기존 등록 경로를 그대로 사용한다. JSON 업로드·일괄 등록 엔드포인트는 없다.
- 서버 계약 원본: [core OpenAPI](../../contracts/openapi/core-service.yaml)의 RegisterModelVersion, EvaluationEvidence, ModelRegistrationMetadata, ModelRegistrationArtifact
- 화면 변경 순서: #366 카드별 입력 분리 이후 #367 가져오기 화면을 연결하는 것을 권장한다. 백엔드는 기다릴 필요 없다.

### 11.3 파일을 읽고 요청을 만드는 순서

S3 산출물을 먼저 준비할 때는 [전체 SHA-256 업로드 절차](model-artifact-upload.md)를 따른다. 기존 manifest와 로컬 원본 대조 → 단일 PutObject → S3 전체 SHA-256 확인 → 사전 검사 순서다. manifest의 파일 해시를 등록 감사에 저장하는 것과 S3가 전체 체크섬을 보유하는 것은 별개다. 기존 모델의 체크섬 보완 때문에 같은 모델을 다시 등록하거나 활성화하지 않는다.

1. registration_1103.json 원본 바이트를 읽어 SHA-256을 계산한다. `file.arrayBuffer()` → `crypto.subtle.digest('SHA-256', buffer)` → 소문자 16진수 64자리. BOM·공백·개행을 포함한 원본 파일 그대로이며 파싱/재직렬화한 JSON으로 계산하지 않는다.
2. 파싱한 requests[]를 모델별 카드로 만든다. 최상위 설명(title/version/date/author/주의/<버킷>)은 POST 본문에 보내지 않는다. requests[]의 승인 관련 값이나 알 수 없는 필드는 가져오기 단계에서 거부한다.
3. 선택한 manifest도 원본 바이트로 해시한다. name/version/scope를 대조하고 해당 모델 files[]만 고른다. manifest가 없으면 manifestSha256 생략, artifactFiles는 []다.
4. 버킷을 치환하고 limitations를 확인한다. 항목에 evaluation.limitations가 있으면 빈 배열도 그 값을 유지한다. 없으면 registration 최상위 주의와 해당 모델 manifest 주의를 후보로 제시해 확인·수정한다.
5. 원본 항목과 최종 등록 값이 다른 필드 경로를 modifiedFields에 중복 없이 기록한다. 버킷 치환도 artifactUri 변경이다. limitations 후보를 새로 넣었으면 evaluation.limitations를 포함한다. 배열은 원소 인덱스가 아닌 배열 필드 경로 하나로 기록한다.
6. 운영자가 개별 등록을 누르면 requests[i]의 등록 필드에 아래 registration 메타데이터를 붙여 POST한다. 성공한 카드만 등록 완료로 표시한다. 실패한 카드 때문에 성공한 레코드를 다시 보내거나 덮어쓰지 않는다.

### 11.4 요청 예시

아래는 **합성 예시**다. a/b/c 반복 해시는 형식 설명용이며 실제 파일의 해시가 아니다. 실제 운영 모델을 다시 등록하지 않는다.

```json
{
  "kind": "MODEL",
  "name": "synthetic-model",
  "version": "1.0",
  "artifactUri": "s3://example-models/models/synthetic-model/1.0/",
  "evaluation": {
    "datasetId": "synthetic-eval",
    "datasetVersion": "1",
    "baselineVersion": "synthetic-baseline",
    "comparisonReport": "synthetic/comparison",
    "trainingEvaluationSeparation": "synthetic/split",
    "quoteAccuracy": "synthetic/quotes",
    "calculationAccuracy": "synthetic/calculations",
    "humanReview": "synthetic/review",
    "evaluatedScopes": [
      "judgment/grade-5/narrative"
    ],
    "limitations": [
      "연동 테스트용 합성 자료이며 품질 승인 근거가 아님"
    ]
  },
  "registration": {
    "source": "JSON_IMPORT",
    "jsonSha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
    "manifestSha256": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "modifiedFields": [
      "artifactUri",
      "evaluation.limitations"
    ],
    "artifactFiles": [
      {
        "file": "config.json",
        "bytes": 123,
        "sha256": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
      }
    ]
  }
}

```

수동 등록은 같은 필드에서 registration을 생략하면 된다. limitations도 생략 가능하며 []로 처리한다. 추가된 registration 정보는 평가 근거에 섞지 않고 등록 감사 detail에만 저장한다.

### 11.5 입력 규칙

| 필드 | 규칙 |
|---|---|
| artifactUri | MODEL이면 필수·공백 불가, 최대 2,048자. 경로 형식 경고·자리표시자 차단은 프론트 담당 |
| evaluation.limitations | 선택, 생략 시 [], 최대 100개, 항목마다 1~4,000자·공백/null 불가 |
| registration.source | MANUAL 또는 JSON_IMPORT. 생략 시 MANUAL |
| jsonSha256 | JSON_IMPORT이면 필수, registration 원본 파일 해시 |
| manifestSha256 | 선택 manifest 원본 파일 해시. artifactFiles가 있으면 필수 |
| modifiedFields | 최대 100개·중복 불가. 아래 필드 경로만 허용 |
| artifactFiles | 선택한 모델의 manifest files[], 최대 100개. 파일 경로 중복 불가 |
| artifactFiles[].file | 1~255자 상대 경로. 절대 경로·역슬래시·콜론·빈 경로 조각·.·.. 금지 |
| artifactFiles[].bytes | 파일 크기, 0 이상 정수 |
| artifactFiles[].sha256 | manifest의 해당 파일 SHA-256, 소문자 64자리 |

MANUAL에는 JSON/manifest 해시와 비어 있지 않은 modifiedFields·artifactFiles를 보내지 않는다.

modifiedFields 허용값:

```text
kind, name, version, refId, artifactUri,
evaluation.datasetId, evaluation.datasetVersion, evaluation.baselineVersion,
evaluation.comparisonReport, evaluation.trainingEvaluationSeparation,
evaluation.quoteAccuracy, evaluation.calculationAccuracy, evaluation.humanReview,
evaluation.evaluatedScopes, evaluation.limitations
```

기존 평가 근거 8개 문자열과 evaluatedScopes는 계속 필수다. RUBRIC만 refId를 필수로 받으며 다른 종류는 refId를 보내지 않는다. 알려지지 않은 모델 이름·scope 후보·버전 형식·모델 저장 경로 형태의 경고는 기존 #367 프론트 요구사항대로 구현한다. core는 새 scope를 임의로 차단하지 않는다.

### 11.6 성공 응답과 화면 연결

201 응답은 기존 ModelVersion이다. 목록 조회도 같은 객체를 반환한다.

```text
id, kind, name, version, refId, artifactUri,
evalResult: {
  evidence: { 기존 평가 필드, limitations: [...] },
  approval: null,
  activeScopes: [],
  revision: 0
},
status: REGISTERED,
approvedBy: null,
activatedAt: null,
createdAt
```

- 요청은 evaluation.limitations, 응답은 evalResult.evidence.limitations로 위치가 다르다.
- 구버전 DB 행에 limitations가 없어도 목록에서 []로 읽힌다. DB 마이그레이션·기존 평가 근거 덮어쓰기는 없다.
- registration 메타데이터는 ModelVersion 응답에 추가하지 않는다. 기존 MODEL_REGISTER 감사 detail에 source/jsonSha256/manifestSha256/modifiedFields/artifactFiles로 저장한다. PR #409의 감사 목록 API는 허용된 모델 조치 상세만 반환한다. 등록 출처·파일 해시의 DB 저장과 화면 공개 범위는 구분하며, 원본 JSON 내용은 감사 응답에 노출하지 않는다.
- 등록자·ID·시각·상태는 서버가 정한다. 등록으로 approval·ACTIVE·활성화 이벤트가 생성되지 않는다.
- 해시·파일 크기는 프론트가 신고한 출처 기록이다. 백엔드는 파일 원문을 받지 않으므로 실제 파일 해시 일치·S3 존재·로딩·품질 승인을 확인했다고 표시하면 안 된다. 사전 검사는 후속 범위다.

### 11.7 오류 표시

| HTTP·code | 프론트 처리 |
|---|---|
| 400 VALIDATION_FAILED | 잘못된 JSON/타입·알 수 없는 필드·승인 관련 필드. 폼 상단 오류, 원본/요청 구조 확인 |
| 401 / 403 | 기존 인증·SERVICE_OPS 권한 처리 |
| 409 MODEL_VERSION_CONFLICT | kind/name/version 중복. 해당 카드 이름·버전 입력에 안내. 기존 평가를 덮어쓰지 않음 |
| 422 MODEL_APPROVAL_REJECTED | MODEL 경로 누락, 불완전 평가/범위, 잘못된 limitations·감사 메타데이터. 폼 상단에 서버 메시지 |

공통 RFC 9457 형식은 바꾸지 않는다. title/detail/code/traceId 처리는 기존 API 클라이언트를 재사용한다. 서버가 필드별 errors 배열을 준다고 가정하지 않는다. UI의 상세 필드 오류는 브라우저 사전 검증에서 표시한다.

### 11.8 통합 완료 확인 (2026-11-09)

- [x] #366 화면 변경을 반영한 #367 프론트 및 웹 타입 연결
- [x] 실제 11/03 registration·manifest를 로컬에서 가져오기 → 버킷 치환 → 개별 등록
- [x] 성공/중복/부분 실패 카드 상태와 수정 표시 확인
- [x] limitations 미리보기·목록·승인 확인 창 표시
- [x] 프론트 lint/test/test:types/build·브라우저 테스트

운영의 기존 서술 3.0·논술 3.1은 재등록하거나 활성화하지 않는다. JSON 원본·실제 모델 파일은 이 변경에 포함하지 않는다.


### 11.9 통합 검증 결과

- 기준: develop `8defa1f3`, PR #409 `4b261e81` 통합. PR #409를 먼저 병합하면 그 변경을 제외한 #367 후속 변경을 리뷰할 수 있다. 다른 PR의 운영 승인이나 병합은 수행하지 않았다.
- core: ModelVersionHttpTest 12개, ModelVersionRepositoryTest 8개, ModelVersionMessagingTest 4개, AdminOperationsIntegrationTest 25개, 합계 49개 통과. bootJar 통과.
- 실제 등록: 별도 opt-in ModelVersionBrowserIntegrationTest 1개와 Playwright desktop 가져오기 1개 통과. 제공받은 11/03 registration_1103.json·manifest.json 원본을 사용했고 브라우저에서 계산한 해시를 원본 바이트 해시와 대조했다.
- 등록/목록 요청은 HTTP 대역 대신 실제 로컬 core와 Testcontainers PostgreSQL로 전달했다. 화면의 로그인 진입은 합성 응답이며 실제 등록 요청에는 테스트용 관리자 JWT를 사용했다. OAuth 로그인, S3 파일 존재, scoring 로딩 검증으로 확대 해석하지 않는다.
- DB 확인: REGISTERED·미승인·미활성 모델 2건, 해당 관리자의 JSON_IMPORT 감사 2건(원본 JSON·manifest 해시와 산출물 파일 목록 포함), 활성화 이벤트 0건.
- web: 단위 244개, 모델 브라우저 9개(실제 제공 파일·HTTP 대역·3개 화면 폭), 기존 브라우저 24개, PR #409 꾸미기 회귀 9개 통과. lint·test:types·build 통과.
- 저장소 계약 검증기 189개 통과. 병합 과정에서 중복된 계약 fingerprint 정규화를 하나로 정리했다. Windows sandbox의 임시 폴더 정리 권한 오류는 동일 테스트를 권한이 있는 실행 환경에서 재실행해 해소했다.
- GitHub CI는 로컬 검증과 별개다. 운영 기존 모델 재등록·활성화, 원본 JSON·가중치 커밋은 하지 않았다.

### 11.10 이슈 요구사항 대응

#### web
- [x] 브라우저 requests[] 파싱 → 기존 API 개별 POST
- [x] 모델별 미리보기·개별 등록·부분 실패·수정 표시
- [x] 버킷 일괄 치환과 자리표시자 등록 차단
- [x] 최상위/manifest 주의 후보 및 명시적 limitations 우선
- [x] 형식·알 수 없는 요청 필드·필수 평가 근거·scope·중복·manifest 일치 검증
- [x] 알려진 scope/모델명·버전·권장 경로 경고
- [x] 409 이름/버전 필드 안내, 422 폼 상단 안내
- [x] 카드와 승인·활성화 확인 창의 limitations 표시

#### core·문서
- [x] limitations 선택 필드, 기본 빈 목록, 기존 JSONB 호환
- [x] MODEL artifactUri 필수
- [x] MANUAL/JSON_IMPORT·원본 JSON SHA-256·수정 필드·산출물 파일 해시 감사 저장
- [x] api-spec 5.2·OpenAPI·웹 타입과 등록 계약 반영

#### 완료 조건·유지 원칙
- [x] core 테스트 및 web lint·test·test:types·build·브라우저 테스트
- [x] 실제 11/03 두 파일로 로컬 가져오기 → 등록 확인
- [x] 승인 정보 거부, 가져오기만으로 활성화하지 않음
- [x] 기존 등록 평가 근거를 덮어쓰지 않음

### 11.11 실제 core 브라우저 검증 재현

1. Docker/JDK 21 환경에서 core 테스트를 `MODEL_BROWSER_LOCAL=true`, `MODEL_BROWSER_OUTPUT=<공유된 테스트 출력 디렉터리>`로 실행한다. Gradle 대상은 `test --tests '*ModelVersionBrowserIntegrationTest'`다. 테스트 포트 8080을 호스트 127.0.0.1:58087에 매핑한다. 일반 CI에서는 이 opt-in 테스트가 건너뛰어지며 기존 HTTP/DB 테스트는 계속 실행된다.
2. 해당 출력 디렉터리의 session.json 생성 후 웹 빌드를 준비하고 `MODEL_LOCAL_CORE_SESSION=<session.json>`, `MODEL_REGISTRATION_FILE=<실제 등록 JSON>`, `MODEL_MANIFEST_FILE=<실제 manifest>`를 설정한다. `npm run test:models -- --project desktop --grep '등록 JSON'`으로 실행한다.
3. Playwright가 실제 core 등록/목록 API를 호출하고 검증 완료 표시를 남긴다. core 테스트가 DB 저장과 비활성을 검사한 뒤 verified.json을 남기고 종료한다. 테스트 세션 파일은 외부 공유·커밋하지 않고 종료 후 삭제한다.

## 12. 모델 사전 검사 (#368)

### 12.1 사전 검사 구현 요약 (2026-11-09)

scoring의 읽기 전용 파일·메타데이터 검사, core 관리자 동기 중계와 별도 MODEL_PREFLIGHT 감사, web 미리보기 검사 버튼을 연결했다. 가중치 본문은 다운로드하지 않으며 전체 S3 SHA-256이 없으면 실패한다. core→scoring local/prod NetworkPolicy와 서비스 URL을 반영했다. 실제 local core·scoring·MinIO·PostgreSQL에서 정상/해시 불일치/누락을 검증했다. 후속 AWS 읽기 전용 확인에서 실제 Pod Identity 연결·S3 읽기 정책과 12개 객체 HEAD를 확인했다. 당시 객체에 S3 SHA-256이 없었으나 #493에서 단일 PutObject 업로드 방식을 정하고 12개 객체를 보완해 CloudShell 사전 검사 PASS까지 확인했다([12.9](#129-전체-sha-256-업로드-방식-결정-493)·[12.10](#1210-aws-s3-보완과-cloudshell-사전-검사-493)). scoring replicas=0이라 실제 Pod 실행 검증만 남아 AWS 항목은 미완료로 유지한다. 운영 배포·재가동·정책 변경은 하지 않았다. 계약·검증·원문 체크리스트는 12.2 이하에 둔다.

### 12.2 구현

최신 develop `17508815`(#409·#410 병합)를 반영한 `feature/368-model-preflight`에서 작업했다. 기존 #367 등록 API·평가 근거·활성화 흐름을 유지하고 읽기 전용 사전 검사 경로를 추가했다.

- scoring: `POST /internal/models/preflight`. 설정된 모델 버킷의 `models/` 경로만 허용한다. manifest의 여섯 파일을 중복 없이 받으며 존재·크기·SHA-256을 검사한다. `config.json`, `train_info.json`, `score_cuts.json`만 최대 1MiB씩 읽는다. 가중치와 tokenizer 본문은 받지 않는다.
- 메타데이터: 기존 `validate_metadata`로 학습 입력·항목·경계를 검사하고 config의 `num_labels` 또는 `id2label` 수와 regression 설정을 검사한다. 실제 가중치 shape·CPU 로딩·추론 확인은 이 검사의 범위가 아니다.
- core: SERVICE_OPS 관리자 `POST /api/v1/admin/models/preflight` → 기존 InternalRestClientFactory로 내부 토큰을 붙여 동기 중계한다. HTTP 20초, 재시도 없음. scoring은 15초 작업 예산·S3 연결/읽기 각각 1초·재시도 없음. 웹은 25초 후 요청을 중단한다.
- 감사: `MODEL_PREFLIGHT`의 `result=SUCCESS|FAILURE`, target_type=MODEL_VERSION, target_id=null(등록 전 검사). detail에 이름·버전·경로·manifest와 안전한 결과 코드만 저장한다. upstream 장애도 실패 이력으로 남기며 제공자 원문 오류·자격 증명은 반환하지 않는다. 기존 평가 JSONB에 결과를 섞지 않는다.
- web: JSON 미리보기 카드에서 manifest의 여섯 파일과 입력 검증을 통과해야 검사 버튼을 사용할 수 있다. 파일별 원인을 표시하고 입력이 바뀌면 이전 결과를 만료시킨다. 검사 성공으로 등록·승인·활성화하지 않는다.
- local·prod NetworkPolicy: core egress 8001 → scoring, scoring ingress에 core를 추가했다. 기존 ai 호출과 포트는 유지한다. Compose 및 local/prod core에 SCORING_URL을 추가했다.

### 12.3 체크섬과 AWS 확인 범위

[Amazon S3 HeadObject 계약](https://docs.aws.amazon.com/AmazonS3/latest/API/API_HeadObject.html)에 따라 `ChecksumMode=ENABLED`로 조회한다. 작은 JSON은 실제 바이트 SHA-256으로 대조한다. 나머지는 S3 전체 파일 SHA-256만 사용하고 ETag, 임의 사용자 metadata의 sha256, multipart COMPOSITE는 대체 근거로 인정하지 않는다. 전체 SHA-256이 없으면 `CHECKSUM_UNAVAILABLE`로 실패한다. 성공처럼 표시하거나 가중치 다운로드로 우회하지 않는다.

따라서 기존 AWS 객체가 multipart COMPOSITE이거나 SHA-256을 저장하지 않았다면 사전 검사가 실패할 수 있다. 객체를 임의로 다시 업로드하거나 운영 모델을 교체하지 않았다. 업로드 방식 보완이 필요하면 #212 담당자와 해당 객체 상태를 확인한 뒤 별도로 반영한다.

2026-11-10 #493에서 단일 PutObject에 전체 원본 SHA-256을 명시하는 방식으로 정했다([12.9](#129-전체-sha-256-업로드-방식-결정-493)). 이후 사용자 추가 지시로 기존 두 모델 12개 객체의 실제 S3 보완과 CloudShell 자격 증명의 사전 검사 PASS를 확인했다([12.10](#1210-aws-s3-보완과-cloudshell-사전-검사-493)). 실제 Pod 검증은 남아 있다.

저장소의 `scoring-s3-read` IAM 정책은 s3:ListBucket·s3:GetObject를 허용한다. 사용 API는 HeadObject·GetObject이며 새 쓰기 권한은 필요 없다. JSON GET은 If-Match로 고정하여 GetObjectVersion 권한을 요구하지 않는다. SSE-KMS 객체의 checksum 조회에는 추가 KMS 권한이 필요할 수 있다. #212 문서의 Pod Identity·S3 Gateway 경로를 검토했고, 2026-11-09 AWS 콘솔 CloudShell에서 실제 IAM 연결·정책과 S3 객체 HEAD를 조회했다. 배포·정책 수정은 하지 않았다. NetworkPolicy YAML/JSON 검증은 실제 클러스터 통신 검증과 구분한다.

### 12.4 로컬 재현

새 일회용 MinIO 컨테이너만 사용한다. 아래 로그인 값은 테스트 전용이며 운영 자격 증명을 사용하지 않는다.

1. MinIO `quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z`를 `127.0.0.1:58100:9000`으로 실행한다. MINIO_ROOT_USER=preflight-local, MINIO_ROOT_PASSWORD=preflight-local-test-only, 명령 `server /data`.
2. 저장소 루트에서 scoring Python 환경으로 `scripts/seed_model_preflight_local.py` 실행. localhost의 새 models 버킷에 합성 파일을 만든다. 이미 존재하는 버킷이면 덮어쓰지 않고 실패한다. 정상 prefix와 가중치가 없는 prefix를 만들고 output/issue368-request.json을 생성한다.
3. scoring 환경에서 INTERNAL_TOKEN=preflight-local-token, S3_ENDPOINT_URL=http://127.0.0.1:58100, S3_BUCKET=models, AWS_ACCESS_KEY_ID=preflight-local, AWS_SECRET_ACCESS_KEY=preflight-local-test-only를 지정한다. `python -m uvicorn tests.preflight_local_server:app --host 0.0.0.0 --port 58101`로 실행한다. 이 테스트 서버는 운영 라우터·인증을 쓰되 사전 검사와 무관한 AMQP/모델 로딩 시작만 생략한다.
4. JDK21·Docker 환경에서 core `test --tests '*ModelPreflightLocalIntegrationTest'` 실행. PREFLIGHT_LOCAL=true, PREFLIGHT_SCORING_URL=http://host.docker.internal:58101(Docker 밖이면 localhost), PREFLIGHT_REQUEST_FILE=<생성한 JSON의 테스트 환경 경로>. core 테스트 DB는 Testcontainers가 생성·삭제한다.
5. 결과는 정상 PASS, 모델 가중치 해시 불일치 FAIL/HASH_MISMATCH, 파일 누락 FAIL/FILE_MISSING. 감사 SUCCESS 1·FAILURE 2건, 등록 모델 0건을 검사한다. 종료 후 테스트 서버와 일회용 MinIO를 중지한다.

실제 모델 파일·등록 JSON·가중치와 운영 비밀 값은 커밋하지 않는다. 로컬 성공은 운영 품질 승인이나 활성화 승인이 아니다.


### 12.5 검증 결과 (2026-11-09)

- core: ModelPreflightHttpTest 4개 + 기존 ModelVersionHttpTest 12개, 합계 16개 및 bootJar 통과.
- 실제 local 연동: ModelPreflightLocalIntegrationTest 1개 통과. 실제 HTTP scoring·MinIO를 사용한 세 경우와 PostgreSQL 감사 저장 확인.
- scoring 전체 212개 통과 후 출력 수 모순 사례를 1개 추가하여 사전 검사 14개를 재검증했다. 총 213개 고유 테스트 검증. Ruff check·format 통과.
- web 단위 244개, 모델 브라우저 12개(데스크톱·태블릿·휴대폰), lint·test:types·build 통과. 새 사전 검사 테스트는 합성 HTTP 응답이며 실제 core/S3 검증과 구분한다.
- 저장소 계약 검증기 192개 통과. core/scoring 요청·응답 계약 일치, 양방향 local/prod NetworkPolicy, 기존 S3 읽기 정책 포함.
- AWS 콘솔 CloudShell에서 아래 읽기 전용 확인을 수행했다. #368 운영 배포와 실제 Pod 통신 검증은 수행하지 않았다. GitHub CI도 별도 확인 대상이다.

### 12.6 이슈 원문 체크리스트 대응

#### 해야 할 일
- [x] scoring `POST /internal/models/preflight`(가칭): name·version·artifactUri와 manifest `files[]`를 받아 6개 파일의 존재·크기·sha256 확인, 작은 JSON 3개(config.json·train_info.json·score_cuts.json)만 읽어 `validate_metadata`·출력 수 확인. 가중치는 받지 않음
- [x] core 관리자 API로 동기 중계(시간 제한 포함), core scoring 클라이언트 추가
- [x] 결과를 별도 감사 action(가칭 `MODEL_PREFLIGHT`, `result` SUCCESS·FAILURE)으로 기록. `evidence`에는 넣지 않음
- [x] NetworkPolicy: scoring ingress에 core 허용, core egress에 scoring 추가(`environments/local/scoring-service.yaml`·`core-service.yaml`, prod 구성도 확인)
- [ ] scoring S3 읽기 권한이 사전 검사 경로에 충분한지 #212 AWS 설정과 조율
- [x] web: 미리보기 카드에 "사전 검사" 버튼과 결과 표시(manifest 필요)
- [x] api-spec·OpenAPI 반영

AWS 실제 역할 연결·정책 및 객체 HEAD 확인까지 완료했다. S3 SHA-256 업로드 방식과 기존 12개 객체 보완은 #493에서 끝났다(12.9·12.10). 실행 중인 scoring Pod가 없어 실제 Pod 검증만 남았으므로 AWS 항목은 미완료로 유지한다. 운영 권한은 변경하지 않았다.

#### 완료 조건
- [x] scoring·core 테스트, web 테스트 통과
- [x] local 환경에서 정상 파일·해시 불일치·파일 누락 세 경우 결과 확인
- [x] AWS 반영 여부와 결과는 실제 실행한 것만 기록

#### 유지할 원칙
- [x] 사전 검사 통과는 "파일·형식 확인"으로만 표시. 품질 승인·활성화 가능 상태로 표시하지 않고 자동으로 다음 단계로 넘기지 않음

### 12.7 AWS 읽기 전용 확인 (2026-11-09)

- 환경: 서울 리전 `sagomungchi-demo-eks`, 모델 버킷 `sagomungchi-demo-347161580747-models`. IAM 사용자 CloudShell에서 확인했으며 scoring 역할을 직접 실행한 결과와 구분한다.
- deployment `app/scoring-service`는 serviceAccount `scoring-service`, replicas=0이다. app 네임스페이스에 Pod가 없어 실제 Pod Identity 자격 증명으로 HeadObject/GetObject를 실행하거나 core→scoring 통신을 확인할 수 없었다. replicas를 변경하지 않았다.
- Pod Identity association `a-8esdvbyftwtdacyfq`는 `app/scoring-service`를 `sagomungchi-demo-scoring-s3-role`에 연결한다.
- 실제 inline policy `sagomungchi-demo-scoring-s3-read`는 모델 버킷의 ListBucket과 객체 전체 경로의 GetObject를 허용한다. attached managed policy는 없다. 확인한 객체는 모두 AES256 암호화다. 정책상 필요한 S3 읽기 작업이 포함되지만 실제 Pod 접근 성공으로 단정하지 않는다.
- 두 모델의 필수 파일 12개 모두 `HeadObject(ChecksumMode=ENABLED)` 성공. 전부 `ChecksumType=FULL_OBJECT`이지만 `ChecksumSHA256`은 없다. FULL_OBJECT 표기만으로 SHA-256 존재를 인정하지 않는다.

| 파일 | 서술형 3.0 크기(bytes) | 논술형 3.1 크기(bytes) |
| --- | ---: | ---: |
| config.json | 1177 | 1383 |
| tokenizer.json | 752095 | 752095 |
| tokenizer_config.json | 452 | 452 |
| train_info.json | 1694 | 1570 |
| score_cuts.json | 531 | 86 |
| model.safetensors | 442524276 | 442539656 |

현재 구현에 이 객체를 입력하면 본문을 읽지 않는 tokenizer.json·tokenizer_config.json·model.safetensors는 CHECKSUM_UNAVAILABLE 대상이다. 작은 JSON은 본문 해시 검사가 가능하지만 이번 AWS 확인에서는 HEAD만 실행했으므로 해시·메타데이터 유효성 통과로 기록하지 않는다.

남은 조치: #212 업로드 담당자와 전체 파일 SHA-256을 S3에 제공하는 업로드 방식을 맞추고, 서비스 재가동 시 실제 scoring Pod의 읽기·통신을 확인한다. 체크섬 검사 완화, 가중치 다운로드, 운영 객체 재업로드, 정책 변경, 서비스 재가동은 수행하지 않았다.

위 기록은 11/09 읽기 전용 확인 결과로 보존한다. 이후 업로드 방식 결정과 11/10 실제 S3 보완 결과는 [#493 업로드 안내](model-artifact-upload.md)에 별도로 기록했다.

### 12.8 kind 확인 (2026-11-10)

local kind에 배포된 이미지(develop `ecc6b71d`)로 core → scoring → MinIO 경로를 다시 확인했다. 확인용 모델은 학습하지 않은 작은 BERT 형태(출력 9개, 회귀)다. scoring Pod 안에서 만들어 실제 로더로 불러지는 것까지 확인했다. 이 모델을 `sagomungchi-local-models`에 `ChecksumSHA256`을 붙여 올렸다.

| 경우 | scoring 내부 API | 관리자 화면(registration·manifest JSON 가져오기 → 사전 검사) |
| --- | --- | --- |
| 정상 | PASS `FILES_AND_METADATA_VERIFIED` | 파일·형식 확인 완료 |
| 해시 불일치(manifest의 가중치 sha256만 변경) | FAIL, `model.safetensors` `HASH_MISMATCH` | SHA-256 불일치 |
| 파일 누락(가중치 없는 경로) | FAIL, `model.safetensors` `FILE_MISSING` | 파일 없음 |

- 감사 `MODEL_PREFLIGHT`는 SUCCESS 1·FAILURE 2였고, 자동 등록된 MODEL 행은 0이다. 확인 후 MinIO 객체를 지웠다
- AWS는 실행하지 않았다. 남은 S3 SHA-256 업로드 방식 결정과 실제 Pod 확인은 #493으로 분리했다

### 12.9 전체 SHA-256 업로드 방식 결정 (#493)

2026-11-10 develop `fd119af1` 기준. 모델별 6개 파일을 `aws s3api put-object`로 단일 업로드하고, 원본 전체 SHA-256의 Base64 값을 명시한다. 현재 약 443MB 가중치는 단일 PUT 한도 안에 있다. multipart SHA-256은 COMPOSITE라 기존 사전 검사 계약을 만족하지 못한다.

- [업로드 안내](model-artifact-upload.md): 공식 근거, 신규 객체 명령, 기존 서술 3.0·논술 3.1의 동일 원본 보완 방침, 메타데이터 보존·동시 변경 방지·복구 및 실제 Pod 확인 절차
- [로컬 준비 도구](../../scripts/prepare_model_upload.py): 기존 manifest 기반 사전 검사 요청과 로컬 6개 파일을 크기·SHA-256으로 대조하고 업로드 계획만 생성. AWS 접속·업로드·등록·활성화 기능 없음
- 기존 두 모델은 아래 12.10에서 실제 S3 보완을 완료했다. EKS·RDS 재가동과 권한 변경은 하지 않았고 실제 scoring Pod 검증은 **미완료**다.
- ETag·사용자 metadata·COMPOSITE 거부와 작은 JSON만 GET하는 계약을 유지한다. 서비스 코드·API·DB·IAM·배포 설정은 변경하지 않는다. 로컬 검증 결과는 [업로드 안내 6절](model-artifact-upload.md#6-로컬-검증)에 따로 기록한다.

### 12.10 AWS S3 보완과 CloudShell 사전 검사 (#493)

2026-11-10 사용자 추가 지시에 따라 서버를 켜지 않고 기존 모델 버킷의 12개 객체를 보완했다. 로컬 원본 및 S3 기존 버전 본문을 담당자 manifest와 대조한 뒤 동일 원본·속성으로 단일 PutObject를 실행했다. 전체 SHA-256·크기 일치와 이전 버전 보존을 확인했다. #212의 IAM·버킷·네트워크 설정은 변경하지 않았다. 별도 담당자 연락을 수행한 것으로 기록하지 않는다.

| 검증 대상 | 결과 |
| --- | --- |
| 기존 서술 3.0·논술 3.1, 총 12개 객체 | 모두 FULL_OBJECT SHA-256과 manifest 일치, 원본 바이트·속성 유지, 이전 버전 보존 |
| CloudShell 운영자 자격 증명으로 실제 S3 대상 검사 | 두 모델 모두 PASS / FILES_AND_METADATA_VERIFIED, 모델별 HEAD 6회·작은 JSON GET 3회 |
| EKS·RDS | 작업 전후 두 nodegroup desiredSize=0, RDS stopped. 재가동 없음 |
| 실제 scoring Pod Identity 및 관리자 → core → scoring | 미실행. 재가동 후 별도 검증 필요 |

검사는 `83500294`의 원본 사전 검사 소스 8개를 해시 대조한 뒤 CloudShell Python 3.13에서 직접 실행했다. 배포 이미지/Python 3.12 Pod의 HTTP·권한·네트워크 검증으로 간주하지 않는다. 자세한 실행 범위·복구 정보는 [업로드 안내 7절](model-artifact-upload.md#7-실제-aws-s3-보완검사-결과-2026-11-10), [객체별 증빙](evidence/issue493-s3-sha256-20261110.json)에 둔다.

## 13. Pod별 모델 로딩 보고 (#370)

### 13.1 요약 (2026-11-09)

3.1.5 후속: scoring의 model.loading.reported 전체 상태 이벤트와 30초 heartbeat를 core가 별도 model_loading_report(V37)에 수집한다. SERVICE_OPS 조회 API와 활성 모델 카드에서 최근 보고 Pod 대비 로딩 완료 수·실패·기존 모델 유지·보고 만료를 구분한다. 전체 Kubernetes replica 수나 품질·추론 승인으로 표현하지 않는다. 설계·배포·검증은 13.2 이하에 둔다.

### 13.2 설계와 범위

최신 develop fb6b08a2에서 시작했다. 필수 선행 #366은 병합됐으며 #368 사전 검사 배포나 AWS 재가동은 필요하지 않다. 운영 AWS를 변경하지 않는다.

| 방식 | 검토 결과 |
| --- | --- |
| scoring → RabbitMQ 결과 이벤트 + heartbeat | 채택. 이미 사용하는 events.topic과 core 소비 구조를 재사용하고 각 프로세스를 식별한다. 발행 장애는 기존 로딩·추론을 막지 않으며 다음 전체 보고로 복구한다. |
| core → scoring Service 단일 조회 | Pod 하나만 확인하므로 전체 상태로 표현할 수 없다. |
| core → Kubernetes API로 Pod 열거·개별 조회 | 정확한 배포 수를 알 수 있지만 새로운 클러스터 권한과 서비스 탐색 결합이 필요해 이번 범위에서 제외한다. |

### 13.3 계약

- 이벤트 `model.loading.reported`, source `scoring-service`, schema v1. Pod명(기본 hostname), 프로세스별 UUID, 단조 증가 sequence, 전체 모델 상태를 보낸다.
- 성공·실패·진행 중에 target name/version/revision과 현재 메모리에 남은 버전/revision을 구분한다. 실패에는 예외 유형만 포함하고 원문·URI·자격 증명은 포함하지 않는다.
- 로딩 중 변경 신호와 30초 heartbeat로 발행한다. 발행은 2초 제한, 단일 태스크이며 실패하면 다음 전체 보고에서 회복한다. 새 로딩 실패 시 기존 모델 유지 동작은 변경하지 않는다.
- core `model_loading_report`(V37)에 프로세스별 최신 전체 상태를 저장한다. 같은 instance의 중복·역순 sequence와 역행 시각은 무시한다. 같은 Pod명은 가장 최근 보고 프로세스만 조회한다.
- `GET /api/v1/admin/model-loading`은 기존 SERVICE_OPS 권한을 요구한다. 상태는 승인·평가 JSONB에 저장하지 않는다.
- 120초 이상 보고가 없으면 stale로 표시하고 성공/실패 집계에서 제외한다. 24시간 지난 기록은 조회에서 제외하고 매시간 정리한다. 축소·비정상 종료·보고 통신 장애는 모두 보고 만료로 표현하며 죽은 Pod라고 단정하지 않는다.
- 화면 분모는 최근 보고된 Pod 수다. 전체 배포 replica 수는 모르므로 전체 배포 성공으로 표시하지 않는다. 아직 보고하지 않은 Pod가 존재할 수 있고 보고 0개는 미확인이다.
- 현재 활성 모델의 name/version/revision이 모두 일치할 때만 완료 수에 포함한다. 과거 버전 보고는 대기 상태로 표시한다. 모델 이외 PROMPT/RUBRIC에는 적용하지 않는다.

### 13.4 배포 순서

V37 migration → RabbitMQ definitions(새 core 큐·재시도·DLQ 바인딩) → core → scoring → web 순서로 반영한다. 기존 라우팅·모델 승인·활성화 계약은 유지한다. 새 공유 큐는 코드에서 선언하지 않는다. 추가 AWS IAM 권한이나 Kubernetes 조회 권한은 없다.

### 13.5 검증

- core: 로딩 상태·인증 4개, 실제 로컬 연동 1개, 기존 모델 HTTP 12개, 관리자 운영 25개로 총 42개 통과. bootJar 통과.
- scoring: 전체 201개 통과. Ruff check·format 통과. #368은 별도 브랜치이므로 해당 브랜치의 사전 검사 테스트 수와 다르다.
- web: 단위 244개, 브라우저 12개(데스크톱·태블릿·휴대폰), 타입 검사·린트·빌드 통과.
- 저장소 계약: 전체 194개 실행에서 큐 개수 1건이 실패해 새 큐 5개와 관리자 조회 allowlist를 반영했다. 해당 계약·새 이벤트·마이그레이션 8개 재검증 통과.
- DB: 격리 PostgreSQL에서 3개 DB 마이그레이션 적용·재적용, report 왕복, ERD 89개 테이블 대조, 무결성 음성 사례 105개, 서비스 역할 6개 분리 검증 통과. 검증용 컨테이너 중지.
- 실제 core HTTP 응답과 두 프로세스의 모델 보고 payload를 OpenAPI·이벤트 JSON Schema에 대조하여 통과.

#### 로컬 2 replica 검증 범위

`ModelLoadingLocalIntegrationTest`는 서로 다른 scoring Python 프로세스 2개를 동시에 실행한다. 합성 로더를 제외한 운영 ModelRegistry·ModelLoadingReporter·EventPublisher → 실제 RabbitMQ → 운영 core consumer → 실제 PostgreSQL → SERVICE_OPS HTTP 조회까지 검증한다. 한쪽은 revision 2 완료, 다른 쪽은 ValueError로 실패하고 revision 1 모델을 유지한다. 실제 M2 가중치 다운로드·추론 및 Kubernetes Pod 기동 검증은 아니다.

이 HTTP 응답을 브라우저 테스트 입력으로 사용하여 2개 중 1개 로딩 완료, 실패 Pod·오류 유형·기존 모델 유지 표시, 3개 화면 크기의 가로 넘침 없음까지 확인했다. 브라우저와 실행 중인 core의 실시간 직접 연결 검증과 구분한다.

재현: scoring Python 의존성이 설치된 환경에서 `MODEL_LOADING_LOCAL=true`, `SCORING_TEST_PYTHON`에 scoring Python 실행 파일을 지정한 뒤 core `test --tests '*ModelLoadingLocalIntegrationTest'` 실행. 이어서 web에서 `MODEL_LOADING_LOCAL=true npm run test:models` 실행한다. 일반 CI 브라우저 테스트는 합성 응답을 사용한다.

### 13.6 이슈 원문 체크리스트

#### 해야 할 일
- [x] 보고 방식 설계: scoring이 로딩 결과 이벤트를 발행하고 core가 모으는 안(추천)과 대안 비교
- [x] scoring: `ModelRegistry.load` 성공·실패 시 Pod 식별자와 함께 보고(실패 시 오류 유형만, 기존 모델 유지 표시)
- [x] core: Pod별 최신 로딩 상태 저장·조회 API
- [x] web: 버전 카드의 "로딩 확인" 단계에 Pod 수 대비 로딩 완료 수, 실패 Pod 표시
- [x] Pod 축소·재시작 시 오래된 기록 처리 규칙

#### 완료 조건
- [x] 레플리카 2개 이상인 local 환경에서 한 Pod 로딩 실패 시 화면에 구분되어 보임을 확인
  - 11/09에는 두 scoring 프로세스와 그 응답을 쓴 브라우저 표시까지만 검증했다. 11/10 kind의 실제 Pod 2개와 관리자 화면 직접 연결로 확인했다(13.9).
- [x] 관련 테스트 통과

#### 유지할 원칙
- 로딩 성공을 품질 승인으로 표시하지 않음. 추론 확인은 자동 판정하지 않음

AWS는 재가동·배포하지 않았다. 기존 운영 이미지와 prod migration digest는 변경하지 않았다. 배포 시 V37이 포함된 migration 이미지를 별도로 반영해야 한다.

### 13.7 최신 develop 병합 충돌 해결 (2026-11-09)

develop `ef18b2ac`(#391·#369 포함)을 병합했다. OpenAPI의 #368 사전 검사와 #370 로딩 상태 스키마, API 명세의 #391·#370 절, ai 보고서의 #368·#370 절을 모두 보존했다. #369가 V36을 사용하므로 아직 병합되지 않은 모델 로딩 상태 마이그레이션만 V37로 변경하고 로컬 migration revision을 v37로 맞췄다. 이미 병합된 V36 파일은 수정하지 않았다.

병합 후 재검증: core 관련 42개(실제 두 scoring 프로세스 연동 포함)·bootJar, scoring 전체 215개·Ruff, 계약 회귀 203개, web 빌드·브라우저 15개, 세 DB 전체 마이그레이션·재적용·report 왕복·ERD 대조·역할 격리 통과. core V36 관리자 인증과 V37 모델 로딩 상태를 동시에 적용했다.

### 13.8 PR #416 core CI 실패 보완

최초 원격 core 전체 검사(585개, 실패 2개)에서 `RabbitDefinitionsTest`가 `model.loading.reported`의 감사 큐 바인딩 누락을 찾았고, `QueueManagementClientTest`는 기존 큐 30개·DLQ 6개 고정값 때문에 실패했다. 앞선 로컬 core 42개 검증에는 두 테스트가 포함되지 않았다.

기존 감사 정책을 유지하도록 `events.topic / model.loading.reported → core.event.audit` 명시적 바인딩을 추가했다. EventAuditConsumer는 기존처럼 이벤트 봉투 메타데이터만 기록하며 모델 상태 본문은 event_log에 저장하지 않는다. 큐 조회 테스트는 버전 관리되는 definitions의 전체 큐·DLQ 수와 실제 브로커 조회 결과를 비교하도록 바꿨다. 기존 allowlist 일치·누락 큐 오류 검증은 유지한다.

수정 후 core 전체 test·bootJar 통과: 585개 중 실패 0개, 조건부 제외 3개. 저장소 계약 회귀 203개 통과.

### 13.9 kind 실제 Pod 2개 확인 (2026-11-10)

1. 12.8의 확인용 모델을 관리자 화면에서 등록·활성화했다. 범위는 실제 채점과 겹치지 않는 `kindcheck/issue-370`이다. 기존 scoring Pod가 `LOADED`를 보고했다
2. MinIO의 `model.safetensors`를 같은 크기의 깨진 파일로 바꾸고 scoring을 레플리카 2로 늘렸다. 새 Pod는 `SafetensorError`로 실패하고 Ready가 되지 않았다
3. `GET /api/v1/admin/model-loading` 응답은 `observedPods 2, loadedPods 1, failedPods [새 Pod]`였다. 관리자 화면 로딩 확인 단계에는 다음이 보였다
   - "최근 보고 Pod 2개 중 로딩 완료 1개"
   - 실패 Pod·오류 유형·"기존 모델 없음"
   - 120초 넘은 이전 Pod의 "보고 만료"

되돌림: 레플리카 1개로 복구했다. MinIO 객체를 지웠다. 확인용 `model_version` 행은 활성화 해제 API가 없어 DB에서 지웠고, 감사 이력은 남겼다. 확인 중 생긴 로딩 보고 행을 지웠다. scoring을 다시 시작해 빈 모델 목록 보고를 확인했다(Deployment에 `restartedAt` annotation 추가).

## 14. 리포트 설명 API (#477, 2026-11-10)

에픽 #473(설명 sLLM)의 ai 몫. report가 대표 답변마다 부르면 M2 항목 점수와 학생 글로 학부모용 설명을 만든다(api-spec 4.2.3, FN-RPT-09). 모델 학습(#475)·서버 배포(#476) 전이라 지금은 설명 모델이 활성이 아니어서 항상 `{active:false}`를 돌려준다.

### API

| 경로 | 요청 | 응답 |
|---|---|---|
| `POST /internal/report-explanations` | `{grade, inputType, text, scores}` | `200 {active:true, explanation:{text, quote\|null}, versions:{model, prompt}}` · `200 {active:false}` · `400`·`422 AI_EXPLANATION_REJECTED`·`503 AI_UNAVAILABLE` |
| `GET /internal/versions` | — | `prompts.reportExplanation` 추가(`report-explanation@1`) |

### 결정과 근거

| 항목 | 결정 | 근거 |
|---|---|---|
| 설명 항목 | 가장 높은 항목(잘한 점) 1개 + 가장 낮은 항목(함께 이야기해 볼 점) 1개, 동점은 항목 표 순서, 모두 같으면 1개. 서술 총점 `hol` 제외 | 학습 데이터(71818) 이유 문장이 항목당 1문장이라 모델도 항목 하나씩 생성. 9항목 전부는 CPU에서 답변당 9회라 길고 느림(사용자 결정 11/10) |
| 인용 구절 | 설명과 낱말 앞 두 글자가 2개 이상 겹치는 학생 글 문장 중 가장 많이 겹치는 것, 없으면 null | 이유 문장에 근거 구절 표시가 없어 모델에게 구절까지 만들게 하면 틀리기 쉬움. 원문 문장을 그대로 잘라 써 부분 문자열 조건을 항상 만족(사용자 결정 11/10) |
| 활성 확인 | 레지스트리 `MODEL` `report-explanation`, scope `explanation/grade-{학년}/{narrative\|essay}`(#480). `ActiveVersions`가 PROMPT와 함께 이 MODEL도 보관(`prompt_versions/models.tracked`) | 기존 활성 목록·`model.version.activated` 수신을 그대로 써 새 구독 없이 승인 범위를 지킴. M2 scope와 같은 모양 |
| 클라이언트 | `create_explanation_llm` → `OpenAICompatibleLlm` 두 번째 인스턴스(`EXPLANATION_BASE_URL`·`EXPLANATION_MODEL`), 재시도 0, `app.state.explanation_llm` | 다른 호출의 `LLM_PROVIDER`는 그대로(닫힌 #341의 리포트 전용 제공자와 달리 OpenAI 호환 주소만 바꿈). 주소가 없으면 `UnconfiguredLlm`이라 설명만 503 |
| 생성 방식 | `LlmClient.stream`의 평문을 모음(JSON 구조화 출력 안 씀), `callType = REPORT_EXPLANATION` | LoRA가 이유 문장 평문으로 학습되므로 JSON 강제는 학습 형식과 다름. 사용량 기록은 기존 스트림 경로 그대로 |
| 후처리·검사 | 숫자나 금지어(분석 대화 `verification.FORBIDDEN`: 레벨·등급·점수·사고력·IQ·상위·하위·뒤처·영재)가 있는 문장을 버리고 항목당 앞 2문장. 남는 문장이 없으면 422 | 전문가 문장에 "4점" 같은 점수 표현이 섞임(`ml/m2/scripts/build_feedback.py` `SCORE_PAT`). 문장 안에서 숫자만 지우면 문장이 깨지므로 문장째 버림. 생성형 AI로 말투를 바꾸지 않음(NFR-DAT-03) |
| 학부모 문장 틀 | `잘한 점: …` / `함께 이야기해 볼 점: …` 줄 | 점수 대신 칭찬과 대화 거리로 전달(D2 규칙 후처리) |
| 시간 | 항목 1회 60초, 요청 마감 125초, 최대 256토큰. 모두 설정값 | CPU 양자화 모델 실측(#475) 전 임시값. 주 1회 배치라 P12 예외 |

### #475 학습 입력 형식 (고정)

```
system: 너는 초등학생 글의 한 평가 항목에 대해 전문가가 쓴 이유 문장을 쓴다. (app/report_explanation/prompts.py SYSTEM)
user:   [학년] 초{학년} [항목] {항목 이름} [점수] {점수}
        {학생 글}
target: 그 항목의 전문가 이유 문장(71818 score.personal.*.feedback 원문)
```

- 항목 이름: 서술 과제 수행·명료성·구체성·적절성·연결성·통일성·어휘·어법(`task_1`·`content_1~3`·`organization_1~2`·`expression_1~2`), 논술 구성·내용·표현(`org`·`cont`·`exp`). 문구를 바꾸면 `PROMPT_VERSION`을 올리고 #475 학습 쌍도 같이 바꾼다
- 확인 필요(#475): 논술 M2는 545 데이터의 `{org,cont,exp}` 0~3점인데 이유 문장은 71819에만 있어 항목 체계가 다르다. 논술 설명 학습 쌍을 만들 때 항목 대응을 정해야 한다

### 검증

- `tests/report_explanation/`(20개): 항목 선택(동점·전부 같음·총점 제외), 후처리(숫자·금지어 문장 버림, 2문장), 문장 틀, 인용(겹침 최대·없으면 null), 활성·미등록·다른 학년·다른 입력 유형·같은 이름 PROMPT는 `{active:false}`이고 sLLM 미호출, 422·503, 사용량 `REPORT_EXPLANATION`, revision 순서·snapshot 전 이벤트 보관, 라우터 camelCase·`{active:false}` 단독·400·401·주소 미설정 503
- `tests/test_versions.py`: `/internal/versions`에 `reportExplanation`
- `scripts/tests/test_ai_openapi.py`: 라우터 8개와 OpenAPI 경로 일치
- 남은 확인: 실제 sLLM 서버(#476)와 학습 모델(#475)로 생성 시간·후처리 통과율 측정. report 연동은 #479(PR #494)에서 완료, 후속 정합화는 #508

## 15. 교육과정 지식 RAG 계약 (#464, 2026-11-11)

에픽 #463 계약 고정의 ai 몫. 구현(#467 임베딩, #470 검색 연결) 전 계약이며 값은 기준안(팀 확인 전)이다. 테이블·샘플·결정 전체는 [learning 28장](learning.md#28-교육과정-지식-rag-계약-고정-464-에픽-463-2026-11-11).

- C6 임베딩([api-spec 4.2.4](../design/api-spec.md#424-지식-임베딩-463-계약-464-c6-구현-467)): `POST /internal/embeddings` `{texts[]}` → `{model, dimensions, vectors[]}`, 1~64개·본문당 8,000자, 502·503. OpenAPI에 `x-implementation-status: planned-issue-467`. 사용량 `callType` 기준안 `KNOWLEDGE_EMBEDDING`은 core 목록과 함께 #467에서(이번에는 목록 그대로)
- C7 근거 칸([api-spec 4.2.5](../design/api-spec.md#425-미션-초안-근거-칸-463-계약-464-c7-구현-470)): 미션 초안 요청 `knowledge`(C5 standards 응답 그대로, 선택), 응답 `sources`(근거 조각 표시, 빈 배열 허용). OpenAPI 칸에 `planned-issue-470`. `mission_draft/models.py`는 바꾸지 않았다(#470)
- `app/knowledge/contracts.py`: C5·C6·C7 pydantic 모델, `KnowledgeApi`·`Embedder`·`KnowledgeRetriever` Protocol, `RetrievalResult`(근거 없음은 예외 대신 `fallback` 사유), `sources_of`
- `app/knowledge/fake.py`: 표준 라이브러리만 쓰는 가짜(계약 시험이 pydantic 없이 불러 씀). 샘플을 활성 판 하나로 올린 `FakeKnowledgeApi`(다섯 경로, 인증·400·409 포함), 글자 2개 조각 해시 벡터 `FakeEmbedder`(모델 `fake-bigram-v1`, 같은 글 같은 벡터), `as_knowledge_api()`·`as_embedder()`(Protocol 만족), `mock_transport()`(httpx), `serve()`(로컬 HTTP)
- 검증: `tests/knowledge/test_contracts.py` 29개(모델 칸·필수 = OpenAPI, 사유·상한 = OpenAPI·가짜, Protocol 통해 응답, MockTransport·HTTP 서버), `scripts/tests/test_knowledge_contracts.py`(learning 28장). `test_ai_openapi.py`는 구현 전 표시 경로를 라우터 대조에서 뺌(라우터 8개 그대로)

## 16. 주간 테마 초안 생성 (#437)

에픽 #436의 ai 몫. 계약은 api-spec 4.2 `POST /internal/theme-drafts`, 구조는 class-diagram 5.5, learning 쪽 작업·저장은 #438. 이 절은 설계 단계 기록이며 구현·실측 결과는 이어서 덧붙인다.

### 16.1 정한 내용

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 호출 단위 | 요청 1번에 그래프 1회 실행. 그래프 안에서 실패한 부분만 실패 사유를 넣어 상한(기준안 단계마다 2회)까지 다시 만들고, 마감까지 남은 시간이 부족하면 다음 재생성을 시작하지 않음. 그래도 실패하면 learning이 다시 부름 | 에픽 "ai 1회(그래프 안에서 노드별 재시도)". 미션 초안(9장)은 반복을 learning에 뒀지만 테마는 단계가 많아 실패한 부분만 다시 만드는 편이 비용·시간이 적음. 텍스트 시험에서 길이 1~4자 초과·줄 수·금지어 실수처럼 다시 만들면 고쳐질 실패가 많았음(사용자 결정 2026-11-10). 상한을 다 쓰면 최악 약 24분이라 15분 마감 안에서 멈추는 조건이 필요 |
| 요청 | 학년(`gradeMin = gradeMax`), 적용 주, 선택 주제, 유형 5개의 성취기준·표준 요소 code·입력 방식, 이전 실패 사유(`previousFailures`) | #437 요청 항목. 학년별 테마(`G3`~`G6`)는 #438 담당자 결정(2026-11-10)이며 ai 계약은 학년 범위 형식 그대로라 바뀌지 않음. `previousFailures`(이전 시도들의 `failure{stage, reasons}` 그대로)는 미션 초안 계약과 같은 방식으로 추가(사용자 결정) |
| 요일 배치 | ai가 줄거리 단계에서 기준안(월 `ANALYZE`·화 `EVALUATE`·수 `CREATE`·목 `SOLVE`·금 `REFLECT`)대로 정해 응답 `day`로 돌려주고 learning이 다시 검사 | #437 응답 "미션 5개(유형·요일)", #438 "learning 검사: 요일 배치", 에픽 배치 기준안(확인 필요) |
| 응답 | 테마 틀(제목·세계관·등장인물·그림 스타일 메모·테마 옷·시작/종료 이야기·큰 질문·후보·정답·요일별 장면과 단서·`rulesOut`), 미션 5개(미션 초안 `draft`와 같은 모양), 대화 5개, 장면 7개의 이미지·움직임, 시작·종료 영상 2개, 경고, 실패, 버전 | #437 응답 항목, 에픽 테마 틀 항목. 요일 영상은 없음(아래 영상 행, 사용자 결정 2026-11-11) |
| 실패 | 끝내 실패하면 200 + `failure{stage, reasons}`(`THEME`·`MISSION`·`REVIEW`·`IMAGE`), learning `CHECK_FAILED`. 대화·영상·움직임은 끝내 실패해도 그 항목만 빼고 성공 + `warnings`. 형식 밖 응답 502, 그 밖 실패·마감 초과 503(learning `FAILED`) | #437 "실패 시 실패 단계·사유", "끝내 실패하면 그 장면만 영상 없이", 미션 초안의 200 + 검사 실패 방식 |
| 정답 구조 | 후보 기준안 모든 학년 4개. 요일별 단서 5개마다 `rulesOut`(빈 배열 허용, 그때 남은 후보를 하나도 빼지 않는 힌트 단서). 정답은 어떤 단서로도 빠지지 않고 틀린 후보는 각각 적어도 한 번 빠지며, 마지막 틀린 후보는 목요일 이후 단서에서 빠짐(기준안). 정답 논리는 코드 검사, 정답은 종료 이야기에만 | #437 큰 질문·정답 항목. 후보보다 단서가 많아 빈 `rulesOut`을 허용(사용자 결정 2026-11-10). 후보 수는 초3·초4 3개 기준안에서 모든 학년 4개로 바꿈(사용자 결정 2026-11-10): 표로 엄격히 따지면 후보를 하나라도 빼는 단서는 힌트가 아니라 빼기라서, 후보 3개면 수요일까지 2개 이상 남기려면 월~수에 1개만 뺄 수 있고 나머지 월~수 단서는 남은 후보 모두에 맞는 밋밋한 말이 됨. 후보 4개 시험에서 단서가 가장 자연스러웠음. 목요일 이후 조건은 금요일 최종 고르기 전에 답이 정해지지 않게 하려는 기준안 |
| 검토 모델 | 생성과 다른 모델(기준안 생성 `gpt-6-luna`, 검토 `gpt-6.1-terra`). 테마 전용 설정 `THEME_GENERATION_MODEL`·`THEME_REVIEW_MODEL`로 두고 기본 `OPENAI_MODEL`과 따로 씀. 두 값이 같거나 OpenAI 키가 없으면 테마 경로만 `503 AI_UNAVAILABLE`(`retryable: false`), 서비스 기동과 다른 경로는 막지 않음 | 이슈의 "다른 제공자"는 팀 운영 키가 OpenAI뿐이라 지금은 같은 제공자의 다른 모델로 함(사용자 결정 2026-11-10). 운영에서 쓸 수 없는 제공자로 시험하면 결과가 운영과 달라짐. 팀 키가 생기면 설정만 바꿔 다른 제공자로. 로컬·운영 `OPENAI_MODEL`이 `gpt-6.1-terra`라 기본 LLM 설정을 그대로 쓰면 생성·검토가 같은 모델이 되어 테마 전용 설정을 둠. 16.3에 "시작할 때 막음"으로 적었던 것을 테마 경로 503으로 바꿈: 기동을 막으면 판정·되묻기 같은 다른 경로까지 멈추기 때문(사용자 결정 2026-11-10) |
| 단서 규칙 | 단서는 그날 장면의 이야기 속 사실로, 문제 활동 결과에서 만들지 않음. 잠김·시각은 사건 전부터 계속, 같은 종류 반복 금지, 후보 이름에 색 낱말 금지, 큰 질문·제목·월~목 장면에 정답 이름 금지. 단서 길이 기준안 40자(학생이 그날 미션을 마친 뒤 한 줄 글로 봄) | 2026-11-10 텍스트 시험(초3 1학기)에서 실패한 유형. 시험 코드가 단서를 문제 활동 결과(수요일 계산값 등)에서 끌어내게 해 논리 빈틈과 장면 반복("목줄·기둥")이 생겼음. 이슈 설계(단서는 대화·장면)로 되돌림. 처음에는 단서를 대화 한 줄로 전해서 40자로 정했고, 단서를 미션 뒤 공개로 바꾼 뒤(사용자 결정 2026-11-11, 아래 단서 공개 행)에도 한 줄 글 길이로 그대로 둠 |
| 단서 논리 판정 | 줄거리가 후보 특징 표(`features`: 특징 이름·후보별 값)와 요일별 단서 조건(`condition`: `RULE`·`HINT`, 특징, 허용 값)을 내부 칸으로 함께 생성하고(응답에서는 뺌), 정답 논리는 코드가 표로 판정. 요일별 `rulesOut`은 LLM이 쓰지 않고 코드가 표와 조건으로 채움(`RULE`은 허용 값 밖 후보 전부(이미 빠진 후보 포함), `HINT`는 빈 배열). `RULE`은 빠지는 후보가 비어 있지 않음, `HINT`는 그때 남은 후보가 모두 허용 값 안(남은 후보를 빼면 `RULE`이어야 함), `RULE`은 그때 남은 후보를 적어도 하나 새로 뺌(이미 빠진 후보만 빼면 `HINT`, learning이 결정적 단서를 "`rulesOut`이 비지 않은 마지막 요일"로 계산하므로, #438), 틀린 후보는 모두 `RULE`로 빠짐, 수요일까지 후보 2개 이상 남음, 정답은 안 빠짐. 단서 문장에는 허용 값 낱말이 모두 들어가고(활용형·숫자 표기 차이 허용) 허용 밖 값 낱말은 없어야 함. 특징마다 고른 성취기준 코드 `standardCode`(장면에서 골랐으면 비움, 이번 주 성취기준만), 단서마다 증거 칸 `evidence{kind: TRACE·SIGHTING·RECORD, when}`(못 찾은 대상 몸의 자국 같은 종류는 고를 수 없음, 다섯 단서가 같은 그때를 가리킴), 찾는 대상 `target`(대화·미션에서 말하거나 지금 있는 것처럼 나오지 않음, 코드로 대화 화자 검사). 특징은 그날 성취기준 내용에서 고르는 것을 기본으로(안 되면 장면). 검토 LLM은 단서 문장이 조건을 그대로 말하는지·표 값이 자연스러운지·없음에만 기대지 않는지·`HINT`가 일찍 답을 정하지 않는지를 봄 | 텍스트 시험(검토까지 간 9회 모두 탈락)의 검토 탈락 대부분이 단서 논리 빈틈("문이 잠겼어도 창문으로", "~전부터 잠김이면 그 뒤는?")이었음. LLM이 문장과 논리를 한 번에 쓰고 검토 LLM이 사후에 판정하는 구조라 빈틈이 반복됨. LLM 추리 이야기 생성 연구는 논리 구조를 먼저 만들고 기계로 검증한 뒤 글을 씀(MuSR arXiv 2310.16049, EnigmaForge arXiv 2609.30144). 특징을 성취기준 내용에서 고르면 단서도 그날 학습과 이어지고 테마마다 달라져 반복이 줄어듦(사용자 결정 2026-11-10). 실측 보완(2026-11-10): "월~수 HINT는 남은 후보 2개 이상"만 보던 첫 규칙은 HINT가 남은 후보를 빼는 경우를 놓쳐 화요일에 답이 정해짐(lab3-inventor-6). 저장된 실제 결과를 다시 넣어 보니 HINT 82개 중 39개가 이 결함이었고 검토 LLM이 대부분 통과시켰음 → 코드 검사로 막음. 단서 문장이 조건보다 좁게 쓰여(조건 모래·나무, 문장 "나무판") 표보다 일찍 답이 정해진 사례(lab3-beach5-1) → 글자 비교. 특징 출처·증거 칸·근거 빈 칸은 RAG(#470)가 붙을 자리. 계약(응답 `days`)은 그대로 |
| 단서 공개·증거 발견 | 단서(`days[].clue`)는 학생이 그날 미션을 마친 뒤 learning이 학생별로 보여 줌(#484 몫). 줄거리가 요일마다 내부 칸 두 개를 함께 만듦(응답 `theme`에는 넣지 않음): `discovery`(미션 전 대화 마지막 줄로 코드가 그대로 넣는 증거 발견 한 줄, 40자 이내, 뭉치가 말함, 그날 증거 종류 `TRACE`·`SIGHTING`·`RECORD`에 맞는 물건·목격자·기록을 찾았다는 말만)와 `missionHook`(증거 발견 줄 바로 다음, 미션 전 대화 맨 끝에 코드가 그대로 넣는 뭉치의 수사 연결 문장, 40자 이내, 오늘 배울 것이 왜 필요한지만 말하고 도움을 청함, 증거를 살펴보라고 하지 않음). 둘 다 후보·정답을 말하지 않고(`ANSWER_LEAK`), 증거 발견 줄은 그날 단서 결론(허용 값)도 말하지 않음(`CLUE_EARLY`). 수사 연결 문장은 배울 개념을 말하는 자리라 허용 값 낱말이 개념 이름과 겹칠 수 있어 `CLUE_EARLY`를 보지 않고 글 검토가 봄. 허용 값 비교는 정확히 일치하거나, 명사형 끝(음함림름움색)을 뗀 줄기가 2자 이상일 때만 줄기 일치(대화 검사도 같은 함수) | 사용자 결정 2026-11-11. 미션이 열쇠 찾기(사건)와 따로 놀아 "미션을 마쳐야 단서를 얻는" 구조로 바꿈. 단서는 미션의 정답이 아니라 완료 기준으로 주므로 답이 하나로 정해지지 않는 서술형 미션과도 맞음. 증거 발견 줄 → 수사 연결 문장(대화 끝 두 줄) → 미션 → 미션 뒤 단서로 하루가 한 수사 흐름이 됨. 수사 연결 문장을 미션 질문 첫머리에서 대화 맨 끝으로 옮긴 것은 사용자 결정 2026-11-11: 실측 3회차(repo-*-3)에서 질문 앞에 붙은 문장 때문에 질문 길이 초과(`QUESTION_LENGTH`)·미션 검토 `MATERIAL`(증거를 살피라는데 문제 글에 자료 없음)·단서 값 겹침(`CLUE_EARLY`)으로 실패했고, 화면에서 대화 바로 다음이 미션이라 흐름은 같음. 1자 줄기(젖음→젖, 좁음→좁)는 오탐이 많아 줄기 비교에서 뺌. 놓친 날 대응은 learning·웹 단서 수첩으로(#484·#440) |
| 뭉치 역할·콘티 | 뭉치는 물건을 잃은 당사자가 아니라 테마 역할(예: 꼬마 탐정단·구조대·안전 순찰대·숲 탐험대)로 사건 현장에 해결하러 가는 주인공이고, 찾는 대상의 주인은 등장인물 중 한 명. 테마 옷(`outfit`)은 그 역할 차림(실제 제복·휘장 금지 규칙 유지). 시작 콘티 4컷: 1 사건 장소의 평소 모습과 주인 인물(대상을 지니거나 쓰는 모습 가능, 둔 곳은 안 보임)·2 사건(주인이 대상이 사라진 걸 알아채고 당황)에는 뭉치가 나오지 않고, 3 뭉치 출동(테마 차림으로 혼자 현장으로 달려감)·4 현장 도착(뭉치와 인물들이 모여 큰 질문). 종료 콘티 4컷: 1 뭉치가 모은 단서 정리, 2 정답 장소로 감, 3 정답 장소에서 찾아 주인에게 돌려줌, 4 함께 기뻐함. 컷마다 내부 칸 `mungchiMood`(그 컷 끝 뭉치 표정 `none`·`smile`·`surprised`·`determined`, 입 모양으로만: 웃는 입·작은 o 입·다문 일자 입, 뭉치가 안 나오면 `none`). 코드 검사 `CUT_MOOD`: 시작 1·2컷은 `none`, 3·4컷은 `none`이 아님. 시작 콘티에 정답 이름·정답 장소 금지는 그대로 | 사용자 결정 2026-11-11 |
| 미션 생성 | 유형마다 미션 초안 생성·검사(9장)를 재사용하고 테마 이야기 조각과 학년별 생각 열기 질문 개수, 찾는 대상 이름(아직 못 찾음, 정답은 주지 않음)을 더함. 미션 요청·미션 검토에는 RAG 근거를 넣을 빈 칸(`knowledge`, 지금은 비움)을 둠. 그날 장면과 그날 찾은 증거(장소·인물·물건·목격·기록)를 문제 소재로 써도 되고, 정답 쓰기·정답 추리 문제·새 사건 사실·미션 답이 단서가 되는 것은 금지. 미션 입력에는 그날 단서도 앞 요일 단서 목록도 넣지 않고 그날 `discovery`·`missionHook`을 넣되 둘 다 대화로 이미 나가므로 질문에 다시 쓰지 않고, 질문이 증거 자체를 살피게 하지 않으며(문제 글에 증거 자료가 없음) 어느 후보가 답인지 묻지 않음. 금요일도 큰 질문·후보·단서 목록을 넣지 않고 안내(`guide`)는 LLM이 만든 그대로(코드가 단서 5개를 넣던 것을 없앰). 최종 후보 고르기는 웹·learning 화면 몫 | #437 그래프. 텍스트 시험에서 미션 생성기를 쓰지 않아 요소(유형 × 성취기준 연결)가 빠졌던 문제를 막음. 사건 자료를 문제에 못 쓰게 막았던 시험에서는 미션이 이야기와 따로 놀아 학습지처럼 됨(강아지 찾기 주에 "오리·낙타 생김새"). 이슈가 막는 것은 활동 결과로 단서 만들기와 정답 유출뿐이라 사건 자료 사용을 허용(사용자 결정 2026-11-10). 비교·점검할 글이 필요한 문제(예: 금요일 돌아보기)는 그 글을 문제 글에 직접 넣음(시험에서 "처음 글과 고친 글을 비교하라"면서 글을 주지 않음, "그날 글만 읽고 풀 수 있어야 함" 위반). 미션 입력에서 단서를 빼고 수사 연결 문장을 넣은 것은 사용자 결정 2026-11-11: 단서는 학생이 그날 미션을 마친 뒤에 얻으므로 그날·앞 요일 단서를 주면 아직 못 얻은 단서가 미션 글로 샐 수 있고, 수사 연결 문장(대화 맨 끝 줄)이 미션을 열쇠 찾기와 이어 줌. 금요일 안내의 단서 5개는 놓친 날 대응이었는데 그 몫을 learning·웹 단서 수첩으로 옮김 |
| 미션 검토 | 새 노드 `review_missions`(`generate_mission`과 코드 검사·실패 유형 재생성 다음, `generate_dialogue` 앞). 검토 모델이 미션마다 따로 병렬로 예시 답(또는 정답 키)이 문제 요구를 모두 채우는지, 성취기준 핵심 행동·생각 유형과 맞는지(혼자 글로 답하는 미션이라 협력·발표는 보지 않음), 그날 글만 읽고 풀 수 있는지(그림에만 있는 정보·비교할 글이 빠진 문제 금지) 확인. `FAIL`은 그 미션만 사유를 넣어 다시 생성(상한 기준안 2회), 끝내 실패하면 `failure.stage = MISSION`, `WARN`은 `warnings`. 최종 `review_story`는 지금처럼 전체 | 텍스트 시험(2026-11-10, lab3-reporter-2·lab3-inventor-2)에서 검토 1·2회차가 단서 논리로 줄거리를 통째로 다시 만들며 미션도 새로 생겨, 예시 답이 문제 요구를 못 채우는 문제가 검토 상한(3회) 마지막에야 드러나 고칠 기회가 없었음. 미션 단계에서 고치면 줄거리를 다시 만들어도 새 미션이 같은 검사를 거침(사용자 결정 2026-11-10). 비용 기준안 미션당 약 $0.003 |
| 대화 | 그날 증거 발견 줄(`discovery`)과 수사 연결 문장(`missionHook`, 뭉치)을 코드가 대화 끝 두 줄로 그대로 넣음(증거 발견 줄 말하는 사람 `discoverySpeaker`는 LLM이 고르고 기본 뭉치, 뭉치나 등장인물만). LLM은 나머지 줄만 만들고 그날 단서는 받지 않음. 화~금 앞 요일 요약 줄(`recap`)은 없앰. LLM 줄이 그날 허용 값을 말하면 `CLUE_EARLY`, 증거 발견 줄·수사 연결 문장을 미리 말하면 `DISCOVERY_REPEATED`. 학년별 줄 수(끝 두 줄 포함)는 초3·초4 3~4줄, 초5·초6 2~3줄(LLM 줄 초3·초4 1~2줄, 초5·초6 0~1줄, 기준안) | 처음 설계(사용자 결정 2026-11-10)는 그날 단서 문장을 대화 한 줄로 그대로 넣었음: 텍스트 시험에서 대화가 단서를 바꿔 말하며 빠져나갈 길을 막는 말("하나뿐인")을 빠뜨리거나 40자를 넘김(lab2-rescue-11, lab2-reporter-4). 검사를 거친 글을 그대로 넣는 방식은 증거 발견 줄에도 그대로 씀. 단서 대신 증거 발견 줄을 넣고 요약 줄을 뺀 것은 사용자 결정 2026-11-11: 단서가 미션 뒤 공개로 바뀌어 대화에 넣을 수 없고, 요약 줄은 학생이 아직 못 얻은 단서(몰아서 풀거나 놓친 날)를 흘림. 놓친 날 대응은 learning·웹 단서 수첩으로. 줄 수를 한 줄씩 늘린 것은 수사 연결 문장이 대화로 들어와도 LLM 줄 수를 그대로 두려고(사용자 결정 2026-11-11) |
| 저장 | 이미지·영상은 ai가 S3 `theme-drafts/{실행 ID}/{장면}`에 올리고 키만 반환. 실행 ID는 ai가 만듦 | 에픽 "ai가 S3에 올리고 키 반환", 요청에 learning 초안 ID를 넣지 않아도 되게(사용자 결정). 버킷·쓰기 권한은 인프라 확인 |
| 시간 | ai 마감 15분, learning→ai 대기 16분, 리스 18분(기준안). 그래프 안 기준안: LLM 호출 타임아웃 300초(2026-11-11 180초에서 변경)·재시도 0, 단계마다 다시 생성 상한 2(첫 생성 포함 최대 3회), 글 검토 재검토 상한 2, 마감까지 180초 미만 남으면 다음 다시 생성을 시작하지 않음, 최대 출력 토큰 줄거리·검토 32000·대화 8000 | 에픽 기준안 9분·10분·12분에서 변경. 텍스트 시험 1회 2~8분(재시도 포함), 그림 7장 동시 약 40초, 영상 7개 동시 약 1~2분, 검토 포함. 비동기 주기 작업이라 기다리는 사람이 없음. 구현 뒤 실측으로 다시 조정. 그래프 안 값(사용자 결정 2026-11-10): 텍스트 시험에서 줄거리·검토 한 번이 길게는 2분 넘게 걸려 타임아웃 180초, 실패는 같은 요청 재시도보다 사유를 넣어 다시 만드는 편이 고쳐져 재시도 0, 줄거리 출력이 시험 최대 약 11,500토큰이라 32000, 다시 생성 한 번이 길게는 3분이라 남은 시간 180초. 그림·영상을 붙여도 15분을 유지하고, 남은 시간이 모자라면 영상(선택 항목)부터 건너뛰고 경고를 남김. 글 단계만 실측 3~14분이라 실측 뒤 마감(learning 대기 포함)을 다시 정함(사용자 결정 2026-11-11). 타임아웃 300초: 줄거리 출력 칸이 늘어 1회 130~170초(출력 약 1만 토큰)가 되면서 180초에서 시간 초과(실측 repo-fair4-4, 2026-11-11) |
| 그림 | OpenAI `gpt-image-2.6-sunburst`, 1536×864(16:9 바로 생성), quality medium, 장당 약 $0.03(설명 글만)~$0.05(참조 그림 포함, 2026-11-11 실측 $0.04~0.054). 테마 옷 뭉치 1장 + 미션 그림 5장(`MON`~`FRI`) + 시작·종료 영상 컷 첫 그림 8장 = 14장(테마당 약 $0.7). 응답 `images`의 `INTRO`·`OUTRO`는 각 영상 4번째 컷 첫 그림. 테마 옷 뭉치 → 시작 1컷 첫 그림(인물 기준 그림) → 나머지 12장(테마 옷 뭉치·인물 기준 그림 참조, 동시) 순. 미션 그림 지시문에는 그날 장면 메모와 함께 그날 미션 질문·생각 열기 질문·증거 발견 줄(한국어 그대로)을 넣어 질문과 증거가 가리키는 물건이 보이게 함. 검토 모델이 그림을 보고 뭉치 모양·정답 노출·글자·안전·장면 일치(`SCENE_FIT`)와 미션 그림이면 미션 맞음(`MISSION_FIT`)을 확인해 실패한 그림만 다시(상한), 미션 그림이 끝내 실패하면 `failure IMAGE`, 컷 첫 그림만 실패하면 그 영상만 빼고 경고. 찾는 대상은 시작 1컷(주인이 지닌 모습)과 종료 3·4컷에서만 그리고, 생각 풍선은 그리지 않음 (구현 16.5) | 사용자 결정 2026-11-10. 예전 실험에서 스타일·뭉치 모습·Veo 시작·끝 고정용 그림까지 검증한 모델(모습 일치 0.96~0.99). 팀 OpenAI 키를 그대로 써서 새 인증 불필요. 1536×864는 공식 크기 조건(16의 배수, 비율 1:3~3:1) 안. 참조 그림 실측(2026-11-10, 초4 과학 축제 장면 3개): 설명 글만도 인물을 알아볼 수 있으나 머리 길이·비율이 장면마다 달라지고, 참조 그림을 넣으면 얼굴·비율·크기가 거의 같아짐(영상이 앞·뒤 그림을 이을 때 인물 변형을 줄임). 참조 그림은 구도가 첫 장면을 닮아 가는 경향이 있어 인물 설정 그림을 따로 만드는 방식은 구현 때 비교. 같은 실측에서 "열쇠를 두는 모습을 떠올려" 장면 메모로 두 방식 모두 생각 풍선에 열쇠 둔 곳을 그려 정답이 드러날 뻔함 |
| 영상 | Google Cloud Agent Platform `veo-3.1-fast-generate-001`(사용자 결정 2026-11-10, 예전 실험 모델), 720p·무음. **시작·종료 영상만**(요일 문제 전 영상 없음). 장면마다 컷 4개(4·6·8·6초)를 **컷 첫 그림만 고정**해 동시에 만들고 0.5초씩 겹쳐 녹아드는 전환으로 이어 22.5초 한 파일로 만듦(`imageio-ffmpeg`, libx264). 컷마다 장소·각도를 다르게 함. 시작은 평소 모습과 주인 → 사건(사라짐) → 뭉치 출동 → 현장 도착(큰 질문), 종료는 단서 정리 → 정답 장소 → 발견해 주인에게 돌려줌 → 축하(순서는 사용자 결정 2026-11-11, 위 뭉치 역할·콘티 행). 컷마다 동작 하나, 시작 영상은 정답 장소를 보여 주지 않음. 영상 속 글자 없음, 컷 문구는 움직임 JSON `captions`로 웹이 띄움. 설정이 꺼져 있거나 마감이 가까우면 건너뛰고 `warnings(VIDEO)` | 첫 그림만 고정(사용자 결정, 실측 2026-11-11): 예전 시험에서 시작·끝 고정이 캐릭터 모양을 유지했으나(SSIM 0.99), 콘티 컷에 둘 다 고정하니 비슷한 두 그림 사이를 억지로 이어 움직임이 흐물거리고 배경이 같아짐. 첫 그림만 고정하고 컷마다 장소·각도를 바꾸니 자연스러움. 컷 길이를 4·6·8·6초로 나누고 녹아드는 전환으로 이어 장면 바뀜이 부드러움. 빠른 모델 유지(표준 모델은 약 5배 비용). 요일 영상을 뺀 근거(사용자 결정 2026-11-11): 매일 같은 길이 영상이 문제 앞 기다림이 되고, 수수께끼 게임처럼 영상은 시작·엔딩 같은 큰 순간에만 쓰는 편이 효과가 큼, 문제 뒤 결과 영상은 답이 학생마다 달라 맞지 않음, 같은 비용을 시작·종료 이야기에 모음. 문구를 영상에 새기지 않는 근거: 관리자가 이야기 글을 고치면 영상 글자와 달라지고 글자 크기 설정(#431)·화면 읽기가 안 됨. 2D 첫 컷 실측(2026-11-11)에서 선 흔들림 거의 없음 |
| 그림체·뭉치 | 2D 만화풍. 뭉치는 앱 솜뭉치 모양(크림색 몽글몽글한 몸·굵은 갈색 외곽선·몸 아래쪽 가운데 얼굴·갈색 짧은 발, 몸 앞 아래쪽 좌우에 작은 손)으로 만든 **기본 뭉치 그림**(`assets/`, 기준안)을 고정 참조로 쓰고, 테마마다 그 그림을 고쳐 테마 옷만 더한 뒤(손에 소품 없음, 몸·얼굴·눈·볼·발·손 위치·크기·색·배경은 그대로) 모든 그림의 첫 참조로 넣음 | 사용자 결정 2026-11-11. 차림마다 따로 그리면 크기·얼굴 위치가 달라졌고(실측), 기본 그림을 고치면 같게 유지됨. 원본 솜뭉치 그림이 저장되면 기본 그림을 다시 만듦 |
| 움직임 | 장면마다 JSON(형식 v1): `transition{kind, seconds}`, `camera{from, to, seconds}`, `speakers{이름: {x, y, zoom}}`(대화 줄마다 화자로 카메라 이동, 요일 장면), `effects[{shape, color, count, size, direction, speed, opacity}]`(최대 2층), `captions[{start, end, text}]`(시작·종료 영상 문구). 좌표는 그림 너비·높이 %(생각 열기 위치와 같은 기준). 화자 위치는 생성 모델이 그림을 보고 정함. 상한(기준안): 확대 1.0~1.4, 카메라 8~20초, 전환 0.3~1.2초, 효과 층당 20개·크기 1~6·속도 2~20·불투명도 0.2~0.8, 문구 30자. 밝기를 바꾸는 칸이 없어 깜빡임이 생기지 않음. 상한 밖 숫자는 코드가 맞추고 `warnings(MOTION)`. 문제 화면은 효과층만, 카메라·화자 초점은 시작·종료와 문제 전 대화 화면에서(웹 #440 기준안) | 이슈 "카메라 이동·대화 줄마다 인물로 이동·화면 전환·효과층". 화자 이름 기준이라 관리자가 대화를 고쳐도 어긋나지 않음(물건 초점은 뺌). learning은 받은 JSON을 그대로 저장(`ThemeMotion` 자유 JSON)해 계약 변경 없음. 이슈의 "실패한 장면만 다시 생성"을 코드 보정으로 바꿈(정해진 처리라 다시 생성할 이유가 없음) |
| 영상 인증 | AWS에서 도는 ai의 Google Cloud 인증은 Workload Identity Federation(기준안), 안 되면 서비스 계정 키를 AWS Secrets Manager → Secret 주입 | 오래 쓰는 키 파일을 두지 않기 위해. 인프라 확인 |
| 프롬프트 | 내장 `theme-draft@1`(생성·검토 묶음), 레지스트리 이름 `themeDraft`·scope `ai/theme-draft` | 7절 규칙. core에 프롬프트 이름 목록이 없어 core 변경 없음 |
| 사용량 | `THEME_DRAFT`(글 생성·검토)·`THEME_IMAGE`·`THEME_VIDEO`. `THEME_VIDEO`는 사용량 이벤트 스키마(`llm.usage.recorded.v1`의 `callType` enum)와 core enum·DB 제약에 먼저 들어간 뒤에만 보냄 | core DB 제약 때문에 core 마이그레이션이 필요(core 담당이 준비, 2026-11-10 회신). 먼저 보내면 core 소비자가 거부해 DLQ에 남음(`MISSION_DRAFT` 선례, 9장) |
| 지식 검색 | `retrieve` 노드·범위 확인 자리만 두고 기능 스위치(기본 꺼짐) | 지식 RAG 에픽 #463, 검색 연결 #470 |
| 버전 응답 | `versions{prompt, model}`만 | 미션 초안과 같은 모양. 모델별 비용은 사용량 이벤트의 모델로 추적(사용자 결정) |

### 16.2 API 변경

- 새 경로 `POST /internal/theme-drafts`(api-spec 4.2). OpenAPI(`contracts/openapi/ai-service.yaml`)와 경로 대조 시험(`scripts/tests/test_ai_openapi.py`, 8 → 9개. develop에 리포트 설명 경로 #477이 먼저 들어와 8에서 시작)은 라우터와 같은 커밋에 넣는다(시험이 실제 라우터와 문서 경로를 대조하므로). OpenAPI 스키마는 FastAPI가 모델에서 뽑은 것을 기준으로 옮기고 미션 초안 스키마(`MissionDraftStandard`·`MissionDraftElementCode`·`MissionDraftDraft`)를 재사용
- 요청 검사(400 `VALIDATION_FAILED`): `gradeMin` = `gradeMax`(학년별 테마), `missions`는 생각 유형 5개에 1개씩, 논술은 초5~6, `previousFailures[].reasons`는 1개 이상
- 응답: 줄거리 단계에서 끝내 실패하면 쓸 수 있는 테마가 없어 `theme`은 `null`(+ `failure.stage = THEME`). `warnings[].stage`는 `THEME`·`MISSION`·`DIALOGUE`·`REVIEW`·`IMAGE`·`VIDEO`·`MOTION`(끝내 실패해도 그 항목만 빼는 단계 포함). `motions` 값 형식은 움직임 단계에서 확정(지금은 JSON 객체)
- 테마 모델 설정이 틀리면(검토 모델 = 생성 모델, OpenAI 키 없음) `503 AI_UNAVAILABLE`(`retryable: false`, 다시 불러도 같음, `detail`에 이유). 1단계(경로 뼈대)의 "그래프가 붙기 전 503"을 이것으로 바꿈
- 요청 `previousFailures[].stage`는 `THEME`·`MISSION`·`REVIEW`·`IMAGE` 네 값만 받는다(그 밖 422, 사용자 결정 2026-11-10, #438과 맞춤). learning 검사 실패는 요일·유형 배치·정답 논리면 `THEME`, 미션 게시 규칙(`ELEMENT_CODE`·`STANDARD_CODE`·`SHAPE` 등)이면 `MISSION`으로 바꿔 넣고, AI 호출 실패(502·503·대기 초과·서킷)는 넣지 않는다(learning `check_results`에는 `AI_CALL`로 남음). `reasons`는 `MISSION`이면 `"<요일> <검사 코드> <자세히>"`(요일 `MON`~`FRI`)로 시작해 ai가 그 요일 미션 재생성에만 넣고, 그 밖은 `"<검사 코드> <자세히>"`. 근거: 응답 `failure.stage`와 같은 값이라 learning이 받은 값을 그대로 돌려줌(api-spec 4.2 "이전 시도들의 failure를 그대로"), ai가 다시 만들 곳을 stage로 바로 정함, AI 호출 실패는 고칠 내용이 없음(미션 초안은 `AI_CALL`을 "형식에 맞게 다시 만든다"로만 바꿈), 정해진 값이라 잘못된 값이 422로 드러남. 미션 초안 선례(자유 문자열, `AI_CALL` 포함)와 다름
- `GET /internal/versions` 응답에 `themeDraft` 추가(core에 읽는 코드 없음)

### 16.3 남은 확인

- 요일↔유형 배치(에픽 확인 필요), 후보 수·`rulesOut` 형식과 "마지막 틀린 후보는 목요일 이후" 기준안(P23 개정 필요)
- 영상 운영 인증·예산(Veo 3.1 Fast 무음 720p 초당 약 $0.08은 제3자 자료 기준, 공식 가격·청구로 확인 필요. 시작·종료 각 컷 합 24초(4·6·8·6초, 이은 영상은 22.5초), 테마당 48초면 약 $3.8로 테마 비용 대부분. 2026-11-11 실측 청구로 확인 필요), 다른 제공자 검토용 팀 키(생기면 검토 설정만 바꿈)
- 금요일 최종 고르기와 정답 공개 시점: 정함(#483 팀 결정 2026-11-10). 금요일 문제 끝에 후보 고르기, 맞히면 바로 엔딩(종료 이야기·`OUTRO` 영상), 틀리면 토요일 다시 풀기를 마친 뒤 엔딩. 종료 이야기는 정답을 밝히는 한 가지로 두고 맞힘·틀림 문구는 화면(#440·#487). ai 응답 계약 변화 없음, 판정·엔딩 상태는 learning #484
- 누적 공개(#483): 공개된 문제를 토요일까지 몰아서 풀 수 있어 화~금 대화의 단서 요약을 "앞 요일 문제까지" 기준으로 두었으나, 단서를 미션 뒤 공개로 바꾸며 요약 줄을 없앰(사용자 결정 2026-11-11, 16.1 대화 행)
- 단서 미션 뒤 공개(사용자 결정 2026-11-11)에 따른 다른 서비스 몫: learning(#484) 단서 공개 조건을 그날 미션 완료로, 웹(#440) 단서 카드·수첩·후보 지우기, state-diagram 기준안 수정. ai 응답 계약(`days[].clue`·`rulesOut`, `dialogues[].lines`)은 그대로
- 해결사 뭉치·시작 콘티 순서·증거 발견 줄·수사 연결 문장 프롬프트(2026-11-11)는 실측 3회차에서 수사 연결 문장 위치 문제가 드러나 대화로 옮김(16.4). 옮긴 뒤 실측은 16.4 끝에 기록
- core `THEME_VIDEO` 반영 시점(반영 전에는 영상 사용량 이벤트를 보내지 않음)
- 텍스트 생성 품질 시험을 이슈 설계대로 다시 만들어 통과(구현 전 선행). 특징 표 판정·단서 그대로 넣기·사건 자료 허용·실패 사유 넣어 다시 생성을 반영해 다시 측정
- 특징 표로 쓰기 어려운 성취기준(예: 4국03-05 쓰기 점검)의 날은 장면에서 특징을 고름. 실측으로 확인
- `review_missions` 추가 뒤 시간·비용 다시 측정(미션 검토 1회 미션 5개 병렬, 상한 2회)
- 텍스트 시험 결과(2026-11-10, 저장소 밖 실험 코드, 실제 LLM 약 60회·누적 약 $3.0): 설계를 고친 뒤 같은 테마 3회 연속 4개 중 3개 통과, 처음 보는 주제(초3·초4·초5·초6 각 1개)에서 4개 모두 통과. 한 번에 글 단계만 6~13분, $0.05~0.13. 독립 판정기 무작위 3만 건과 정답 논리 계산 일치. 남은 품질 과제: 단서 문장이 허용 값을 늘어놓아 기계적("모래·바위·나무 바닥 중 한 곳"), 특징을 성취기준에서 억지로 가져옴("알림 간격 6분·9분·10분") → 구현에서 문장 다듬기, 성취기준·주제 연결은 #470
- 시간: 글 단계만 실측 6~13분이라 그림·영상·검토를 더하면 15분 마감을 넘을 수 있음. 마감까지 남은 시간이 부족하면 다시 생성을 시작하지 않는 구현이 필요하고, 실측 뒤 마감 기준안을 다시 정함(에픽 작성자 확인)
- 생성·검토 모델 설정: 정함(2026-11-10). 테마 전용 설정(`THEME_GENERATION_MODEL`·`THEME_REVIEW_MODEL`)을 두고 같으면 시작할 때 막는 대신 테마 경로만 503(16.1 검토 모델). 운영 환경 변수에 두 값을 넣을지는 배포 담당 확인
- learning 다시 검사 범위: 특징 표는 내부 칸이라 learning은 `rulesOut` 수준(정답 안 빠짐·틀린 후보 다 빠짐·목요일 이후)까지만 볼 수 있음. 관리자 화면에 단서 근거(특징 표)를 보여 주려면 계약에 추가 필요(팀 확인)
- 그림·영상·움직임은 텍스트 시험 범위 밖. 구현 때 가짜 구현과 실측으로 확인
- 발견(이번 범위 밖, 보고만): 기존 `followup/leak_guard`의 금지어 비교가 숫자 경계 없이 부분 문자열이라 금지어 '6장'이 질문의 '26장' 안에서 잡힘(텍스트 시험 lab2-reporter-1). 미션 초안 경로에도 같은 오탐 가능. 정답 숫자 비교는 숫자 경계를 지킴

### 16.4 글 단계 구현 (2026-11-10)

그래프는 `retrieve → plan_theme → check_theme → generate_mission ×5(Send) → missions_done → generate_dialogue ×5(Send) → review_story`까지 붙였다. 그림·영상·움직임은 다음 단계라 응답 `images`·`videos`·`motions`는 빈 값이다.

| 항목 | 구현 | 설계와 다른 점·근거 |
|---|---|---|
| 파일 | `app/theme_draft/`에 `graph.py`, `nodes/`(`plan`·`mission`·`dialogue`·`review`), `checks.py`, `prompts.py`. LLM 구조화 출력 모델은 `models.py`에, 그래프 실행·응답 조립은 `service.py`의 `ThemeDraftGraphRunner`에 | 설계 트리 그대로(`schemas.py`·`runner.py` 없음) |
| `review_missions` | 요일별 `generate_mission` 노드 안에서 코드 검사 통과 뒤 실행 | 설계는 별도 노드. 생성 → 검사 → 미션 검토 → 다시 생성 루프를 요일마다 독립으로 돌려 다른 요일을 기다리지 않게 하려고 한 노드에 넣음. 검토 내용·상한·실패 처리는 설계 그대로 |
| 미션 재사용 | `MissionDraftService.generate`에 선택 인자 `extra_user`·`call_type`·`deadline`·`timeout` 추가 | 재시도(`MISSION_DRAFT_LLM_RETRIES`)·최대 토큰은 미션 초안 설정 그대로. 인자를 주지 않으면 `/internal/mission-drafts` 요청·응답이 같음(시험으로 확인) |
| 검사 분담 | ai 미션 검사 = 미션 초안 ai 검사 + `HINT_COUNT`·`THEME_ANSWER_LEAK`·`LANGUAGE`. 요소 code·`standardCode` 검사는 넣지 않음 | learning.md 21절 그대로 |
| 사유 → 다시 생성 | 사유는 `"<검사 코드> <자세히>"`. 미션 초안이 아는 코드(`REQUIRED`·`QUESTION_LENGTH`·`LEAK`·`STANDARD_CODE`·`ELEMENT_CODE`·`SHAPE`)는 미션 초안 `previousFailures`(고칠 점 문장)로, 나머지는 테마 프롬프트 뒤에 그대로 | 새로 정한 값 |
| `review_story` 경로 | `CLUE_LOGIC`·`ANSWER_HINT`·`SAFETY` `FAIL` → 줄거리부터, `STANDARD_FIT`·`GRADE_VOCAB` `FAIL` → 그 요일 미션·대화만, 항목 형식 오류 → 검토만 다시 | 새로 정한 경로(기준안). 줄거리부터 다시 만들 때 줄거리 시도 횟수는 다시 0부터(전체는 재검토 상한 2로 묶임) |
| `previousFailures` | `THEME`·`REVIEW` → 첫 줄거리 생성부터, `MISSION` → 그 요일 미션 생성마다(요일 접두어가 없으면 다섯 요일), `IMAGE` → 글 단계에서는 무시 | 새로 정한 값. `IMAGE`는 그림 단계에서 사용(16.5) |
| 응답 | 실패해도 만든 것까지 함께 돌려줌(`THEME` 실패만 `theme: null`). `warnings`는 `MISSION`(미션 검토 WARN)·`DIALOGUE`(뺀 요일, 사유마다 1개)·`REVIEW`(`item` = 항목 ID와 요일). `versions.model`은 생성 모델 | 계약 그대로 |
| 오류 | 그래프 안 LLM 형식 오류 502 `AI_BAD_RESPONSE`, 그 밖 LLM 실패 503 `AI_UNAVAILABLE`. 미션 생성 중 오류는 미션 초안 서비스가 바꾼 502·503 그대로 | 16.1 실패 행 그대로 |
| `rulesOut` | LLM 줄거리 출력 칸에서 빼고, 줄거리를 받은 직후 코드가 특징 표와 조건으로 채움(`checks.fill_rules_out`, `RULE`은 허용 값 밖 후보 전부·후보 순서, `HINT`는 빈 배열). "LLM이 쓴 `rulesOut`이 표 계산과 다름"·"`HINT`인데 `rulesOut`" 검사는 없앰. 프롬프트에서도 `rulesOut` 쓰는 규칙을 뺌 | 설계는 `rulesOut`의 성질(허용 값 밖 후보)만 정했고 누가 쓰는지는 정하지 않았음. 표와 조건이 정해지면 계산으로 하나로 정해지는 값이라 LLM에 쓰게 하면 틀릴 기회만 생김. 저장소 코드 첫 실측(2026-11-10, repo-beach5-1)에서 검토 뒤 줄거리를 다시 만든 3번이 모두 단서는 맞는데 `rulesOut`에 새로 빠지는 후보만 적어(이미 빠진 후보 누락) 줄거리 단계 실패로 끝남. 정답 논리 검사(정답 안 빠짐, `RULE`은 남은 후보를 새로 뺌, 수요일까지 2개 이상, 단서 문장과 조건 일치)는 그대로. 응답 계약·learning 처리는 같음(사용자 결정 2026-11-10). 프롬프트 버전은 아직 배포 전이라 `theme-draft@1` 그대로 |
| 단서 미션 뒤 공개·해결사 뭉치(2026-11-11) | 줄거리 출력에 `GeneratedDay.discovery`·`missionHook`, `GeneratedCut.mungchiMood` 추가(응답 `theme`은 `public_theme` 그대로라 계약 변화 없음). `GeneratedDialogue`는 `recap`을 없애고 `clueSpeaker`를 `discoverySpeaker`로(비면 뭉치). 검사 코드: 새 `CLUE_EARLY`(증거 발견 줄·수사 연결 문장·대화 LLM 줄이 그날 허용 값을 말함, 비교는 `checks.mentions_value` 하나)·`HOOK_MISSING`(미션 질문이 그날 `missionHook`으로 시작하지 않음: 공백 뺀 수사 연결 문장 앞 12자가 공백 뺀 질문 앞 24자 안에 있어야 통과)·`CUT_MOOD`(콘티 표정 값, 시작 1·2컷 `none`·3·4컷 `none` 아님), 증거 발견 줄·수사 연결 문장에 후보·정답 이름이면 `ANSWER_LEAK`. 대화 `CLUE_SPEAKER` → `DISCOVERY_SPEAKER`, `CLUE_REPEATED` → `DISCOVERY_REPEATED`(증거 발견 줄을 미리 말함), `RECAP` 없앰. 금요일 안내에 단서를 넣던 `finish_mission`과 그 때문에 따로 두던 상태 `raw_drafts`(대화는 이제 `drafts`를 씀), `clue_list`·`day_clue`를 없앰. `llm_line_range`는 마지막 줄 1줄만 뺌(초3·초4 LLM 1~2줄, 초5·초6 0~1줄) | 사용자 결정 2026-11-11(16.1 단서 공개·뭉치 역할·대화·미션 생성 행). 결정에 이름이 없던 표정 검사 코드는 `CUT_MOOD`로 새로 정함. 대화가 단서 대신 증거 발견 줄을 넣으므로 "단서를 다시 말함" 검사를 "증거 발견 줄을 미리 말함"으로 바꿈(같은 구조의 반복 방지). `HOOK_MISSING`이 질문 맨 앞이 아니라 앞 24자 안을 보는 것은 따옴표 같은 몇 글자가 붙는 것을 허용하려고(새로 정한 값). 단서 문장 검사(`CLUE_TEXT`)의 `value_in_text`는 1자 줄기도 그대로 봄(허용 값이 빠진 것을 잡는 검사라 넓게 봐야 하고, `CLUE_EARLY`는 잡으면 다시 만들게 하므로 좁게 봄). 프롬프트 버전은 배포 전이라 `theme-draft@1` 그대로 |
| 수사 연결 문장 대화로(2026-11-11) | `missionHook`을 미션 질문 첫머리에서 대화 맨 끝 줄(증거 발견 줄 다음, 뭉치)로 옮김: `checks.dialogue_lines(generated, discovery, hook)`, 길이 상한 60자 → 40자(`LINE_MAX`). `HOOK_MISSING` 검사를 없앰. `CLUE_EARLY`는 증거 발견 줄과 대화 LLM 줄만 보고 수사 연결 문장은 보지 않음(`ANSWER_LEAK`는 둘 다). `DISCOVERY_REPEATED`는 LLM 줄이 끝 두 줄 중 하나를 미리 말하면. 대화 유출 검사의 허용 글에 수사 연결 문장 추가. `DIALOGUE_LINES` 초3·초4 (3, 4)·초5·초6 (2, 3), `llm_line_range`는 2줄을 뺌(LLM 줄 수는 그대로). 미션 프롬프트는 "두 줄은 대화로 이미 나오므로 question에 다시 쓰지 않고 증거 자체를 살피게 하지 않음". 줄거리 프롬프트 콘티 줄에 컷 길이 4·6·8·6초와 가장 큰 동작은 3컷을 적음. 글 검토 프롬프트는 시작 1컷에서 주인이 찾는 대상을 지닌 모습(사라지기 전)을 허용 | 사용자 결정 2026-11-11(16.1 단서 공개·대화·미션 생성 행). 실측 3회차 실패: 질문 앞 수사 연결 문장의 `QUESTION_LENGTH`·`MATERIAL`·`CLUE_EARLY`, 글 검토가 시작 1컷의 찾는 대상(설계상 허용)을 `ANSWER_HINT`로 잡음. 컷 길이는 16.5 남은 확인(콘티 생성에 알릴지)을 이번에 정함. 40자는 대화 한 줄 상한과 같은 값 |
| 칸 고쳐 쓰기 `fix_theme`(2026-11-11) | `check_theme` 사유가 모두 칸 하나만 고치면 되는 것이면(`checks.fix_targets`: `LENGTH`·증거 발견 줄 `CLUE_EARLY`·`ANSWER_LEAK`이고 칸이 `title`·`bigQuestion`·`intro`·`outro`·요일 `place`·`sceneNote`·`clue`·`discovery`·`missionHook`·콘티 `caption`) 줄거리 전체 대신 `fix_theme`이 생성 모델로 그 칸만 고쳐 쓰고(`GeneratedFixes{fixes:[{path, text}]}`, 받은 경로 밖은 무시) `check_theme`이 모든 검사를 다시 봄. 상한 `theme_max_text_fix` 2(줄거리 다시 생성 횟수와 따로, 줄거리를 새로 만들면 0부터), 넘거나 다른 사유가 섞이면 지금처럼 줄거리 다시 생성. 프롬프트 `FIX_SYSTEM`·`fix_user`는 칸마다 지금 글·글자 수·상한·사유와 줄거리 프롬프트와 같은 지킬 점(단서는 허용 값 낱말 모두·허용 밖 값 금지, 증거 발견 줄은 증거 종류·단서 값 금지, 수사 연결 문장은 이유와 도움 요청, 모두 후보 이름 금지)을 줌 | 설계에 없던 단계(2026-11-11). 실측 4회차(repo-*-4)에서 4개 중 3개가 첫 줄거리에서 수사 연결 문장 41~50자로 걸렸고, 줄거리 전체를 다시 만들면 다른 칸(단서 44~49자 등)이 새로 길어져 글자 수만으로 3번을 다 씀. 줄거리 한 번이 130~170초라 시간도 많이 듦. 이야기 틀·정답 논리·표에 닿는 사유는 칸 하나로 못 고치므로 그대로 줄거리부터. 상한 2는 새로 정한 값 |

실제 LLM 실측(2026-11-10, 저장소 코드 그대로, 처음 보는 주제 초3·초4·초5·초6 각 2회, 생성 `gpt-6-luna`·검토 `gpt-6.1-terra`): 8회 중 2회 통과. 1회차(`rulesOut` 변경 전) 2/4, 실패는 줄거리 1(`rulesOut` 적는 방식)·미션 1. 2회차(변경 후) 0/4, 줄거리 단계는 4회 모두 통과(`rulesOut` 사유 0건)했고 실패는 미션 검토 3(초6 수요일 6과05-03 "조사하여 공유" × 만들기, 초3 금요일 예시 답 빠짐, 초4 월요일 자료 없음과 마감 보호)·글 검토 1(목요일 단서가 그날 계산 답을 알려 줌). 한 번에 169~826초, 약 $0.03~0.15(캐시 할인 없이 계산한 상한). 같은 주제 실험 코드 결과(8회 중 6회)와 합치면 16회 중 8회. 실험 코드와 사용자·시스템 프롬프트를 같은 입력으로 비교해 `rulesOut` 두 줄 말고 모두 같음을 확인했고, 다른 점은 저장소의 마감 보호뿐

시험(실제 LLM 호출 없음, 가짜 LLM): 검사 표 시험 75개(결함 하나에 정확한 사유 코드, 시험 결함 lab3-inventor-6·lab3-beach5-1 재현, `rulesOut` 채우기 포함), 정답 논리 대조 5000건(따로 짠 판정기, seed 437, 그중 통과 사례 1018건, 불일치 0, 코드가 채운 `rulesOut`도 판정기 계산과 대조), 그래프 시험 20개(경로·상한·마감·사유 넣기·502/503), 연결 시험 4개(같은 모델·키 없음 503, 설정되면 그래프 실행), 미션 초안 확장 시험 2개, `/internal/versions`에 `themeDraft`.

단서 미션 뒤 공개·해결사 뭉치 변경 뒤(2026-11-11, 가짜 LLM): 검사 표 시험 파일 111개(콘티 표정 `CUT_MOOD`, 증거 발견 줄·수사 연결 문장의 필수·길이·`CLUE_EARLY`·`ANSWER_LEAK`, `mentions_value` 2자 줄기 비교, 미션 `HOOK_MISSING`, 대화 `CLUE_EARLY`·`DISCOVERY_SPEAKER`·`DISCOVERY_REPEATED` 포함), 그래프 시험 23개(대화 마지막 줄 = 그날 증거 발견 줄, 미션·대화 user 글에 그날·앞 요일 단서 없음·수사 연결 문장 있음, 금요일 user 글에 큰 질문·후보·단서 목록 없음, 금요일 안내 그대로, 글 검토 user 글에 증거 발견 줄·수사 연결 문장), ai 전체 587개 통과.

수사 연결 문장 대화로 옮긴 뒤(2026-11-11, 가짜 LLM): `HOOK_MISSING` 사례를 빼고 수사 연결 문장은 단서 값 낱말이 있어도 통과·41자면 `LENGTH`, 대화 끝 두 줄 = 증거 발견 줄·수사 연결 문장, `llm_line_range` 초3·초4 1~2줄·초5·초6 0~1줄, 그래프 응답 대화 끝 두 줄, 미션 user 글에 "question에 다시 쓰지 않는다", 요청 `IMAGE` 사유가 그림 지시문에 들어감(아래 16.5). ai 전체 610개 통과.

실측 4·5회차(2026-11-11, 실제 LLM): 4회차(수사 연결 문장 대화로 옮긴 뒤, 기존 주제 4개) 0/4. 줄거리 단계에서 글자 수(수사 연결 문장 41~50자, 단서 44~49자)로 3번을 다 쓰거나 줄거리 호출 180초 초과. 칸 고쳐 쓰기·타임아웃 300초 뒤 5회차 12건 중 7건 통과(실제 서비스 자동 입력과 같은 규칙(주제 없음, 풀이 수학·나머지 국어 무작위) 8건 중 5건, 기존 주제 4건 중 2건), 줄거리 단계 12/12 통과, 통과한 테마는 대화 빠짐 없음, 1건 약 210~600초·$0.03~0.11. 실패 5건은 모두 미션 단계: 예시 답이 질문 요구를 다 채우지 못함(`EXAMPLE_COMPLETE`, 시도 단위 21번), 문제 글에 없는 사진·녹음을 보라고 함(`MATERIAL`), 듣기·조사 성취기준에서 자료를 글로 주면 `STANDARD_FIT`·안 주면 `MATERIAL`로 걸리는 충돌, 미션 초안 `LEAK`. 대화 `TARGET_SPEAKS` 16번은 대상 이름에 주인 이름이 들어가 주인을 대상으로 본 오탐이라 `is_target`이 뭉치·등장인물을 대상으로 보지 않게 고침. 남은 확인: 예시 답만 고쳐 쓰기, 글로 대신하는 활동 허용 기준(사용자 결정 필요), 다시 실측(목표 한 번에 70% 이상, 기준안).

미션 단계 보강(2026-11-11): 미션 검토가 예시 답 미완성(`EXAMPLE_COMPLETE`)으로만 실패하면 질문·생각 열기 질문은 두고 예시 답(풀이면 `answerKey.finalAnswer`도)만 생성 모델로 고쳐 쓴 뒤 코드 검사·검토를 다시 함(`GeneratedExampleFix`, 상한 `theme_max_text_fix` 2, 넘으면 지금처럼 미션 다시 생성). 듣기·말하기·조사·관찰처럼 글로 직접 할 수 없는 성취기준 활동은 문제 글 자료(대화·녹음을 옮긴 글, 조사 결과·사례, 관찰 기록)로 대신하고 미션 검토 `STANDARD_FIT`도 그렇게 대신한 것을 맞다고 봄(사용자 결정 2026-11-11, 나중에 TTS·STT가 생기면 그 성취기준은 직접 활동으로 다시 정함). 내용을 문제 글에 적지 않은 사진·녹음·그림·영상·지도·활동지를 살피게 하지 않음(미션 프롬프트, 검토 `MATERIAL`). 실측 6회차 12건 중 10건 통과(자동 입력 8건 중 7건, 기존 주제 4건 중 3건), 1건 약 205~714초·$0.05~0.15. 실패 2건: 생각 열기 질문이 '그림 속 안내판'을 떠올리게 해 `MATERIAL`(미션 프롬프트의 "생각 열기 질문은 장면 그림 속 물건을 가리킬 수 있게"와 새 자료 규칙이 부딪침), 글 검토 `CLUE_LOGIC`(714초, 마감 근처).

실측 7회차(2026-11-11, 서비스 자동 입력 20건, 학년마다 5건): 13건 통과(65%, 초3 2·초4 3·초5 4·초6 4). 6회차와 합치면 자동 입력 28건 중 20건(71%). 사례마다 고치던 방식을 멈추고 6·7회차 32건의 시도 단위 실패 약 300건을 원인별로 분류함(사용자 지적 2026-11-11 "한 번에 제대로"). 가장 큰 원인은 우리 규칙끼리 맞지 않는 것: ① 글로 대신하는 활동 인정을 미션 검토에만 넣고 글 검토에는 넣지 않음 ② 미션 초안 형식은 풀이에 `exampleAnswer`를 요구하지 않는데 미션 검토가 예시 답 없음을 실패로 봄 ③ 줄거리 프롬프트가 허용한 "대상을 찍은 사진"·"배울 것을 말하는 수사 연결 문장"을 글 검토가 정답 암시로 봄. 그 밖에 ④ 질문이 성취기준 행동 대신 방법·계획을 물음(약 15번) ⑤ 다룰 글·작품·자료 내용 없음(약 25번)과 넣으면 질문 200자 초과(11번) ⑥ 요구가 많아 예시 답이 빠뜨림(약 20번) ⑦ 돌아보기·따져 보기가 성취기준 행동을 빼거나 다른 관점을 선택 사항으로 둠 ⑧ 단서가 표에 없는 물건 종류를 특정하거나 증거 종류와 단서 문장이 다름(약 10번) ⑨ 풀이 답이 문제에 주어진 수인 비교 문제(정답 유출 3번) ⑩ (ai 밖) 초3 테마에 학년군(초3~4) 표에서 4학년 내용 성취기준이 뽑힘(learning 자동 뽑기, #464 학기 관계로 해결할 몫).

| 묶음 수정(2026-11-11) | 내용 | 근거 |
|---|---|---|
| 글로 대신하는 활동 원칙 `TEXT_ONLY` | "학생은 글로만 답한다. 듣기·말하기·발표·조사·관찰·실험·그리기·만들기·사전 찾기·검색처럼 글로 직접 할 수 없는 활동은 문제 글 자료로 대신하고 결과는 글로 쓴다(그림·전개도는 말로 설명)"를 미션 생성·미션 검토·글 검토·예시 답 고쳐 쓰기에 같은 글로 넣음 | 사용자 결정 2026-11-11(듣기·말하기·조사·관찰 인정 뒤 원칙 하나로 넓힘). 한 곳에만 넣어 생긴 ①을 막으려고 상수 하나를 네 곳이 씀 |
| 풀이 검토 | 미션 검토 `EXAMPLE_COMPLETE`는 풀이(SOLUTION_STEPS)에서 `answerKey.finalAnswer`만 봄 | ② 미션 초안 형식과 맞춤 |
| 글 검토 허용 | 수사 연결 문장이 배울 개념·방법 이름을 말하는 것, 사진·기록에 찍힌 그때의 대상 모습은 허용(지금 있는 곳이 드러나면 결함) | ③ 줄거리 프롬프트와 맞춤 |
| 미션 생성 규칙 | 성취기준 행동을 답 안에서 직접(방법·계획 금지), 다룰 자료 내용을 문제 글에, 요구는 요소 수(2~3가지)만큼, 생각 유형 활동은 성취기준 행동 뒤, 따져 보기 다른 관점 필수, 풀이 답은 새로 구하는 값, 예시 답은 완성된 결과물·서로 다른 까닭 | ④~⑦·⑨ |
| 단서 | 표에 없는 물건 종류를 특정하지 않음, 코드 검사 `CLUE_EVIDENCE`(단서 문장이 사진·영상·녹음·기록·일지·메모를 말하면 evidence `RECORD`, `RECORD`면 기록 낱말이 있어야 함) | ⑧. `CLUE_EVIDENCE`는 새로 정한 검사 코드 |
| 테마 미션 질문 상한 | `theme_question_max_chars` 학년 모두 400자(기준안, P19 확인 필요). `MissionDraftService.generate`에 선택 인자 `question_max_chars`(주지 않으면 미션 초안 설정 그대로) | 사용자 결정 2026-11-11. 자료를 문제 글에 넣으면 200자를 자주 넘음. learning에는 질문 길이 검사가 없음 |

실측 8회차(묶음 수정 뒤, 서비스 자동 입력 20건): 16건 통과(80%, 초3 2·초4 4·초5 5·초6 5), 완료 기준(한 번에 70% 이상, 기준안) 충족으로 글 단계 품질 보강을 마무리함. 실패 4건: 초3 글 검토 `GRADE_VOCAB`(분모가 같은 분수 덧셈, 4학년 내용)·`STANDARD_FIT`(정다각형 성취기준, 4학년 내용)은 위 ⑩(학년군 표에서 4학년 성취기준이 뽑힘, learning·#464 몫), 줄거리 `CLUE_EVIDENCE`로 상한까지 실패 1건(새 검사가 잡았으나 줄거리 다시 생성 3번 안에 못 고침), 미션 `EXAMPLE_COMPLETE`·`MATERIAL` 1건. ⑩을 빼면 18건 중 16건.


생성·검토 규칙 충돌 점검(2026-11-11): 그림 실측(테마 1개)에서 월요일 미션 그림이 "지은이·펴낸 해를 확인할 수 없다"(그림은 글자 금지)와 "손전등(찾는 대상)이 안 보인다"(대상은 그리지 않음)로 3번 실패해 테마 전체가 IMAGE 실패. 사례별로 고치지 않고 그래프 전 단계의 생성 프롬프트·검토 프롬프트·코드 검사를 대조해(점검 보고서, 에이전트가 찾고 코드에서 직접 확인) 확실한 충돌 20건과 같은 뿌리의 애매한 항목 6건을 한 번에 고침.

| 단계 | 고친 것 | 충돌 |
|---|---|---|
| 그림 검토 | 물건·장소·인물이 보이는지만 보고 적힌 내용·개수·그림 속 사진 내용·그릴 수 없는 행동(생각·시선)은 보지 않음, 장면 글 밖 등장인물은 결함 아님, 손에 든 물건·자세는 달라도 됨 | 그림은 글자 금지인데 검토가 글자·개수를 확인, 인물 전원을 그리게 하면서 장면 밖 인물을 지적 |
| 증거 | 증거 종류(`evidence.kind`)별로 그릴 것: 흔적 자리·물건, 사진·기록 물건, 본 사람. 찾는 대상은 증거가 아님(미션 그림 지시문·그림 검토 `evidenceKind`·살펴보기 `dayInfo.evidenceKind`) | 목격 요일에는 증거 물건이 없고, 증거 발견 줄 속 대상을 증거로 읽어 그리라고 함 |
| 테마 옷·종료 콘티 | 옷 그림 글자·휘장 금지. 종료 4컷은 모두 뭉치(코드 `CUT_MOOD`), 정답 이름·장소 공개 허용(줄거리·칸 고쳐 쓰기·글 검토·그림·영상 검토 `answerPlaceAllowed`) | 옷을 그대로 따라 그리게 하는데 글자 금지가 없음, 종료 콘티는 정답 장소로 가는 장면인데 검토가 정답 장소 노출로 봄 |
| 영상 | 지시문을 그림과 같은 컷 판정으로(시작 1·2컷 뭉치 없음, 3컷 뭉치 혼자, 대상 두는 곳 숨김은 시작 1컷만, 다른 대상 금지 컷은 대상 금지, 종료 3·4컷은 문구 없음), 영상 검토 MORPH가 뭉치 등장도 봄 | 모든 컷에 뭉치 문구와 대상 숨김 문구가 들어가 종료 3컷 동작과 모순 |
| 대화 | 유출 검사(금지어·정답 키·정답 낱말)는 LLM 줄만, 대화 입력에 피할 낱말(그날 단서 값·장소 후보 이름) | 코드가 그대로 넣는 끝 두 줄에 미션 금지어가 겹치면 다시 만들어도 계속 실패 |
| 살펴보기 | 피할 낱말(단서 값·후보 이름·미션 금지어)을 주고, 한마디·이름이 미션 답·금지어·예시 답을 말하면 그 물건을 뺌(`checks.spot_leaks`) | 대화에는 있는 유출 규칙이 살펴보기에는 없음 |
| 줄거리 | 특징 값에 등장인물 이름 금지, 장면 메모에 글자로만 보이는 것·그릴 수 없는 행동 금지 | 목격 증거 발견 줄이 본 사람을 말해 그 이름이 단서 결론으로 걸림 |
| 미션 | 장소 후보 이름을 쓰지 말 낱말로 주고 정답 유출 사유에 낱말 표시, 증거 발견 줄·수사 연결 문장 낱말은 금지어에 넣지 않음, 기록 속 지나간 대상 모습 허용(미션 생성·미션 검토). 따져 보기 다른 관점은 질문·예시 답에 넣고 필수 여부는 관리자가 미션 요소(`goodThought`)에서 정함, 검토는 선택처럼 쓰였다는 이유로 실패시키지 않음 | 생성은 정답을 모르는데 정답 낱말로 실패, 기록 속 대상을 글 검토는 허용·미션 검토는 결함, 요소 규칙(다른 관점은 좋은 생각)과 테마 규칙(필수)이 어긋남 |
| 예시 답 고쳐 쓰기 | 서술·논술·풀이만(고르기·순서·분류는 미션 다시 생성), 최종 답 단위 없이, 사건에 관한 새 사실만 막고 경험·새 생각은 씀, 안내 문장 옮기지 않음. 예시 답 완결은 미션 검토 한 곳에서만(글 검토는 계산 값만) | 고쳐 쓰기가 정답 키를 못 고치는 유형에도 걸림, 단위 규칙이 미션 초안과 반대, 두 검토가 같은 것을 다른 기준으로 봐 미션 전체를 다시 만듦 |

결정: 따져 보기 다른 관점의 필수 여부는 관리자가 정함(사용자 결정 2026-11-11, learning 미션 요소 `goodThought` 칸이 이미 있어 공유 규칙을 바꾸지 않음). 근거가 약하거나 의도일 수 있는 애매한 항목 12건은 이번에 두고 점검 보고서에 남김. 미션 그림 하나가 끝내 실패하면 테마 전체 실패인 지금 방식은 유지(사용자 결정 2026-11-11, 다음 실측에서 그림 실패가 잦으면 다시 검토).

전체 실측(초5, 그림·영상까지, 2026-11-11): 통과, 400초, 그림 14장 다시 그림 없음, 영상 2개, 약 $4.7. 영상을 0.5초 간격으로 확인해 품질 문제를 모아 한 번에 고침: 컷 안 0.4~0.9초 멈춤(재생 중 끊김), 인물이 화면 밖으로 나가거나 사라짐·겹침, 카메라 확대로 인물 잘림, 뭉치에게 큰 팔이 생김, 뭉치 옷(조끼)이 주머니로 바뀜, 옷 자체가 역할을 드러내지 않음("연두색 조끼와 주황 가방"), 살펴보기 3곳이 휴대전화 한 물건 위에 겹침. 고친 것: 줄거리 옷 규칙(역할을 한눈에 알아보는 머리·목 차림 1~2개, 예시 탐정 모자·돋보기), 콘티 동작은 제자리 작은 동작(화면 밖 이동 금지), 영상 지시문(인물 유지·뭉치 작은 손만·옷 유지·느린 카메라·끊김 없이), 금지 조건 추가, 영상 검토는 첫 장면 기준 + 1초마다 최대 8장에 항목 `CONTINUITY`(인물 수·화면 안·뭉치 모양·옷) 추가, 멈춤 코드 검사(`media.freeze_spans`·`trim_clip`, 앞뒤 정지 화면은 잘라 내고 중간 0.5초 넘는 멈춤이나 남는 길이가 요청의 60% 미만이면 `FREEZE`로 그 컷만 다시 생성, 기준안), 문구 시각은 실제 컷 길이(`video_durations`)로, 살펴보기는 서로 8%(그림 %, 기준안) 안이면 하나만 남김(증거 우선). 시험용 가짜 영상은 매 장면 달라지는 잡음 무늬로 바꿈(단색은 멈춤으로 잡힘).


### 16.5 그림·영상·움직임 구현 (2026-11-11)

그래프는 `review_story`가 `PASS`면 `generate_images → generate_videos → generate_motion → END`로 이어진다. 그림 클라이언트나 저장소가 없으면(버킷 `ASSET_S3_BUCKET`이 비거나 OpenAI 키 없음) `generate_images`가 경고 `IMAGE`/`ALL`/"그림 설정 없음" 하나만 남기고 끝나며 글 단계 결과는 그대로 성공이다. 미션 그림이 끝내 실패해도 `END`(영상·움직임 없음).

| 항목 | 구현 | 설계와 다른 점·근거 |
|---|---|---|
| 파일 | `nodes/images.py`(`generate_images`, 그림마다 검토), `nodes/video.py`(`generate_videos`, 컷마다 검토·이어 붙이기), `nodes/motion.py`(`generate_motion`), `assets/mungchi-2d.png`(기본 뭉치 그림, 기준안), `checks.motion`·`dialogue_speakers`, `prompts.py` 끝의 그림 지시문·그림 검토·영상 지시문·영상 검토·움직임 시스템 프롬프트(버전 `theme-draft@1` 그대로). 조립은 `service.assemble`, 클라이언트는 기동 때 `create_media_clients`·`create_storage`로 만들어 `app.state.theme_image`·`theme_video`·`theme_storage`에 두고 라우터가 실행기에 넘김 | `review_images`·`review_videos`는 별도 노드가 아니라 `generate_images`·`generate_videos` 안에서 그림·컷마다 돈다. 다시 만들고 다시 검토하는 루프가 그림·컷마다 독립이라 다른 그림을 기다리지 않게(`review_missions`와 같은 이유) |
| 그림 수 | 테마 옷 뭉치 1 + 미션 그림 5(`MON`~`FRI`) + 시작·종료 컷 첫 그림 8. S3에는 응답 장면 7개만(`MON`~`FRI` 미션 그림, `INTRO`·`OUTRO`는 4번째 컷 첫 그림) `.png`로 올림 | 설계는 장면 7장 + 경계 그림 7장. 영상이 첫 그림만 고정하게 되어 경계 그림 대신 컷마다 첫 그림이 필요하고, 요일 장면 그림은 그날 미션 그림(질문이 가리키는 물건이 보이는 그림)으로 바꿈(사용자 결정 2026-11-11) |
| 그림 순서·참조 | 테마 옷 뭉치(기본 그림 1장 참조) → 시작 1컷 첫 그림(참조 없이 글로만, `images.generate`) → 나머지 12장을 [테마 옷 뭉치, 시작 1컷 그림] 참조로 동시에. 시작 1·2컷은 뭉치 참조 없음(뭉치 안 나옴), 시작 3컷은 인물 참조 없음(뭉치 혼자 출동). 시작 1컷이 끝내 실패하면 인물 참조 없이 | 설계는 "첫 장면을 먼저". 새 콘티(시작 1컷 = 평소 모습과 주인)에서 시작 1컷이 인물을 가장 잘 보여 줘 인물 기준 그림으로 씀. `OpenAIImageClient.edit`은 참조가 없으면 `images.generate`를 부름(edits는 그림이 필요) |
| 그림 지시문 | 고정 스타일(2D, 굵고 고른 짙은 갈색 외곽선, 단순한 면 색·부드러운 음영, 단순한 배경, 3D 아님) + 뭉치 생김새(테마 옷) + 인물 모습(한국어 그대로) + 장면. 미션 그림은 장소·장면 메모, 그날 증거 발견 줄, 미션 질문·생각 열기 질문(한국어 그대로, 가리키는 물건이 보이게), 컷 그림은 콘티 `scene`과 `mungchiMood` 입 모양(`none`이면 넣지 않음). 규칙: 찾는 대상 금지(시작 1컷·종료 3·4컷만 허용), 생각·말 풍선 없음, 글자·숫자 없음, 얼굴 보이게, 위쪽 여백 | 증거 발견 줄은 살펴보기 단계에서 학생이 그 증거를 누르게 될 예정이라 넣음(조정자 전달 2026-11-11). 표정은 `smile` 웃는 입, `surprised` 작은 o 입, `determined` 다문 일자 입(점 눈 유지) |
| 그림 검토 | 검토 모델에 [그림, 테마 옷 뭉치]. 항목 `MUNGCHI`·`ANSWER_HINT`·`TEXT`·`SAFETY`·`SCENE_FIT`, 미션 그림은 `MISSION_FIT` 추가(`ImageReviewId`에 두 값 추가, 내부 출력이라 계약 영향 없음). `FAIL`은 그 그림만 사유를 넣어 다시(상한 `theme_max_regen`, 마감 `can_regenerate`), 그림 호출 실패(안전 정책 거절 400 등)·검토 호출 실패도 사유로 다시. 통과한 검토의 `WARN`은 `warnings(IMAGE, item=그림 키)` | `MISSION_FIT`·`SCENE_FIT`은 설계에 없던 항목(사용자 결정 2026-11-11). 그림 `WARN`을 경고로 남기는 것과 테마 옷 뭉치는 검토하지 않고 호출 실패만 다시 만드는 것은 새로 정한 값 |
| 그림 실패 처리 | 미션 그림이 끝내 실패하면 `failure{IMAGE, ["<요일> <항목> <사유>"]}`(글은 함께 반환, 통과한 그림 키도 담음), 컷 첫 그림이 끝내 실패하면 그 장면 영상만 빼고 `warnings(VIDEO, item=INTRO·OUTRO, "<컷> 그림 <사유>")`, 테마 옷 뭉치가 끝내 실패하면 `failure IMAGE`(`OUTFIT …`). S3 올리기 실패는 미션 그림이면 `failure IMAGE`, `INTRO`·`OUTRO`면 `warnings(IMAGE)` | 설계 그대로(경계 그림 → 컷 첫 그림). 올리기 실패·테마 옷 실패 처리는 새로 정한 값 |
| 영상 | 영상 클라이언트가 없으면(기본 `THEME_VIDEO_ENABLED=false`) `warnings(VIDEO, ALL, "영상 설정 꺼짐")`, 마감까지 `theme_video_timeout + 60`초가 안 남으면 `warnings(VIDEO, ALL, …마감…)`. 시작·종료 각 4컷을 동시에(컷 길이 설정 `theme_video_cut_seconds` 기본 [4, 6, 8, 6]), 첫 그림만 고정(`VideoClient.generate`의 `last`를 선택 인자로, 없으면 Veo에 `lastFrame`을 보내지 않음), Veo `parameters.negativePrompt`. 지시문 = 콘티 `action` + 고정 문구(2D 유지·뭉치 모양·점 눈 유지·표정은 입 모양·자연스럽고 단순한 움직임·카메라 움직임 하나·글자 없음·찾는 대상을 어디 두는지 보여 주지 않음). 검토 모델이 2초마다 뽑은 장면(최대 4장)을 보고 `MORPH`·`ANSWER_HINT`·`TEXT`·`SAFETY`, 실패한 컷만 다시(상한·마감). 끝내 실패한 컷이 있으면 그 장면 영상만 빼고 경고. 컷을 0.5초 겹쳐 녹아드는 전환(`media.join_xfade`, ffmpeg xfade, libx264·yuv420p·24fps 다시 인코딩)으로 이어 S3 `.mp4`. 사용량 `THEME_VIDEO`는 이벤트 없이 로그만 | 설계의 "컷마다 경계 그림으로 시작·끝 고정·6초"를 바꿈(16.1 영상 행 근거). 경고 `item` `ALL`(단계 전체를 건너뜀)은 새로 정한 값. 컷 길이는 요청한 길이로 이어 붙임(Veo가 요청 길이대로 돌려줌) |
| 문구 시각 | 컷 i 시작 = 앞 컷 길이 합 − i × 0.5초, 경계 = 그 + 0.25초(겹치는 구간 한가운데). 4·6·8·6초면 0~3.75·3.75~9.25·9.25~16.75·16.75~22.5초(`media.xfade_caption_times`) | 새로 정한 값 |
| 움직임 | 그림이 있는 장면마다 생성 모델에 그 그림 1장을 주고 `GeneratedMotion`. `speakers`는 그 요일 대화 줄의 화자(찾는 대상 제외, 시작·종료는 비움), 화자 초점 확대는 1.2로 고정. 시작·종료 `captions`는 영상이 있을 때만(컷 `caption`, 위 시각). `checks.motion`이 확대 1.0~1.4·카메라 8~20초·전환 0.3~1.2초·효과 최대 2층·층당 20개·크기 1~6·속도 2~20·방향 0~359(360으로 나눈 나머지)·불투명도 0.2~0.8로 맞추고, 색이 `#RRGGBB`가 아니면 그 효과를, 화자가 아닌 이름은 그 화자를 빼고, 좌표는 0~100으로 맞춤. 맞춘 항목마다 `warnings(MOTION)`. 움직임 LLM이 실패하면 그 장면만 빼고 경고. 응답에서 `ThemeMotion`으로 검증 | 화자 확대 1.2·움직임 최대 출력 토큰 `theme_motion_max_tokens` 8000은 새로 정한 값(기준안) |
| 살펴보기 `spots`(2026-11-11) | 요일 장면 움직임 호출에서 그날 그림과 `dayInfo`(증거 발견 줄·미션 질문·생각 열기 질문, 단서 없음)를 주고 그림 속 누를 물건 2~3개(`GeneratedSpot{label, line, evidence, x, y}`)를 함께 정함. `checks.spots`: 이름·한마디가 비거나 10자·30자(기준안)를 넘거나, 한마디가 그날 단서 결론을 말하거나(`mentions_value`) 후보·정답 이름이 있으면 그 물건을 빼고, 증거 물건은 정확히 1개(여럿이면 첫 번째만), 3개 넘으면 증거 물건을 남기고 줄이며, 증거 물건이 없거나 2개 미만이면 그 장면 `spots`를 비움. 맞춘 항목마다 `warnings(MOTION)`, 다시 생성하지 않음. 응답 `ThemeMotion.spots`(선택 칸, 시작·종료는 빈 배열) | 사용자 결정 2026-11-11(살펴보기, 매일 짧게 2~3곳). 그림 모델이 좌표를 주지 않아 이미 그림을 보고 화자 위치를 잡는 움직임 호출에서 위치를 찾음. 물건이 그림에 보이는지는 그림 검토 `MISSION_FIT`(질문·증거 물건이 보이는지)이 봄. 기존 칸을 바꾸지 않는 선택 칸이라 version 1 유지(사용자 결정). 살펴보기는 미션 전이라 단서 결론을 막는 것은 증거 발견 줄과 같은 기준 |
| 응답 | `images`(장면 → S3 키)·`videos`(`INTRO`·`OUTRO` → 키)·`motions`(장면 → `ThemeMotion`), 그림·영상·움직임 경고는 글 단계 경고 뒤에 | 계약 그대로 |
| `previousFailures` `IMAGE` | 사유가 그림 이름(`MON`~`FRI`·`INTRO1`~`INTRO4`·`OUTRO1`~`OUTRO4`)으로 시작하면 그 이름을 떼고 그 그림의 첫 그리기부터, 이름이 없으면(`OUTFIT …` 포함) 모든 그림(테마 옷 뭉치 제외)의 첫 그리기부터 지시문 고칠 점에 넣음(`service.initial_state`의 `image_seed`) | ai가 돌려주는 미션 그림 실패 사유가 이미 `"<요일> <항목> <사유>"`라 learning이 그대로 돌려주면 그 그림에만 들어감(사용자 결정 2026-11-11, `MISSION` 사유와 같은 방식). 그림 이름 `INTRO1` 같은 컷 번호 형식과 이름 없는 사유를 모든 그림에 넣는 것은 새로 정한 값 |

시험(실제 OpenAI·Google·S3 호출 없음): 가짜 그림·영상 클라이언트, 메모리 저장소, 가짜 LLM. `tests/llm/test_media.py`(가짜 클라이언트, `join_xfade` 길이 = 컷 합 − 겹침, 문구 시각, `video_frames`, 참조 없을 때 `images.generate`, Veo 요청에 `lastFrame` 없음·`negativePrompt`, 설정별 클라이언트 생성), `tests/theme_draft/test_storage.py`(키 형식), `tests/theme_draft/test_media_graph.py`(설정 없으면 경고 하나로 건너뜀, 그림 순서·참조 수·지시문, 그림 검토 실패 다시 그리기, 미션 그림 끝내 실패 → `IMAGE` 실패, 컷 그림 실패 → 그 영상만 빠짐, 영상 꺼짐·마감 경고, 영상 성공 시 22.5초 영상·문구 시각·컷 다시 만들기, 움직임 보정 경고, 움직임 실패 장면만 빠짐, 요청 `IMAGE` 사유가 그 그림·모든 그림 지시문에 처음부터 들어감, 응답 `ThemeMotion` 형식, 앱 상태의 클라이언트로 경로 실행). 글 단계 그래프 시험은 그림 설정이 없어 생기는 경고만 걸러 보던 그대로 봄.

남은 확인: 실제 그림·영상 실측(시간·비용·검토 통과율), 기본 뭉치 그림은 기준안(앱 원본 그림이 저장되면 바꿈).
