# learning 학습 서비스 (#22~#27·#79·#80·#128·#145·#146)

통합 원본: learning-mission, learning-attempt, learning-answer, learning-feedback, learning-reflection, learning-records, learning-judgment-rules

계약은 [API 명세](../design/api-spec.md) 2.2·3.1~3.8·4.1과 [learning OpenAPI](../../contracts/openapi/learning-service.yaml), 판정 상태는 [상태 다이어그램](../design/state-diagram.md) 3장.

## 1. 미션 조회 (#22)

- 학생 확인: `X-User-Role: STUDENT`이고 `X-Student-Scope`에 학생 1명일 때만(`UserContext.requireSelfStudent()`, 다른 학생 Controller도 공용). 학년 `grade`(3~6)·시연 여부 `demo`(기본 false)는 core가 붙임
- 학생용 객체는 `MissionView`(정답·예시 답·기준표 필드 없음). 노출 규칙은 `MissionView.isOpenTo(grade, demo)` 한 곳(학년 범위, 논술 초5~6, `demo_only`는 demo일 때만)
- 상세는 목록과 같은 범위. 비공개·범위 밖 409 `MISSION_NOT_AVAILABLE`, 없으면 404
- 수행 상태는 `MissionRepository`가 미션별 가장 최근 시도로 읽음(없으면 `NOT_STARTED`). `AttemptService`를 부르면 순환이라 Repository에서 직접
- 진행 중 시도는 시작 당시 미션 버전을 유지(P07). 목록·상세는 현재 공개 버전

### 데모 미션 시드

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 문항 수 | 초3~6 학년마다 생각 유형별 1문항, 총 20(문항마다 학년 하나) | P03 |
| 공개 범위 | 초3·초5 10문항 `PUBLISHED`, 초4·초6 10문항 `DRAFT`, 모두 `demo_only = false` | 시연 초3·초5 각 5문항(P03) |
| 입력 방식 | 학년마다 고르기·순서·서술·풀이 단계·논술(논술은 초5·6, 분류는 시드에 없음) | P03, #22 시드 조건 |
| 고르기·순서 | 까닭을 쓰라고 하지 않고 오답에 되묻기로 받음. 기준표 요소는 "고르는 생각" 하나, 예시 답은 정답 해설 | 제출 형식이 `choiceIds`뿐, 정답이면 바로 마무리(P04) |
| 기준표 설명 | 요소 설명에 미션 주제를 넣음 | ai 판정 요청에 미션 질문이 없어 일반적인 설명이면 무관한 답도 충족될 수 있음 |
| 풀이 단계 | 입력 틀 ① 무엇을 구하나요? ② 어떻게 구할까요? ③ 계산 ④ 확인해 보기 / 최종 답. 요소는 방법과 무관한 생각 단계 + `FINAL_ANSWER` | 풀이 방법이 여러 가지 |
| 정답 키 | 고르기·순서 `{"choiceIds":[...]}`(순서는 정답 순), 풀이 `{"finalAnswer":"30"}`(수만, 단위는 `answer_unit`) | 학생 제출 필드와 같은 이름 |
| 질문 은행 | 되묻기 유형마다 2개, 정답·미션 내용 없음 | P16 |
| 기타 | `judge_verified = false`(사람 검증 전), `basic_skills` 비움, 고정 시드용 `created_by`. AI Hub 문항·답안 미사용 | 기초 능력 값 목록이 문서에 없음 |
| 적재 | `backend/learning-service/db/seed/`의 SQL을 직접 적용(Flyway 아님). 고정 ID + `ON CONFLICT (id) DO UPDATE`라 재실행하면 덮어씀. 파일에서 뺀 행은 직접 삭제 | 개발·시연 데이터를 운영 스키마와 분리 |

### 성취기준

2022 개정 교육과정(교육부 고시 제2022-33호 과학과 [별책 9]·국어과 [별책 5]·도덕과 [별책 6], 수학과)에서 코드와 문장을 확인. 초5·6은 기획서 5.3(1)의 생각 유형별 예시 기준을 따름.

| 학년 | 분석하기 | 따져 보기 | 새로 만들기 | 문제 해결하기 | 돌아보기 |
|---|---|---|---|---|---|
| 초3 | `[4과04-02]` | `[4국03-03]` | `[4도02-02]` | `[4수02-01]` | `[4도01-04]` |
| 초4 | `[4과09-02]` | `[4국02-04]` | `[4과05-03]` | `[4수01-04]` `[4수01-03]` | `[4국03-05]` |
| 초5 | `[6과07-02]` | `[6국01-02]` | `[6도03-02]` | `[6수03-14]` | `[6국03-05]` |
| 초6 | `[6과14-02]` | `[6국03-02]` | `[6도04-01]` | `[6수03-19]` | `[6국06-04]` |

- 기준과 맞지 않던 초안 2개는 문항을 고침: `[6국01-02]`는 친구 주장과 까닭의 타당성을 따진 뒤 내 주장을 쓰게, `[6수03-14]`는 사다리꼴 화단 넓이로
- 3~4학년군 과학에 그림자 성취기준이 없어(`[6과13-01]`) 초4 분석하기는 자석. 초4 수학은 세 자리 수 범위만

## 2. 학습 시도·초안·생각 열기 (#23)

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 시작 응답 | 새 시도 `201`, 진행 중 시도 `200` | core 일일 한도는 `201`만 집계(P13) |
| 동시 시작 | `INSERT … ON CONFLICT … WHERE status = 'IN_PROGRESS' DO NOTHING` 후 0행이면 커밋된 시도 반환 | 부분 UK `uq_attempt_in_progress` |
| 완료한 미션 | 다시 시작하면 새 시도 | 부분 UK가 진행 중 시도만 막음 |
| 첫 초안 | 시도 생성 트랜잭션에서 빈 초안(version 0) 생성, 저장은 항상 `UPDATE … WHERE version = :ifMatch` | 충돌 시 최신 초안을 항상 돌려줄 수 있음. version 0은 `savedAt` 없음 |
| `If-Match` | `"7"`·`7`·`W/"7"` 허용, 아니면 400. 응답 `ETag`는 `"8"` | api-spec 1.4 |
| 초안 충돌 | 409 `ATTEMPT_DRAFT_CONFLICT` + `latest` + 최신 `ETag`(attempt 전용 예외로 공통 처리 불변) | FN-LRN-17 |
| 초안 저장 잠금 | 시도 행을 잠그고(`lockOwned`) 열림 확인 후 저장 | 마무리·돌아보기와 같은 순서로 직렬화([점검 기록 B14](audit.md)) |
| 쓰기 막는 때 | `COMPLETED` 시도의 초안·생각 열기는 409 `ATTEMPT_CLOSED`. 마무리 뒤 막는 것은 답변 제출 | state-diagram 3.2, P04 |
| 생각 열기 | 열지 않은 질문을 `seq` 순으로, 다 열면 마지막 질문 반복, 열 때마다 `hint_usage` 기록. 질문 없는 미션 404 | 도움 이용 집계 근거(P08) |
| 하루 미션 한도 | learning은 확인하지 않음 | core Redis 책임 |

## 3. 답변 제출 (#24)

- 한 트랜잭션: 시도 행 잠금·본인 확인 → 같은 키 답변 조회 → 마무리·완료 409 → 입력 방식 불일치 400 → 누락 422 → 되묻기 연결 422 → 저장 → 판정 PENDING → 초안 답 칸 비우기. 같은 키 재요청은 열림·검증보다 먼저 확인해 최초 결과(`201`, PENDING) 그대로
- 시도 행 잠금이 없으면 같은 키 두 요청·다른 키 두 요청이 UK 위반 500이 됨(동시 테스트로 확인)
- 같은 키·다른 본문 422 `IDEMPOTENCY_KEY_REUSED`(입력 방식·사용 필드·`followupId`·`dictatedByGuardian` 비교). 키가 없거나 UUID가 아니면 400
- 누락 검사: 서술 글 / 풀이 최종 답 + 단계 1개 이상 / 논술 주장·까닭 2개·반대 의견 / 고르기 1개 / 순서·분류 모든 선택지 한 번씩. 안내 문구는 웹 `validateAnswer`와 같음
- `content`에는 입력 방식에 쓰는 필드만 저장(`AnswerContent.only`), 메모는 버림(P05)
- `plain_text`(판정 인용 대조용 원문): 칸 이름을 붙인 줄(`"{칸 이름}: …"`, 풀이는 `"최종 답: …"`+단위), 고르기·순서는 선택지 이름을 `" → "`로, 분류는 `"선택지 이름: 그룹 이름"`
- 보완 답변: 첫 답변은 `followupId` 없이, 이후는 이 시도의 가장 최근이면서 답하지 않은 되묻기만(아니면 422). 되묻기는 판정 후에만 생기고 시도당 2회라 판정 전 추가 제출·네 번째 답변·고르기 정답 뒤 제출이 같은 규칙으로 막힘
- 제출 뒤 초안: 같은 트랜잭션에서 `content.answer`를 비우고 memo 유지, version +1(사용자 결정). 그대로 두면 제출한 답이 미제출 초안으로 다시 채워짐
- 타임라인은 `AttemptService.get`이 `JudgmentService.timeline`으로 읽음(`AnswerService`가 `AttemptService`를 써서 순환 방지)
- 구현 중 수정: 논술 검사 함수 `isComplete()`를 Jackson이 값으로 직렬화해 `allFilled()`로 변경

## 4. 피드백 오케스트레이션 (#25)

| 항목 | 정한 내용 |
|---|---|
| 상태 전이 | `PENDING`·`FAILED`·리스 만료 `RUNNING`만 `RUNNING`으로(리스 90초). 0행이면 `DONE`은 저장 결과, 그 밖은 처리 중 응답 |
| 저장·실패 | 모두 `WHERE process_status='RUNNING' AND lease_until = 획득 값`. 리스를 잃었으면 저장하지 않음 |
| 엔티티 | `Judgment.acquire`·`done`·`hold`·`fail`이 전이를 판단(불허 409 `JUDGMENT_STATE_CONFLICT`, 내부 방어 코드), Repository가 조건부 UPDATE |
| 실패 기록 | DB에서 다시 읽어 이 요청의 리스일 때만 `fail`. 기록이 실패해도 원래 오류로 응답(기록 오류는 suppressed) |
| 트랜잭션 | 리스 획득·결과 저장·실패 기록을 각각 짧게, ai 호출은 밖 |
| 판정 방식 | 고르기·순서·분류는 정답 키(`RULE`, `trial=false`), 서술·논술은 ai, 풀이 단계는 풀이 ai + 최종 답 규칙 |
| 요소 기록 | 규칙 판정은 요소마다 `verified=true`·`ANSWER_KEY`·고른 선택지 이름. ai는 근거가 있으면 `AI_OBSERVATION`. 기준표에 없는 요소·중복·누락·검증 안 된 충족은 `AI_BAD_RESPONSE` |
| 되묻기 조건 | 시도 내 2회 미만 + 고르기 활동 `CORRECT` 아님 + 마무리 전. 수학 `CORRECT`는 건너뛸 수 있는 되묻기(`[ANSWER_FOLLOWUP, FINISH]`) |
| 질문 은행 | ai가 재생성까지 유출이면 같은 유형 활성 질문 중 이 시도에서 안 쓴 것을 생성 순으로(`source=BANK`). 비었으면 `INTERNAL_ERROR` |
| 유출 검사 정답 | 학생에게 보이는 글자로 변환: 고르기 선택지 이름, 순서 전체, 수학 최종 답+단위, 분류 "선택지: 그룹" |
| 되묻기만 실패 | 판정도 저장하지 않고 `FAILED`, 재요청 시 판정부터 |
| 실패 코드 | `AI_TIMEOUT`·`AI_UNAVAILABLE`·`AI_BAD_RESPONSE`·`AI_CIRCUIT_OPEN`·`INTERNAL_ERROR`. `retryable`은 ai 503 본문 값, 시간 초과·연결 실패·차단 true, 4xx·계약 밖 false |
| `nextActions` | 읽는 시점 기준: 답하지 않은 되묻기 있음 `[ANSWER_FOLLOWUP, FINISH]`, 없음 `[FINISH]`, 마무리·완료 `[]`, 처리 중·실패 `[]` |
| 버전 | `versions{mission:"미션 code@버전", rubric:"미션 code@기준표 버전", model, prompt}`(기준표에 code 컬럼이 없어 미션 code 사용) |
| ai 호출 | 응답 35초, 재시도 없음, 서킷 20건·50%·30초(core와 같은 값). 요청 본문에 학생 이름·ID 없음(학년만) |
| 결과 조회 순서 | 판정 행을 먼저 읽고 요소·되묻기를 읽음(READ COMMITTED에서 섞임 방지) |

- 후속(이슈 분리): 판정 정정 수신 API(#80, 8절에서 구현), 미션 공개 검사(#81, 고르기도 요소 1개 이상 등), 판정 요청에 미션 질문 넣기, 고착 `RUNNING` 1분 주기 탐지(현재는 요청 때 리스 만료로 재획득)

## 5. 마무리·돌아보기·자기 평가 (#26)

- 마무리 조건: 시도 안에 판정 `DONE` 1회 이상(보류 포함). 되묻기에 답하지 않아도 가능. 이미 마무리했으면 같은 결과(기록 불변)
- 처리 순서: 시도 행 잠금 → 타임라인 → `FinishPolicy.canFinish` → `Attempt.finish(now)` → `finished_at` 조건부 UPDATE
- `reveal`은 시도의 기준표 버전 `example_answer`(닫힌 문제 시드는 "정답: …" 형식), `revealKind`는 고르기·순서·분류·풀이 `ANSWER`, 서술·논술 `EXAMPLE`
- 체크리스트: 기준표 요소 전체, 이 시도의 처리 완료 판정 중 원문 구절과 함께 충족된 적이 있는 요소만 체크(가장 최근 구절). 보완 답변 판정은 그 답변만 보므로 마지막 답변만 쓰면 앞에서 확인된 요소가 빠짐. 읽을 때 계산
- 돌아보기 `{difficulty(EASY·NORMAL·HARD 필수), text(선택, 빈 글 null)}`. DDL은 nullable이지만 P04가 필수라 API에서 막음. 완료 뒤 409 `ATTEMPT_CLOSED`, 마무리 전 409 `REVEAL_CONDITION_UNMET`
- 자기 평가: 마무리 뒤·완료 전. `{checks:[{elementId, checked}]}` 일부만 보내도 되고 재전송은 `checked`만 변경. 응답은 요소마다 `{elementId, label, selfChecked, aiChecked, quote}`
- 마무리 경합: 판정 `saveResult` 트랜잭션 시작에서 시도 행을 `FOR UPDATE`로 다시 읽어 닫혔으면 되묻기를 저장하지 않음(마무리 대기·거절은 P04에 없는 조건이라 채택하지 않음)
- 잠금 순서는 모두 시도 → 판정

## 6. 학습 기록 조회 (#27)

- 집계 대상(P08): 기간 안에 답변 제출이 있는 시도(판정 상태 무관). 제외는 조회 종료일까지 답변이 모두 `FAILED`인 시도, 삭제 학생, 초안만 있는 시도. 시도별 사실(완료·최초 답변 전 생각 열기·되묻기·보완 답변)은 조회 종료일까지만(지난 기간 조회가 이후 활동으로 바뀌지 않게)
- summary 지표: 학습한 활동(집계 대상 수), 완료한 활동, 도움 없이 시작한 활동, 되묻기 후 생각을 더한 활동(보완 답변 시도 / 되묻기 받은 시도)
- 상태: 0건 `NO_RECORD`, 1~4건 `INSUFFICIENT_SAMPLE`(비율 null), 5건 이상 `OK`
- 같은 집계 SQL을 `RecordRepository.findEligible` 한 곳에 둠. 목록·상세 항목은 `AttemptService.get`을 재사용하고 초안만 제거(사용자 결정, 조립을 두 벌로 만들지 않으려고). 목록이 항목마다 시도 상세를 읽어 느리면 묶음 조회로 변경 필요
- 학생 홈 `resume`: 진행 중 시도 중 시작·답변·초안 저장 시각이 가장 늦은 하나(기간 무관, 초안만 있는 시도·돌아보기 전 시도 포함, 사용자 결정). `missions`는 `MissionService.listForStudent` 재사용
- 전후 변화 수: 글자 수(공백 포함, 코드 포인트)·문장 수(`.?!`·줄바꿈)·까닭을 잇는 말(`왜냐하면·때문·그래서·따라서`, report와 확정)을 학생이 쓴 칸만으로 셈(칸 이름을 세지 않음)
- evidence: 요청 순서, 없는 답변·삭제 학생은 `available:false`(원문·제목 없음, `attemptId` null 가능), 범위 밖 학생 답변이 섞이면 403, ID 1~100개
- 식별자는 역할과 무관하게 `studentId`(core·report와 합의). 메모·초안은 어떤 응답에도 없음. 기록 조회 SELECT는 `flushCache="true" useCache="false"`
- `student.deleted` 소비(`StudentDeletedConsumer`·`StudentDeletionService`)는 9절(#128)

## 7. 판정 규칙 확정 (#79, 사용자 결정)

| 항목 | 결정 |
|---|---|
| 수학 단위 | 비교하지 않음. 정답 키에는 수만, 단위는 `mission_version.answer_unit`으로 답 칸 뒤 고정(`answerUnit`). 학생이 단위를 써도 앞쪽 수만 비교 |
| 수 읽기 | 정수·쉼표·소수·분수·대분수·한글 분수(`4분의 3`, `1과 4분의 3`), 위첨자는 수로 보지 않음, 수로 못 읽는 정답 키는 글자 비교(`MathEquivalenceJudge.normalize`) |
| 풀이 단계 결합 | 최종 답 동치 + 풀이 `CORRECT` → `CORRECT`, 불일치 + `RETHINK` → `RETHINK`, 한쪽만 → `PARTIAL`, ai 보류 → 보류 |
| 최종 답 요소 | 풀이 기준표에 `code = 'FINAL_ANSWER'` 요소. ai 요청에서는 빼고(`Rubric.aiElements`) 결합 뒤 `ANSWER_KEY`로 기록, 맞을 때만 충족(되묻기 요청에는 포함). 최종 답이 틀렸는데 체크리스트가 다 맞아 보이던 문제 해결 |
| 분류 | `mission_version.categories`, 그룹 이름 제공·없는 그룹 422·유출 검사 정답 전달. 아이가 기준을 정하는 분류는 서술 미션 |
| 마이그레이션 | learning `V6__mission_categories_and_answer_unit.sql`(기존 V1~V5 불변) |

- 웹 확인 필요: 최종 답 칸 뒤 `answerUnit` 표시, `categories` 표시, 수학 체크리스트의 "최종 답" 항목

## 8. 판정 정정 수신 (#80)

core #46 관리자가 신고를 검토해 판정을 고치면 core가 `POST /internal/judgments/{judgmentId}/corrections`로 알림. 원판정·요소·답변은 그대로 두고 `judgment_correction` 행을 추가하고, 조회 때 최신 정정 결과를 보여 줌(FN-SUP-03, ERD "덮어쓰기 금지"). 설계 이름(`CorrectionController`·`JudgmentService.correct`·`CorrectionRepository`·`JudgmentCorrection`) 그대로, DB 변경 없음(V2 테이블). core 소비 계약은 `feature/core-support`의 `contracts/openapi/support-learning-required.yaml`(0.2.0 `x-correction-rules`)

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 인증 | 내부 토큰 + `ADMIN` + `X-Student-Scope`에 판정 학생 정확히 1명 + UUID `X-User-Id`(= `corrected_by`). 토큰 401, 역할·범위 403, `X-User-Id`·`Idempotency-Key` 누락·형식 400, 빈 사유 400 | core 계약 |
| 처리 순서 | 판정 행 `FOR UPDATE` → 없으면 404 → 학생 범위 403 → 같은 키(같은 요청이면 처음 정정, 아니면 422 `IDEMPOTENCY_KEY_REUSED`) → `DONE` 전 409 `JUDGMENT_STATE_CONFLICT` → 같은 `reportId`·다른 키 409 `CORRECTION_REPORT_CONFLICT` → 저장 | 사용자 결정 → core 확인. 같은 키는 처음 상태와 관계없이 처음 응답 재현. 잠금은 #24 답변 제출과 같은 방식 |
| 같은 요청 | 판정 ID·`reportId`·`reason`·`corrected`가 같으면 같음(관리자는 비교 안 함) | core 계약 "같은 키·같은 본문" |
| 응답 | `{correctionId, previousResult, corrected, createdAt, impact}`. 같은 키 재요청은 저장된 행으로 다시 만듦 | core 계약 |
| `previousResult` | 정정 직전에 보이던 결과(앞선 정정이 있으면 그 결과). 최신 정정은 `created_at`(같으면 `id`) 가장 늦은 행. 다른 신고 정정이 동시에 와도 앞 정정 결과(#145에서 잠근 뒤 다시 읽도록 보완, 10절) | ERD "정정 전 결과" |
| 저장 모양 | `previous`·`corrected` jsonb는 `{"result": "PARTIAL"}` | ERD 비고에 추가 |
| 보이는 곳 | `findStored` 한 쿼리라 피드백 결과·시도 상세·#27 기록 모두 최신 정정 결과. 바꾸는 것은 `result`뿐: 정정이 있으면 `heldReason` null(ai 판정의 이유라서), 판정 요소·되묻기·`nextActions`·마무리 체크리스트는 원판정 | 사용자 결정 ②. `nextActions`는 결과가 아니라 되묻기·시도 상태로 계산 |
| impact | `aggregation: NOT_APPLIED`(learning 수치 집계는 판정 결과를 쓰지 않아 바꿀 것 없음, 오류 아님), `conversation`·`report: UNKNOWN`(learning이 확인할 수 없음) | core와 합의 ④ |
| 오류 코드 | `JUDGMENT_STATE_CONFLICT`는 기존 코드 재사용, `CORRECTION_REPORT_CONFLICT`는 새 코드. 둘 다 api-spec 4.1에만(1.3 공개 표에 넣지 않음) | #78 리뷰대로 learning 내부 코드는 4.1 비고. core가 409·422를 공개 코드로 바꿈 |

- 설계 문서: api-spec 4.1 정정 줄, class-diagram 4.2 끝 메모(`results()`·잠금 순서), state-diagram 3.3(정정은 `DONE`만), ERD 비고(jsonb 모양), OpenAPI(경로·`AdminUserId`·`AdminRole`·`CorrectionScope`·`CorrectionRequest`·`CorrectionResult`·`JudgmentResult`, 버전은 #26·#27처럼 그대로)
- 기존 파일 수정: `JudgmentService`(`correct`), `JudgmentMapper.xml` `findStored`(최신 정정 결과·보류 이유), `scripts/tests/test_record_exists_openapi.py` 컨트롤러 경로 수 22 → 23(#126 결제 사용 증빙 경로가 먼저 22로 올림)
- 검증: 테스트 202개(새 15: 서비스 8·동시 2·컨트롤러 5), scripts/tests 58개, #126 머지 뒤 develop 병합 상태로 206개·scripts 74개. 보호 장치 12개를 빼면 각각 실패(`DONE` 전 409는 DB 제약 `ck_judgment_result_when_done`·null 검사와 세 겹). compose 실제: 고르기 정답 `CORRECT` → `RETHINK` 정정, 같은 키 처음 응답 그대로, 422·409·409·403·404, 피드백·시도 상세·기록 모두 `RETHINK`, DB 원판정 `CORRECT` 그대로(ai 호출 없음, 만든 시도 2건만 삭제)
- 한계: 같은 신고를 다른 판정에 동시에 보내면 판정 잠금이 달라 둘 다 저장될 수 있음(`error_report_id` UK 없음, core는 신고마다 한 정정만 보냄), 같은 키를 다른 판정에 동시에 보내면 키 UK로 한쪽 500. `judgment_correction.judgment_id` 인덱스 없음(정정은 드묾)
- 확인 필요: core가 정정 전에 부르는 `/support/targets/{type}/{id}`·관리자 원문 `/support/attempts/{id}`는 별도 이슈(#80만으로 실제 흐름 미완성). learning 학생 삭제를 만들 때 `judgment_correction`을 판정보다 먼저 지움(FK)

## 9. 학생 삭제 소비·완료 보고 (#128)

core가 자녀 삭제·탈퇴를 확정하면 `student.deleted`를 보내고, learning·report 두 곳의 완료 보고가 모두 와야 삭제 요청이 `COMPLETED`가 됨(api-spec 5.6). learning에 소비자가 없어 삭제·탈퇴가 끝나지 않던 문제([점검 기록 B3](audit.md))를 고침. 클래스 다이어그램 4.3 이름(`StudentDeletedConsumer`·`StudentDeletionService`·`CoreClient`·`DeletedStudentRepository`·`ProcessedEventRepository`·`AttemptService.deleteByStudent`) 그대로, DB 변경 없음(큐는 `definitions.json`, 표는 V3)

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 흐름 | 소비자가 봉투 검증 → SYSTEM 컨텍스트 + 대상 학생 범위 → 한 트랜잭션에서 `processed_event`에 없으면 삭제·`deleted_student`·`processed_event` 저장 → 커밋 뒤 트랜잭션 밖에서 core `POST /internal/deletion-requests/{id}/completions {service:"learning"}` | api-spec 4.5·5.6, class-diagram 4.3 |
| 재전달·보고 실패 | 이미 처리한 이벤트는 지우지 않고 보고만 다시 보냄(core가 첫 보고를 놓쳤을 수 있음). 보고 실패는 예외 → 1·5·15분 지연 재시도 → 3회 초과 DLQ, 재시도 때도 삭제 없이 보고만 | 이슈 해야 할 일 3, report 삭제와 같은 규칙 |
| 하위 기록 삭제 | CASCADE 없이 한 트랜잭션에서 순서대로: 정정·판정 요소 → 자기 평가·돌아보기·생각 열기·초안 → 되묻기 → 판정 → 답변 → 시도. 답변 → 되묻기 → 판정 → 답변 고리는 `answer.followup_id`(DEFERRABLE)를 `SET CONSTRAINTS … DEFERRED`로 커밋 때 검사 | 사용자 결정(이슈 확인 필요). 마이그레이션·ERD 공유 계약을 바꾸지 않고, 시도 하나만 지워도 아래가 다 지워지는 위험이 없음 |
| 범위 | PROFILE·RECORDS 모두 학습 기록 전부 삭제. learning에는 프로필이 없어 차이는 표식의 `scope`뿐 | api-spec 5.6 "두 scope 모두 learning 기록 삭제" |
| 삭제 표식 | `deleted_student`는 학생당 한 행. 다시 삭제되면 `event_id`·`deleted_at` 갱신, `scope`는 이미 PROFILE이면 유지(RECORDS 뒤 탈퇴의 PROFILE은 PROFILE) | report 삭제 장벽과 같은 규칙 |
| 봉투 검증 | `specversion` 1.0, `id` UUID, type `student.deleted`·source `core-service`·dataschema `student.deleted.v1`, `subject` = `data.studentId`, data 필드는 정확히 `studentId`·`deletionRequestId`·`scope`. 위반은 재시도 없이 바로 DLQ(`InvalidEventException`), 필드 누락·시간대 없는 `time`은 변환 단계에서 거부 | 아키텍처 1.6 "형식 오류는 재시도 없이 DLQ", envelope·student.deleted.v1 스키마, report 소비자와 같은 검사 |
| 삭제 뒤 새 기록 | learning은 막지 않음. 학생 이용 차단은 core(RECORDS 완료 뒤에도 `DELETION_REQUESTED` 유지) | api-spec 5.6 "삭제 표식 이후 새 기록 허용 계약은 후속", auth-account 3장 |

- 설계와 다른 점: `StudentDeletionService.delete`에 `deletionRequestId` 인자 추가(설계는 `(eventId, studentId, scope)`). 완료 보고 경로에 필요한데 learning DB에 없어 이벤트에서 받아야 함. 소비자가 직접 보고하면 설계 화살표(서비스 → `CoreClient`)가 바뀌어 인자 추가가 가장 작은 변경(사용자 확인). `onStudentDeleted`는 수동 ACK용 `message`·`channel`을 함께 받음(core 소비자와 같음)
- 새로 둔 것: `_common/messaging/RetryingConsumer`(core와 같은 이름·동작 + 계약 위반 바로 DLQ), `InvalidEventException`, `record/domain/DeletionScope`. 삭제와 보고를 트랜잭션 안·밖으로 나누려고 Spring `TransactionTemplate` 사용(learning 첫 사용, 새 계층 아님)
- 기존 파일 수정: `EventEnvelope`(발행용 기본값 제거: `id`가 빠진 메시지에 무작위 id가 채워져 멱등 키가 매번 달라지는 문제, learning은 발행하지 않음), `MessagingConfig`(confirm 대기 시간), `AppProperties`(`messaging.maxRetries`), `application.yml`(수동 ACK·`missing-queues-fatal: false`·publisher confirm·readiness에 `rabbit`·`app.messaging.max-retries: 3`, read-timeout 주석을 core 호출까지로), `AttemptService`·`AttemptRepository`·`AttemptMapper`(`deleteByStudent`), 테스트 6개 클래스에 `spring.rabbitmq.listener.simple.auto-startup=false`(core 테스트와 같음, 리스너가 실제 RabbitMQ에 붙지 않게)
- 설계 문서: class-diagram 4.3(구현 상태·소비자 검증·삭제 흐름·`deleteByStudent` 순서·`delete` 시그니처), ERD 1장 FK 줄·4.3 비고·7장 확인 필요 줄 삭제, api-spec 5.6 마지막 줄(B3 해소), 아키텍처 1.6 수동 ACK 줄
- 검증: learning 테스트 217개(새 11: 삭제 4·소비자 3·재시도 4)·scripts/tests 74개, 보호 장치 16개를 빼면 각각 실패(삭제 순서 4·멱등·보고 3·표식 1·소비자 5·재시도 3). 통합 확인은 #148의 격리 compose(`scripts/report_integration/compose.yaml`, 합성 값, 프로젝트 `learning128`)에 learning `CORE_URL`만 덮어써서: core DB에 보호자·학생 2명과 `CONFIRMED` PROFILE 삭제 요청·outbox 행 저장 → core 중계가 `student.deleted` 발행 → learning·report 둘 다 보고하고 core 요청 `COMPLETED`(2초)·학생 `DELETED`, learning은 대상 학생 시도·초안·답변·판정 0행·다른 학생 그대로·표식 PROFILE. 같은 이벤트 재전달은 처리 뒤 만든 시도를 지우지 않고 보고만(재시도·DLQ 0), source가 다른 봉투는 재시도 없이 learning DLQ 1건. readiness에 rabbit 포함 UP. 확인 뒤 격리 환경 삭제

## 10. 관리자 미션 API (#145, 구 #81 흡수)

core #126(#47)이 관리자 미션 요청 10개(경로 8개)를 learning `/internal/admin/missions`로 넘기지만 learning에 받는 API가 없어 관리자 미션 화면이 동작하지 않던 문제를 고침. 클래스 다이어그램 4.1 이름(`AdminMissionController`·`MissionService`·`Mission.requirePublishable`·`MissionRepository`·`RubricRepository`)과 상태 다이어그램 3.1 전이 그대로. 계약은 api-spec 4.1 `/internal/admin/missions…` 줄과 learning OpenAPI(`/admin/missions…` 10개). 프론트·core와 계약 합의 뒤 구현

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 인증 | 내부 토큰 + `ADMIN`(아니면 403) + UUID `X-User-Id`(작성자·검토자, 없거나 형식 오류 400). `CONTENT` 권한 검사는 core, 학생 범위는 비어 옴 | core #126 프록시 |
| 응답 | 성공은 모두 JSON 객체. 목록 `{items, page, size, totalElements, counts:[{status, count}]}`, 나머지는 미션 전체 `AdminMission`(버전·기준표·검토 이력 포함, 작성 201). `counts`는 페이지·필터와 무관한 전체 4개 상태(없으면 0) | core 프록시는 JSON 객체만 중계, 이슈 확인 필요 ②(사용자 결정 → core 확인: 건수용 경로 따로 없음) |
| 버전 | 수정 `PATCH`·기준표 `PUT`은 새 불변 버전 추가 + `current_*`만 바꿈. 게시가 `published_*` ← `current_*`. 학생 목록·상세·시도 시작은 `published_*`, 진행 중 시도는 시작 당시 버전 | P07, ERD 4.1 |
| 공개 중 수정 | 상태는 `PUBLISHED` 그대로, 학생은 계속 공개 버전. `PUBLISHED`에서 검토 요청은 바뀐 것이 있을 때만(상태 유지), 승인 뒤 재게시로 교체 | 프론트·core 합의(학생 화면에서 미션이 갑자기 사라지지 않게) |
| 전이 | 검토 중(`REVIEW_REQUIRED`) 수정은 `DRAFT`로. 검토 요청 `DRAFT`·`UNPUBLISHED` → `REVIEW_REQUIRED`. 반려(`CHANGES_REQUESTED`)는 검토 중이면 `DRAFT`, 공개 중 수정본이면 상태 유지. 게시는 검토 대상일 때만, 중단은 `PUBLISHED`만. 그 밖은 409 `CONFLICT` | state-diagram 3.1 |
| 버전 대조 | 검토 요청·검토 본문의 `missionVersion`·`rubricVersion`이 현재 버전과 다르면 409 `MISSION_VERSION_CONFLICT`(낡은 화면에서 다른 버전을 승인하지 않게) | P07, core 허용 오류 코드 |
| 공개 검사 | 누락을 모두 모아 422 `MISSION_PUBLISH_INCOMPLETE` + 영문 `missingFields`(`title`·`question`·`subject`·`grade`·`achievementStandards`·`choices`·`categories`·`rubric`·`rubric.elements`·`rubric.elements.points`·`answerKey`·`exampleAnswer`·`review`). 기준표 요소는 **입력 방식 무관 1개 이상**(구 #81), `review`는 현재 버전 최신 검토가 `APPROVED` | FN-ADM-11, 프론트 합의(화면이 한글 표시), core 프록시가 영문 경로 모양만 통과 |
| 정답 키 | 입력 방식 모양 객체 `{choiceIds}`·`{assignments}`·`{finalAnswer}`, 선택지·그룹과 맞는지 공개 검사 | 프론트 합의, #79 |
| 동시 수정 | 쓰기 전 미션 행만 `FOR UPDATE`로 잠그고 다시 읽음. 같은 미션 동시 수정 8건 → 버전 2~9, 실패 없음 | 조인한 채 잠그면 기다린 뒤 새 버전 행을 못 보고 404가 나던 것을 동시 테스트로 확인 |
| 업로드·감사 | 장면은 URI 입력 유지(업로드 미구현). 감사 기록은 core(#47 후속, 응답의 `missionId`·버전 사용) | 이슈 확인 필요 ①, core 답변 |

- 설계와 다른 점: 컨트롤러 반환을 모두 `AdminMission`(설계는 `Mission`·`RubricVersion`·없음)으로. core가 JSON 객체 응답을 요구하고 화면이 바뀐 미션 전체를 다시 그려서. 상세 `detail`·`listForAdmin`·`getForAdmin` 추가(2.8 표의 상세 경로). `requestReview`·`review`에 버전 인자 추가(버전 대조). 관리자 SQL은 `AdminMissionMapper`로 나눔(학생 조회 `MissionMapper`와 섞지 않고, Repository는 설계대로 `MissionRepository` 하나)
- DB: learning `V7__mission_published_versions.sql`(기존 V1~V6 불변). `mission.published_version_id`·`published_rubric_version_id`(NULL 허용, DEFERRABLE FK) 추가 + 기존 `PUBLISHED` 행은 현재 버전으로 채움. 데모 시드도 같은 규칙으로 채움. ERD 1장·4.1·8장 반영
- 기존 파일 수정: `MissionService`(관리자 메서드, 생성자에 `RubricRepository`), `MissionRepository`(관리자 메서드, 생성자에 `AdminMissionMapper`), `MissionMapper.xml`(학생 조회·`findCurrentVersions`가 `published_*`), `db/seed/demo_missions.sql`, 테스트(`TestRows.mission`이 게시 미션에 `published_*`, `MissionRepositoryTest`·`AttemptServiceTest`·`MissionServiceTest` 공개 버전 반영), `scripts/tests/test_record_exists_openapi.py`(`@PatchMapping` 포함, 경로 수 33)
- 같이 고친 것(이슈 해야 할 일에 추가):
  - #80 판정 정정 잠금: `lockTarget`이 최신 정정 하위 조회를 붙인 채 잠가, 다른 신고 정정이 동시에 오면 기다린 뒤에도 앞 정정을 못 보고 `previousResult`가 원판정으로 저장됨(동시 8건 모두 `PARTIAL`로 재현). 위 동시 수정과 같은 방법으로 판정 행만 잠그고(`lockJudgment`) 다시 읽음(`findTarget`). 8절 `previousResult` 규칙이 동시 요청에서도 지켜짐
  - 연동 검증 스크립트 4개(`verify_dashboard_learning`·`verify_report_learning`·`report_integration/scenario`·`verify_feedback_learning`): DB에 직접 넣는 게시 미션에 `published_*`도 채움(V7 뒤 학생 시작 실패 방지, CI 밖 수동 검증)
  - class-diagram 4.1 구현 상태 줄: #128 뒤에도 남아 있던 "`deleteByStudent` 미구현", "별도 `RubricRepository` 없음"
- 설계 문서: state-diagram 3.1(공개 중 수정 전이·전이 표·학생은 `published_*`), ERD(공개 버전 칸·DEFERRABLE·4.1 비고·공개 검사·8장 V1~V7, 같은 줄의 표·컬럼 수는 develop의 #157 report 표까지 실제 검사 값 69/606으로), class-diagram 4.1(컨트롤러·서비스 메서드·`requirePublishable` 조건·관리자 API·버전 메모), api-spec 4.1 관리자 미션 줄·3.10 합의·2.8 공급자 계약 문구, OpenAPI(경로 10개·`AdminMission` 등 스키마·422 `missingFields` 목록)
- 검증: learning 테스트 238개(새 21: 미션 전이 6·관리자 서비스 7·동시 수정 1·컨트롤러 6·동시 정정 1), scripts/tests 79개(새 `test_admin_missions_contract.py` 3: core 프록시 경로 10개 = OpenAPI, 목록 쿼리, `missingFields` 코드가 core 필터 통과). 보호 장치 17개를 빼면 각각 실패(공개 버전 조회 2·게시 복사·잠금·전이 4·요소 1개 이상·풀이 단계·정답 키·승인·평평한 요소 행·관리자만·422 `missingFields`·배점·`counts`), 동시 정정 테스트는 고치기 전 코드에서 실패 확인. DB: 임시 PostgreSQL에서 `check_db_migrations.py` 통과(learning 19표/160컬럼 ERD 일치·재실행 이력 불변), V6 데모 데이터 위에 V7 적용 시 게시 10건 채움·초안 10건 비움. 실제 연동: core·learning JAR + 임시 DB로 core `/api/v1/admin/missions` 경유 `CONTENT` 없는 관리자 403 → 작성 201 → 400 통과 → `DRAFT` 게시 409 → 기준표·미리보기 → 승인 전 게시 422 `["review"]` → 승인·게시 → 학생 1판 시작 → 공개 중 수정(2판, 학생은 1판) → 낡은 버전 409 → 재검토·재게시(학생 2판, 진행 중 시도 1판) → 목록 필터·`counts` → 중단(학생 상세 409, 진행 중 시도 이어하기 200)
- 확인 필요·한계:
  - core가 learning 404를 아직 503 `ADMIN_MISSIONS_UNAVAILABLE`로 바꿈(없는 미션 실제 확인). core가 고치기로 함
  - 프론트 `missingMissionFields`를 같은 조건으로 맞추는 것은 프론트 반영 중(이슈 해야 할 일 4)
  - `verify_feedback_learning.py`는 학생 시작·답변 제출까지 통과(위 스크립트 수정 확인)하지만 AI 실패 단계에서 멈춤. develop 원본에서도 같아 #145와 무관한 기존 문제, 지금 core는 Redis도 필요. 원인은 스크립트가 learning에 `CORE_URL`을 넘기지 않아 피드백 전 결제 사용 확인이 503 `PAYMENT_USAGE_UNAVAILABLE`로 끝나는 것(11절에서 확인)
  - V7 추가는 DB 담당에게 공유

## 11. 신고 지원 조회 (#146)

core #46 신고·문의는 접수·문의 연결·관리자 정정 전에 learning에서 대상의 학생·시도를 확인하고, 관리자는 신고된 시도 원문을 봄. core `LearningSupportClient`는 두 경로를 이미 부르지만 learning 구현이 없어 #80 정정이 있어도 실제 흐름이 이어지지 않던 문제를 고침. 계약은 api-spec 4.1 두 줄·5.7과 learning OpenAPI(core 소비 계약 `support-learning-required.yaml` 0.2.0은 그대로). 설계에 없던 자리만 추가하고 나머지는 기존 판정 조회를 다시 씀

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 위치 | 새 패키지 없이 `judgment/`: `SupportController` + `JudgmentService.supportTarget`·`supportOriginal` + `JudgmentMapper.findSupportTarget` | 아키텍처 learning `judgment/controller` "피드백·정정 내부 API", 이슈 "class-diagram 확인 후 결정" |
| 대상 확인 | `GET /internal/support/targets/{JUDGMENT·FOLLOWUP·ATTEMPT}/{id}` → `{studentId, attemptId, judgmentId?, previousResult?}`. 판정은 판정 ID·지금 보이는 결과(최신 정정, 8절 정정 직전 결과와 같은 규칙, `DONE` 전이면 없음), 되묻기는 만든 판정 ID, 시도는 둘 다 없음. 없는 칸은 null 대신 생략. 원문 없음 | core 계약(선택 칸), core는 정정 전 `previousResult`가 결과 값이 아니면 409 |
| 대상 확인 권한 | `STUDENT`·`PARENT`·`ADMIN`(관리자는 학생 1명, #80과 같음) 아니면 403, `X-User-Id` UUID 아니면 400, 대상 없음 404 → 대상 학생이 범위 밖 403(#80 정정과 같은 순서) | core가 학생·보호자 신고와 관리자 정정 전 확인에 같은 경로를 씀 |
| 원문 | `GET /internal/support/attempts/{id}` → `{studentId, attemptId, answers:[{answerId, version, text, feedback}]}`. 기존 `timeline`·`results`를 그대로(`text`는 시도 상세 원문, `feedback`은 시도 상세와 같은 모양). 초안·메모·이름·돌아보기 없음. `ADMIN` + 학생 1명 + `X-User-Id` | core는 이 네 칸만 골라 씀, api-spec 5.7 "학생 전용 `/internal/attempts`를 관리자로 쓰지 않음" |
| `judgmentId` | 피드백 결과 `judgment`에 `judgmentId`(피드백 SSE·시도 상세·원문 모두, 만드는 곳은 `stored()` 한 곳). 판정 전(`judgment: null`)이면 판정 신고 없음 | core 합의 (a): 프론트 신고 버튼이 판정 ID로 신고(이슈 해야 할 일에 추가) |

- 설계와 다른 점: 없음. 설계에 없던 `SupportController`·서비스 메서드 2개·`judgmentId`만 class-diagram 4.2·api-spec에 먼저 추가
- 기존 파일 수정: `JudgmentView`(`judgmentId`), `StoredJudgment`·`JudgmentMapper.xml` `findStored`(`judgment_id`), `JudgmentMapper`·`JudgmentRepository`(`findSupportTarget`), 테스트 `AttemptControllerTest`·`FeedbackControllerTest`(`judgmentId` 인자·확인), `scripts/tests/test_record_exists_openapi.py`(경로 수 33 → 35)
- 같이 고친 것:
  - `scripts/tests/test_support_openapi.py`(core #46 담당 테스트) 22행: "learning 계약에 `/support/targets`가 없어야 함"(미구현 경계)을 "조회 두 경로가 있어야 함"으로. 구현해서 깨지는 줄이라 같은 PR에서(사용자 확인, 같은 테스트의 다른 검사·core 소비 계약은 그대로, 담당에게 공유)
  - `JudgmentMapper.xml` 주석이 #145에서 바뀐 `CorrectionMapper.lockTarget`을 가리키던 것을 `findTarget`으로
  - api-spec 5.7 "learning 공급자 필요 계약 (아직 구현되지 않음)" 제목·"정정 구현이 없다" 문장을 사실대로(#80·#146 구현), 나머지 문장은 그대로
- 설계 문서: api-spec 3.2(`judgmentId` 예시·설명)·4.1(피드백 줄 `judgmentId`, 두 경로 줄)·5.7(위 두 곳), class-diagram 4.2(`SupportController`·`supportTarget`·`supportOriginal`·화살표·메모), OpenAPI(경로 2·`SupportTarget`·`SupportOriginal`·`Judgment.judgmentId`, 버전은 #80처럼 그대로)
- 검증: learning 테스트 246개(새 8: 서비스 4·컨트롤러 4), scripts/tests 83개(새 `test_support_lookup_contract.py` 4: core가 부르는 경로 = OpenAPI, 대상 유형, core가 읽는 칸, `judgmentId`). 보호 장치 13개를 빼면 각각 실패(범위 403·없음 404·최신 정정·되묻기 판정 ID·원문 범위·피드백 판정 ID·컨트롤러 역할·관리자 1명·`X-User-Id` 2·원문 관리자만·학생 1명·없는 칸 생략). 실제 연동: core·learning JAR + 임시 DB(합성 계정, ai 없이 고르기 규칙 판정, 되묻기 1건만 합성 행)로 core 경유 피드백 SSE·시도 상세에 `judgmentId` → 학생 JUDGMENT 신고(core가 learning 학생·시도 저장) → 보호자 FOLLOWUP 신고·ATTEMPT 문의 연결 → 다른 가족 신고 거부 → 관리자 신고·문의 상세 원문(답변 네 칸, 메모 없음, 열람 감사 1건) → 검토 → 정정(`previousResult: CORRECT` → `RETHINK`, 학생 시도 상세 `RETHINK`, 원판정 `CORRECT` 그대로)
- 확인 필요·한계:
  - 범위 밖 신고: learning 403을 core가 503 `SUPPORT_DEPENDENCY_UNAVAILABLE`로 바꿈(core는 공급자 비-2xx를 모두 503, 5.7). 신고는 막힘
  - 학생 신고 버튼이 `judgmentId`를 쓰는 화면 반영은 프론트(#82 쪽)
  - `verify_feedback_learning.py`는 learning에 `CORE_URL`이 없어 피드백이 결제 사용 확인에서 503(10절 기존 문제의 원인). 다른 팀원 스크립트라 고치지 않음
