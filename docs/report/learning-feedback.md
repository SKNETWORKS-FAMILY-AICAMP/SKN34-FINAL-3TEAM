# 이슈 #25 learning 피드백 오케스트레이션 (규칙 판정·ai 판정·되묻기)

작성일: 2026-10-27. 기준: #76 머지 후 develop 826e4dc 위에서 작업, PR #78 리뷰 반영 때 develop 9a372c5(#77 머지)를 병합. [이슈 #25](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/25), [아키텍처 1.3·2.5](../design/architecture.md), [API 명세 1.4·2.2·3.2·4.1·4.2](../design/api-spec.md), [ERD 4.2](../design/erd.md), [기능 명세 FN-JDG-01~10](../design/functional-spec.md), [시퀀스 다이어그램 3.2](../design/sequence-diagram.md), [상태 다이어그램 3.3](../design/state-diagram.md), [클래스 다이어그램 4.2](../design/class-diagram.md).

learning-service의 `POST /internal/answers/{answerId}/feedback`을 만들고, 시도 상세의 `answers[].feedback`·`nextActions`를 채우면서 정한 내용과 근거를 기록한다. 데이터베이스 스키마는 바꾸지 않았다.

## 설계 문서 갱신

| 문서 | 변경 전 | 변경 후 | 근거 |
|---|---|---|---|
| [api-spec 4.1](../design/api-spec.md) | 피드백: "규칙 판정 또는 ai 호출 → 저장 → 결과 반환 (동기)" | 200 결과 모양(3.2 `result`와 같음, `elementId`는 `rubric_element.id`, `versions`는 `미션 code@버전`), 처리 중 `200 {status:"RUNNING", judgment:null, followup:null, nextActions:[], versions:null}`, 실패 `503 AI_UNAVAILABLE` + `retryable`, `nextActions` 규칙, 판정 전이 충돌 `409 JUDGMENT_STATE_CONFLICT`(내부 방어 코드) | core(#39)가 SSE로 바꿀 때 상태별 응답이 필요. 처리 중 응답의 HTTP 상태는 문서에 없었음 |
| [class-diagram 4.2](../design/class-diagram.md) | `saveResult(judgmentId, judged, followup)`·`markFailed(judgmentId, code)`, `done(result, elements, versions)`·`hold(reason)` | `saveResult(judgment, judged, followup)`·`markFailed(judgment, code)`, `done(result, elements, by)`·`hold(reason, by)`, 조회 메서드 `target`·`followupCount`·`bankQuestion`·`results(attemptId)` 추가, 처리 순서 설명에 풀이 결합·유출 검사용 정답·질문 은행 선택·엔티티와 조건부 UPDATE의 역할 | 저장·실패 기록은 획득한 리스 값과 비교해야 해 ID 대신 `acquire`로 얻은 `Judgment`가 필요. `by`는 판정 방법·trial·모델·프롬프트 버전(보류도 기록). 클래스·관계(엔티티 `Judgment`·`JudgmentElement`·`Followup`, `FollowupRepository`, `FeedbackFacade --> RuleJudge`·`RuleJudge.judge(answer, answerKey) Judged`, `FeedbackFacade --> AttemptService : 타임라인`)와 `result(answerId)`는 원래 설계 그대로 |
| class-diagram 4.1 | - | `MissionService.rubric(missionVersionId, rubricVersionId)`, `AttemptService.timeline(attemptId)`, `Attempt.acceptsAnswers` | `FeedbackFacade --> MissionService : 기준표·정답 키`, `FeedbackFacade --> AttemptService : 타임라인`(본인 시도 확인 + 각 답변이 답한 되묻기 질문이 있는 타임라인). 마무리한 시도에는 되묻기를 만들지 않음 |
| [sequence-diagram 3.2](../design/sequence-diagram.md) | 되묻기 조건에 마무리 없음, 처리 중·결과 응답의 HTTP 상태 없음, 저장·실패 기록의 리스 조건 없음 | 되묻기는 마무리·완료 전만, 처리 중 `200 {status: RUNNING}`(나머지 null)·결과 `200`, 저장·실패 기록은 획득한 리스일 때만(잃었으면 저장 없이 현재 상태). 분기("고르기·수학 최종 답 → 규칙 / 서술·논술·풀이 단계 → ai")는 원래 그대로: 풀이 단계 답변은 최종 답을 규칙, 풀이를 ai로 보고 합침 | 마무리한 시도에는 답변을 받지 않음(P04, #24). 리스 조건은 state-diagram 3.3 |
| [state-diagram 3.3](../design/state-diagram.md) | 결과 결정 표에 풀이 단계 없음 | 풀이 단계 결합 규칙, `failure_code` 값, 획득 조건에 리스 없는 `RUNNING`(`lease_until IS NULL`)도 만료로 | 아래 "임시로 정한 것", 실패 코드는 문서에 값 목록이 없었음. 리스 없는 `RUNNING`은 엔티티(`isLeaseExpired`)가 만료로 보는데 SQL은 가져가지 않아 기준을 맞춤(PR #78 리뷰). 전이 담당(`Judgment.acquire`·`done`·`fail`)과 조건부 UPDATE는 원래 설계 그대로 구현 |
| [api-spec 2.2](../design/api-spec.md) 판정 규칙 | "고르기·수학 최종 답: 규칙 / 서술·논술: LLM" | 풀이 단계 줄 추가(풀이 LLM + 최종 답 규칙을 합침) | 위와 같음 |
| api-spec 1.4 | 피드백 `RUNNING`은 "새로 실행하지 않고 status"까지 | 그사이 다른 요청이 실패한 경우도 처리 중으로 응답하고 다시 요청하면 실행 | 판정 전이 충돌 코드(state-diagram 1.3 "불허 시 409")는 내부 방어 코드라 1.3 공통 오류 표가 아니라 4.1 비고에만 둠(PR #78 리뷰 의견). 그사이 실패한 경우를 200 `FAILED`로 보내면 core #39(DONE·RUNNING·503만 처리)가 다룰 수 없음 |
| api-spec 4.1 시도 상세 | `answers[].feedback:{status, nextActions}`, "판정 결과·되묻기는 #25" | `feedback`은 피드백 결과와 같은 모양, 시도 `nextActions`는 마지막 답변 기준 | #24에서 남긴 자리 |

## 구현에서 정한 것 (설계를 따르거나 설계에 없던 값을 채운 것)

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 처리 상태 전이 | `PENDING`·`FAILED`·리스 만료 `RUNNING`만 `RUNNING`으로(리스 90초). 0행이면 `DONE`은 저장 결과, 그 밖은 처리 중 응답. 리스 없는 `RUNNING`도 만료로 봄(엔티티·SQL 같게) | state-diagram 3.3, api-spec 1.4, P12 |
| 끝낼 때 | 완료·실패 모두 `WHERE process_status='RUNNING' AND lease_until = 획득한 값`. 리스를 잃었으면 저장하지 않고 현재 상태 반환 | state-diagram 3.3 "늦게 끝난 이전 처리의 덮어쓰기 방지" |
| 엔티티와 조건부 UPDATE | `Judgment.acquire`·`done`·`hold`·`fail`이 전이 허용을 판단하고(허용 안 되면 `409 JUDGMENT_STATE_CONFLICT`), `JudgmentRepository`가 조건부 UPDATE(획득은 상태·리스 만료, 저장·실패는 리스 값)로 저장 | state-diagram 1.3 "엔티티 메서드가 전이 검사, 불허 시 409"와 3.3 조건부 UPDATE를 함께 따름. 엔티티가 판단하고 조건부 UPDATE로 저장하는 점은 #23 초안(`AttemptDraft.update` + `updateIfVersion`)과 같고, 설계 시그니처(`acquire(...) Boolean`, `done(...)`·`fail(...)`)대로 엔티티가 자기 상태를 바꿈. 엔티티가 판단한 뒤 그사이 다른 요청이 먼저 가져갔으면 UPDATE가 0행이라 물러남. 409 `JUDGMENT_STATE_CONFLICT`는 기존 409 코드 중 맞는 것이 없어 새로 정하고 api-spec 4.1 비고에 둠(정상 흐름에서는 리스 조건으로 막혀 발생하지 않는 내부 방어 코드라 1.3 공통 오류 표에는 넣지 않음) |
| 실패 기록 | `markFailed`는 DB에서 판정을 다시 읽어 이 요청의 리스일 때만 `fail`. 실패 기록 자체가 실패해도 원래 오류(503 `retryable` 또는 원래 예외)로 응답하고 기록 오류는 suppressed로 붙임, 판정은 리스(90초)가 끝나면 다시 가져감 | `saveResult`가 엔티티를 `DONE`으로 바꾼 뒤 저장 중 오류로 롤백되면 메모리의 엔티티만 `DONE`이라 그대로 쓰면 실패 기록이 안 남음. 기록 오류가 원래 오류를 가리면 학생에게 잘못된 응답이 감(PR #78 리뷰) |
| 트랜잭션 | 리스 획득·결과 저장·실패 기록을 각각 짧은 트랜잭션, ai 호출은 그 밖 | class-diagram 4.2, 아키텍처 2.5 |
| 판정 방식 | 고르기·순서·분류는 정답 키(`method=RULE`, `trial=false`), 서술·논술은 ai(`method=LLM`), 풀이 단계는 풀이 ai + 최종 답 규칙 | sequence-diagram 3.2, class-diagram 4.2, FN-JDG-01~03 |
| 규칙 판정 요소 | 기준표 요소마다 `verified=true`, `satisfied=정답 여부`, `source_type=ANSWER_KEY`, 인용은 고른 선택지 이름 | ERD `source_type`, 마무리 체크리스트(#26)에서 그대로 사용 |
| ai 판정 요소 | 근거 구절이 있으면 `AI_OBSERVATION`, 없으면 `source_type`·`quote` NULL. 기준표에 없는 요소 ID·검증 안 된 충족은 `AI_BAD_RESPONSE` | api-spec 3.2 예시, ERD 4.2 "근거가 없으면 NULL", CHECK `verified OR NOT satisfied`(도메인 `JudgmentElement.satisfy()`에서도 거부) |
| 되묻기 조건 | 시도 내 되묻기 2회 미만 + 고르기 활동 `CORRECT` 아님 + 마무리·완료 전 | P04, api-spec 2.2. 고르기 활동은 선택지·순서·분류 (FN-LRN-04) |
| 수학 `CORRECT` | 되묻기(한 걸음 더)를 만듦, `nextActions`는 `[ANSWER_FOLLOWUP, FINISH]`라 건너뛸 수 있음 | 이슈 #25 할 일 2줄은 "고르기·수학 CORRECT면 FINISH"지만 계약 문서 api-spec 2.2와 P04는 "고르기 `CORRECT`"만 되묻기 없이 마무리. 계약 문서를 따름. 이슈 문구는 기획서 5장 "문항 종류별 판정과 진행"(수학 최종 답을 규칙 찾기·순서 맞추기와 같은 "정답이 있는 문항"으로 묶음)에서 온 것으로 보임. 기획서도 맞았을 때 바로 끝내지 않고 "어떻게 알았어?"(답하지 않아도 됨)를 물어, 건너뛸 수 있는 되묻기와 같음. 설계 문서는 기획서를 좁혀 정함(되묻기 학년별 1~3회 → 최대 2회, 고르기 오답은 다시 고르기 → 까닭 되묻기, 고르기 정답은 바로 마무리) |
| 수학 단위 | 단위는 비교하지 않음, 앞쪽 수 표현만 동치로 비교(`30`·`30 ㎡`·`30 cm²` 모두 `30 m²`와 같음) | FN-JDG-02·usecase 4.3은 "분수·소수·한글 분수 등 동치 표현"까지만 정하고, 이슈 #25·기획서 5장에도 단위가 없음. 단위 비교는 단위 누락·환산(m·cm) 처리를 새로 정해야 해 설계에 없는 규칙이라 넣지 않음. #23 리포트(learning-mission.md 정답 키)의 "단위·동치 비교는 판정 규칙의 일"은 정답 키에 단위를 함께 저장한다는 뜻이고 비교 규칙은 정하지 않음 → 후속 확인 |
| 분류 문항 | 고르기 활동으로 정답 키 판정, 정답이면 바로 마무리 | FN-LRN-04(고르기 = 선택지·순서·분류)·FN-JDG-01, #22 구현. 기획서 5장은 "분류 기준"을 "정답이 여러 개인 문항"(이유를 봄)에 두지만, 이는 스스로 기준을 세우는 활동이고 정해진 그룹에 나누는 지금 분류 문항과 다를 수 있음. #22에서 정한 범위라 여기서는 바꾸지 않음 |
| 고르기 오답 | 다시 살펴보기 되묻기 후 보완 답변은 다시 고르기 | FN-JDG-01 "까닭을 묻는 되묻기". 보완 답변은 미션 입력 방식과 같아야 함(#24) |
| 질문 은행 | ai가 재생성까지 유출 검사에 실패(`question: null`)하면 같은 유형의 활성 질문 중 이 시도에서 아직 쓰지 않은 것을 생성 순으로. `source=BANK`, `bank_question_id`, `leak_check_passed=false`(ai 검사 결과 그대로), 모델·프롬프트 버전 없음(LLM 질문이 아님) | P16, ERD CHECK `ck_followup_bank_source`. 같은 시도에서 같은 질문을 두 번 보이지 않음 |
| 되묻기 요청 | 타임라인은 이 답변까지의 답변 원문(`plain_text`)과 각 답변이 답한 되묻기 질문을 순서대로, 판정 요약, 기준표 요소, 금지어·예시 답, 미션 제목·질문·생각 유형, 학년 | api-spec 4.2, ai `FollowupRequest` |
| 유출 검사용 정답 | DB `answer_key`(`{"choiceIds":[...]}` 등)를 학생에게 보이는 글자로 바꿔 보냄: 고르기는 선택지 이름, 순서는 정답 순서 전체("노랑, 파랑, 빨강"), 수학은 최종 답. 분류는 그룹 이름 저장 위치가 없어 보내지 않음(금지어로 대신) | ai `answerKey`는 `list[str]`이고 질문 글자에서 찾음. ID("c2")를 보내면 정답 글자가 나와도 못 잡음 |
| 되묻기만 실패 | 판정도 저장하지 않고 `FAILED`, 재요청하면 판정부터 다시 | sequence-diagram 3.2 "위 처리 중 예외 → FAILED". 첫 판정 결과는 학생에게 보인 적이 없음 |
| 실패 코드 | `AI_TIMEOUT`(응답 시간 초과), `AI_UNAVAILABLE`(연결 실패·연결 시간 초과·ai 5xx), `AI_BAD_RESPONSE`(ai 4xx·계약 밖 응답), `AI_CIRCUIT_OPEN`, `INTERNAL_ERROR`(그 밖 예외도 리스를 풀어 재요청이 다시 실행되게) | 문서에 값 목록이 없었음 |
| `retryable` | ai 503 본문의 값을 그대로(LLM 인증 실패 등은 false), 없으면 true. 시간 초과·연결 실패·차단은 true, 4xx·계약 밖 응답은 false | api-spec 4.2. 고칠 수 없는 오류를 "다시 시도"로 안내하지 않음 |
| `nextActions` | 지금 할 수 있는 행동: 이 판정의 되묻기가 아직 답을 받지 않았으면 `[ANSWER_FOLLOWUP, FINISH]`, 되묻기가 없으면 `[FINISH]`, 마무리·완료한 시도는 `[]`. 처리 중·실패는 `[]`. 시도 상태는 결과를 읽을 때 함께 읽음(처리 중에 마무리해도 맞게 나옴) | 설계는 생성 시점 규칙(api-spec 2.2·sequence-diagram 3.2)만 정함. FN-JDG-09 "현재 가능한 행동 표시"에 따라 읽는 시점 기준으로 정함. 프론트 `canAddAnswer`가 마지막 답변의 `nextActions`로 보완 답변 칸을 염 |
| 버전 | 판정에 `rubric_version_id`(제출 때 저장)·`model_version`·`prompt_version`, 되묻기에 되묻기의 모델·프롬프트 버전. 응답 `versions`는 `{mission: "미션 code@버전", rubric: "미션 code@기준표 버전", model, prompt}`(판정 값, 규칙 판정이면 없음) | ERD 4.2. api-spec 1.6 예시(`m-12@3`·`r-12@2`)는 mission·rubric code가 다르지만 기준표에는 code 컬럼이 없어 미션 code에 기준표 버전을 붙임(두 버전이 같으면 같은 문자열) |
| 마무리한 시도의 남은 답변 | 판정은 하고 되묻기는 만들지 않으며 `nextActions: []`. 시도 상태는 ai 호출 전에 확인(ai 호출 동안 마무리되는 경우는 아래 "후속" #26) | 문서에 없음. 기록은 남겨야 하고(P08), 마무리 뒤에는 답변을 받지 않음(P04, #24) |
| 시도 상세 | `answers[].feedback`은 피드백 API와 같은 모양, 시도의 `nextActions`는 마지막 답변의 `nextActions` | #24에서 "#25에서 채움"으로 둔 부분 |
| ai 호출 | 응답 35초(`app.internal.read-timeout`), 재시도 없음, 서킷 브레이커 최근 20건·최소 20건·실패율 50%·30초 차단·half-open 1건(전송 오류·5xx만 실패로 셈) | 아키텍처 1.3, P12. core #38과 같은 값·같은 라이브러리(`resilience4j-circuitbreaker 2.3.0`) |
| 식별정보 | ai 요청 본문에 학생 이름·ID 없음(학년만). 공통 내부 클라이언트가 붙이는 사용자 컨텍스트 헤더(`X-Student-Scope` 등)는 내부 인증 규칙대로 전달 | 이슈 #25, api-spec 4장 "인증: 내부 토큰 + 사용자 컨텍스트 헤더". ai는 헤더를 판정·LLM 입력에 쓰지 않음 |
| 추적 | `judgment.trace_id`에 요청 `traceparent`의 trace-id | ERD 4.2 |
| ai 판정 요소 목록 | 보류가 아니면 기준표 요소마다 한 번씩(중복·누락이면 `AI_BAD_RESPONSE`) | 중복이면 UK 위반 500, 누락이면 일부만 저장돼 마무리 체크리스트에서 빠짐 |
| 처리하지 않는 요청의 응답 | 리스를 못 잡았거나 잃었으면 저장 결과가 `DONE`일 때만 결과, 아니면 `RUNNING` | api-spec 1.4. 그사이 다른 요청이 실패했어도 다시 요청하면 가져가 실행되므로 `FAILED`를 200으로 보내지 않음(core #39는 DONE·RUNNING·503만 다룸) |
| 결과 조회 순서 | 저장된 판정 행을 먼저 읽고 요소·되묻기를 읽음 | 문장마다 스냅샷이 달라(READ COMMITTED) 반대로 읽으면 그사이 커밋된 DONE과 섞여 "DONE인데 되묻기 없음"이 나갈 수 있음. 저장은 DONE·요소·되묻기를 한 트랜잭션으로 커밋 |
| 질문 은행이 비었을 때 | `INTERNAL_ERROR`로 `FAILED`(500), 질문을 넣고 다시 요청하면 실행 | 시드에 유형마다 2개가 있어 운영 데이터 문제로 봄 |

## 임시로 정한 것 (설계에 없음, 바꾸기 쉬움)

| 항목 | 정한 내용 | 바꿀 위치 |
|---|---|---|
| 풀이 단계 결합 | 최종 답 동치 + 풀이 `CORRECT` → `CORRECT`, 최종 답 불일치 + 풀이 `RETHINK` → `RETHINK`, 한쪽만 → `PARTIAL`, ai 보류 → 보류(최종 답 결과는 쓰지 않음). `method`는 `LLM`. 최종 답은 기준표 요소가 아니라 요소로 저장하지 않아, 최종 답이 틀려 `PARTIAL`이어도 풀이 요소는 충족으로 남음(마무리 체크리스트는 풀이 요소, 정답은 마무리 공개로 보임). FN-JDG-04 "미검증 M1 수학 과정은 보류"는 M1 모델 결과를 쓸 때의 규칙이라 M1을 쓰지 않는 지금은 해당 없음(ai `JudgmentRequest` 주석 "M1 점검은 범위 밖, 같은 근거 추출·원문 대조로 판정", sequence-diagram 3.2 "M1 활성 범위"일 때만 `LOW_CONFIDENCE`) | `FeedbackFacade.withFinalAnswer` |
| 수 읽기 | 정수·쉼표(`1,000`)·소수·분수(`3/4`)·대분수(`1 3/4`)·한글 분수(`4분의 3`, `1과 4분의 3`). 자연수와 분수 사이에 "과·와"나 띄어쓰기가 있어야 대분수(`14분의 3`은 3/14). 위첨자(`²`)는 수로 보지 않음. 수로 읽을 수 없는 정답 키는 글자 그대로 비교 | `MathEquivalenceJudge.normalize` |
| 분류 정답 키 | `{"assignments":[{choiceId, categoryId}]}`, 배정 순서와 무관하게 모두 같아야 정답 | 시드에 분류 문항 없음 |

## 기존 파일 수정

| 파일 | 변경 | 근거 |
|---|---|---|
| `_common/config/InternalRestClientFactory.kt` | JDK `HttpClient`를 HTTP/1.1로 고정 | compose 실제 호출에서 발견: JDK 기본(HTTP/2)은 http 주소에 `Upgrade: h2c`를 보내고 uvicorn(ai)이 `Unsupported upgrade request`로 거절해 `AI_BAD_RESPONSE`가 남. WireMock(Jetty)은 업그레이드를 받아 테스트로는 안 드러남. 이 팩토리의 첫 사용처라 영향받는 기존 호출 없음. 테스트가 요청 프로토콜·`Upgrade` 헤더를 확인(빼면 실패) |
| `application.yml` | `app.internal.read-timeout` 30s(확정 전 임시값) → 35s | P12 learning→ai 35초. learning이 부르는 내부 서비스는 ai뿐이라 공통 값 변경으로 충분. 30초면 ai 되묻기 마감(33초)보다 먼저 끊김 |
| `build.gradle.kts` | `resilience4j-circuitbreaker 2.3.0`, 테스트 `wiremock-standalone 3.13.1` | 아키텍처 1.3 서킷 브레이커, 이슈 완료 조건 "ai 목(WireMock 등)". 사용자 동의(10/27) |
| `attempt/` | `Attempt.acceptsAnswers`, `AttemptService.timeline`, 시도 상세 `feedbacks`·`nextActions` | 위 표 |
| `_common/security/UserContext.kt`, `attempt/service/AttemptService.kt` | 학생 본인 확인을 UUID끼리 비교하는 `requireStudent(UUID)` 추가, 시도 확인(`requireOwned`·`lockForAnswer`)이 그것을 씀. 문자열 버전은 그대로 | PR #74 리뷰 지적 1번: `requireSelfStudent`는 UUID로 읽어 대소문자와 무관한데 시도 확인은 문자열 비교라, core가 대문자 UUID를 보내면 본인 시도도 403. 피드백 API도 같은 확인을 거쳐 여기서 고침. 대문자 범위 테스트(문자열 비교로 되돌리면 실패) |
| `mission/` | `Rubric`·`AnswerKey`, `MissionService.rubric`, 판정용 기준표 조회(정답 키·예시 답 포함, 학생 응답에 쓰지 않음) | class-diagram 4.2 `FeedbackFacade --> MissionService` |

## 프론트 확인 (프론트 담당, #82)

| 항목 | 프론트 타입·목업 | 구현 | 근거 |
|---|---|---|---|
| `versions` | `Feedback`에 없음 | 있음 | api-spec 3.2. 화면은 무시해도 됨 |
| `elementId` | 목업은 `e1` 같은 코드 | `rubric_element.id`(UUID) | judgment_element가 UUID로 저장, ai 계약도 UUID |
| 근거 없는 ai 요소의 `sourceType` | 필수(`RULE`·`ANSWER_KEY`·`AI_OBSERVATION`) | `null` | ERD "근거가 없으면 source_type NULL 가능". 프론트 타입에 `null` 추가 필요 |
| 없는 값 | `judgment?`·`followup?`·`heldReason?`(필드 없음) | `null`로 보냄 | Jackson 기본 직렬화 |
| 처리 중 | SSE `status` 이벤트 | learning은 `200 {status:"RUNNING", judgment:null, followup:null, nextActions:[], versions:null}` → core #39가 이벤트로 바꿈 | sequence-diagram 3.2 |
| 고르기 정답 바로 마무리 | 목업 `demoGateway.ts`는 `CHOICE` `CORRECT`만 `FINISH`, 순서·분류 정답은 되묻기를 만듦 | 순서·분류 `CORRECT`도 되묻기 없이 `["FINISH"]` | FN-LRN-04 고르기 = 선택지·순서·분류, P04·api-spec 2.2 "고르기 `CORRECT`". 목업 조건 확인 필요 |
| 실패의 `retryable` | api-spec 3.2 예시는 `{"code":"AI_UNAVAILABLE","retryable":true}`만 | ai가 다시 해도 안 되는 오류(LLM 인증 실패·ai 4xx·계약 밖 응답)는 `retryable:false` | 고칠 수 없는 오류를 "다시 시도"로 안내하지 않음. 화면에서 `false`일 때 재시도 버튼 처리 필요 |

## core에 전달할 것 (#39 피드백 SSE)

- learning 응답: `200` + `status`가 `DONE`이면 `result` 이벤트, `RUNNING`이면 `status` 이벤트 후 종료, `503 AI_UNAVAILABLE`이면 `error` 이벤트에 `retryable` 그대로.
- 판정 한 번의 최악 소요: ai 판정 35초 + 되묻기 35초 + 저장. core→learning 80초, 판정 리스 90초 안 (P12).

## PR #78 리뷰 반영 (10/28)

| 지적 | 고친 내용 | 테스트 |
|---|---|---|
| 연결 시간 초과가 `AI_TIMEOUT`으로 기록됨 (`HttpConnectTimeoutException`이 `HttpTimeoutException`의 하위 타입) | 응답 시간 초과만 `AI_TIMEOUT`, 연결 시간 초과는 연결 실패 `AI_UNAVAILABLE` (`AiClient.transportFailureCode`) | `AiClientTest`: 예외로 분류 확인(실제 연결 시간 초과는 네트워크 환경마다 다르게 나 CI에 넣지 않음). 닿지 않는 주소·연결 제한 1초로 한 번 직접 확인: `ResourceAccessException → HttpConnectTimeoutException → ConnectException`, 1.3초 뒤 `AI_UNAVAILABLE` |
| `lease_until`이 NULL인 `RUNNING`을 엔티티는 만료로, SQL은 비만료로 봄 | 획득 SQL에 `lease_until IS NULL OR` 추가, state-diagram 3.3 SQL도 같이 | `JudgmentServiceTest`: 리스 없는 `RUNNING`을 가져감 |
| `markFailed` 예외가 원래 오류를 가림 | 기록 오류는 원래 오류에 suppressed로 붙이고 원래 응답 유지 | `FeedbackFacadeTest`: ai 실패는 503 `retryable`, 예상 못 한 오류는 원래 예외 |
| api-spec 4.1 처리 중 응답 표기가 실제와 다름 | `{status:"RUNNING", judgment:null, followup:null, nextActions:[], versions:null}`로, sequence 3.2·이 리포트·컨트롤러 주석도 같이 | `FeedbackControllerTest`: 처리 중 응답 JSON을 null 필드까지 그대로 비교 |
| (의견) `JUDGMENT_STATE_CONFLICT`를 1.3 공통 오류 표 대신 4.1 비고에만 | 1.3 줄을 빼고 4.1 비고에 설명을 옮김 | - |
| (마무리 경합) ai 호출 동안 시도가 마무리되면 마무리된 시도에 되묻기가 저장될 수 있음 | 리뷰에서 #26 이슈 코멘트로 분리돼 이 PR에서는 처리하지 않음. 한때 `saveResult`가 시도를 다시 확인하도록 넣었다가(`e03eff0`·`9237859`) 리뷰대로 되돌림(revert) | - |

## 검증

- `./gradlew test`: 130개 통과(develop #77의 기록 유무 테스트 12개 포함), 실패·생략 0개. 새로 추가 50개: `RuleJudgeTest` 6, `JudgmentTest` 6, `AiClientTest` 6(WireMock), `FeedbackFacadeTest` 20(Testcontainers + WireMock), `FeedbackControllerTest` 5, `FeedbackConcurrencyTest` 3, `JudgmentServiceTest` 2, `AttemptControllerTest` 1(판정 결과가 있는 시도 상세), `AttemptServiceTest` 1(대문자 학생 범위).
- 이슈 #25 완료 조건
  - ai 목으로 정상·보류·실패·유출 검사 실패: `FeedbackFacadeTest`(서술 PARTIAL 요소·버전 저장, HELD `TOO_SHORT`와 되묻기, ai 503 → `FAILED`·retryable, 되묻기만 실패 → `FAILED`·판정 미저장, 유출 실패 → 질문 은행 두 번 다른 질문), `AiClientTest`(503 `retryable` 전달, 500, 400, 깨진 JSON, 시간 초과, 연결 실패, 서킷 차단)
  - `FAILED` 후 재요청 시 재실행, `DONE` 후 재요청 시 같은 결과: `FeedbackFacadeTest`(재실행 뒤 ai 판정 호출 2번·되묻기 1번, 세 번째 요청은 ai 호출 없이 같은 결과, `retry_count` 1 유지), `FeedbackConcurrencyTest`(실제 커밋: 실패가 따로 커밋된 뒤 재요청이 처음부터 실행)
  - 그 밖의 경로: 근거 없는 충족 → `AI_BAD_RESPONSE`, 질문 은행이 비면 `INTERNAL_ERROR` 후 재요청, 순서 문항(순서까지 비교·유출 검사용 정답은 정답 순서 전체), 풀이 단계 `RETHINK` 결합·보류 통과
  - 처리 상태: 유효 리스면 `RUNNING`, 만료면 다시 실행(`FeedbackFacadeTest`), 같은 답변 동시 6개 → ai 판정 1번·나머지 `RUNNING`·끝난 뒤 같은 결과(`FeedbackConcurrencyTest`, 별도 컨테이너), 리스를 잃은 늦은 처리는 저장·실패 기록 모두 0행(`JudgmentServiceTest`)
- 보호 장치를 하나씩 빼면 테스트가 실패함을 확인: 획득 SQL 조건(동시 요청 1개 실패), 엔티티의 리스 만료 판단(2개), 저장의 리스 조건(1개), 실패 기록의 다시 읽기(1개), `satisfy()` 거부(1개), 기준표 요소 ID 확인(1개), 질문 은행 대체(2개), 되묻기 2회 제한(1개), 고르기 정답 되묻기 생략(2개), 수학 최종 답 결합(1개), 실패 기록(4개), HTTP/1.1 고정(1개), ai 요소 목록(중복·누락) 확인(1개), 결과를 읽을 때의 시도 상태(1개), 엔티티 전이 검사(1개), 리스 시각 자르기(5개), 서킷 차단 기준 50%를 60%·40%로 바꾸면 각각 실패. PR #78 리뷰 반영분: 연결 시간 초과 분류(1개), 리스 없는 `RUNNING` 획득(1개), 실패 기록 오류 감싸기(2개).
  - 저장 중 롤백: 없는 시도의 되묻기로 외래키 오류를 내 판정 저장까지 롤백된 뒤에도 `markFailed`가 `FAILED`를 기록하고 다시 가져갈 수 있음(`FeedbackConcurrencyTest`, 실제 커밋)
- compose 실제 확인(`docker compose up -d --build learning-service ai-service`, `LLM_PROVIDER=openai`, `gpt-6.1-terra`, 시드 2번 서술 미션 "쉬는 시간을 늘린다면?", 확인 후 만든 행 삭제·컨테이너 정지):

| 요청 | 결과 |
|---|---|
| 첫 시도(고치기 전) | `503 AI_UNAVAILABLE`, `failure_code=AI_BAD_RESPONSE`, ai 로그 `Unsupported upgrade request` → 위 HTTP/1.1 수정 |
| 피드백 | 200, 7.8초. `CORRECT`, 주장·근거 요소는 학생 원문 구절 인용(`AI_OBSERVATION`), "다른 관점"(들어가면 좋은 생각) 미충족·`sourceType` null, `trial: true` |
| 되묻기 | `ONE_STEP_MORE`, LLM, 유출 검사 통과: "쉬는 시간을 늘리는 걸 반대하는 친구는 왜 그렇게 생각할까?" |
| 버전 | `DEMO-02-G3-EVALUATE@1`, model `gpt-6.1-terra`, prompt `judge@2`, 되묻기 `followup@4` |
| 같은 피드백 재요청 | 200, 0.02초, LLM 호출 없이 같은 결과 |
| 시도 상세 | 같은 피드백, `nextActions: [ANSWER_FOLLOWUP, FINISH]` |
| DB | `judgment` DONE·LLM·`retry_count` 0, 요소 3행, 되묻기 1행 |
| 리뷰 반영 후 다시(10/28, 마무리 경합을 되돌린 0c882bd) | 피드백 200 7.3초 `CORRECT`·`ONE_STEP_MORE`, 재요청 0.17초 같은 결과, 시도 상세 같은 피드백·`[ANSWER_FOLLOWUP, FINISH]` |

## 후속

PR #78 리뷰에서 후속 항목을 이슈로 나눔(kty2001): #79 판정 규칙 확정, #80 판정 정정 수신 API, #81 미션 공개 검사, #82 학생 피드백 화면 계약.

- 기준표 요소가 0개인 고르기 미션: ai 되묻기가 요소 1개 이상을 요구해(`FollowupRubric.elements` min 1) 오답이면 `AI_BAD_RESPONSE`가 됨. 지금 시드는 모두 요소가 있음. 미션 공개 검사(`Mission.requirePublishable`)에서 고르기도 요소 1개 이상을 요구해야 함 → #81

- 판정 요청에 미션 질문 넣기(B안): ai 판정 요청은 학생 답과 기준표만 받아 요소 설명이 일반적이면 주제와 무관한 답도 충족될 수 있음(#22 검사에서 A안 "요소 설명에 주제"로 대응). api-spec 4.2·ai 판정 프롬프트(judge@3)·learning을 함께 바꿔야 해 별도 이슈
- 수학 단위 비교 여부(위 "수학 단위", 설계에 규칙 추가가 필요), 풀이 단계 결합 규칙 확정(위 "임시로 정한 것") → #79
- 같은 답이 실행마다 다르게 판정되는 경우(#22 검사): 사람 검증(P11) 대상
- 분류 문항: 그룹(`categories`) 저장 위치가 정해지면 그룹 ID 확인·유출 검사용 정답 추가. 기획서 5장 "분류 기준"(이유를 봄)과 지금 분류 문항(정답 키)의 관계 확인 → #79
- 판정 정정(`POST /internal/judgments/{judgmentId}/corrections`, class-diagram 4.2 `CorrectionController`·`JudgmentService.correct`·`CorrectionRepository`, FN-SUP-03): 이슈 #25 범위가 아님. 관리자 정정과 learning 전달은 core #46(20220348-kim) 몫이지만, learning 쪽 받는 API는 #80에서 #46과 요청·응답을 맞춤. 고착 `RUNNING` 탐지 주기(1분)는 운영 작업. 지금은 요청 때 리스 만료로 다시 가져감
- 마무리(#26): 판정 `DONE` 1회 이상 확인, 체크리스트는 저장된 요소(`ANSWER_KEY`·`AI_OBSERVATION`) 사용. 피드백은 ai 호출 전에 읽은 시도로 되묻기 여부를 정하므로, 판정 처리 중에 마무리하면 마무리된 시도에 되묻기가 생길 수 있음 → PR #78 리뷰에서 #26 이슈 코멘트로 분리: finish가 같은 시도 잠금(`lockById`)을 쓰고 `RUNNING` 판정이 있으면 기다리거나 거절, 또는 `saveResult` 직전에 시도를 다시 확인
