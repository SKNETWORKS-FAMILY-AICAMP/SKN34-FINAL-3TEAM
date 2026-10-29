# learning 학습 서비스 (#22~#27·#79·#80)

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
- 미구현: `student.deleted` 소비(`StudentDeletedConsumer`·`StudentDeletionService`)

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
| `previousResult` | 정정 직전에 보이던 결과(앞선 정정이 있으면 그 결과). 최신 정정은 `created_at`(같으면 `id`) 가장 늦은 행 | ERD "정정 전 결과" |
| 저장 모양 | `previous`·`corrected` jsonb는 `{"result": "PARTIAL"}` | ERD 비고에 추가 |
| 보이는 곳 | `findStored` 한 쿼리라 피드백 결과·시도 상세·#27 기록 모두 최신 정정 결과. 바꾸는 것은 `result`뿐: 정정이 있으면 `heldReason` null(ai 판정의 이유라서), 판정 요소·되묻기·`nextActions`·마무리 체크리스트는 원판정 | 사용자 결정 ②. `nextActions`는 결과가 아니라 되묻기·시도 상태로 계산 |
| impact | `aggregation: NOT_APPLIED`(learning 수치 집계는 판정 결과를 쓰지 않아 바꿀 것 없음, 오류 아님), `conversation`·`report: UNKNOWN`(learning이 확인할 수 없음) | core와 합의 ④ |
| 오류 코드 | `JUDGMENT_STATE_CONFLICT`는 기존 코드 재사용, `CORRECTION_REPORT_CONFLICT`는 새 코드. 둘 다 api-spec 4.1에만(1.3 공개 표에 넣지 않음) | #78 리뷰대로 learning 내부 코드는 4.1 비고. core가 409·422를 공개 코드로 바꿈 |

- 설계 문서: api-spec 4.1 정정 줄, class-diagram 4.2 끝 메모(`results()`·잠금 순서), state-diagram 3.3(정정은 `DONE`만), ERD 비고(jsonb 모양), OpenAPI(경로·`AdminUserId`·`AdminRole`·`CorrectionScope`·`CorrectionRequest`·`CorrectionResult`·`JudgmentResult`, 버전은 #26·#27처럼 그대로)
- 기존 파일 수정: `JudgmentService`(`correct`), `JudgmentMapper.xml` `findStored`(최신 정정 결과·보류 이유), `scripts/tests/test_record_exists_openapi.py` 컨트롤러 경로 수 21 → 22
- 검증: 테스트 199개(새 13: 서비스 6·동시 2·컨트롤러 5), scripts/tests 58개. 보호 장치 12개를 빼면 각각 실패(`DONE` 전 409는 DB 제약 `ck_judgment_result_when_done`·null 검사와 세 겹). compose 실제: 고르기 정답 `CORRECT` → `RETHINK` 정정, 같은 키 처음 응답 그대로, 422·409·409·403·404, 피드백·시도 상세·기록 모두 `RETHINK`, DB 원판정 `CORRECT` 그대로(ai 호출 없음, 만든 시도 2건만 삭제)
- 한계: 같은 신고를 다른 판정에 동시에 보내면 판정 잠금이 달라 둘 다 저장될 수 있음(`error_report_id` UK 없음, core는 신고마다 한 정정만 보냄), 같은 키를 다른 판정에 동시에 보내면 키 UK로 한쪽 500. `judgment_correction.judgment_id` 인덱스 없음(정정은 드묾)
- 확인 필요: core가 정정 전에 부르는 `/support/targets/{type}/{id}`·관리자 원문 `/support/attempts/{id}`는 별도 이슈(#80만으로 실제 흐름 미완성). learning 학생 삭제를 만들 때 `judgment_correction`을 판정보다 먼저 지움(FK)
