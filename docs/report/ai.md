# AI (판정·되묻기·분석 대화·모델 레지스트리·M2·리포트·초안 생성)

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

- P25(#392, [서비스 기획 방향](planning.md#3-서비스-기획-방향-리텐션일일-리포트-2026-11-06-p20p25)): 일일 리포트 고정 대화는 core가 범위(그날)와 리포트 요약을 요청에 넣는다. ai는 report를 직접 호출하지 않고 기존 흐름을 그대로 쓴다
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

- 정책(사용자 결정): 평가 근거 필수, SERVICE_OPS의 명시적 사람 승인, 평가 범위 안에서만 활성화, 복귀는 원 승인 범위의 부분 집합, 자동 합격선·새 승인 상태 없음. 근거의 사실성·통계적 합격은 운영자 판단(서버가 평가를 실행했다고 주장하지 않음)
- 흐름: `PublicAuthFilter` → `AuthService` SERVICE_OPS 검사 → `ModelVersionService`. 같은 kind·name의 transaction advisory lock → 재조회 → 기존 ACTIVE를 INACTIVE → 대상 ACTIVE·범위·revision → 감사 행 → `OutboxWriter.append`가 한 트랜잭션. 부분 unique index가 ACTIVE 단일성을 최종 강제
- 사용량 조회: KST 양 끝 포함 최대 366일, 범위 밖은 DB 조회 전 400. 미산정 비용이 섞이면 `costUsd` null + `unpricedCalls`
- scope 배열의 null 요소는 명시적으로 422
- 기존 NULL 평가 행은 목록에 null로 남기고 활성화·복귀는 422, 불완전한 기존 ACTIVE는 내부 snapshot에서 503 `MODEL_VERSION_STATE_INVALID`
- scoring 소비는 [scoring 2절](scoring.md#2-활성-버전-이벤트롤백-86), ai 소비는 7장

### 3.1 등록·활성화 절차 개선 설계안 (#301)

#185 AWS 배포 때 서술 3.0·논술 3.1을 관리자 화면으로 등록하면서 등록 자료를 화면에 반복 전사해야 했던 문제의 개선 설계. 구현은 #366(화면 범위 분리·감사 detail, [frontend 10절](frontend.md#10-366367-모델-버전-운영-화면-2026-11-09)), #367(11장), #368(12장), #370(13장).

원칙: 파일 업로드·등록·사전 검사만으로 활성화하지 않는다. 파일 무결성·로딩 성공을 품질 승인으로 표시하지 않는다. 사람 승인과 감사 이력을 유지하고 임시 경계·평가 범위 제한·미검증 사항을 화면에 드러낸다. 새 승인 상태 enum은 없다.

당시 화면의 문제:

- 상단 "적용 범위" 입력 하나가 등록의 평가 범위(`evaluatedScopes`), 활성화의 승인 범위, 복귀 범위 세 의미로 쓰여 "평가는 했지만 적용하지 않은 범위"를 표현하기 어려웠음
- 종류 기본값이 `PROMPT`, 이름·버전 형식 미검사, `MODEL`인데 `artifactUri`가 선택(빈 값이면 scoring 계약 검사에서 거부)
- core는 scoring의 로딩 결과를 모름. 화면의 `ACTIVE`는 "core에서 활성화됨"까지만 뜻함

결정(2026-11-05, kty2001 확인):

| 항목 | 결정 | 검토한 대안 |
|---|---|---|
| 등록 자료 형식 | M2 담당이 주는 `registration_*.json`(등록 API 본문 `requests[]`)과 `manifest.json`(모델별 6개 파일의 `bytes`·`sha256`)을 그대로 받음. 둘 다 저장소에 넣지 않음 | 한 파일 형식 |
| JSON 파싱 위치 | 브라우저에서 읽어 기존 `POST /admin/model-versions`를 항목별로 호출 | core JSON 업로드 API |
| 여러 모델 | 모델별 미리보기 카드와 개별 등록, 부분 실패는 항목별 표시 | 일괄 등록 API |
| `limitations` | `evidence`에 선택 필드 `limitations: string[]`(jsonb라 마이그레이션 없음). 최상위·manifest의 `주의`를 후보로 채우고 운영자가 확인 | `comparisonReport` 문장에 기록 |
| JSON에 넣지 않는 값 | 승인 여부·활성화 범위·변경 사유·재분석 계획·승인자. `requests[]`에 있으면 거부 | |
| `<버킷>` | 웹에서 한 번 입력해 모든 항목에 치환, 치환 전에는 등록 차단 | |
| 범위 분리 | 평가 범위는 등록 폼 안, 활성화·복귀 입력은 버전 카드마다. 활성화 범위는 그 버전의 `evaluatedScopes` 체크박스(기본 미선택) | 전체 미리 선택 |
| 범위 후보 목록 | 웹 domain의 알려진 scope 상수. 목록 밖 값은 경고만 | core scope 목록 API |
| 사전 검사 위치 | core 관리자 API가 scoring 내부 API를 동기 HTTP로 중계. 가중치는 받지 않고 6개 파일의 존재·크기·해시와 작은 JSON 3개만 | core에 S3 SDK 추가, 운영자 CLI |
| 오류 표시 | 공통 오류 형식은 그대로. 필드 검사는 화면에서 먼저, 서버 409는 이름·버전 칸에 연결, 422는 폼 상단 | 오류 형식 변경 |
| 로딩 확인 | 1차는 "core 활성화 완료, 로딩은 scoring에서 확인" 안내. Pod별 로딩 보고는 #370 | core가 `/internal/versions` 한 번 조회 |
| 거부된 시도 감사 | 제외(같은 트랜잭션이 롤백되어 남지 않음) | 별도 트랜잭션 |
| 기존 3.0·3.1 레코드 | 파일과 대조해 다르면 고치지 않고 새 버전명으로 재등록. 2026-11-05 대조 결과 글자까지 같아 재등록 불필요 | |

- 화면 단계(상태 enum 없이 계산): 등록 → 사전 검사 → 승인·활성화 → 로딩 확인 → 추론 확인
- 기존 운영 레코드: 서술 3.0은 초5·6 서술형, 논술 3.1은 초5·6 논술형으로 11/03 활성화(논술 초4는 평가했지만 미적용). 허용 기준은 11/22 확정(NFR-AIQ-06) 전이며 논술 score_cuts는 임시값

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

문제: ai가 scoring 장애·시간 초과·5xx와 400(M2 입력 토큰 한도 초과)을 모두 `503 SCORING_UNAVAILABLE`로 바꿨다. learning `AiClient`는 판정·되묻기가 함께 쓰는 서킷 `ai`(20건·50%·30초)에서 ai 5xx를 실패로 센다. 그래서 keywords가 긴 미션 하나나 scoring 장애가 scoring과 무관한 LLM 단독 판정·되묻기까지 모든 학생에게 30초 동안 막았다. 또 `M2_CROSS_CHECK_ENABLED=false`(기본)여도 scoring을 불렀다([감사](testing-ci.md#5-develop-종합-점검-원장-16회차) 6.3 A20·B36).

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
- 로컬 이관 체험 Compose가 scoring을 함께 띄우도록 바꾼 [로컬 플랫폼](infra.md) 결정은 그대로 둔다(플래그 꺼짐이면 판정이 scoring을 부르지 않으므로 필수 의존은 아님).

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

core #43의 `GET /internal/model-versions/active`와 `model.version.activated.v1` data는 같은 `id·kind·name·version·refId·artifactUri·scopes·revision·activatedAt` 필드를 사용한다. 이벤트에만 `previousVersionId`가 추가된다. 이미 있는 스키마를 재작성하지 않는다. core는 kind·name별 revision을 증가시키므로 ai는 정해진 `PROMPT` 이름(아래 표와 `reportExplanation`(#477, 14장))만 골라 높은 revision을 적용하고 각 기능의 승인 scope를 정확히 검사한다. 형식 오류 이벤트는 원문·URI 없이 경고하고 ACK하여 재시도하지 않는다.

| name | 승인 scope | ai 이미지에 포함된 기본 본문·버전 |
|---|---|---|
| `judgment` | `ai/judgment` | `judgment/prompts.py`, `judge@2` |
| `followup` | `ai/followup` | `followup/prompts.py`, `followup@4` |
| `analysis` | `ai/analysis` | `analysis_agent/prompts.py`, `analysis@4` (#454) |
| `reportNarrative` | `ai/report-narrative` | `report_narrative/prompts.py`, `report@1` |
| `reportTemplate` | `ai/report-template` | `analysis_agent/template_prompts.py`, `analysis-template@1` (#280) |
| `missionDraft` | `ai/mission-draft` | `mission_draft/prompts.py`, `mission-draft@1` (#354) |
| `themeDraft` | `ai/theme-draft` | `theme_draft/prompts.py`, `theme-draft@1`(생성·검토 프롬프트 한 묶음, #437) |
| `memoryExplanation` | `ai/memory-explanation` | `memory_explanation/prompts.py`, `memory-explanation@1` (#565) |

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

기획서 6.2 ②·③(성취기준 문장으로 LLM 초안 → 자동 검사 → 실패 사유를 붙여 재생성)의 ai 몫. 전체 결정은 [learning 21절](learning.md#21-성취기준성취수준-표와-미션-초안-흐름-문서계약-336), 계약은 api-spec 4.2 `POST /internal/mission-drafts`.

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 호출 단위 | 요청 1번에 LLM 생성 1회 + 검사. 반복은 learning 주기 작업이 `previousFailures`를 넣어 다시 호출 | ai 안에서 반복하면 learning→ai 대기를 넘음 |
| ai 검사 | `REQUIRED`(필수 항목·선택지·정답 키·예시 답·생각 열기 질문), `QUESTION_LENGTH`, `LEAK`(질문·안내·생각 열기 질문 속 정답 키·금지어·예시 답) | `followup/leak_guard`를 학생 답 없이 재사용 |
| learning 검사 | 성취기준 실재·요소 code 규칙·`standardCode`·입력 방식 모양 | 표와 게시 규칙이 learning에 있음 |
| 입력 | 성취기준 문장, 생각 유형, 그 유형 표준 요소 코드·공통 설명, 학년, 입력 방식 | 학생 정보·학생 답 없음 |
| 실패 응답 | 형식 밖 출력은 `502 AI_BAD_RESPONSE`, 그 밖 LLM 실패는 `503 AI_UNAVAILABLE`. 임의 내용으로 성공 처리하지 않음 | FAC-18 |
| 프롬프트 | 내장 `mission-draft@1`, 레지스트리 이름 `missionDraft`·scope `ai/mission-draft` | 7장 규칙 |
| 사용량 | `callType = MISSION_DRAFT` | |

### 9.1 ai 구현 (#354)

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 질문 길이 상한 | `mission_draft_question_max_chars` 기본 전 학년 200자, `gradeMin` 학년 값으로 검사 | P19 확정 전 기준안. 데모 시드 질문이 67~193자 |
| 정답 키 노출 | 고르기는 정답 선택지 이름, 풀이는 최종 답을 글로 비교. 숫자뿐인 최종 답은 숫자 경계로 비교(정답 30이 "300원"에 걸리지 않게). 순서·분류는 비교하지 않음 | 순서·분류 정답은 한 낱말로 나타낼 수 없음 |
| 예시 답 노출 | 질문은 예시 답과 비교하지 않고, 안내·생각 열기 질문은 질문에 이미 있는 글을 빼고 비교 | 풀이 예시 답이 질문 조건을 옮겨 써 떨어진 오탐 |
| 들어가면 좋은 생각 | 유형별 고정(`prompts.ELEMENT_RULE`): `ANALYZE_REASON`·`EVALUATE_PERSPECTIVE`·`CREATE_CONNECT`·`SOLVE_CHECK`·`REFLECT_CONNECT`. 따져 보기 논술은 세 요소 모두 필수 | LLM에 맡기면 시드와 달라져 데모 시드의 유형별 지정을 기본값으로. 기준표 담당이 정하면 `ELEMENT_RULE`만 바꾸면 됨 |
| 노출 검사 공유 | `find_leaks`가 `find_text_leaks`(글 하나 검사)에 위임 | 새 공통 라이브러리를 만들지 않음 |

### 9.2 미션 초안 시간 설정 변경 (#353)

실제 2022 개정 성취기준 문장을 넣으면 출력이 길어져 LLM 1회 15초를 넘었다(논술 초안이 3번 모두 실패).

| | `gpt-6.1-terra` | `gpt-6-luna`(기본 모델) |
|---|---|---|
| 걸린 시간(14건) | 10.5~18.8초 | 15.0~31.7초 |
| 출력 토큰 | 791~1,245 | 1,024~3,514 |

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| LLM 대기 | 미션 초안만 60초 1회(재시도 없음). `LlmClient.generate`에 호출별 `timeout`·`max_retries`. 다른 호출은 15초·1회 그대로 | 주기 작업이라 기다리는 사람이 없음. Luna 최대 31.7초에 여유 |
| 마감 / learning→ai | 63초 / 초안 클라이언트만 70초. 생성 리스 90초 안 | |
| 출력 상한 | `mission_draft_max_tokens` 8192 | 잘리면 형식 밖 출력(502) |

P12 예외라 팀 확인 필요.

## 10. 일일 리포트 고정 대화 리포트 요약 입력 (#392)

P25의 ai 몫. core가 메시지마다 고정 판을 읽어 넘긴 리포트 요약을 분석 에이전트 입력에 더한다. ai는 report를 직접 호출하지 않는다(core 쪽은 [core 12장](core-gateway.md#12-일일-리포트-고정-대화-392)).

- 요청 `AnalysisRequest.report`(`reportId`, `revision`, `date`, `metrics[]`, `problems[]`). 있으면 `scope.from = scope.to = date`가 아니면 400
- 답변 프롬프트에 `[고정 리포트]` 블록(지표·문제 JSON). 리포트 지표 개수·문제 수·문제 제목 속 숫자를 숫자 대조 허용 목록에 더함. 인용 대조는 learning `[원문]`만
- 고정 대화에서 `DIFFERENT_PERIOD`면 "이 대화는 {날짜} 일일 리포트로 고정돼 있어요. 다른 날은 새 대화에서 물어봐 주세요."
- **리포트 인용은 받지 않음**: 요약에 원문을 넣으면 근거 구조와 core 근거 ID 저장을 바꿔야 함
- **프롬프트 버전**: 본문을 바꾸면 `PROMPT_VERSION`을 올림. 어떤 환경에서 이전 버전을 활성으로 지정해 두었다면 새 이미지에서는 `503 AI_PROMPT_VERSION_UNAVAILABLE`이므로 배포 때 활성 항목을 바꾸거나 지움

### 10.1 상대 날짜 질문 분류 (#454)

고정 대화에 "오늘 …"으로 물으면 같은 날짜인데도 `DIFFERENT_PERIOD` 되묻기로 끝났다(분류 프롬프트에 현재 날짜가 없었음). 되묻기도 사용 1회로 차감된다.

- ai가 요청 시작 때 `kst_today`(UTC+9 고정 오프셋)로 오늘을 계산해 `AgentContext.today`에 넣음. 시계는 `AnalysisService(clock=...)`로 주입
- `analysis@4`: 분류 user 본문 맨 앞에 `[오늘] 2026-11-10(화)`, 범위에도 요일. 상대 표현(오늘·어제·이번 주·지난주 등)을 실제 날짜 범위로 바꿔 비교(한 주는 월~일)
- core 요청에 날짜를 넣지 않음(계약 변경 없음. 시계 차이는 자정 전후 몇 초 범위)
- 범위 안의 더 좁은 기간도 다른 기간으로 봄(한 주를 골라 두고 "오늘"을 물으면 `DIFFERENT_PERIOD`)
- 실제 LLM으로의 확인은 kind에서 필요

## 11. 모델 등록 API (#367)

기존 `POST /api/v1/admin/model-versions`(SERVICE_OPS)에 `EvaluationEvidence.limitations`와 등록 출처 메타데이터 `registration`을 추가했다. JSON 업로드·일괄 등록 엔드포인트는 없다. 계약 원본은 [core OpenAPI](../../contracts/openapi/core-service.yaml)의 `RegisterModelVersion`·`ModelRegistrationMetadata`·`ModelRegistrationArtifact`, api-spec 5.2.

- `MODEL`의 `artifactUri` 누락은 등록 시 422. 기존 evaluation JSONB를 쓰므로 마이그레이션 없음(기존 행은 `limitations=[]`로 읽힘)
- `MODEL_REGISTER` 감사 detail에 `source`·`jsonSha256`·`manifestSha256`·`modifiedFields`·`artifactFiles` 기록. `ModelVersion` 응답에는 넣지 않음
- **해시·파일 크기는 클라이언트 신고**: 서버는 파일 원문을 받지 않으므로 실제 파일 일치·S3 존재·로딩·품질 승인을 확인했다고 표시하지 않음(사전 검사는 12장)
- 등록으로 approval·ACTIVE·활성화 이벤트가 생기지 않음. 요청의 승인 관련 값·알 수 없는 필드는 거부
- S3 산출물 준비는 [scoring 6절](scoring.md#6-모델-산출물-sha-256-업로드-절차-493)

### 11.1 요청을 만드는 순서 (web)

1. registration JSON **원본 바이트**의 SHA-256(`file.arrayBuffer()` → `crypto.subtle.digest`). 파싱·재직렬화한 JSON으로 계산하지 않음
2. `requests[]`를 모델별 카드로. 최상위 설명 키는 POST 본문에 보내지 않음
3. manifest도 원본 바이트로 해시. name·version·scope를 대조하고 해당 모델 `files[]`만 고름. manifest가 없으면 `manifestSha256` 생략·`artifactFiles: []`
4. 버킷 치환, `limitations` 확인(항목에 `evaluation.limitations`가 있으면 빈 배열도 그 값 유지)
5. 원본과 최종 값이 다른 필드 경로를 `modifiedFields`에(버킷 치환도 `artifactUri` 변경, 배열은 배열 필드 경로 하나)
6. 카드별로 개별 POST. 실패한 카드 때문에 성공한 레코드를 다시 보내지 않음

### 11.2 입력 규칙

| 필드 | 규칙 |
|---|---|
| `artifactUri` | MODEL이면 필수, 최대 2,048자 |
| `evaluation.limitations` | 선택, 생략 시 `[]`, 최대 100개, 항목마다 1~4,000자 |
| `registration.source` | `MANUAL`(기본) 또는 `JSON_IMPORT` |
| `jsonSha256` | `JSON_IMPORT`이면 필수 |
| `manifestSha256` | `artifactFiles`가 있으면 필수 |
| `modifiedFields` | 최대 100개·중복 불가. `kind`·`name`·`version`·`refId`·`artifactUri`와 `evaluation.*` 필드 경로만 |
| `artifactFiles[]` | 최대 100개. `file`은 1~255자 상대 경로(절대 경로·역슬래시·콜론·`.`·`..` 금지), `bytes` 0 이상, `sha256` 소문자 64자리 |

- `MANUAL`에는 해시와 비어 있지 않은 `modifiedFields`·`artifactFiles`를 보내지 않음
- 요청은 `evaluation.limitations`, 응답은 `evalResult.evidence.limitations`로 위치가 다름
- 오류: 400 `VALIDATION_FAILED`(구조·알 수 없는 필드·승인 관련 필드), 409 `MODEL_VERSION_CONFLICT`(중복, 기존 평가를 덮어쓰지 않음), 422 `MODEL_APPROVAL_REJECTED`(경로 누락·불완전 평가·잘못된 메타데이터). 서버는 필드별 errors 배열을 주지 않음

### 11.3 실제 core 브라우저 검증 재현

1. core 테스트를 `MODEL_BROWSER_LOCAL=true`, `MODEL_BROWSER_OUTPUT=<출력 디렉터리>`로 `test --tests '*ModelVersionBrowserIntegrationTest'`(일반 CI에서는 건너뜀). 테스트 포트 8080을 호스트 127.0.0.1:58087에 매핑
2. 생성된 `session.json`으로 `MODEL_LOCAL_CORE_SESSION`·`MODEL_REGISTRATION_FILE`·`MODEL_MANIFEST_FILE`을 설정하고 `npm run test:models -- --project desktop --grep '등록 JSON'`
3. core 테스트가 DB 저장과 비활성을 검사한 뒤 종료. 세션 파일은 커밋하지 않고 삭제

운영의 기존 서술 3.0·논술 3.1은 재등록하거나 활성화하지 않는다.

## 12. 모델 사전 검사 (#368)

등록 전에 S3 산출물의 존재·크기·해시와 메타데이터를 확인하는 읽기 전용 경로. 통과는 "파일·형식 확인"일 뿐 품질 승인·활성화 가능 상태가 아니며 자동으로 다음 단계로 넘기지 않는다.

- scoring `POST /internal/models/preflight`: 설정된 모델 버킷의 `models/` 경로만. manifest의 여섯 파일을 받아 존재·크기·SHA-256 검사. `config.json`·`train_info.json`·`score_cuts.json`만 최대 1MiB씩 읽고 가중치·tokenizer 본문은 받지 않음
- 메타데이터: 기존 `validate_metadata`와 config의 출력 수·regression 설정 검사. 실제 가중치 shape·로딩·추론은 범위 밖
- core `POST /api/v1/admin/models/preflight`(SERVICE_OPS) → 내부 토큰으로 동기 중계. HTTP 20초·재시도 없음, scoring 작업 예산 15초, 웹은 25초 후 중단
- 감사 `MODEL_PREFLIGHT`(`result=SUCCESS|FAILURE`, target_id null). upstream 장애도 실패 이력으로 남기며 제공자 원문 오류는 반환하지 않음. 평가 JSONB에 결과를 섞지 않음
- web: manifest의 여섯 파일과 입력 검증을 통과해야 검사 버튼 활성. 입력이 바뀌면 이전 결과 만료
- NetworkPolicy(local·prod): core egress 8001 → scoring, scoring ingress에 core. Compose·values에 `SCORING_URL`

### 12.1 체크섬 계약

`HeadObject(ChecksumMode=ENABLED)`로 조회한다. 작은 JSON은 실제 바이트 SHA-256으로 대조하고, 나머지는 S3 전체 파일 SHA-256만 인정한다. ETag·사용자 metadata·multipart COMPOSITE는 대체 근거가 아니다. 전체 SHA-256이 없으면 `CHECKSUM_UNAVAILABLE`로 실패하며 가중치 다운로드로 우회하지 않는다. `ChecksumType=FULL_OBJECT`만 있고 `ChecksumSHA256`이 없어도 실패다.

필요 권한은 기존 `scoring-s3-read`(ListBucket·GetObject)로 충분. JSON GET은 If-Match로 고정해 GetObjectVersion 권한을 요구하지 않는다. SSE-KMS 객체는 KMS 권한이 추가로 필요할 수 있다.

### 12.2 로컬 재현

1. 일회용 MinIO `quay.io/minio/minio:RELEASE.2025-09-07T16-13-09Z`를 `127.0.0.1:58100:9000`으로 실행(`MINIO_ROOT_USER=preflight-local`, `MINIO_ROOT_PASSWORD=preflight-local-test-only`)
2. 저장소 루트에서 `scripts/seed_model_preflight_local.py` 실행(새 버킷에 합성 파일 생성, 기존 버킷이면 실패). `output/issue368-request.json` 생성
3. scoring 환경에서 `INTERNAL_TOKEN=preflight-local-token`, `S3_ENDPOINT_URL=http://127.0.0.1:58100`, `S3_BUCKET=models`와 위 자격 증명으로 `python -m uvicorn tests.preflight_local_server:app --host 0.0.0.0 --port 58101`
4. core `test --tests '*ModelPreflightLocalIntegrationTest'`(`PREFLIGHT_LOCAL=true`, `PREFLIGHT_SCORING_URL`, `PREFLIGHT_REQUEST_FILE`)
5. 기대 결과: 정상 PASS, 가중치 해시 불일치 `HASH_MISMATCH`, 파일 누락 `FILE_MISSING`. 감사 SUCCESS 1·FAILURE 2, 등록 모델 0건

### 12.3 검증 상태

- kind(2026-11-10): core → scoring → MinIO 경로로 정상·해시 불일치·파일 누락 세 경우를 내부 API와 관리자 화면 양쪽에서 확인
- AWS: Pod Identity 연결·S3 읽기 정책 확인. 기존 두 모델 12개 객체의 SHA-256 보완과 CloudShell 자격 증명 사전 검사 PASS([scoring 6.5](scoring.md#65-실행-결과와-남은-검증-2026-11-10))
- **남은 것**: scoring replicas=0이라 실제 Pod Identity 자격 증명의 읽기와 관리자 → core → scoring 경로는 미실행

## 13. Pod별 모델 로딩 보고 (#370)

scoring의 `model.loading.reported` 전체 상태 이벤트와 30초 heartbeat를 core가 `model_loading_report`(V37)에 모으고, SERVICE_OPS 조회 API와 활성 모델 카드에서 최근 보고 Pod 대비 로딩 완료 수·실패·기존 모델 유지·보고 만료를 구분해 보여 준다. 로딩 성공을 품질 승인으로 표시하지 않는다.

| 방식 | 검토 결과 |
| --- | --- |
| scoring → RabbitMQ 결과 이벤트 + heartbeat | 채택. 기존 events.topic과 core 소비 구조 재사용. 발행 장애는 로딩·추론을 막지 않고 다음 전체 보고로 복구 |
| core → scoring Service 단일 조회 | Pod 하나만 확인하므로 전체 상태로 표현할 수 없음 |
| core → Kubernetes API로 Pod 열거 | 새 클러스터 권한과 서비스 탐색 결합이 필요해 제외 |

계약:

- 이벤트 `model.loading.reported`(schema v1): Pod명, 프로세스별 UUID, 단조 증가 sequence, 전체 모델 상태. target name/version/revision과 현재 메모리에 남은 버전을 구분. 실패에는 예외 유형만
- 발행은 2초 제한·단일 태스크. 새 로딩 실패 시 기존 모델 유지 동작은 그대로
- core는 프로세스별 최신 전체 상태 저장. 같은 instance의 중복·역순 sequence는 무시, 같은 Pod명은 가장 최근 보고 프로세스만 조회
- `GET /api/v1/admin/model-loading`(SERVICE_OPS). 상태는 승인·평가 JSONB에 저장하지 않음
- 120초 이상 보고가 없으면 stale로 표시하고 집계에서 제외. 24시간 지난 기록은 매시간 정리. 축소·비정상 종료·통신 장애는 모두 "보고 만료"로 표현(죽은 Pod라고 단정하지 않음)
- **화면 분모는 최근 보고된 Pod 수**. 전체 배포 replica 수는 모르므로 전체 배포 성공으로 표시하지 않음. 보고 0개는 미확인
- 현재 활성 모델의 name/version/revision이 모두 일치할 때만 완료 수에 포함

배포 순서: V37 migration → RabbitMQ definitions(새 core 큐·재시도·DLQ, 감사 큐 바인딩 `model.loading.reported → core.event.audit`) → core → scoring → web. 새 큐를 추가하면 `RabbitDefinitionsTest`(감사 바인딩)와 관리자 큐 조회 allowlist도 함께 맞춘다.

검증:

- 로컬 2프로세스: `MODEL_LOADING_LOCAL=true`, `SCORING_TEST_PYTHON=<scoring Python>`으로 core `test --tests '*ModelLoadingLocalIntegrationTest'`, 이어서 web `MODEL_LOADING_LOCAL=true npm run test:models`
- kind 실제 Pod 2개(2026-11-10): 가중치를 깨진 파일로 바꾸고 레플리카를 2로 늘려 `observedPods 2, loadedPods 1, failedPods [새 Pod]`와 화면의 실패 Pod·오류 유형·보고 만료 표시 확인. 확인용 `model_version` 행은 활성화 해제 API가 없어 DB에서 삭제

## 14. 리포트 설명 API (#477, 2026-11-10)

에픽 #473(설명 sLLM)의 ai 몫. report가 대표 답변마다 부르면 M2 항목 점수와 학생 글로 학부모용 설명을 만든다(api-spec 4.2.3). 설명 모델이 활성이 아니면 `{active:false}`.

| 경로 | 요청 | 응답 |
|---|---|---|
| `POST /internal/report-explanations` | `{grade, inputType, text, scores}` | `200 {active:true, explanation:{text, quote\|null}, versions}` · `200 {active:false}` · `400`·`422 AI_EXPLANATION_REJECTED`·`503 AI_UNAVAILABLE` |

| 항목 | 결정 | 근거 |
|---|---|---|
| 설명 항목 | 가장 높은 항목(잘한 점) 1개 + 가장 낮은 항목(함께 이야기해 볼 점) 1개. 서술 총점 `hol` 제외 | 학습 데이터 이유 문장이 항목당 1문장. 9항목 전부는 CPU에서 느림 |
| 인용 구절 | 설명과 낱말 앞 두 글자가 2개 이상 겹치는 학생 글 문장 중 가장 많이 겹치는 것, 없으면 null | 모델에게 구절까지 만들게 하면 틀리기 쉬움. 원문 문장을 잘라 써 부분 문자열 조건을 항상 만족 |
| 활성 확인 | 레지스트리 `MODEL` `report-explanation`, scope `explanation/grade-{학년}/{narrative\|essay}`. `ActiveVersions`가 PROMPT와 함께 보관 | 기존 활성 목록·이벤트 수신 재사용 |
| 클라이언트 | `OpenAICompatibleLlm` 두 번째 인스턴스(`EXPLANATION_BASE_URL`·`EXPLANATION_MODEL`), 재시도 0. 주소가 없으면 설명만 503 | 다른 호출의 `LLM_PROVIDER`는 그대로 |
| 생성 방식 | 평문 스트림을 모음(JSON 구조화 출력 안 씀), `callType = REPORT_EXPLANATION` | LoRA가 평문으로 학습 |
| 후처리 | 숫자나 금지어(레벨·등급·점수·사고력·IQ·상위·하위·뒤처·영재)가 있는 문장을 버리고 항목당 앞 2문장. 남는 문장이 없으면 422 | 전문가 문장에 점수 표현이 섞임. 생성형 AI로 말투를 바꾸지 않음(NFR-DAT-03) |
| 문장 틀 | `잘한 점: …` / `함께 이야기해 볼 점: …` | |
| 시간 | 항목 1회 60초, 요청 마감 125초, 최대 256토큰(설정값) | CPU 실측(#475) 전 임시값 |

학습 입력 형식(#475와 고정, 문구를 바꾸면 `PROMPT_VERSION`과 학습 쌍을 같이 바꿈):

```
system: 너는 초등학생 글의 한 평가 항목에 대해 전문가가 쓴 이유 문장을 쓴다. (app/report_explanation/prompts.py SYSTEM)
user:   [학년] 초{학년} [항목] {항목 이름} [점수] {점수}
        {학생 글}
target: 그 항목의 전문가 이유 문장(71818 score.personal.*.feedback 원문)
```

- 항목 이름: 서술 과제 수행·명료성·구체성·적절성·연결성·통일성·어휘·어법, 논술 구성·내용·표현
- 확인 필요(#475): 논술 M2는 545 데이터의 `{org,cont,exp}`인데 이유 문장은 71819에만 있어 항목 체계가 다름
- 남은 확인: 실제 sLLM 서버(#476)와 학습 모델(#475)로 생성 시간·후처리 통과율 측정

## 15. 교육과정 지식 RAG 계약 (#464, 2026-11-11)

에픽 #463 계약 고정의 ai 몫. 구현(#467 임베딩, #470 검색 연결) 전 계약이며 값은 기준안(팀 확인 전)이다. 테이블·샘플·결정 전체는 [learning 28장](learning.md#28-교육과정-지식-rag-계약-고정-464-에픽-463-2026-11-11).

- C6 임베딩([api-spec 4.2.4](../design/api-spec.md#424-지식-임베딩-463-계약-464-c6-구현-467)): `POST /internal/embeddings` `{texts[]}` → `{model, dimensions, vectors[]}`, 1~64개·본문당 8,000자, 502·503. 계약 고정 당시 OpenAPI에 `x-implementation-status: planned-issue-467`, 사용량 `callType`은 #467에서 추가(16장에서 구현·표시 제거)
- C7 근거 칸([api-spec 4.2.5](../design/api-spec.md#425-미션-초안-근거-칸-463-계약-464-c7-구현-470)): 미션 초안 요청 `knowledge`(C5 standards 응답 그대로, 선택), 응답 `sources`(근거 조각 표시, 빈 배열 허용). OpenAPI 칸에 `planned-issue-470`. `mission_draft/models.py`는 바꾸지 않았다(#470)
- `app/knowledge/contracts.py`: C5·C6·C7 pydantic 모델, `KnowledgeApi`·`Embedder`·`KnowledgeRetriever` Protocol, `RetrievalResult`(근거 없음은 예외 대신 `fallback` 사유), `sources_of`
- `app/knowledge/fake.py`: 표준 라이브러리만 쓰는 가짜(계약 시험이 pydantic 없이 불러 씀). 샘플을 활성 판 하나로 올린 `FakeKnowledgeApi`(다섯 경로, 인증·400·409 포함), 글자 2개 조각 해시 벡터 `FakeEmbedder`(모델 `fake-bigram-v1`, 같은 글 같은 벡터), `as_knowledge_api()`·`as_embedder()`(Protocol 만족), `mock_transport()`(httpx), `serve()`(로컬 HTTP)
- 검증: `tests/knowledge/test_contracts.py` 29개(모델 칸·필수 = OpenAPI, 사유·상한 = OpenAPI·가짜, Protocol 통해 응답, MockTransport·HTTP 서버), `scripts/tests/test_knowledge_contracts.py`(learning 28장). `test_ai_openapi.py`는 구현 전 표시 경로를 라우터 대조에서 뺌(라우터 8개 그대로)

## 16. 지식 임베딩 API (#467, 2026-11-11)

15장 계약 C6 구현. learning 지식 적재·관계 후보 스크립트·ai 검색 클라이언트가 이 API를 부른다.

- `POST /internal/embeddings` `{texts[], purpose?}` → `200 {model, dimensions, vectors[]}`(순서·개수 보존). `400`(0개·65개 이상, 빈 글, 8,000자 초과), `502 AI_BAD_RESPONSE`·`503 AI_UNAVAILABLE`
- 설정: `EMBEDDING_PROVIDER`(openai\|fake)·`EMBEDDING_MODEL`(text-embedding-3-small)·`EMBEDDING_DIMENSIONS`(1536)

| 항목 | 결정 | 근거 |
|---|---|---|
| 시간 기준 | LLM 공통 `LLM_TIMEOUT` 15초·재시도 1회 그대로 | 임베딩은 보통 1~2초. 새 설정이 늘지 않음 |
| 제공자·주소 | `openai`는 `OPENAI_API_KEY`를 쓰고 `OPENAI_BASE_URL`은 쓰지 않음. 키가 없으면 임베딩만 503, 서버는 기동 | `OPENAI_BASE_URL`은 sLLM 대화용이라 임베딩 모델이 없을 수 있음 |
| 가짜 전환 | `fake`면 계약 가짜 규칙(`fake-bigram-v1`) 벡터를 돌려주고 사용량을 남기지 않음 | 키 없이 로컬·시험에서 연동 확인 |
| 구조 | `app/llm/embeddings.py` `EmbeddingClient`, `app/embedding/` 라우터·서비스. `EmbeddingService`가 `Embedder` Protocol을 만족 | 검색 클라이언트가 HTTP 없이 같은 객체 사용 |
| 순서·검사 | 응답 `data`를 `index`로 정렬. 개수·차원이 요청과 다르면 재시도 대상 → 재실패 시 502 | learning 판 차원 보호 |
| 사용량 | 요청 1회 = 1건, `callType = KNOWLEDGE_EMBEDDING`, `outputTokens` = 0 | 0으로 남겨야 단가가 생겼을 때 입력 토큰만으로 계산됨([core 19장](core-gateway.md#19-지식-임베딩-사용량-knowledge_embedding-467-2026-11-11)) |
| 상한 | 개수 64·글자 8,000은 계약 고정값(설정으로 만들지 않음) | 설정으로 바꾸면 OpenAPI·가짜·learning 대역과 어긋남 |

한계:

- OpenAI는 입력 하나 8,192토큰 제한이 있어 한국어 8,000자 글은 넘을 수 있음(지금 조각은 짧아 해당 없음)
- 실측(2026-11-11): 관련 문장 쌍 코사인 0.46, 무관한 쌍 0.12. 계약 기준안 `DEFAULT_MIN_SIMILARITY = 0.7`이면 근거가 대부분 `BELOW_THRESHOLD`가 될 수 있어 실제 적재 데이터로 기준값을 다시 재야 함(#466·#470)

## 17. 주간 테마 초안 생성 (#437)

에픽 #436의 ai 몫. 계약은 api-spec 4.2 `POST /internal/theme-drafts`, 구조는 class-diagram 5.5, learning 쪽 작업·저장은 [learning 31절](learning.md#31-테마-초안-작업학년별-테마이야기-열람-438). 코드는 `app/theme_draft/`(`graph.py`, `nodes/`, `checks`).

그래프: `retrieve → plan_theme → check_theme(→ fix_theme) → generate_mission ×5 → generate_dialogue ×5 → review_story → generate_images → generate_videos → generate_motion`.

### 17.1 정한 내용

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 호출 단위 | 요청 1번에 그래프 1회. 그래프 안에서 실패한 부분만 사유를 넣어 다시 생성(단계마다 상한 2회), 마감까지 180초 미만 남으면 다시 생성을 시작하지 않음. 그래도 실패하면 learning이 다시 호출 | 단계가 많아 실패한 부분만 다시 만드는 편이 비용·시간이 적음 |
| 실패 | 끝내 실패하면 200 + `failure{stage, reasons}`(`THEME`·`MISSION`·`REVIEW`·`IMAGE`). 대화·영상·움직임은 그 항목만 빼고 성공 + `warnings`. 형식 밖 응답 502, 그 밖·마감 초과 503. 줄거리 실패만 `theme: null` | 만든 것까지 함께 돌려줘 관리자가 볼 수 있게 |
| `previousFailures` | `stage`는 네 값만(그 밖 422), `reasons` 1개 이상. `MISSION` 사유는 `<요일> <검사 코드> <자세히>`로 시작해 그 요일 미션 재생성에만 사용 | 응답 `failure.stage`와 같은 값이라 learning이 그대로 돌려줌 |
| 요일 배치 | 월 `ANALYZE`·화 `EVALUATE`·수 `CREATE`·목 `SOLVE`·금 `REFLECT`(기준안). learning이 다시 검사 | 에픽 확인 필요 |
| 정답 구조 | 후보는 모든 학년 4개. 요일별 단서마다 `rulesOut`(빈 배열 허용). 정답은 어떤 단서로도 빠지지 않고 틀린 후보는 모두 빠지며, 마지막 틀린 후보는 목요일 이후(기준안) | 후보 3개면 월~수 단서가 밋밋해짐. 금요일 최종 고르기 전에 답이 정해지지 않게 |
| 단서 논리 판정 | 줄거리가 후보 특징 표(`features`)와 요일별 단서 조건(`condition`: `RULE`·`HINT`, 특징, 허용 값)을 내부 칸으로 만들고 **코드가 표로 판정**. `rulesOut`은 LLM이 쓰지 않고 코드가 채움. 단서 문장에는 허용 값 낱말이 모두 들어가고 허용 밖 값 낱말은 없어야 함 | LLM이 문장과 논리를 한 번에 쓰고 검토 LLM이 사후 판정하면 논리 빈틈이 반복됨(논리 구조를 먼저 만들고 기계로 검증하는 방식: MuSR arXiv 2310.16049) |
| 단서 규칙 | 단서는 그날 장면의 이야기 속 사실(문제 활동 결과에서 만들지 않음). 40자 이내. 큰 질문·제목·월~목 장면에 정답 이름 금지. 허용 값이 여럿이면 "그중 한 곳"이라는 뜻으로 쓰고 `RULE` 단서는 단정(`CLUE_WORDING`) | 텍스트 시험에서 실패한 유형 |
| 단서 공개 | 단서(`days[].clue`)는 학생이 그날 미션을 마친 뒤 learning이 공개(#484). 미션 전 대화 끝 두 줄은 코드가 그대로 넣는 `discovery`(증거 발견 줄)와 `missionHook`(수사 연결 문장, 뭉치). 둘 다 후보·정답을 말하지 않음 | 미션을 마쳐야 단서를 얻는 구조. 서술형 미션과도 맞음 |
| 뭉치 역할·콘티 | 뭉치는 물건을 잃은 당사자가 아니라 사건을 해결하러 가는 주인공, 찾는 대상의 주인은 등장인물. 시작 4컷(평소 모습 → 사건 → 뭉치 출동 → 현장 도착), 종료 4컷(단서 정리 → 정답 장소 → 돌려줌 → 축하). 시작 콘티에 정답 장소 금지 | 사용자 결정 2026-11-11 |
| 미션 생성 | 미션 초안 생성·검사(9장) 재사용 + 테마 이야기 조각. 그날 장면·증거를 문제 소재로 써도 되지만 정답 쓰기·정답 추리 문제·미션 답이 단서가 되는 것은 금지. 미션 입력에 단서를 넣지 않음. 비교·점검할 글이 필요하면 문제 글에 직접 넣음. 테마 미션 질문 상한 400자(기준안) | 사건 자료를 막으면 미션이 이야기와 따로 놂. 단서를 주면 아직 못 얻은 단서가 샐 수 있음 |
| 미션 검토 | 검토 모델이 미션마다 예시 답이 요구를 채우는지, 성취기준 행동·생각 유형과 맞는지, 그날 글만 읽고 풀 수 있는지 확인. `FAIL`은 그 미션만 다시 생성 | 줄거리를 다시 만들 때마다 미션이 새로 생겨 마지막에야 문제가 드러났음 |
| 글로 대신하는 활동 | 학생은 글로만 답함. 듣기·말하기·발표·조사·실험·그리기처럼 글로 직접 할 수 없는 활동은 글로 대신하는 형태로(`TEXT_ONLY`) | 성취기준 행동을 그대로 요구하면 풀 수 없는 문제가 됨 |
| 검토 모델 | 생성과 다른 모델(기준안 생성 `gpt-6-luna`, 검토 `gpt-6.1-terra`). 테마 전용 설정 `THEME_GENERATION_MODEL`·`THEME_REVIEW_MODEL`. 두 값이 같거나 키가 없으면 테마 경로만 `503`(`retryable: false`) | 팀 운영 키가 OpenAI뿐. 기동을 막으면 판정·되묻기까지 멈춤 |
| 시간 | ai 마감 15분, learning→ai 16분, 리스 18분(기준안). LLM 호출 타임아웃 300초·재시도 0. 남은 시간이 모자라면 영상부터 건너뛰고 경고 | 실측 한 테마 약 8.3분 |
| 저장 | 이미지·영상은 ai가 S3 `theme-drafts/{실행 ID}/{장면}`에 올리고 키만 반환 | |
| 그림 | OpenAI `gpt-image-2.6-sunburst`, 1536×864, 14장(테마 옷 뭉치 1 + 미션 그림 5 + 시작·종료 컷 첫 그림 8, 테마당 약 $0.7). 테마 옷 뭉치와 인물 기준 그림을 참조로 넣어 얼굴·비율 유지. 검토 모델이 뭉치 모양·정답 노출·글자·안전·장면 일치·미션 맞음을 확인해 실패한 그림만 다시. 생각 풍선은 그리지 않음(정답이 드러날 뻔함) | |
| 그림체·뭉치 | 2D 만화풍. 기본 뭉치 그림(`assets/`, 기준안)을 고쳐 테마 옷만 더한 그림을 모든 그림의 첫 참조로 | 차림마다 따로 그리면 크기·얼굴 위치가 달라짐 |
| 영상 | Google `veo-3.1-fast-generate-001`, 720p·무음, **시작·종료만**(요일 영상 없음). 컷 4개(4·6·8·6초)를 첫 그림만 고정해 만들고 0.5초 겹쳐 22.5초 한 파일(ffmpeg). 기본 `THEME_VIDEO_ENABLED=false` | 매일 영상은 문제 앞 기다림이 됨. 시작·끝 모두 고정하면 움직임이 흐물거림 |
| 영상 검사 | 검토 모델이 1초마다 뽑은 장면으로 `MORPH`·`CONTINUITY` 등 확인, 멈춤은 코드 검사(`FREEZE`). 실패한 컷만 다시, 끝내 실패하면 첫 그림을 천천히 확대하는 컷으로 대신하고 경고 | |
| 콘티 동작 | 뭉치는 제자리 작은 동작·표정만(손짓·건네기·뛰기는 사람만), 누구도 화면 쪽으로 다가오거나 나가지 않음(`CUT_ACTION`) | 영상 모델이 뭉치에게 팔을 만들거나 인물이 사라짐 |
| 움직임 | 장면마다 JSON 형식 v1(`transition`·`camera`·`speakers`·`effects`·`captions`·`spots`). 상한 밖 숫자는 코드가 맞추고 경고. 영상 속 글자 없이 문구는 `captions`로 웹이 표시 | 관리자가 이야기 글을 고치면 영상 글자와 달라짐 |
| 살펴보기 `spots` | 요일 그림 속 누를 물건 2~3개(증거 물건 1개). 한마디가 단서 결론·후보·정답을 말하면 그 물건을 뺌 | 미션 전이라 증거 발견 줄과 같은 기준 |
| 사용량 | `THEME_DRAFT`·`THEME_IMAGE`·`THEME_VIDEO`. `THEME_VIDEO`는 core enum·DB 제약에 들어간 뒤에만 이벤트 발행(그 전에는 로그만) | 먼저 보내면 DLQ(`MISSION_DRAFT` 선례) |
| 지식 검색 | `retrieve` 노드 자리만 두고 기능 스위치(기본 꺼짐) | 연결은 #470 |

### 17.2 실측 (2026-11-11)

- 글 단계(서비스 자동 입력 20건): 통과율 65% → 80% → 줄거리 단계 20/20. 줄거리 단계 평균 163초, 20건 합계 약 $0.17
- 전체(초4, 그림·영상 포함): 통과, 498초, 그림 14장 다시 그림 없음, 영상 컷 8개 통과. 비용 약 $4~5(영상 48초 × 약 $0.08이 대부분. 단가는 제3자 자료 기준이라 청구로 확인 필요)
- 초3 통과율이 가장 낮음: 학년군 표에서 4학년 성취기준이 뽑혀 검토 `GRADE_VOCAB`·`STANDARD_FIT` 실패(learning 자동 성취기준 한계)
- 남은 품질 문제(검사는 통과): 미션이 사건과 무관한 내용이 되거나 수사 연결 문장과 문제 소재가 어긋나는 경우
- 실측 도구와 실험 코드는 저장소 밖

### 17.3 남은 확인

- 요일↔유형 배치, 후보 수, "마지막 틀린 후보는 목요일 이후" 기준안(P23 개정 필요)
- 영상 운영 인증(17.4, #538 인프라 확인)·예산
- 정답 고르기·엔딩 판정과 단서 공개 조건(그날 미션 완료)은 learning #484, 단서 카드·수첩·후보 지우기는 웹 #440
- core `THEME_VIDEO` 반영 시점
- 운영 환경 변수에 테마 모델 두 값을 넣을지(배포 담당)
- 관리자 화면에 단서 근거(특징 표)를 보여 주려면 계약 추가 필요. learning은 `rulesOut` 수준까지만 다시 검사
- 기본 뭉치 그림은 기준안(앱 원본 그림이 저장되면 교체)
- 관리자 부분 다시 생성, 학년에 맞는 성취기준 고르기는 후속
- 발견: `followup/leak_guard`의 금지어 비교가 숫자 경계 없이 부분 문자열이라 금지어 '6장'이 질문의 '26장'에서 잡힘(미션 초안 경로에도 같은 오탐 가능)

### 17.4 영상 운영 인증 (#538, 2026-11-12)

고정 `VIDEO_ACCESS_TOKEN`(약 1시간 만료, 갱신 경로 없음)을 Google 표준 자격 증명으로 바꿈. 인증 방식(서비스 계정 키·WIF)은 코드가 아니라 `GOOGLE_APPLICATION_CREDENTIALS`가 가리키는 파일로 정해짐.

| 항목 | 내용 | 근거 |
|---|---|---|
| 토큰 공급 | `TokenSource`(`async token()`). `GoogleTokenSource`가 `google.auth.default(scopes=cloud-platform)` 자격 증명을 `valid`가 거짓일 때만 갱신(`asyncio.to_thread`, 잠금으로 동시 갱신 1번) | 이벤트 루프를 막지 않고 컷 4개 동시 생성 때 갱신이 겹치지 않게 |
| 요청 | `VeoVideoClient`가 시작·대기 요청마다 토큰을 받음 | 컷 하나가 최대 400초 대기라 대기 중 만료돼도 갱신되게 |
| 갱신 실패 | `RefreshError` → `LLM_AUTH_FAILED`(재시도 안 함), `TransportError` → `LLM_CONNECTION`(재시도 가능) | 기존 Veo 상태 코드 분류와 같은 기준 |
| 자격 증명 없음 | 영상 켜짐 + `VIDEO_PROJECT`일 때만 찾고, 못 찾으면 경고 로그 뒤 영상만 건너뜀 | 지금과 같은 동작 |
| 설정 | `VIDEO_ACCESS_TOKEN` 삭제(사용자 결정). 로컬은 `gcloud auth application-default login`의 ADC를 그대로 읽음 | 경로를 하나로 |
| 의존성 | `google-auth[requests]>=2.40`(lock 2.62.2) | 공식 자격 증명 라이브러리 |
| 운영(기준안) | Veo를 실측한 개인 GCP 프로젝트의 Veo 전용 서비스 계정(`roles/aiplatform.user`) 키 → Secrets Manager → ExternalSecret 파일 마운트 → `GOOGLE_APPLICATION_CREDENTIALS`. WIF(EKS OIDC)는 대안. PC의 ADC는 운영에 쓰지 않음 | 사용자 결정 2026-11-12, PM·인프라 확인 전. 비용은 개인 결제 계정으로 청구 |

- 로컬 확인(2026-11-12): ADC로 갱신 성공, 없는 Veo 작업 조회가 404(인증 통과). 실제 영상 생성은 비용 때문에 하지 않음
- 인프라 확인(담당자와): 인증 방식 확정, GCP 권한·Veo 동시 요청 할당량, ai-service 서비스 계정 생성(지금 `create: false`)과 S3 쓰기 IRSA, 영상 env(`THEME_VIDEO_ENABLED`·`VIDEO_PROJECT`·`VIDEO_LOCATION`·`VIDEO_MODEL`·`ASSET_S3_BUCKET`·`GOOGLE_APPLICATION_CREDENTIALS`), 자원 한도(메모리 512Mi·CPU 500m, 컷 다시 인코딩에 모자랄 수 있음, 측정 안 함)
- 자격 증명을 못 찾으면 google-auth가 GCE 메타데이터 서버를 확인하는데 네트워크 정책이 `169.254.0.0/16`을 막아 기동이 몇 초 늦어질 수 있음(영상 켜짐 + `VIDEO_PROJECT`일 때만)

## 18. 추억 임베딩 구분·추억 설명 API (#565, 2026-11-12)

P27 추억 검색(에픽 #562)의 ai 몫. 계약은 [api-spec 4.2.4·4.2.6](../design/api-spec.md#426-추억-설명-p27-구현-565), 결정은 [리텐션 확장 9.2](retention-expansion.md#92-ai-추억-임베딩-구분추억-설명-api-565-2026-11-12)에 있다.

- 임베딩: 요청 `purpose`(`KNOWLEDGE` 기본·`MEMORY`)로 사용량 `KNOWLEDGE_EMBEDDING`·`MEMORY_EMBEDDING`만 가른다. 생략한 기존 호출은 그대로 `KNOWLEDGE_EMBEDDING`. 가짜 `FakeEmbedder.handle`도 `purpose`를 받는다
- 설명: `POST /internal/memory-explanations`, 모듈 `app/memory_explanation/`(router·service·models·checks·prompts·fake). 기본 LLM 1회, 사용량 `MEMORY_EXPLANATION`, 프롬프트 `memoryExplanation`(`memory-explanation@1`)
- 설정: `MEMORY_EXPLANATION_PROVIDER`(`llm` 기본·`fake`), `MEMORY_EXPLANATION_MAX_TOKENS`(512, 기준안)
- 시험: `tests/memory_explanation/`(정상·400·422·502·503·401, 가짜 규칙이 검사를 늘 통과, 로그에 원문 없음, OpenAPI 대조), `tests/embedding/`(purpose별 사용량·400), `scripts/tests/test_ai_openapi.py`(경로 11개·`/versions` 9개 키·응답 코드·purpose 값)
- 확인 필요: 실제 LLM(기본 `OPENAI_MODEL`)으로 문장 수·근거 번호·인용 규칙 준수율과 응답 시간 실측(비용 때문에 #565에서는 하지 않음). learning #564 연동 뒤 kind에서 한 번 확인
