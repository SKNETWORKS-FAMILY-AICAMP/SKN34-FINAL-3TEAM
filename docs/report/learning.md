# learning 학습 서비스 (#22~#27·#79·#80·#128·#145·#146·#82·#169·#137·#164·#205·#241·#207·#201·#262·#336·#353·#355·#385·#386)

계약은 [API 명세](../design/api-spec.md) 2.2·3.1~3.8·4.1과 [learning OpenAPI](../../contracts/openapi/learning-service.yaml), 판정 상태는 [상태 다이어그램](../design/state-diagram.md) 3장.

## 1. 미션 조회 (#22)

- 학생 확인: `X-User-Role: STUDENT`이고 `X-Student-Scope`에 학생 1명일 때만(`UserContext.requireSelfStudent()`, 다른 학생 Controller도 공용). 학년 `grade`(3~6)·시연 여부 `demo`(기본 false)는 core가 붙임
- 학생용 객체는 `MissionView`(정답·예시 답·기준표 필드 없음). 노출 규칙은 `MissionView.isOpenTo(grade, demo)` 한 곳(학년 범위, 논술 초5~6, `demo_only`는 demo일 때만)
- 상세는 목록과 같은 범위. 비공개·범위 밖 409 `MISSION_NOT_AVAILABLE`, 없으면 404
- 수행 상태는 `MissionRepository`가 미션별 가장 최근 시도로 읽음(없으면 `NOT_STARTED`). `AttemptService`를 부르면 순환이라 Repository에서 직접
- 진행 중 시도는 시작 당시 미션 버전을 유지(P07). 목록·상세는 현재 공개 버전
- 2026-11-06 결정([서비스 기획 방향](service-direction.md)): 학생 기본 경로가 주간 테마 당일 문제로 바뀌고 이 목록은 추가 문제(`EXTRA`) 고르기로 쓴다. 테마·요일 검사는 learning `theme`(24절, [API 2.11](../design/api-spec.md), [ERD 4.2.1](../design/erd.md#421-주간-테마-p23-385-v11v12))

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
| 하루 미션 한도 | learning은 확인하지 않음 | core 책임. #210 결정으로 Redis가 아닌 PostgreSQL(`mission_daily_usage`, 무료 하루 1개, 구현 예정) |

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
| 실패 코드 | `AI_TIMEOUT`·`AI_UNAVAILABLE`·`AI_BAD_RESPONSE`·`AI_CIRCUIT_OPEN`·`INTERNAL_ERROR`, 고착 탐지는 `LEASE_EXPIRED`(#241, 17절). `retryable`은 ai 503 본문 값, 시간 초과·연결 실패·차단 true, 4xx·계약 밖 false |
| `nextActions` | 읽는 시점 기준: 답하지 않은 되묻기 있음 `[ANSWER_FOLLOWUP, FINISH]`, 없음 `[FINISH]`, 마무리·완료 `[]`, 처리 중·실패 `[]` |
| 버전 | `versions{mission:"미션 code@버전", rubric:"미션 code@기준표 버전", model, prompt}`(기준표에 code 컬럼이 없어 미션 code 사용) |
| ai 호출 | 응답 35초, 재시도 없음, 서킷 20건·50%·30초(core와 같은 값). 요청 본문에 학생 이름·ID 없음(학년만) |
| 결과 조회 순서 | 판정 행을 먼저 읽고 요소·되묻기를 읽음(READ COMMITTED에서 섞임 방지) |

- 후속 결과: 판정 정정 수신 API(#80, 8절)·미션 공개 검사(#81)·고착 `RUNNING` 1분 주기 탐지(#241, 17절) 구현. 판정 요청의 미션 질문(`AiModels.question`)은 M2 입력에만 사용

## 5. 마무리·돌아보기·자기 평가 (#26)

- 마무리 조건: 시도 안에 판정 `DONE` 1회 이상(보류 포함). 되묻기에 답하지 않아도 가능. 이미 마무리했으면 같은 결과(기록 불변)
- 처리 순서: 시도 행 잠금 → 타임라인 → `FinishPolicy.canFinish` → `Attempt.finish(now)` → `finished_at` 조건부 UPDATE
- `reveal`은 시도의 기준표 버전 `example_answer`(닫힌 문제 시드는 "정답: …" 형식), `revealKind`는 고르기·순서·분류·풀이 `ANSWER`, 서술·논술 `EXAMPLE`
- 체크리스트: 기준표 요소 전체, 이 시도의 처리 완료 판정 중 원문 구절과 함께 충족된 적이 있는 요소만 체크(가장 최근 구절). 보완 답변 판정은 그 답변만 보므로 마지막 답변만 쓰면 앞에서 확인된 요소가 빠짐. 읽을 때 계산
- 돌아보기 `{difficulty(EASY·NORMAL·HARD 필수), text(선택, 빈 글 null)}`. DDL은 nullable이지만 P04가 필수라 API에서 막음. 완료 뒤 409 `ATTEMPT_CLOSED`, 마무리 전 409 `REVEAL_CONDITION_UNMET`
- 자기 평가: 마무리 뒤·완료 전. `{checks:[{elementId, checked}]}` 일부만 보내도 되고 재전송은 `checked`만 변경. 응답은 요소마다 `{elementId, label, selfChecked, aiChecked, quote}`
- 마무리 경합: 판정 `saveResult` 트랜잭션 시작에서 시도 행을 `FOR UPDATE`로 다시 읽어 닫혔으면 되묻기를 저장하지 않음(마무리 대기·거절은 P04에 없는 조건이라 채택하지 않음)
- 잠금 순서는 모두 시도 → 판정
- 구현 예정(P20·P21, [서비스 기획 방향](service-direction.md)): 돌아보기 저장(학습 완료) 성공 뒤 core가 포인트를 적립하고, 커뮤니티 공개가 켜진 학생이면 learning에 공유를 요청한다(학생·미션당 1개, 처음 마무리한 시도의 마지막 답변). 시작 요청 `context`가 `THEME_DAY`면 신규 시도만 요일 검사

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

- 웹 표시: `answerUnit`·`categories`는 `StudentWorkPage`에 반영. 수학 체크리스트의 "최종 답" 항목은 확인 필요

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

- 한계: 같은 신고를 다른 판정에 동시에 보내면 판정 잠금이 달라 둘 다 저장될 수 있음(`error_report_id` UK 없음, core는 신고마다 한 정정만 보냄), 같은 키를 다른 판정에 동시에 보내면 키 UK로 한쪽 500. `judgment_correction.judgment_id` 인덱스 없음(정정은 드묾)

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

- 위치 정리(#256, 11/02): 원래 설계(architecture 2.6, 10/24)는 별도 `deletion/` 패키지였으나 #128에서 `record/consumer`·`record/service`에 구현했다(이슈 #128 작업 위치 "`record/` 또는 삭제 기능 패키지", 현재 이슈 본문 기준이며 11/02 수정 기록 있음). 위치를 고른 이유는 당시 기록하지 않았다. 종합 검증(audit A15)이 설계를 `record/`로 맞췄고, #256에서 빈 `deletion/` 폴더(`.gitkeep` 2개)를 지우고 architecture 2.6 트리·class-diagram 4.3을 `record/` 기준으로 정리했다. 코드 변경은 없다
- 알려진 한계(#256): `record/`가 기록 조회와 함께 삭제 소비(쓰기)·이벤트 처리 기록(`processed_event`와 정리 작업)·결제 사용 증빙을 맡아 "조회 API" 패키지 설명과 다르다. report-service는 같은 기능을 `deletion/`에 둬 서비스 간 위치도 다르다. `processed_event`는 모든 이벤트 소비자가 쓸 수 있는 중복 처리 방지 테이블이라 다른 소비자가 생기면 `_common/messaging` 쪽이 맞을 수 있다. 조회 SQL(`RecordMapper.xml`·`RecordExistsMapper.xml`)은 `deleted_student`로 삭제된 학생을 거르므로 위치를 옮겨도 이 읽기는 남는다. 경계 정리는 별도 리팩터로 다룬다

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
| 업로드·감사 | 장면은 URI 입력 유지(업로드 미구현). 감사 기록은 core #47 `MissionAuditService`(응답의 `missionId`·버전 사용) | 이슈 확인 필요 ①, core 답변 |

- 설계와 다른 점: 컨트롤러 반환을 모두 `AdminMission`(설계는 `Mission`·`RubricVersion`·없음)으로. core가 JSON 객체 응답을 요구하고 화면이 바뀐 미션 전체를 다시 그려서. 상세 `detail`·`listForAdmin`·`getForAdmin` 추가(2.8 표의 상세 경로). `requestReview`·`review`에 버전 인자 추가(버전 대조). 관리자 SQL은 `AdminMissionMapper`로 나눔(학생 조회 `MissionMapper`와 섞지 않고, Repository는 설계대로 `MissionRepository` 하나)
- DB: learning `V7__mission_published_versions.sql`(기존 V1~V6 불변). `mission.published_version_id`·`published_rubric_version_id`(NULL 허용, DEFERRABLE FK) 추가 + 기존 `PUBLISHED` 행은 현재 버전으로 채움. 데모 시드도 같은 규칙으로 채움. ERD 1장·4.1·8장 반영
- 같이 고친 것(이슈 해야 할 일에 추가):
  - #80 판정 정정 잠금: `lockTarget`이 최신 정정 하위 조회를 붙인 채 잠가, 다른 신고 정정이 동시에 오면 기다린 뒤에도 앞 정정을 못 보고 `previousResult`가 원판정으로 저장됨(동시 8건 모두 `PARTIAL`로 재현). 위 동시 수정과 같은 방법으로 판정 행만 잠그고(`lockJudgment`) 다시 읽음(`findTarget`). 8절 `previousResult` 규칙이 동시 요청에서도 지켜짐
  - 연동 검증 스크립트 4개(`verify_dashboard_learning`·`verify_report_learning`·`report_integration/scenario`·`verify_feedback_learning`): DB에 직접 넣는 게시 미션에 `published_*`도 채움(V7 뒤 학생 시작 실패 방지, CI 밖 수동 검증)
  - class-diagram 4.1 구현 상태 줄: #128 뒤에도 남아 있던 "`deleteByStudent` 미구현", "별도 `RubricRepository` 없음"
- 확인 필요·한계:
  - 당시 core가 learning 404를 503 `ADMIN_MISSIONS_UNAVAILABLE`로 바꿨으나, 이후 `AdminLearningService`가 404 `NOT_FOUND`를 그대로 전달하도록 수정됨

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
- 같이 고친 것:
  - `scripts/tests/test_support_openapi.py`(core #46 담당 테스트) 22행: "learning 계약에 `/support/targets`가 없어야 함"(미구현 경계)을 "조회 두 경로가 있어야 함"으로. 구현해서 깨지는 줄이라 같은 PR에서(사용자 확인, 같은 테스트의 다른 검사·core 소비 계약은 그대로, 담당에게 공유)
  - `JudgmentMapper.xml` 주석이 #145에서 바뀐 `CorrectionMapper.lockTarget`을 가리키던 것을 `findTarget`으로
  - api-spec 5.7 "learning 공급자 필요 계약 (아직 구현되지 않음)" 제목·"정정 구현이 없다" 문장을 사실대로(#80·#146 구현), 나머지 문장은 그대로
- 확인 필요·한계:
  - 범위 밖 신고: learning 403을 core가 503 `SUPPORT_DEPENDENCY_UNAVAILABLE`로 바꿈(core는 공급자 비-2xx를 모두 503, 5.7). 신고는 막힘
  - 학생 신고 버튼이 `judgmentId`를 쓰는 화면 반영은 프론트(#82에서 반영, 12절)

## 12. 학생 피드백 화면 계약 반영 (#82, web)

learning 피드백 응답(#25 PR #78 "프론트 확인", #146 `judgmentId`)을 학생 화면·웹 어댑터·목업에 맞춤. core는 learning 결과를 SSE `result`로 그대로 넘기므로 화면까지 같은 모양. API 계약 변경 없음(api-spec 3.2·4.1 그대로). 이슈 지침대로 기존 `apiGateway`·`demoGateway`·도메인 타입만 고치고 새 계층 없음

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| null 필드 | `Feedback.judgment`·`followup`·`judgment.heldReason`·`versions`는 생략 대신 `null` 허용, 요소 `sourceType`은 근거 구절 없는 ai 요소면 `null`. 화면은 이미 `?.`·참거짓 검사라 동작 그대로, 타입만 맞춤 | learning 응답은 판정 전·되묻기 없음을 `null`로 보냄(api-spec 4.1) |
| `versions` | `{mission, rubric, model, prompt}` 타입만 받음(화면 미사용), `elementId`는 기존대로 문자열(실서버는 `rubric_element.id` UUID) | 이슈 해야 할 일 3 |
| 어댑터 검증 | `feedbackDto`: 판정이 있으면 `judgmentId` 문자열·`result` 4종 필수, 요소 `sourceType`은 4종 중 하나(`null` 포함), 아니면 계약 오류(`CONTRACT_NOT_READY`) | 신고 대상 ID가 없으면 신고가 실패하므로 받을 때 막음 |
| 재시도 | SSE `error`가 `retryable:false`면 "피드백만 다시 요청" 버튼 대신 "지금은 피드백을 다시 받을 수 없어요…" 안내(오류 상자 "다시 시도"는 원래 숨김) | learning은 ai 4xx·계약 밖 응답을 `retryable:false`로 보냄(4절) |
| 신고 버튼 | 판정 신고 `targetId`를 마지막 답변 ID 대신 피드백 `judgment.judgmentId`로, 판정이 없으면 버튼 숨김 | #146 learning이 판정 ID로 대상을 찾음(답변 ID면 core 503), core 합의 (a). 이슈 해야 할 일에 추가 |
| 목업 되묻기 | 고르기뿐 아니라 순서·분류 정답도 되묻기 없이 `["FINISH"]`, 목업 판정에 `judgmentId` | learning 되묻기 조건 "고르기 활동 `CORRECT` 아님"(4절) |

- 설계와 다른 점: 없음(설계 문서 변경 없음)
- 확인 필요·한계:
  - 새로고침하면 실패한 피드백의 `retryable`을 알 수 없음(시도 상세의 `FAILED` 결과에는 없음). 그때는 다시 요청 버튼을 보여 주고, learning이 `FAILED`를 다시 실행

## 13. domain 프레임워크 의존 정리 (#169)

[점검 기록](audit.md) A3: learning domain 6개 파일이 `HttpStatus`(5개)·Jackson `@JsonInclude`(`Support.kt`)를 참조해 아키텍처 2.1 "Domain은 프레임워크 의존 금지"와 다름. 확인 필요 항목(domain의 HttpStatus 허용 여부)은 허용하지 않는 쪽으로 정함(core #168과 같은 결정 대상). 설계 문서의 원칙은 그대로이고, API 응답(code·status·본문)은 바뀌지 않음

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| domain 오류 | domain은 `BusinessException(ErrorKind.CONFLICT, code, …)`처럼 오류 종류(`INVALID`·`CONFLICT`·`UNPROCESSABLE`)만 넘기고, 400·409·422 변환은 `_common/exception`의 `BusinessException` 보조 생성자가 함. domain 5개 파일 10곳(`AnswerContent`·`Attempt`·`Judgment`·`Mission`·`Period`, `MissionPublishIncompleteException` 포함) | 아키텍처 2.1(domain 의존 금지)·2.3(예외 → 응답 변환은 `_common/exception`), 이슈 "새 계층·공통 라이브러리 만들지 않음" |
| 별도 domain 예외를 두지 않은 이유 | 같은 code(`ATTEMPT_CLOSED`·`ANSWER_INCOMPLETE`·`REVEAL_CONDITION_UNMET`·`JUDGMENT_STATE_CONFLICT`)를 service도 던짐. 예외 타입을 나누면 처리기·테스트 약 40곳이 "어느 층에서 던졌나"에 따라 갈리고, 기존 테스트가 하던 HTTP 상태 확인을 잃음 | 이슈 완료 조건 "오류 응답 code·status 변화 없음"을 기존 테스트 그대로 검증 |
| 신고 대상 응답 | `@JsonInclude(NON_NULL)`을 domain `SupportTarget`에서 새 응답 DTO `SupportTargetResponse`(`judgment/controller/SupportResponses.kt`)로 옮김. `SupportController.target`이 변환해 반환 | 이슈 해야 할 일 3, 기존 `AttemptResponses`·`MissionResponses` 방식 |

- 설계와 다른 점: 없음. class-diagram 4.2 `SupportController.target` 반환 타입만 `SupportTargetResponse`로 고침. 공통 `BusinessException` 그림(class-diagram 1장, core와 공유)은 필드가 그대로라 손대지 않음. OpenAPI 스키마 이름 `SupportTarget`은 응답 모양이 같아 그대로
- 한계: 예외 객체는 실행 중에 HTTP 상태를 들고 있음(domain 코드는 모름). 오류 종류는 지금 domain에서 쓰는 세 가지뿐이고, 새 종류가 필요하면 `ErrorKind`와 변환을 함께 늘림
- #249(11/02): 위 한계를 해소함. domain은 HTTP 상태가 없는 `DomainException(kind, code, …)`을 던지고, 상태 변환은 `_common/exception`의 `statusOf` 한 곳, 처리기·service 테스트는 `httpStatusOf`·`errorCodeOf`로 두 예외를 같게 다룸. 위 "별도 domain 예외를 두지 않은 이유"의 걱정(처리기·테스트 분리, HTTP 상태 확인 상실)을 이렇게 피함 ([#249 절](core-gateway.md#domain-예외-168249))

## 14. 공통 예외·초안 저장 경합 테스트 (#137)

[점검 기록](audit.md) 1회차 테스트 공백의 learning 테스트 공백을 채움. 테스트만 추가했고 코드·설계·API 계약은 바꾸지 않음

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 405·415 | 실제 학생 경로(`AttemptController`)로 없는 메서드(`DELETE /internal/attempts/{id}`)·JSON 아닌 본문(`PUT …/draft` `text/plain`)을 보내 `application/problem+json`, `status`, `code`(`METHOD_NOT_ALLOWED`·`UNSUPPORTED_MEDIA_TYPE`), `type`, `instance`, `traceparent`의 `traceId`를 확인. 405는 `Allow` 헤더도 | api-spec 1.3 Problem Details, `GlobalExceptionHandler.createResponseEntity`가 Spring 기본 예외에도 `code`·`traceId`를 붙임 |
| 초안 저장 경합 | 마무리한 시도에서 돌아보기 트랜잭션이 시도 행을 잠그고 완료로 바꾼 채 커밋 직전에 멈춘 사이 초안을 저장: 초안 저장은 잠금을 기다렸다가(0.5초 뒤에도 끝나지 않음) 커밋 뒤 `409 ATTEMPT_CLOSED`, 초안 행(버전·내용·저장 시각)은 그대로 | audit B14(#127에서 `saveDraft`가 `lockOwned`로 시도 행 잠금). 여러 요청을 한꺼번에 보내면 겹칠지가 운이라, 겹치는 순서를 직접 만들어 잠금이 없으면 항상 실패하게 함 |

- 범위 밖: audit 1회차 테스트 공백 learning 줄의 `EventEnvelope`·`MessagingConfig`는 #128 소비자 테스트에서 다룸

## 15. 피드백 실제 연동 검증 환경 복구 (#164)

### 수정 범위와 실행 전제

- 원인: `scripts/verify_feedback_learning.py`가 임의 포트로 core를 띄우면서 learning에 `CORE_URL`을 넘기지 않아 결제 사용 확인이 기본 8080으로 향함
- 수정: 실행별 고유 PostgreSQL(`postgres:17.11-alpine`)·Redis(`redis:8.2.10-alpine`) 컨테이너, 자식 JVM에 서비스 URL·Redis 설정 명시, 종료·예외 때 이 실행의 컨테이너만 역순 제거
- 실행: JDK 21·Python 3.12·Docker로 core·learning `bootJar` 후 스크립트 실행(인자는 스크립트 `--help`). Docker CLI가 없는 Linux에서는 `--db-host`·`--redis-host`로 호출자가 만든 일회용 sidecar를 지정하고 정리도 호출자가 함

### 검증

기존 6사례(FAILED → 재시도 DONE → 저장 결과 재사용, RUNNING 중 중복 방지, SSE 연결 종료 후 저장, HELD의 DONE 저장, 영구 AI 실패 보존 등)가 실제 core·learning HTTP/SSE·PostgreSQL·Redis(AI만 합성 대역)로 통과. 정상·실패 종료 모두 이 실행이 만든 컨테이너·익명 볼륨이 남지 않음을 확인.

## 16. 학생 답변 표현 필터링 (#205)

10/29 멘토링("초~중학생 대상이라 욕설·비속어 입력 대응 필수, 공신력 있는 가이드 기반 필터링·제출 차단")과 11/1 결정("유사 서비스 방식 탐색 후 답변 필터링, 필터 대상이면 제출 차단", [멘토링 기록](planning-decisions.md#1-1029-오프라인-멘토링-결정후속))에 따라 학생 답변(최초·보완)에 표현 검사를 넣음. 막는 답변은 저장·판정 요청 없이 `422 ANSWER_INAPPROPRIATE`. 계약은 [API 명세](../design/api-spec.md) 1.3과 4.1 답변 제출 줄, learning OpenAPI `submitAnswer` 422·`SubmitRequest`

### 조사

| 대상 | 방식 | 이번에 따른 것 |
|---|---|---|
| Scratch | 제출 차단, 걸린 단어 비공개, 예외 목록 | 제출 차단·걸린 말 비공개·오탐 예외 |
| Roblox(13세 미만 채팅) | 가리기, 전화번호·주소 걸러 냄 | 연락처 범주 |
| 네이버 클린봇·세이프봇 | AI 판단·가리기 | 따르지 않음(외부 AI 없이, 아래 사용자 결정) |
| Code.org | 외부 필터 API | 따르지 않음 |
| 국내 초중등 학습 서비스(밀크T·홈런·스마트올·클래스팅·엔트리·AI 디지털교과서) | 공개 자료 없음, 직접 시험 못 함 | 한계로 기록 |

| 출처 | 라이선스·조건 | 결정 |
|---|---|---|
| [korcen](https://github.com/Tanat05/korcen) 2026판 `eecd9763` | MIT | 데이터·전처리 규칙만 JSON으로 옮김(코드·의존성 없음) |
| korcen 2023판 `2cfdf958` | Apache 2.0 | 2026판에 없는 항목만. 2024-11 개편에서 `씨발`(오탐 예외로만 남음)·`존나`·`졸라`가 빠진 것을 측정에서 확인해 보충 |
| 국립국어원 우리말샘 Open API | CC BY-SA 2.0 KR | 뜻풀이가 "욕하여·욕으로·비속하게 이르는 말"로 끝나는 3자 이상 일반어 61개 + "낮잡아·속되게 이르는 말" 중 데이터로 확인한 7개. 키는 `.env`, 응답 원자료는 저장소에 넣지 않음 |
| Curse-detection-data, NSMC test | MIT, CC0 | 측정에만 씀. 저장소에 넣지 않음 |
| KISO 이용자보호시스템(KSS) | 기업 신청 외부 API | 쓰지 않음. 학생 원문이 외부로 나가 NFR-SEC-03·architecture 4.3 허용 목록과 충돌, 장애 시 처리·키 관리·승인 시점 미정. 후속 |
| LDNOOBW `ko` | CC BY 4.0 | 쓰지 않음. 72개, 검색 자동완성용이라 korcen·우리말샘으로 대신 |
| hlog2e/bad_word_list, badwords-ko | 라이선스 없음, 단어 출처 불명 | 쓰지 않음 |
| AI Hub 텍스트 윤리검증, K-MHaS | 신청·용도 제한(공개 저장소 재배포 불가), 원 저장소 라이선스 미확인 | 쓰지 않음 |

### 기준과 범주

| 범주(`ExpressionCategory`) | 근거 | 처리 | 안내(`detail`) |
|---|---|---|---|
| `PROFANITY` 욕설·비속어 | 청소년 보호법 시행령 [별표 2] 2.차, 방송심의에 관한 규정 제51조 제3항 | 항상 차단 | "고운 말로 바꿔서 다시 적어 주세요." |
| `SEXUAL` 성적 표현 | [별표 2] 2.가·나·라, 같은 규정 제35조 제2항 | 항상 차단 | 같음 |
| `HATE` 혐오·차별 | KISO 혐오표현 자율정책 가이드라인 제2조, 같은 규정 제21조 제3항 | 미션 본문에 나온 말이면 허용([별표 2] 1.가 맥락 고려) | 같음 |
| `THREAT` 남을 향한 위협·자해 조장 | [별표 2] 2.바·사 | 항상 차단. 자기 감정 표현("죽고 싶다")은 막지 않음 | 같음 |
| `PERSONAL_INFO` 연락처(휴대전화·이메일) | 유사 서비스(Roblox·Scratch)의 연락처 공유 금지, 이슈 제목 "금지 표현"과 11/1 결정의 해석(사용자 결정) | 항상 차단 | "전화번호나 이메일 같은 개인정보는 빼고 다시 적어 주세요." |

- 응답 `title`은 범주와 관계없이 "고쳐야 할 말이 있어요"(목업·실제 화면 비교 후 사용자 결정). 걸린 말·원문은 응답·로그에 넣지 않음(NFR-SEC-05). 로그는 `답변 표현 차단 attemptId=… category=…`
- [별표 2]의 나머지 항목(아·자·카·타·파·하)과 약물·폭력 묘사는 글의 내용을 봐야 해서 단어로 다루지 않음. 단어로 막으면 교과 답변("담배는 몸에 해롭다", "전쟁에서 많이 죽었다")이 막힘
- 여러 범주에 걸리면 enum 순서(`PROFANITY` → … → `PERSONAL_INFO`)로 하나

### 목록 (`backend/learning-service/src/main/resources/answer-filter/`)

| 파일 | 내용 |
|---|---|
| `korcen.json` | 2026판 패턴 877·오탐 예외, 2023판에만 있는 패턴 54(`patterns2023`)·예외(`falsePositives2023`), 비슷한 글자 393·여러 글자 15, 범주별 남길 글자·치환. 범주 `general`·`minor`·`parent` → `PROFANITY`, `sexual` → `SEXUAL`, `race`·`belittle` → `HATE` |
| `urimalsaem.json` | 61개, 항목마다 `targetCode`(우리말샘 원 항목) |
| `team.json` | 팀 조정과 근거 수치(Curse 욕설·정상 표시 문장 수, NSMC 문장 수): 뺀 패턴 18, 좁힌 korcen 예외 1(`씨발라` → `수박씨발라`), 팀 오탐 예외 74, 맥락 단어 `새끼`와 항상 막는 결합형 8, 데이터로 더한 우리말샘 7, 철자 변형 24, 위협 14(뺀 후보 4) |
| `korcen-LICENSE.txt`, `korcen-2023-LICENSE.txt` | MIT, Apache 2.0 원문 |

- 원칙(사용자 결정): 팀이 낱말을 지어내지 않음. 더하는 말은 출처(korcen·우리말샘)나 측정 데이터에 실제로 나온 것만, 빼는 말은 겹치는 정상 문장 예와 횟수를 남김. 생성·측정 스크립트와 원자료는 저장소 밖
- 뺀 korcen 패턴 예: `보지`(책을 보지)·`자지`(잠을 자지)·`세끼`(하루 세끼)·`시바`(시바견)·`자위`(자위권)·`운지`(행운지수)·`야스`(야스쿠니)·`깔보`·`뒤져`(가방을 뒤져, 위협 쓰임은 `THREAT`의 `뒤져라`·`뒤질래`로)·`ㅅㅅ`·`qt`·`tq` 등
- 팀 오탐 예외 예: `새끼손가락`·`새끼줄`·`새끼를낳`·동물+`새끼`(22종), `강조까지`·`글자지`·`전개같`·`마이애미`, `닥쳐올`·`닥쳐왔`(닥치다=다가오다), `등신대`·`팔등신`·`0~9등신`, `눈깔사탕`
- 맥락 단어 `새끼`: 동물 새끼 뜻이 있어 미션 본문에 나오면 허용. korcen은 맨 `새끼` 하나로 결합형을 잡아, 허용만 두면 미션에 `새끼`가 있을 때 `개새끼`까지 통과 → Curse에서 5회 이상 나온 결합형 8개(`개새끼`·`이새끼`·`저새끼`·`그새끼`·`새끼야`·`새끼들아`·`씹새끼`·`이런새끼`)는 항상 차단. 맨 `새끼`는 Curse 욕설 문장 322 / 정상 표시 8, 데모 미션에는 없음
- 데이터로 더한 우리말샘 7개(실제 화면에서 `등신`이 통과해 기준을 세움): "낮잡아·속되게 이르는 말" 중 지금 목록으로 안 막히고 Curse 욕설 3회 이상·정상 표시 0 → `등신`·`아가리`·`개쓰레기`·`눈깔`(`PROFANITY`), `갈보`·`돌림빵`(`SEXUAL`), `저능아`(`HATE`). 같은 기준에 걸린 `깡통`·`나발`·`똥꼬`는 정상 낱말이라 뺌
- 넣지 않은 말(사용자 결정): `바보`·`멍청이`·`호구`(비속어가 아닌 놀림말, `바보` NSMC 97회), 지역·장애를 낮잡는 우리말샘 22개(`봉사`·`장님`·`외다리`·`판수`·`벙어리`는 봉사활동·장님 코끼리 만지기·외다리 서기 같은 교과 문장과 겹치고 Curse 욕설에 거의 없음, 많이 나온 `정신병자`·`찐따`는 korcen에 있음), `홍어`(공신력 있는 출처에 없고 생선 이름)

### 검사 흐름 (`ExpressionPolicy`)

1. 대상은 학생이 쓴 칸(`AnswerContent.writtenTexts`: 서술 글, 풀이 최종 답·단계, 논술 4칸)이고 칸마다 따로 검사(칸 사이를 잇지 않음). 원문과 "우회 보기"(전각 → 보통 글자, 한글 바로 옆 영문 한 글자 → 글자 이름, 풀어 쓴 자모 → 글자) 두 글을 검사
2. 정규화(korcen 전처리): 주소 지우기 → 소문자 → 비슷한 글자(코드포인트 기준, 보조평면 57자 포함) → 여러 글자 → 띄어쓰기 지우기
3. korcen 범주마다 범주 안 치환 → 오탐 예외 지우기(korcen 원본 그대로 + 글과 같이 정규화한 팀 예외) → 남길 글자만 둔 보기와 한글·자모만 둔 보기에서 부분 일치. 한글·자모 보기는 `시1발`을 잡으려고 #205에서 더함
4. 낱말 목록(우리말샘 61·더한 7·변형·결합형·위협): 팀 예외를 지운 뒤 자모 포함 보기·한글만 보기에서 부분 일치
5. `HATE`와 맥락 단어는 같은 말이 미션 본문(제목·질문·안내·선택지·그룹)에 나오면 제외. 연락처는 이메일 형식, 휴대전화(구분 기호 `-`·`.`·괄호·띄어쓰기를 지우고 한글 숫자 `공일공…`을 숫자로)
6. 위치: `AnswerService.submit`의 누락 검사 다음·되묻기 연결 검사 전(api-spec 4.1 순서). 단어 대조라 외부 호출 없음. 막힌 요청은 core가 422를 같은 키 응답으로 저장(원문 없음), 웹은 답이 바뀌면 새 키

### 우회 표기 범위 (이슈 해야 할 일 3)

| 막는 우회 | 예 | 근거 |
|---|---|---|
| 띄어쓰기·기호·숫자 끼우기 | `씨 발`, `씨.발`, `씨*발`, `시1발`, `씨8발` | korcen 전처리 + 한글 보기 |
| 영문 표기·비슷한 글자·센소리·자음 줄임 | `sibal`, `tlqkf`, `씨빨`, `씌발`, `시ㅂ발`, `ㅅㅂ` | korcen 패턴·비슷한 글자 표 |
| 데이터에서 나온 철자 변형 | `븅신`, `씨밸`, `졵나`, `조온나`, `새낀` | 핵심 욕과 자모 1~2개 다르고 Curse 욕설 문장에 나오며 정상 글·함정에 없는 것 |
| 풀어 쓴 자모 | `ㅆㅣㅂㅏㄹ`, `ㅂㅕㅇㅅㅣㄴ`, `ㅆㅣ발` | 두벌식 규칙(겹모음·겹받침)으로 합침. `ㅋㅋ`·`ㅠㅠ`·`ㅇㅇ`은 안 합쳐짐. Curse 정상 +0, NSMC +3(모두 실제 욕) |
| 전각 글자 | `ｓｉｂａｌ`, `０１０-１２３４-５６７８` | 전각 영문·숫자·기호 범위만(NFKC는 호환 자모를 바꿔 `ㅅㅂ` 패턴이 깨져 쓰지 않음). 오탐 +0 |
| 한글 옆 영문 글자 소리 | `c발`, `C발`, `M창`, `돌I` | 앞뒤가 영문이 아닌 한 글자만 글자 이름으로. `PC방`·`TV에서`·`B형`·`비타민C를`·`K팝`은 그대로. Curse 정상 +0, 데모 0, NSMC +35(모두 실제 욕) |
| 연락처 표기 | `010.1234.5678`, `(010)1234-5678`, `공일공 일이삼사 오육칠팔` | 구분 기호 지우기·한글 숫자 |

| 막지 않는 우회 | 이유 |
|---|---|
| 영문 낱말을 자판 위치대로 친 글(`qudtls` = 병신) | 측정: Curse 욕 +3에 Curse 정상 +33·NSMC +203·데모 문장 47 오탐(`Hello` → `ㅗ디ㅣㅐ`, `ㅗ`가 korcen 손가락 욕 패턴), 주소도 바뀜 |
| 이메일을 말로 쓰기(`abc 골뱅이 naver.com`), 집 전화번호 | `@` 형식·휴대전화만 봄 |
| 정상 낱말과 겹치는 욕 | `졸라`(엄마를 졸라서), `병신년`(丙申年), `새 끼니`·`쌍년도`·`애미야`처럼 띄어쓰기를 지우면 생기는 말 |

### 측정 (최종 목록, 기준 구현과 Kotlin 판정 같음)

| 데이터 | 결과 |
|---|---|
| Curse-detection-data 욕설 표시 2,044문장 | 1,223 막음(59.8%). 라벨에 욕 없는 모욕·비꼼·정치 비하가 섞여 낮게 나옴. 명시적 욕만 본 새 표본에서는 약 94~95%(목록 9차 시점 표본 검토) |
| Curse 정상 표시 3,781문장 | 49(1.3%) |
| NSMC test 리뷰 50,000문장 | 1,030(2.06%). 대부분 리뷰 속 실제 욕이고, 표본 검토로 정상 글 오탐은 약 0.1%(목록 9차 시점) |
| 우리 데모 문장 491(learning 데모 시드·웹 데모 데이터) | 0 |
| 학생 글 함정 약 80문장(교과·이야기·계산 답·영어·자음 줄임) | 0. 미션 없이 쓴 "고양이가 새끼를 다섯 마리 낳았다"만 막히고, 미션 본문에 `새끼`가 있으면 허용 |
| Kotlin(`ExpressionPolicy`)과 Python 기준 구현 | Curse+NSMC 55,825문장 판정이 모두 같음 |

- 경과: korcen 2026판 네 범주만 47.8%(`씨발`·`존나`·패드립을 놓침) → 2023판 합침·`parent`·`minor`·한글 보기·오탐 정리·변형 59.1% → 우리말샘 7개 59.8%. 정상 표시 오탐은 49~50으로 거의 그대로
- 측정 데이터는 성인 인터넷 글이라 초중등 답변과 다름. 그래서 우리 데모 문장과 학생 글 함정을 따로 검사하고 테스트(`ExpressionPolicyTest`)로 고정함

### 실제 앱 확인 (11/02, 로컬 docker compose + web dev)

- 학부모 Google 로그인 → 자녀(5학년) → 서술 미션에서 욕·연락처·`c발`·`ㅆㅣㅂㅏㄹ` 제출: 화면에 "고쳐야 할 말이 있어요"와 범주별 문구, 입력 유지, 다시 시도 버튼 없음(422). 정상 답은 저장·피드백 진행
- 처음에 `등신`이 저장되어 위 "데이터로 더한 우리말샘 7개" 기준을 세움. 새 목록 배포(01:25:45 UTC) 뒤 `answer` 테이블에 막힌 답 없음, 로그는 `attemptId`·`category=PROFANITY`만
- 화면에서 막혀도 "초안 저장 완료"가 보임: 초안 자동 저장(FN-LRN-15)은 검사하지 않아 `attempt_draft`에 남음(아래 사용자 결정)

### 결정 (11/01~11/02)

- 기준은 공신력 있는 가이드([별표 2]·방송심의 규정·KISO), 목록은 korcen(2026+2023)·우리말샘, 변형·위협·추가 낱말은 데이터에 나온 것만
- 외부 AI 없음(제출 경로 의존·지연·비용·검증 가능성). 제출 전 검수 LLM도 넣지 않음: 막을 글도 LLM으로 보내게 되어 완료 조건 "저장·판정 요청 없이 차단"과 어긋나고, 연락처가 LLM으로 넘어가며, 제출 경로에 ai 호출·장애 처리·비용 2배가 생김 → 후속 이슈로 설계 다시
- 범주 5개(연락처 포함), 범주별 안내, 제목 "고쳐야 할 말이 있어요"
- 서버만 검사: 단어 목록을 웹 번들에 넣지 않음. 웹 데모 모드는 시나리오 `submit-inappropriate`(첫 제출 1회 차단, 연락처처럼 보이면 연락처 안내)
- 초안(`answer`·`memo`)과 돌아보기 글은 검사하지 않음. 초안 `answer` 검사안을 api-spec·OpenAPI에 넣었다가 되돌림(초안은 학생 본인만 보는 `attempt_draft` 한 행이고 제출에 성공하면 비워짐, 판정·학부모·리포트로 가지 않음)
- 우회: 자모 합치기·전각·한글 옆 영문 글자 소리는 넣고 영문 자판 위치는 넣지 않음(위 측정)

- 설계와 다른 점: 없음. 설계에 새로 더함: class-diagram 4.1(`ExpressionPolicy`, `AnswerContent.writtenTexts`, `AnswerService --> ExpressionPolicy`, 답변 표현 검사 설명), sequence-diagram 3.1(검사 줄·설명), functional-spec FN-LRN-05(예외·상태), api-spec 1.3·4.1, learning OpenAPI. 목록 읽기를 `answer/repository`의 설정으로 두고 domain은 Kotlin 정규식만 쓰는 것은 architecture 2.1(domain 의존 금지·데이터 적재는 infrastructure)과 `FinishPolicy` <<value>> 선례를 따름
- 한계: 욕 없는 모욕·비꼼·돌려 말한 성적 표현·특정 친구 놀림은 단어로 못 막음(후속 검수 LLM). 맥락 허용은 미션 본문에 같은 말이 있는지만 봄. 낱자 `ㅗ`는 korcen 손가락 욕 패턴이라 낱자를 섞어 쓴 글(`ㄱㅗㅏ자`)이 걸림(원래 동작). korcen 원본 오탐 예외 중 숫자가 든 것(`8등신`)은 korcen 정규화 때문에 원본에서도 동작하지 않음(팀 예외는 정규화해서 비교). 측정 데이터의 분포가 초중등 답변과 다름
- 확인 필요: ① `ANSWER_INAPPROPRIATE`(범주별 `detail`) 팀 공지(api-spec 공유 계약, PR 전 사용자) ② 초안 자동 저장·돌아보기 글에는 걸리는 말이 남을 수 있음(학생 본인만 열람) ③ 학생 자기 감정 표현("죽고 싶다")의 보호자 알림 여부(아동 안전, 별도 기능) ④ korcen의 MIT·Apache는 코드 라이선스라 단어 데이터의 출처까지 보증하지 않음 ⑤ core 동의 문서 시드 부재(로컬 실행 시 발견, core 담당) ⑥ KISO KSS 신청 여부
- 후속: 검수 LLM(제출 전 별도 검사, ai-service 검수 API·장애 시 처리·오탐·우회·비용 설계), 판정 LLM 응답에 "부적절 표현 의심" 표시(저장 후 보호자·관리자 확인), KISO KSS

## 17. 고착 RUNNING 판정 1분 주기 탐지 (#241)

P12 "판정 리스 90초·고착 탐지 1분"의 탐지 작업. 지금까지는 같은 답변에 피드백을 다시 요청할 때만 만료 리스를 재획득해서, 처리 Pod 종료·결과 기록 실패(`FeedbackFacade` 실패 기록) 뒤 학생이 떠난 판정은 `RUNNING`으로 계속 남았다.

### 결정 (11/02)

| 항목 | 결정 | 근거 |
|---|---|---|
| 탐지 후 동작 | `FAILED`로 전이, 실패 코드 `LEASE_EXPIRED`, `retry_count + 1`, 자동 재실행 없음 | 설계 문서에 동작이 없어 이슈 지침(`Judgment.fail`의 실패 기록 규칙)과 core 분석 대화의 고착 처리(130초 넘은 `RUNNING`을 `STREAM_INTERRUPTED` 실패로, 자동 재실행 없음, api-spec #47 절)를 따름. 로그만 남기는 안은 상태 표시·집계·결제 사용 증빙이 그대로라 탐지 의미가 없어 택하지 않음 |
| 클래스 위치 | `judgment/scheduler/StuckJudgmentScheduler` → `JudgmentService.failStuck` → `JudgmentRepository.failExpired` | 아키텍처 2.1: 스케줄 수신은 Presentation `scheduler`, DB 접근 금지. core 스케줄러(`report/scheduler` 등)와 같은 구조 |

### 구현

| 위치 | 내용 |
|---|---|
| `judgment/scheduler/StuckJudgmentScheduler` | `@Scheduled` 주기 `app.judgment.stuck-detection-interval`(기본 `PT1M`, 첫 실행도 1분 뒤), `app.judgment.stuck-detection-enabled=false`면 실행하지 않음. ShedLock 없음(조건부 UPDATE라 레플리카 동시 실행 안전, `ProcessedEventCleanupScheduler`와 같은 방식) |
| `JudgmentService.failStuck(now)` | 트랜잭션 하나에서 일괄 전이, 바뀐 답변 ID 반환. 1건 이상이면 `warn` 로그에 건수와 `answerId`만(학생 원문 없음) |
| `JudgmentMapper.failExpired` | `UPDATE judgment SET process_status='FAILED', failure_code=:code, retry_count=retry_count+1 WHERE process_status='RUNNING' AND (lease_until IS NULL OR lease_until < :now) RETURNING answer_id`. 만료 조건은 `acquire` SQL·`Judgment.isLeaseExpired`와 같음(리스 없는 `RUNNING`도 만료). 탐지용 인덱스 `(process_status, lease_until)`는 기존(V2) |
| `Judgment.LEASE_EXPIRED` | 실패 코드 상수 |
| `AppProperties.Judgment`, `application.yml` | `stuck-detection-enabled: true`, `stuck-detection-interval: PT1M` |
| 설계 | state-diagram 3.3(전이·표·설명·`failure_code` 목록), class-diagram 4.2(`StuckJudgmentScheduler`, `failStuck`, `failExpired`, 설명), architecture 2.6 learning 트리(`judgment/scheduler/`) |

### 겹칠 때

| 상황 | 결과 |
|---|---|
| 재획득이 먼저 행을 잡음 | 탐지 UPDATE가 행 잠금을 기다린 뒤 조건을 다시 봐 새 리스가 잡힌 행은 건너뜀(READ COMMITTED) |
| 탐지가 먼저 행을 잡음 | 재획득 UPDATE가 기다린 뒤 `FAILED`를 보고 `FAILED → RUNNING`으로 가져감 |
| 두 Pod가 같은 주기에 탐지 | 한쪽만 바뀌고 `retry_count`는 1만 오름 |
| 탐지 뒤 이전 처리가 늦게 끝남 | 저장·실패 기록 모두 획득한 리스 조건(`process_status='RUNNING' AND lease_until=:until`)이라 0행, 결과 버림(재획득 때와 같음) |

### 영향

- 결제 사용 증빙(`GET /internal/payment-usage/students/{id}`, #48): `RUNNING` 판정을 사용으로 보므로 고착 판정이 있으면 계속 `used=true`였음. 탐지 뒤에는 ai 실패로 `FAILED`가 된 판정처럼 사용으로 보지 않음. core 결제 쪽 코드 변경은 없고 값만 달라짐 → core 담당에게 알림(PR)
- 학습 기록 집계: 조회 종료일까지 답변이 모두 `FAILED`인 시도를 빼는 기존 규칙(P08)에 고착 시도도 들어감
- 학생 화면: 화면에 있는 동안은 web이 `RUNNING`이면 피드백을 다시 요청해(`feedbackPolling.ts`) 지금도 리스 만료 뒤 재획득됨. 차이는 떠났다 돌아온 학생의 시도 상세가 "처리 중" 대신 실패로 보이고 다시 요청할 수 있다는 점

### 설계·이슈와 다른 점

- 이슈 작업 위치는 `judgment/service/`(새 스케줄 클래스)였으나 아키텍처 2.1대로 `judgment/scheduler/`에 둠(사용자 결정). 이슈가 따르라고 한 `ProcessedEventCleanup` "방식"(설정 가능한 주기·조건부 UPDATE·잠금 없음)은 그대로 따름
- 이슈 배경의 "남은 `RUNNING`은 마무리 조건(P04)·다음 행동 계산에서 처리 중으로 보임": 마무리 조건은 `DONE` 1회 이상이라 `RUNNING`·`FAILED` 모두 충족하지 않고, `nextActions`도 둘 다 `[]`라 이 부분은 탐지 전후가 같음. 달라지는 것은 위 "영향"
- 일괄 UPDATE라 엔티티 `Judgment.fail`을 거치지 않음. 이슈 작업 위치의 "조건부 일괄 전이"를 따르고, 전이 결과(`FAILED`·실패 코드·`retry_count + 1`)와 만료 조건은 엔티티·`acquire` SQL과 같게 맞춤(`acquire`도 엔티티 판단과 같은 조건을 SQL에 둠)

### 검증

`JudgmentServiceTest`: 만료·리스 없음만 전이, 미만료·`PENDING` 유지, 두 번 실행해도 한 번만, 탐지 뒤 재요청이 `FAILED → RUNNING` 후 정상 저장. SQL에서 리스 조건을 빼면 실패함을 확인.

### 한계

- 리스 90초를 넘겨 아직 살아 있는 처리가 있으면 탐지가 먼저 `FAILED`로 바꿔 그 결과가 버려짐. 탐지 전에는 다른 요청이 가져가지 않았다면 저장됐음. learning→ai 판정·되묻기가 각 35초라 정상 처리는 약 70초 안에 끝나고, 탐지는 리스 획득 90~150초 뒤라 드묾
- 만료 판단은 각 Pod의 시각 기준(재획득과 같음). Pod 사이 시각 차이만큼 탐지가 앞당겨지거나 늦어짐
- learning의 기존 `record/service/ProcessedEventCleanup`은 스케줄 클래스가 service 패키지에서 repository를 바로 부름(아키텍처 2.1과 다름). 이번 범위 밖이라 그대로 둠. #278에서 `record/scheduler/ProcessedEventCleanupScheduler` → `record/service/ProcessedEventCleanupService`로 분리
- 탐지 건수는 로그로만 남음(지표 수집 없음). DB에서는 `failure_code='LEASE_EXPIRED'`로 셀 수 있음

## 18. 같은 미션 재시도 비교 (#207)

- 사용자 확정: 같은 학생·미션의 **직전 마무리 시도**와 비교합니다. 현재 시작 시점 이전에 마무리한 시도를 `finished_at DESC, started_at DESC, id DESC`로 한 건 선택합니다. 다른 학생/미션·현재 시도·현재 시작 뒤에 마무리한 시도는 제외합니다. 돌아보기 완료만을 기준으로 잘못 좁히지 않습니다.
- 기존 진행 중 시도 재사용·돌아보기 완료 규칙은 유지합니다. 완료한 결과에서 ‘이 미션 다시 풀기’는 기존 시작 API로 새 시도를 생성합니다. 예전 답변·판정·피드백·초안은 수정하거나 삭제하지 않습니다.
- `GET /internal/attempts/{attemptId}/comparison`과 core `GET /api/v1/attempts/{attemptId}/comparison`을 추가했습니다. 학생 본인만, 마무리 이후에 조회합니다. core는 상세 캐시와 마찬가지로 no-store입니다.
- 응답 `NO_PREVIOUS | COMPARABLE | CRITERIA_CHANGED`, 이전/현재의 전체 제출 답변·마무리 시각·마지막 판정·기준표와 각 시도에 고정된 문항을 담습니다. 문항/기준표 버전이 같을 때만 항목별 추가 확인·유지·이번 미확인·양쪽 미확인을 표시합니다. 기준 변경이면 원문만 나란히 읽고 충족 개수를 직접 비교하지 않습니다. 이를 능력 점수나 향상률로 바꾸지 않습니다.

## 19. 실행 모델: 가상 스레드 비활성 (#201)

#201 실제 스케줄 검증에서 learning이 cold start 후 기록 요청·health에 응답하지 않아 리포트 생성이 실패했다. learning 설정만 수정.

- JDK 21, `ActiveProcessorCount=2`, 가상 스레드 활성 상태의 기존 JAR에서 기록 API 16개 동시 첫 요청이 모두 12초 시간 초과했고, 이후 readiness도 응답하지 않았다.
- CPU·DB 잠금 부족은 관측되지 않았다. 스레드 덤프의 carrier 2개는 Jackson `SerializerCache.addAndResolveNonTypedSerializer` 및 Kotlin reflection 저장소 잠금에서 진행하지 못했다. 후자는 `VirtualThread.parkOnCarrierThread`를 포함한다. DB에는 미완료 읽기 트랜잭션이 남았다.
- 이는 애플리케이션 SQL 교착으로 확인된 것이 아니라, JDK 21의 monitor pinning과 라이브러리 초기화 잠금이 carrier를 소진하는 형태다. [Oracle 설명](https://inside.java/2024/02/21/quality-heads-up/)도 synchronized 진입·대기 시 carrier가 반환되지 않아 starvation/deadlock이 생길 수 있음을 명시한다.

learning의 `spring.threads.virtual.enabled`를 false로 바꿔 기존 Tomcat의 제한된 플랫폼 스레드 풀을 사용한다. 캐리어 수 증가·순차 예열·가짜 정상 응답을 사용하지 않는다. core virtual threads, JDK 21 버전, 라이브러리 의존성, API/DTO/DB 및 서비스 경계는 변경하지 않는다. 이는 처리량 개선 주장이 아니라 콜드 초기화 시 서비스 전체 진행 정지를 피하는 변경이다.

검증: 수정 전 JAR(2 CPU)은 첫 기록 API 16개 동시 요청이 모두 12초 시간 초과·readiness 무응답, 수정 JAR은 새 JVM 3회 모두 16/16 성공·readiness 200. `RecordColdStartHttpTest`가 내장 Tomcat에 4종 기록 API 16개 동시 요청과 platform 스레드 처리를 고정. 이후 예열 없는 원본 월요일 cron(테스트 시계)으로 주간 리포트 COMPLETED·LLM 서술 검증 통과까지 확인.

## 20. 생각 요소 표준 코드 문서·계약 (#262)

기준표 요소 code가 미션마다 자유 값(`e1` 등)이라 미션이 달라지면 같은 요소인지 알 수 없었다. 요구사항 FBF-38(요소 3회 연속 누락 시 그 유형 추천)·FAC-09(요소 지표)·기획서 5.3(4)(같은 유형 미션끼리 요소 비교)를 채우려고 표준 코드를 정했다. 이 이슈는 문서·계약만 고치고, 구현은 PM이 아래 "구현 인계"를 보고 learning·web 이슈로 발행한다.

### 결정 (11/03)

| 항목 | 결정 | 근거 |
|---|---|---|
| 이슈 범위 | 문서·계약만, 구현은 PM 발행 | 기획 변경 의견이 오면 코드 없이 문서만 고침. 사람 평가(#199)는 표준 코드·공통 설명만 있으면 시작 가능. 이슈 지침 "API 계약 변경은 api-spec 먼저" |
| FAC-09 "같은 기준표" | 유형별 평가 요소로 해석, 기획서 5.3(4) "같은 유형·학년군 미션끼리"와 같은 뜻 | FAC-09가 "유형/학년군"을 함께 적음(같은 미션끼리면 둘은 하나뿐). 비교 대상(처음 답 충족·되묻기 후 새 요소·연결어 변화)이 기획서 5.3(3)·(4) 지표와 같음 |
| 요소 3종류 | 유형 공통(표준 코드)·성취기준 고유(`e`+숫자)·정답(`ANSWER_KEY`·`FINAL_ANSWER`) | 기획서 5.3(2) "요소를 성취기준에 맞춰 구체화", 새 컬럼 없이 `FINAL_ANSWER` 선례 |
| 공통 설명 | 표준 코드마다 한 줄 정의, 미션 요소 설명은 그 구체화 | 같은 코드가 미션마다 같은 뜻으로 판정되고 사람 평가의 "같은 요소표"(기획서 5.3(5))가 됨. 판정 프롬프트는 그대로(LLM은 요소 이름·설명으로 판정하고 code는 받지 않음, `FeedbackFacade` `AiRubricElement`) |
| 분석하기 | 기획서 2요소 그대로(`ANALYZE_RELATION`·`ANALYZE_REASON`) | 블룸 개정 분류 원문(Anderson & Krathwohl 2001, Potsdam 사본): 분류·비교는 "이해"(Understanding: classifying, comparing), "분석"은 나눈 부분 사이의 관계까지(determining how the parts relate). 11/2 "기획서가 블룸 분석·성취기준(분류·비교)보다 좁다"는 판단을 바로잡음. 비교·분류는 기획서의 기초 사고력 쪽(후속) |
| 돌아보기 | 바뀐 생각·바뀐 까닭·자기 생각 과정·경험과 연결 **[기획서 변경]** | 시드 M05·M10·M15 모두 바뀐 생각(e1)·바뀐 까닭(e2)·자기 경험 연결(e3, 들어가면 좋은 생각). 기획서 ① "자기 생각 과정"은 미션 질문이 묻지 않아(시드 질문은 등장인물의 변화를 물음, functional-spec 1.5 "요소는 미션 질문에서 요구") 세 번째 요소에 넣음 |
| M20 | "나의 사용" `REFLECT_CONNECT`, "돌아본 점"·"앞으로의 계획" 고유 | M20은 바뀐 생각이 아니라 지금 습관을 돌아보는 미션. 계획·다짐은 실제 적용이 아님(VALUE Transfer 제외와 같은 이유) |
| 충족률·보완률 분모 | 필수 요소만, 들어가면 좋은 생각은 따로 셈 **[기획서 변경]** | 판정 규칙이 들어가면 좋은 생각을 필수에서 뺌(ai `judgment/service.py` `_result`). 분모에 넣으면 정답인데 충족률이 100%가 아님 |
| 정답 예약 코드 | `ANSWER_KEY` 하나로 고르기·순서·분류 | 세 입력 방식은 규칙 판정이라 요소를 모두 정답 키로 기록(`FeedbackFacade.withAnswerKey`, `AI_INPUT_TYPES` 밖). 이름은 판정 출처 `source_type = ANSWER_KEY`와 같게 |
| 따져 보기 논술 | `EVALUATE_CLAIM`·`EVALUATE_EVIDENCE`·`EVALUATE_PERSPECTIVE` 필수 | 기획서 5.3(3) 논증 요소 충족률(주장·근거·반론). 유형이 다른 논술과 "같은 유형 코드만" 규칙이 부딪히지 않게 따져 보기로 한정 |
| 기록 응답 필드 | 공통 `Element`에 `code`·`goodThought` | 기록 API는 판정 요소(`elementId`·`label`·`satisfied`·`quote`·`sourceType`)와 `trial`을 이미 줌. report 지표에 빠진 것은 이 둘뿐. 학생 화면과 같이 쓰는 구조라 하나로 유지(#251 `AnswerItem<F>`) |
| 검사 위치 | 저장 때 code 모양 400, 게시 때 유형·입력 방식 맞춤 422 `rubric.elements.code` | 저장 때는 미션 유형을 모름(미션 내용 `PATCH`와 기준표 `PUT`이 따로). 기존 게시 검사(`Mission.requirePublishable`, `FINAL_ANSWER` 검사)와 같은 자리 |
| 시범 판정 포함 여부 | report 후속에서 정함 | 이 이슈는 `trial`을 내보내기만 함 |
| 검증 지표(카파·QWK) | #199에서 정함 | 이 이슈와 무관. 있음/없음처럼 값이 두 개인 판정은 두 값이 같음 |
| 기록 방식 | 기획 변경 2건을 "확정"으로 쓰고 팀 채팅에 공유, 의견이 오면 수정 | 사용자 결정 |

### 표준 코드와 근거

VALUE 루브릭 문구는 이슈 근거 자료의 원문 PDF 4종에서 확인했다(11/03).

| 유형 | 코드 | 요소 | 근거 |
|---|---|---|---|
| 분석하기 | `ANALYZE_RELATION` | 원인·특징·관계 | 기획서 5.3(1) ①, 블룸 "분석", `[6과07-02]` 원인을 추리 |
| | `ANALYZE_REASON` | 까닭 잇기 | 기획서 5.3(1) ② |
| 따져 보기 | `EVALUATE_CLAIM` | 주장 | VALUE Critical Thinking "Student's position" |
| | `EVALUATE_EVIDENCE` | 근거 | 같은 루브릭 "Evidence" |
| | `EVALUATE_PERSPECTIVE` | 다른 관점·반론 | 같은 루브릭 "Others' points of view are acknowledged" |
| 새로 만들기 | `CREATE_NEW` | 새로운 생각 | VALUE Creative Thinking "Innovative Thinking" |
| | `CREATE_WHY` | 왜 나은지 | 같은 루브릭 "Solving Problems … can articulate reason for choosing solution" |
| | `CREATE_CONNECT` | 연결·변형 | 같은 루브릭 "Connecting, Synthesizing, Transforming" |
| 문제 해결하기 | `SOLVE_DEFINE` | 문제 정하기 | VALUE Problem Solving "Define Problem" |
| | `SOLVE_PLAN` | 방법 세우기 | "Identify Strategies"·"Propose Solutions/Hypotheses" |
| | `SOLVE_CHECK` | 결과 확인 | "Evaluate Outcomes" |
| 돌아보기 | `REFLECT_CHANGE` | 바뀐 생각 | 기획서 5.3(1) ②, VALUE Lifelong Learning "Reflection" |
| | `REFLECT_REASON` | 바뀐 까닭 | 시드 M05·M10·M15 "바뀐/고친 까닭" |
| | `REFLECT_CONNECT` | 생각 과정·경험과 연결 | 기획서 5.3(1) ①, "Reflection: Reviews prior learning (past experiences inside and outside of the classroom)", `[6국05-06]` |

- 나이: 블룸은 학년이 아니라 생각 방식의 분류이고 VALUE는 대학생용이라, 학년 수준은 기획서 5.3대로 미션마다 연결한 성취기준이 맞춘다(functional-spec 1.5 한계)
- 뺀 VALUE 항목: Curiosity·Initiative·Independence·Taking Risks·Acquiring Competencies(긴 기간의 행동이라 답 구절로 판정 어려움), Implement Solution(풀이 틀 계산·최종 답 규칙으로 대신), Transfer(돌아보기의 다짐은 실제 적용이 아님)

### 시드 20문항 code 대조

요소 56개: 표준 44개(79%), 정답 7개, 고유 5개. 같은 행의 code만 바꾸므로 지난 판정은 `judgment_element.rubric_element_id`로 이어지고, 필수·들어가면 좋은 생각 여부(`good_thought`)는 그대로다.

| 미션 | 유형·입력 | e1 | e2 | e3 | e4 |
|---|---|---|---|---|---|
| M01·M06·M16 | 분석·고르기 | `ANSWER_KEY` | | | |
| M02 | 따져·서술 | `EVALUATE_CLAIM` | `EVALUATE_EVIDENCE` | `EVALUATE_PERSPECTIVE` | |
| M03·M08·M13·M18 | 새로·서술 | `CREATE_NEW` | `CREATE_WHY` | `CREATE_CONNECT` | |
| M04 | 문제·순서 | `ANSWER_KEY` | | | |
| M05·M10·M15 | 돌아·서술 | `REFLECT_CHANGE` | `REFLECT_REASON` | `REFLECT_CONNECT` | |
| M07 | 따져·서술 | 고유 `e1`(사실과 의견) | `EVALUATE_CLAIM`(내 의견) | `EVALUATE_PERSPECTIVE`(의견 비교) | |
| M09·M14·M19 | 문제·풀이 | `SOLVE_DEFINE` | `SOLVE_PLAN` | `SOLVE_CHECK` | `FINAL_ANSWER`(그대로) |
| M11 | 분석·서술 | 고유 `e1`(관찰 사실) | `ANALYZE_RELATION`(원인) | `ANALYZE_REASON`(까닭 잇기) | |
| M12 | 따져·논술 | `EVALUATE_CLAIM` | `EVALUATE_PERSPECTIVE`(근거 평가) | `EVALUATE_EVIDENCE` | |
| M17 | 따져·논술 | `EVALUATE_CLAIM` | `EVALUATE_EVIDENCE` | `EVALUATE_PERSPECTIVE` | 고유 `e4`(근거 출처) |
| M20 | 돌아·서술 | `REFLECT_CONNECT`(나의 사용) | 고유 `e2`(돌아본 점) | 고유 `e3`(앞으로의 계획) | |

- M12 "근거 평가"는 논술 틀 "반대 의견에 답하기" 칸에서 지우의 까닭을 따지는 요소라(시드 안내 문구) 반론으로 본다
- 모든 시드가 게시 검사(유형 맞춤, 고르기·순서는 `ANSWER_KEY` 하나, 따져 보기 논술 세 코드)를 통과한다

### 영향 확인

learning `Element`에 `code`·`goodThought`를 더했을 때 응답을 받는 곳을 모두 확인했다.

| 받는 곳 | 결과 | 근거 |
|---|---|---|
| core 학생 시도 상세 | 영향 없음. 계약이 "learning 응답 보존" | core `LearningController` `exchange` |
| core 학부모 대시보드 | 코드 변경 없음, 계약 `DashboardElement`에 두 필드 추가 | `LearningRecordClient`가 기록 JSON을 그대로 넘김(`memo`·`draft`만 제거) |
| core 관리자 게시 실패 | 영향 없음. `rubric.elements.code`가 모양 검사 통과 | `AdminLearningService` `missingFields` 정규식 |
| report | 영향 없음. 모르는 필드 무시, `feedback.status`만 읽음 | `report-service/app/clients/learning_client.py` `extra="ignore"` |
| 분석 대화(ai 에이전트) | 영향 없음. 모르는 필드 무시 | `analysis_agent/models.py` `extra="ignore"` |
| web | 영향 없음. 쓰는 필드만 검사 | `data/classroom/apiGateway.ts` |
| 이전 시도 비교(#207) | 영향 없음. 요소를 자유 형식으로 받음 | core `ComparisonSnapshot.elements` |
| CI | core 계약 지문 테스트에 `DashboardElement` 변경 허용 추가. learning 응답을 계약으로 검사하는 CI는 없어 구현 전 일시 불일치로 깨지지 않음 | `scripts/tests/test_admin_operations_contract.py`, `.github/workflows/ci-contracts.yml` |
| ai 되묻기 "한 걸음 더 방향" | 변경 없음. 필수 요소를 다 쓴 뒤 쓰는 방향이고 분석하기("원인·특징·관계를 하나 더")·돌아보기("자기 생각이 어떻게 흘러갔는지")가 새 요소와 어긋나지 않음 | ai `followup/prompts.py` `THINKING_DIRECTION` |

### 구현 인계

구현 완료: learning 시드·저장·게시 검사(#344·#353), web 요소 code 선택·사전 검사는 #356(진행 중).

### 설계·이슈와 다른 점

- 이슈 해야 할 일·작업 위치의 구현(관리자 검사·시드·기록 API·web)은 이 이슈에서 빼고 PM 발행으로 넘김(사용자 결정)
- 작업 위치 밖 수정: `contracts/openapi/core-service.yaml` `DashboardElement`, `scripts/tests/test_admin_operations_contract.py`. core가 learning 기록을 그대로 넘겨 계약을 맞춰야 하고, core 계약을 바꾸면 지문 테스트가 실패해서(선례 #242·#289)
- 이슈 "위반 시 400" → 저장 400·게시 422로 나눔(위 결정)
- 이슈 "고르기 정답용 예약 코드" → 고르기·순서·분류 공통 `ANSWER_KEY`. 이슈의 정답 요소 "고르기 M04"는 순서 미션
- 이슈 "기록 API에 요소별 판정 결과가 없음" → 판정 요소와 `trial`은 이미 있고 `code`·`goodThought`만 없음. api-spec 4.1.1 `answers[].feedback` 설명이 실제 계약보다 짧았던 것을 함께 맞춤. 이슈의 "검증 여부"는 `trial`로 정함(`judgment_element.verified`는 미검증 충족을 DB CHECK가 이미 막아 새 정보가 없음)
- 이슈 설계 초안의 분석하기 3요소(`ANALYZE_PARTS` 포함)는 쓰지 않음(위 결정). 시드 대조도 M11 "관찰 사실"은 고유, M12 "근거 평가"는 `EVALUATE_PERSPECTIVE`로 바꿈
- FN-RPT-05 요소 지표, FN-DSH-12 추천·13 생각 조각은 report·프론트가 구현할 기능이라 "(#262, 담당 확인)"으로 표시
- DB CHECK를 두지 않음: 이전 기준표 버전은 불변이라 자유 code가 남고, 미션 유형이 `mission_version`에 있어 행 단위 CHECK로 맞춤을 볼 수 없음
- 기존 파일 수정: `functional-spec.md`(1.5 표·표준 요소 소절과 기획서와 다른 점, FN-ADM-10·11, FN-RPT-05, FN-DSH-12·13), `erd.md`(`rubric_element.code`, 게시 검사, #262 메모), `api-spec.md`(2.8 기준표 PUT, 3.2 예시, 4.1 관리자 미션 게시 실패, 4.1.1 `answers[]`), `class-diagram.md`(게시 검사), `learning-service.yaml`(`missingFields`, 요소 code, `Element`), `core-service.yaml`(`DashboardElement`), `test_admin_operations_contract.py`, `planning-decisions.md`(#213 2.4 "생각 유형 평가 요소" 확인 필요 행을 #262 결과로 갱신), `docs/README.md`

### 검증

- scripts/tests 100개 통과, `git diff --check` 통과
- 지문 테스트의 `DashboardElement` 허용 줄을 빼면 `schemas/DashboardElement`로 실패하는 것을 확인 후 되돌림
- DB 스키마 검사(`scripts/check_db_migrations.py`, 임시 PostgreSQL 17.11): 3개 DB 테이블·열·CHECK 값·인덱스가 ERD와 일치. 처음에는 `rubric_element.code` 주석의 `ANSWER_KEY|FINAL_ANSWER`를 검사기가 CHECK 허용 값으로 읽어(`verify_db_schema.py` `allowed_values`, `A|B` 모양) PR CI `ci-db-schema`가 실패해 `·`로 고침
- 코드 변경이 없어 gradle 테스트는 돌리지 않음

### 한계

- 이전 기준표 버전·#262 전에 만든 미션의 자유 code는 표준 코드가 아니라 미션을 넘는 지표에서 빠짐(고유 요소처럼 그 미션 충족률에만)
- 표준 요소는 사람 검증(P11) 전이라 AI 판정은 시범 표시
- 후속: 기초 사고력(`mission_version.basic_skills`, 비교·분류) 연결, 성취수준 문장 연결, 기획서 6.2 미션 제작 흐름(LLM 초안 → 자동 검사 → APM 검수)의 FN-ADM-09 반영, 답 속 다른 유형 생각 기록

## 21. 성취기준·성취수준 표와 미션 초안 흐름 문서·계약 (#336)

기획서 6.2(미션 제작 방법)·5.3(2)(성취수준 문장에 맞춘 요소)와 요구사항 FAD-03·FAD-08·FAC-18·FFJ-10·FBN-09가 설계 문서에 처음부터 없던 것을 반영했다. #262처럼 문서만 바꾸고 구현은 별도 이슈(learning #353·ai #354·core #355 완료, web #356 진행 중)로 learning·ai·core·web 이슈를 발행한다. 결과는 functional-spec 1.5 "성취기준·성취수준 연결"·FN-ADM-09·11·19·20·21, erd 4.1.1, api-spec 1.5·2.8·4.1·4.2·4.6, class-diagram 4.1.1·5.4, state-diagram 3.4, sequence-diagram 11. 모두 "(#336, 구현 전)"으로 표시했다.

### 결정 (11/04)

| 항목 | 결정 | 근거 |
|---|---|---|
| 이슈 범위 | 문서·계약만, 구현은 PM 발행. 12/7까지 설계 전체 구현(이슈 결정 1) | #262 결정과 같음 |
| 성취기준 표 범위 (확인 필요 1) | 2022 개정 현행 765개 전체(초1~중3) | FAD-08이 수집본 전체 관리를 요구, functional-spec 1.5 학년 확장. 데이터가 작음 |
| 이용 조건 (확인 필요 2) | 고시 원문(성취기준 문장)은 넣고, 평가원 성취수준 문장은 이용 조건 확인 전까지 넣지 않음 **[팀 확인 필요]** | 저장소가 공개(public)라 시드에 넣으면 공개됨. 수집데이터 보고서 "성취기준 문서: 이용 조건 확인 후 사용", 출처 국가교육과정정보센터 공개 문서. 평가원 자료의 이용 조건은 찾지 못함 |
| 2026.1 일부개정 25개 (확인 필요 3) | 넣지 않고 FAD-08("790개")과 다름을 기록 | 12개 코드(`2즐01-01` 등)가 현행과 코드는 같고 문장이 달라 코드를 키로 쓸 수 없음. 2028년 적용, 초1~2만이라 지원 학년(P03) 밖 |
| 생성 방식 (확인 필요 4) | 비동기: 요청은 `GENERATING`으로 저장하고 202, learning 주기 작업이 생성 1회씩 반복 | core→learning 일반 대기 30초(core `LearningHttpProperties`), ai LLM 1회 15초 + 재시도 1회(ai `config.py` `llm_timeout`·`llm_retry_backoff`, P12)라 동기 요청 안에서 재시도까지 끝낼 수 없음. 주기 작업은 learning `StuckJudgmentScheduler`, 점유는 `judgment.lease_until` 선례 |
| 성취수준 단계 (확인 필요 5) | 미션 작성·초안 요청 때 성취기준마다 관리자가 고르고, `achievementStandards`(문자열 배열)는 그대로 둔 채 단계 필드(`achievementLevels`)를 따로 둠 | FAD-03 "모든 자체 미션은 … 성취수준 … 에 연결". `achievementStandards`를 객체로 바꾸면 web(`domain/admin/operations.ts` 85·260행, `presentation/admin/MissionManager.tsx` 278행)·learning OpenAPI 두 곳·learning 테스트 4개가 깨짐. 학년별 목표 단계는 기획에 없는 새 정책이라 정하지 않음 |
| 시드 20문항 (확인 필요 6) | `source = MANUAL`, 성취수준 단계·요소 `standardCode`는 비우고 APM 검수 때 채움 | 추측으로 채우지 않음 |
| "행동" | 칸을 두지 않고 검토 항목(학년·내용·행동이 미션과 맞는지)으로 | 기획서 6.2 ④ "검수·확정(APM): 학년·내용·행동(성취기준 동사)이 미션과 맞는지 확인". 수집데이터 보고서 `missions` 필드에도 없음. 현행 765개 중 605개(79%)가 "~하고·~하며·~하여"로 동작을 여러 개 이어 값 하나로 정하기 어려움 |
| 계약 파일 시점 | ERD Mermaid·OpenAPI는 구현 이슈에서 코드와 함께 | ERD Mermaid는 `scripts/verify_db_schema.py`가 실제 DB와 테이블·컬럼을 그대로 대조하고(`erd.md`가 바뀌면 `ci-db-schema` 실행), learning·ai OpenAPI 경로는 컨트롤러·라우터와 같아야 함(`test_record_exists_openapi.py` 36개, `test_ai_openapi.py` 6개). #262는 기존 경로의 필드만 바꿔 OpenAPI를 같이 고쳤지만 #336은 새 경로·테이블이 중심 |

### 성취기준 표 대조 (`standards_2022.csv`, #213 담당 개인 폴더)

| 항목 | 값 |
|---|---|
| 전체 | 790행 = 2022 개정 현행 765 + 2026.1 일부개정 25(즐거운 생활 16·건강한 생활 9, 모두 초1~2) |
| 현행 학년군 | 초1~2 100·초3~4 162·초5~6 169·중1~3 334. 성취수준 단계는 초 3단계(A~C), 중 5단계(A~E), 현행은 모두 있음 |
| 코드 중복 | 12개(`2즐01-01`~`2즐03-04`). 현행과 2026.1이 같은 코드에 다른 문장 |
| 코드 모양 | 원자료는 대괄호 포함(`[6국01-02]`), 시드 `achievement_standards`는 대괄호 없음(`6국01-02`) → 표도 대괄호 없이. `9사(일사)01-01` 같은 괄호 코드 74개 |
| 시드 20문항 | 성취기준 코드 21개(초4 문제 해결 1문항이 2개) 모두 표에 있음 |
| 생각 유형 후보(자동) | 현행 765개 중 335개 빈칸, 88개는 후보 2개 이상. 동사 낱말 규칙 값(`extract_standards.py` "사람이 검토해야 함")이라 넣지 않음 |
| 비고 | 현행 79행. 66행은 "A·B 같은 기술(원자료 병합 칸)" 등, 13행은 고시 변환 때 빠진 기호 보완·성취수준 자료 문구 차이 같은 원문 대조 기록 → `note`로 넣음(FAD-08 "원문 대조" 구분) |

### 설계에서 정한 것

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 검사 분담 | ai: 필수 항목·학년별 질문 길이·정답·금지어·예시 답 노출. learning: 성취기준 실재·요소 code 규칙·요소 `standardCode`·입력 방식 모양 | 각자 가진 코드를 재사용: 노출 검사는 ai `followup/leak_guard.find_leaks`, 표와 code 규칙(게시 검사)은 learning. 이슈 초안은 ai가 모두 검사 |
| 반복 위치 | ai는 호출 1번에 생성 1회, 반복은 learning | ai 안에서 3회 반복하면 최대 약 90초로 learning→ai 35초를 넘음. ai 마감은 되묻기와 같은 33초(`followup_deadline`) |
| 서킷 | learning 초안용 ai 호출은 별도 서킷 `ai-mission-draft`(P12 값) | learning `AiClient`는 판정·되묻기가 서킷 `ai` 하나를 공유. 초안 실패가 학생 판정을 막지 않게(#305와 같은 문제). core `ai-report-template` 분리 선례 |
| 실패 상태 | 상한에서 마지막 실패가 검사면 `CHECK_FAILED`, AI 호출이면 `FAILED`(`failure_code`는 판정과 같은 `AI_*`) | FAC-18 "반복 실패는 반려/실패로", 판정 실패 코드 재사용 |
| 생성 방식 기록 | `mission.source`(`MANUAL`·`LLM_DRAFT`), 초안 연결은 `mission_draft.mission_id` 한쪽 | 미션이 처음 만들어진 방식이라 버전마다 바뀌지 않음. 이슈 초안은 `mission_version.source`·`draft_id` |
| 성취기준 FK | 두지 않고 게시 검사 | `achievement_standards`가 jsonb 배열, 교육과정이 바뀌어 표를 다시 넣을 때 지난 버전이 막히지 않게 |
| 초안 목록 API | `GET /admin/mission-drafts?status` 추가 | FFJ-10 "생성 출처·오류 이유·시도 횟수·… 상태를 확인". 이슈 초안에 없음 |
| 다시 만들기 | 새 초안 요청(실패한 초안을 되살리지 않음) | 상태 전이가 단순하고 시도 기록이 초안마다 남음 |
| 장면 | 초안의 `sceneNote`는 그림 제작 메모로 초안에만 두고 미션에 저장하지 않음 | 지금 미션은 장면을 질문 문장(시드)과 `scene_uri`(그림)로만 가짐 |
| 표준 요소 입력 | learning이 FN 1.5 표에서 그 유형 코드·공통 설명을 ai에 보냄 | 코드 목록을 learning 한 곳에만 둠 |

### 기준안 (새 값, 확정 필요)

| 값 | 기준안 | 정할 사람 | 근거 |
|---|---|---|---|
| 생성 시도 상한 | 3회(첫 생성 포함) | 김동섭(P19 "재생성 상한") | 이슈 예시 |
| 학년별 질문 길이 | 전 학년 200자 기준안(ai 9.1, P19 확정 전) | 김동섭(P19, FAD-06) | 참고: 시드 질문 길이 초3 67~156자, 초4 87~193자, 초5 88~173자, 초6 92~185자 |
| 미션 상태 이름 | 기존 `DRAFT`·`REVIEW_REQUIRED`·`PUBLISHED`·`UNPUBLISHED` 유지 | 김동섭(P19 "상태 enum") | 기획서 6.2 ④ "초안 → 검토 완료 → 공개", 수집데이터 보고서 `draft`·`reviewed`. 이미 구현된 상태(#145)와 이름만 다름 |
| 생성 주기 | 10초 | learning 구현 담당 | 관리자가 기다리는 시간 |
| 생성 리스 | 90초 | - | 판정 리스(P12)와 같은 값 재사용 |
| 채택 때 요소 배점 | 1 | APM | 시드 요소 56개 중 53개가 1. 채택 뒤 관리자가 고침 |

### 구현 인계

구현 완료: learning 표·시드·관리자 검사·초안 작업(#353, 22절), ai 초안 생성·검사(#354, [ai 9장](ai.md#9-미션-초안-생성자동-검사-336-설계-354-구현)), core 프록시·`MISSION_DRAFT` 사용량(#355, 23절). web 화면은 #356(진행 중).

### 영향 확인

| 받는 곳 | 결과 | 근거 |
|---|---|---|
| 학생 미션 응답 | 영향 없음. 성취기준을 내보내지 않음 | learning 학생 응답(`MissionView`·`MissionResponses`)에 `achievementStandards` 없음 |
| core 관리자 미션 프록시 | 응답 필드 추가(`source`·`achievementLevels`·`standardCode`)는 그대로 전달, 새 게시 누락 코드도 모양 검사 통과 | `AdminLearningService` 성공 응답 그대로, `missingFields` 정규식 `[a-zA-Z][a-zA-Z0-9.\[\]]{0,99}` |
| core 관리자 미션 계약 테스트 | 새 경로는 `/admin/missions` 밖이라 10개 그대로 | `test_admin_missions_contract.py` |
| `/internal/versions` 소비자 | core에 읽는 코드 없음, ai·api-spec만 바뀜 | core 전체에서 `/internal/versions` 호출 없음 |
| LLM 사용량 | 호출 종류가 다섯 곳(이벤트 스키마·core enum·core CHECK·ERD·core OpenAPI)과 ai·scoring 발행 목록에 고정돼 같이 바꿔야 함 | 위 core 인계 |
| report·분석 대화 | 영향 없음 | 성취기준·초안을 읽지 않음. 리포트의 연결 성취기준 표시는 범위 밖 |

### 설계·이슈와 다른 점

- 이슈 작업 위치 "OpenAPI 3개" → 구현 이슈에서(위 결정). 이슈 "erd 4.1에 추가" → Mermaid 밖 4.1.1 "구현 전" 절
- 이슈 설계 초안 `mission_version.source`·`draft_id` → `mission.source` + `mission_draft.mission_id`(위 표)
- 이슈 요구사항 목록에 FAD-08이 없어 더하고 FN-ADM-21(성취기준 표)을 신설. 이슈의 FN-ADM-20은 그대로 미션 초안
- 이슈 "ai 자동 검사" → ai·learning 분담, 이슈에 없던 초안 목록 API 추가
- `code` PK 그대로지만 2026.1 25개를 넣지 않아 가능(FAD-08과 다름, planning-decisions 2.5)
- 기존 파일 수정: `functional-spec.md`(1.5 판정·표준 요소 문구와 새 소절, FN-ADM-09·11·19·20·21), `erd.md`(4.1 게시 검사 문구, 3.5 `llm_usage` 메모, 4.1.1), `api-spec.md`(1.5 상태 코드값, 2.8 표·프록시, 4.1 관리자 미션 행과 새 행, 4.2 새 행·`/internal/versions`·#68, 4.6 `callType`, 5.2 프롬프트 이름), `class-diagram.md`(3.5 메모, 4.1.1, 5.1 `ActiveVersions`, 5.4), `state-diagram.md`(3.4), `sequence-diagram.md`(9 메모, 11 신설, 확인 필요 가정 11 → 12), `ai.md`(9절), `planning-decisions.md`(2.5), `docs/README.md`

### 검증

- 기획서·수집데이터 보고서 PDF(PyMuPDF로 본문 추출)와 요구사항 정의서 v0.5 원문을 대조함. 이슈 본문의 기획서 6.2 요약은 원문과 같음
- 성취기준 표 숫자는 원자료 CSV를 직접 셈(위 대조표)
- 검증 명령 결과는 PR 본문에 적음

### 한계

- 성취수준 문장을 넣기 전에는 요소·초안을 성취기준 문장으로만 구체화해 기획서 5.3(2) "성취수준 문장에 맞춰"와 다름. 이용 조건이 확인되면 `levels`만 채우면 됨
- 학년별 질문 길이는 P19 확정 전이라 전 학년 200자 기준안으로 검사(ai 9.1)
- 생성 시간은 #353·#354에서 실측해 시간 설정을 바꿈([ai 9.2](ai.md#92-미션-초안-시간-설정-변경-353))
- 범위 밖(이슈 그대로): 시범 풀이 기록(FAR-09), 요소 기반 다음 미션 추천(FBF-38), 리포트의 연결 성취기준 표시, 기초 사고력 연결

## 22. 성취기준 표·미션 초안 구현 (#353)

21절 설계의 learning 몫과, #262에서 남은 관리자 code 검사를 구현했다. ai 초안 생성은 #354(PR #357), core 프록시·사용량은 #355, 관리자 화면은 #356이다.

| 위치 | 내용 |
|---|---|
| V10 | `achievement_standard`·`mission_draft`, `mission.source`(기존 행 `MANUAL`, SQL DEFAULT 없음)·`mission_version.achievement_levels`·`rubric_element.standard_code`, 인덱스 `ix_mission_draft_status_created`. ERD 4.1 Mermaid·6장·8장으로 옮김 |
| `db/seed/achievement_standards.sql` | 현행 765행(초1~2 100·초3~4 162·초5~6 169·중1~3 334), `levels` NULL, `note` 79행, `source` 교육부 고시 제2022-33호. 코드가 키라 다시 넣으면 덮어씀 |
| `mission/domain/Standards.kt` | FN 1.5 표준 요소 표·code 규칙(`StandardElements`), 성취기준 행(`AchievementStandard`: 학년군 범위·단계 수) |
| `PublishSnapshot` | 게시 누락 추가: `rubric.elements.code`(#262), `achievementStandards`(표에 없음·학년군 밖), `achievementLevels`, `rubric.elements.standardCode` |
| `AdminMissionController` | 저장 때 모양 400: 요소 code(표준·`e`+숫자·예약), `achievementLevels`(A~E), 빈 `standardCode` |
| 초안 | `MissionDraft`(상태 전이)·`DraftRules`(채택 변환·learning 검사·ai 요소 입력)·`MissionDraftService`·`MissionDraftRepository`(리스 점유·리스 대조 저장)·`AdminMissionDraftController`(경로 6개)·`MissionDraftScheduler`·`MissionDraftAiClient`(서킷 `ai-mission-draft`) |
| 계약 | learning OpenAPI 경로 5개(조작 6개)·스키마, 관리자 미션 스키마에 `source`·`achievementLevels`·`standardCode` |

### 결정

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 채택 미션 칸 | 교과는 첫 성취기준의 교과, 입력 틀은 입력 방식별 고정 틀(풀이 4칸·논술 4칸, 데모 시드와 같음), 장면 그림·단위는 비움, 시연 전용 아님. `sceneNote`는 저장하지 않음 | 초안 출력에 `subject`·`inputTemplate`·`answerUnit`이 없음(계획 결정 1) |
| learning 검사 | 채택할 미션·기준표를 게시 검사에 그대로 넣고(검토는 통과로 봄) 누락을 `ELEMENT_CODE`·`STANDARD_CODE`·`SHAPE`로 바꿈 | class-diagram 4.1.1 "게시 검사와 같은 함수". 채택한 초안이 검토만 거치면 게시 규칙을 통과함 |
| 성취기준 학년군 검사 (#353 추가) | 미션 학년 범위가 고른 성취기준 각각의 `grade_band` 안. 초안 요청 400, 게시 422 `achievementStandards`. 이미 게시된 버전은 그대로 | 설계는 학년을 사람 검토 항목(기획서 6.2 ④)으로만 두어 초3 미션에 `6국…`을 골라도 생성·게시됨. 표의 학년군으로 자동 확인 가능(2026-11-04 결정, 이슈 #353 본문) |
| 요청 때 성취수준 확인 | 단계가 고른 성취기준의 단계 수 안인지 요청 때 400 | 잘못된 단계로 ai를 부르지 않게. 게시 검사와 같은 규칙 |
| 다음 생성의 이전 실패 | 지금까지 모든 시도의 실패 사유(겹치는 것 한 번) | 앞에서 고친 문제가 다시 나오지 않게. ai는 같은 사유를 한 번만 고칠 점으로 바꿈 |
| 한 주기 생성 수 | 레플리카마다 주기(10초)에 초안 1개, 생성 1회 | class-diagram 4.1.1. 점유는 `FOR UPDATE SKIP LOCKED` + 조건 재확인 UPDATE |
| ai 오류 분류 | `AiClient`의 오류 분류·서킷 값을 `postToAi`·`aiCircuitBreaker`로 빼서 함께 씀(판정 동작 그대로) | "AiClient와 같은 오류 분류" 설계를 코드 복사 없이 |
| 미션 초안 시간 (P12 예외) | ai LLM 60초 1회·마감 63초, learning 초안 ai 클라이언트 대기 70초(`app.mission-draft.ai-read-timeout`, `InternalRestClientFactory.create(service, readTimeout)`). 생성 리스 90초 안 | 로컬 실연에서 논술 초안이 15초 제한에 막혀 3번 모두 `FAILED`. 기본 모델 `gpt-6-luna`는 실제 성취기준으로 15~31.7초(ai.md 9.2). 주기 작업이라 기다리는 사람이 없음(2026-11-05 결정, 이슈 #353 본문) |
| 스케줄러 스레드 | `spring.task.scheduling.pool.size: 3`(`@Scheduled` 작업마다 하나) | 기본값 1이면 초안 생성(ai 대기 최대 70초) 동안 고착 판정 탐지(P12 1분)·처리 이벤트 정리가 밀림. 같은 작업은 `fixedDelay`라 스스로 겹치지 않음(`SchedulingPoolTest`) |
| `mission.source` SQL DEFAULT | 두지 않고 V10에서 기존 행을 채운 뒤 NOT NULL. 데모 시드·검증 스크립트 7개·테스트 3곳이 값을 넘김 | ERD 1장 "DEFAULT 없음", `verify_db_schema.py`가 허용하는 예외는 `student.parent_sharing_enabled` 하나. 정책 검사(`check_policy_migrations.py`)는 V5까지만 적용해 그대로 |
| 성취기준 시드 적용 | 파일만 추가하고 적용 방법은 시드 주석에. E2E 시드에는 넣지 않음 | 계획 결정 2. E2E 흐름이 게시 검사를 쓰지 않음 |

### 이슈와 다른 점

- 이슈 "테스트: 시드 파일을 읽어 765행" → 테스트 DB에 시드를 실제로 넣어(`PostgresRepositoryTest`) 행 수·학년군별 수·데모 시드 코드 21개·`levels` NULL을 확인. 시드가 스키마에 그대로 들어가는지도 함께 봄
- 학년군 검사를 범위에 추가(이슈 #353 본문 갱신)
- ai 미션 초안 시간 설정 변경을 범위에 추가(이슈 #353 본문·라벨 `area:ai` 갱신). #354(PR #357)의 "기본 설정 유지" 결정을 실제 성취기준 실측으로 바꿈
- learning OpenAPI는 경로 5개에 조작 6개(`/mission-drafts`에 POST·GET), `test_record_exists_openapi.py`는 조작 수를 세어 36 → 42
- gitops 로컬 값의 learning 마이그레이션 리비전 v9 → v10(`test_core_migration_versions.py`)

### 한계

- **배포 순서**: ai(#357)를 먼저 배포. learning이 먼저 나가면 초안 요청이 AI 호출 실패 3회로 `FAILED`가 됨(초안이 없으면 ai를 부르지 않음)
- **성취기준 시드를 먼저 넣어야 게시 가능**: 게시 검사가 성취기준 표를 읽으므로, V10 적용 뒤 `achievement_standards.sql`을 넣기 전에는 모든 미션의 게시가 `achievementStandards`로 막힘. 운영·로컬 모두 마이그레이션 직후 시드를 넣음
- **관리자 화면 기준표 저장**: #262 저장 검사로 자유 code(`e1` 모양이 아닌 값)는 400. web(#356) 전까지 관리자 화면에서 표준 코드·`e`+숫자만 써야 함
- **대괄호 성취기준 코드**: 관리자 화면에서 `[6국01-02]`처럼 넣은 미션은 표에 없어 게시가 막힘(표는 대괄호 없음)
- 사용량 `MISSION_DRAFT`는 core(#355) 전까지 DLQ에 남음(#354). #355에서 반영(23절)

### 검증

- learning `./gradlew test bootJar` 통과(322개, Testcontainers). 새 테스트: `MissionTest`(code·성취기준·학년군·성취수준·요소 성취기준 게시 검사), `MissionDraftTest`(상태 전이·상한·실패 종류), `DraftRulesTest`(learning 검사 분류·채택 변환·ai 요소 입력), `MissionDraftServiceTest`(시드 765행, 요청 400, 생성·실패 누적·상한, 늦은 작업 덮어쓰기 없음, 채택·버리기·목록), `MissionDraftConcurrencyTest`(레플리카 4곳 동시 생성 1회, 동시 채택 미션 1개), `MissionDraftAiClientTest`(계약 필드·오류 분류·서킷 분리), `AdminMissionDraftControllerTest`, `DemoSeedPublishTest`(데모 시드 20문항이 새 게시 검사 통과, #262 인계)
- `ci-db-schema` 재현: `check_db_migrations.py`(일회용 PostgreSQL, learning 21개 테이블·194개 칼럼이 ERD와 일치, 반복 마이그레이션 변화 없음), `scripts/tests` 156개
- 로컬 실연(2026-11-05, 이 브랜치로 learning·ai 재빌드, 로컬 learning_db에 V10·성취기준 시드, ai `OPENAI_MODEL=gpt-6-luna`): learning 내부 API로 입력 방식 6가지 초안(논술은 성취기준 2개·성취수준 B)을 한꺼번에 요청 → 주기 작업이 차례로 생성해 6건 모두 첫 시도에 `READY`(193초 동안, ai 응답 200 6번·5xx 0번) → 채택(`LLM_DRAFT`) → 검토 → 게시 200(누락 없음). 학년군이 안 맞는 요청은 400, 같은 초안 재채택은 409. 시간 설정을 바꾸기 전에는 같은 실연에서 논술이 3번 모두 `AI_CALL` 실패로 `FAILED`였음
- ai `ruff`·`pytest` 399개 통과(호출별 대기 덮어쓰기·초안 60초 1회 테스트 포함)

## 23. core 성취기준·미션 초안 프록시와 사용량 MISSION_DRAFT (#355)

21절 구현 인계의 core 몫. 관리자 화면은 #356이다.

| 위치 | 내용 |
|---|---|
| `learning/controller/AdminMissionDraftsController` | 공개 경로 `GET /admin/achievement-standards`, `POST·GET /admin/mission-drafts`, `GET /admin/mission-drafts/{draftId}`, `POST …/{draftId}/adopt`·`…/discard` → learning `/internal/admin/…` 같은 경로 |
| `learning/service/AdminLearningService` | `achievementStandards`·`missionDrafts` 추가. 관리자 미션의 요청 감사 → 한 번 호출 → 응답 대상 확인 → 결과 감사 흐름을 `audited`로 빼서 미션·초안이 함께 씀(미션 동작 그대로) |
| `account/controller/PublicAuthFilter` | `/admin/mission-drafts`·`/admin/achievement-standards`도 CONTENT |
| `admin/service/MissionAuditService`·`MissionAuditRepository`·`MissionAuditMapper.xml` | `target_type`을 고정 `MISSION`에서 인자로(`MISSION`·`MISSION_DRAFT`), 채택 결과 detail에 `draftId` |
| `V28__mission_draft_call_type.sql` | `ck_llm_usage_call_type`에 `MISSION_DRAFT`(V14와 같은 DROP·ADD). V27은 #243(PR #359) |
| 호출 종류 목록 | core `CallType` enum, `llm.usage.recorded.v1` 스키마, core OpenAPI `CallType`, ERD 3.5 Mermaid, scoring `publisher.py` `CallType`. ai 발행 목록에는 #354에서 이미 있음. 순서는 ai와 같게 `REPORT_NARRATIVE` 다음 |
| 계약 | core OpenAPI 경로 5개(조작 6개)·`AdminMissionDraftDocument`, gitops 로컬 core 마이그레이션 리비전 v27 → v28 |

### 결정

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 컨트롤러 | 새 `AdminMissionDraftsController`(같은 `learning/controller` 패키지)·서비스는 기존 `AdminLearningService` | `AdminMissionsController`는 `/api/v1/admin/missions` 아래만 받고, `test_admin_missions_contract`가 그 파일의 `service.missions(…)` 호출로 learning 경로 10개를 셈. 같은 파일에 넣으면 그 대조가 흐려짐 |
| 감사 대상 | 요청·버리기: `target_type = MISSION_DRAFT`, 결과는 응답 `draftId`(요청의 요청 감사는 아직 ID가 없어 NULL). 채택: 요청 감사는 초안, 결과 감사는 응답 `missionId`·버전(`target_type = MISSION`, detail `draftId`) | api-spec 2.8 "채택은 응답 `missionId`, FN-ADM-13". 채택이 미션을 만들므로 `MISSION_CREATE`처럼 미션 ID로 찾으면 처음부터 이력이 보임. 감사 조회 `targetType`은 정규식만 검사해 새 값이 바로 됨 |
| 감사 action | `MISSION_DRAFT_REQUEST`·`MISSION_DRAFT_ADOPT`·`MISSION_DRAFT_DISCARD` + 기존 접미사 `_REQUESTED`·`_SUCCEEDED`·`_REJECTED`·`_UNKNOWN` | 미션 감사와 같은 규칙. 요청 본문·learning 오류 문장은 남기지 않음 |
| 응답 대상 확인 | 초안 응답은 `draftId`(UUID, 버리기는 경로와 같아야 함)·`status`(문자열), 채택 응답은 미션 응답과 같은 `missionId`·`currentVersion`·`currentRubricVersion`. 어긋나면 503 `LEARNING_INVALID_RESPONSE` + `_UNKNOWN`, 다시 부르지 않음 | 관리자 미션과 같은 기준. 결과를 모르는데 다시 부르면 초안이 두 번 생길 수 있음 |
| 오류 전달 | learning `VALIDATION_FAILED`(400)·`NOT_FOUND`(404)·`CONFLICT`(409)·`FORBIDDEN`은 기존 허용 목록 그대로 전달, 공급자 문장은 버림. 404 고정 문구 "미션 초안을 찾을 수 없습니다.", 미지원 405/501은 미션과 같은 `ADMIN_MISSIONS_UNAVAILABLE` | 새 코드를 만들면 web(#356) 처리가 늘어남. 같은 learning 관리자 API라 같은 코드로 충분 |
| 쿼리 검사 | core는 `page`·`size`(기존 `operationPage`)·초안 `status`(learning `DraftStatus` 6개)·문자 쿼리 100자만 보고, `gradeBand`·`subject`·`q` 값은 learning이 검사 | 학년군 이름 목록을 learning 한 곳에만 둠. 문자 길이는 learning에 넘길 쿼리를 제한하려고 |
| `MISSION_DRAFT` 위치 | 목록 가운데(`REPORT_NARRATIVE` 다음) | ai `CallType`(#354)과 같은 순서로 두어 일곱 곳을 같은 목록으로 대조 |
| 계약 지문 | `admin_operations_base_contracts.json`은 그대로 두고, 테스트에서 `CallType`의 `MISSION_DRAFT`만 빼고 지문 비교 | 기존 #262·#242 정규화와 같은 방식. 지문 파일을 다시 만들면 다른 변경도 묻힘 |

### 이슈와 다른 점

- 이슈 작업 위치 "`AdminMissionsController`"에 넣지 않고 같은 패키지 새 컨트롤러로(위 결정)
- 이슈에 없던 것: gitops 로컬 core 마이그레이션 리비전 v28(`test_core_migration_versions.py`), 새 계약 테스트 `test_admin_mission_drafts_contract.py`(core ↔ learning·core OpenAPI 경로 6개, 쿼리 이름, 초안 상태, CONTENT, 호출 종류 일곱 곳 대조), `LlmUsageQueryTest` 호출 종류 수 6 → 7
- web의 사용량 호출 종류 이름표·목업(`frontend/web/src/presentation/admin/adminFormatting.ts`·`src/mocks/handlers/admin.ts`)에는 `MISSION_DRAFT`가 없음. web 범위(#356)라 바꾸지 않음

### 한계

- **마이그레이션 순서**: PR #359(V27)가 develop에 병합된 뒤 그 위에서 작업해 V27 → V28 순서. V28이 V27보다 먼저 적용된 DB는 없음(`outOfOrder` 꺼짐)
- **DLQ 재처리**: #354 배포 뒤 이 변경 전까지 나온 `MISSION_DRAFT` 사용량 메시지는 core 소비자가 거부해 DLQ에 있음. 배포 뒤 다시 넣으면 기록됨(`event_id` UK로 중복 없음)

### 검증

- core `./gradlew clean test bootJar` 통과(develop #359 병합 뒤 기준 510개, 실패 0, JDK 21 임시 컨테이너 + Testcontainers). 새 테스트(`AdminOperationsIntegrationTest`): 초안 경로 6개가 learning 같은 경로로 ADMIN·관리자 ID·빈 학생 범위로 감, CONTENT 아닌 관리자는 403이고 learning을 부르지 않음, 잘못된 `status`·`size`·`page`·100자 넘는 `q`·배열 본문은 learning 전에 400, 요청·채택·버리기 감사 행(대상 종류·ID·`draftId`·결과), 응답에 초안·미션 ID가 없거나 다르면 503 `LEARNING_INVALID_RESPONSE` + `_UNKNOWN`이고 한 번만 부름, 404 고정 문구·400·409 코드 전달과 공급자 문장 제거, 405는 `ADMIN_MISSIONS_UNAVAILABLE`. 기존 `LlmUsageQueryTest`가 `CallType` 7개 모두를 실제 DB(V28 CHECK)에 넣고 조회
- 루트 계약 테스트 `python -O -m unittest discover -s scripts/tests` 통과(163개, 새 `test_admin_mission_drafts_contract.py` 7개 포함)
- `ci-db-schema` 재현: `check_db_migrations.py`(일회용 PostgreSQL) 통과. develop(#359 V27 병합 뒤) 기준 core V26 → V27 → V28 적용, 48개 테이블·448개 칼럼이 ERD와 일치, 반복 마이그레이션 변화 없음. 적용 뒤 `ck_llm_usage_call_type`에 `MISSION_DRAFT` 확인
- scoring `ruff check`·`pytest` 통과(199개, 임시 컨테이너)
- 로컬 실연(2026-11-05, 이 브랜치로 core·learning 이미지 빌드, compose 별도 프로젝트에 호스트 포트는 core만 열고 공유 kind·컨테이너는 그대로, 끝난 뒤 볼륨까지 삭제): learning_db에 성취기준 시드 765행, ai 자리에는 learning 테스트 `sampleDraft`와 같은 초안을 돌려주는 대역(LLM 호출 없음). core 공개 경로로 성취기준 조회(`gradeBand=초5~6`·`q=6국01-02`) 200 → 초안 요청 202(`GENERATING`, `X-Admin-Operation-Id`) → learning 주기 작업이 대역 ai를 불러 `READY`(1회) → 목록 `status=READY` 1건 → 채택 201(`DRAFT`·`LLM_DRAFT`, 미션 경로로 조회 200) → 재채택·채택된 초안 버리기 409 `CONFLICT`, 없는 초안 404, 학년군 밖 요청 400 `VALIDATION_FAILED` → 새 초안 버리기 200(`DISCARDED`). 감사 14행이 위 결정대로 남음(채택 결과는 `MISSION`·미션 ID·`draftId`). 실제 LLM과 사용량 이벤트 흐름은 이 실연에 없음(사용량 소비는 위 테스트와 CHECK로 확인)

## 24. 주간 테마·요일 문제·되돌아보기 (#385)

2026-11-06 결정 P23(학년군별 주 1테마, 월~금 하루 1문제, 그 요일에만 신규 시도, 토·일 되돌아보기·다시 풀기)의 learning 몫. core 프록시·무료 하루 1개 한도는 #387(develop 머지), 웹은 #393·#395(MSW 목업 기준)이다.

| 위치 | 내용 |
|---|---|
| `V11__prepare_weekly_themes.sql` | `weekly_theme`·`weekly_theme_version`·`weekly_theme_day`·`theme_review_view`, 게시 부분 UK, `attempt.context`·`theme_id`·`theme_week_start`(nullable) 추가와 기존 행 `EXTRA` 채움, 인덱스 2개 |
| `V12__apply_attempt_context.sql` | `LOCK TABLE attempt` + 사전 검사 뒤 `context NOT NULL`, `ck_attempt_context`·`ck_attempt_theme_context` |
| `theme/domain` | `GradeBand`·`ThemeDay`·`DayState`·`ThemeWeek`(KST 주·요일 상태), `WeeklyTheme`(상태 전이), `ThemePublishCheck`(게시 검사), 응답 모양 |
| `theme/repository` + `mybatis/theme/WeeklyThemeMapper.xml` | 테마·버전·요일, 이번 주 테마 해석, 학생 테마 시도, 열람 기록(`ON CONFLICT DO NOTHING`), 학생 삭제 |
| `theme/service/WeeklyThemeService` | `current`·`checkStart`·`recordReviewView`·`summary`·`deleteByStudent(MANDATORY)` |
| `theme/service/WeeklyThemeAdminService` | 목록·작성·상세·수정(새 버전)·검토 요청·게시·중단 |
| `theme/controller` | `WeeklyThemeController`(`/internal/students/{id}/weekly-theme…` 3경로), `AdminWeeklyThemeController`(`/internal/admin/weekly-themes…` 7경로) |
| `attempt` | `AttemptContext`·`ThemeAttempt`, `Attempt`에 3칸, `AttemptController.start` 선택 본문 `{context}`, `AttemptService.start(…, context)` |
| `_common/config/ClockConfig` | `Clock.system(Asia/Seoul)` 빈. 요일 판정만 쓰고 기존 `Instant.now()`는 그대로 |
| `record/service/StudentDeletionService` | 같은 트랜잭션에서 `weeklyThemeService.deleteByStudent` |
| 계약·문서 | learning OpenAPI 10경로·스키마, ERD 4.2·4.2.1·6장·8장, api-spec 1.3·2.8·2.11·4.1, state-diagram 3.2.1·3.5, sequence-diagram 3.4·3.6, class-diagram 4.1·4.4, architecture `theme/`, gitops 로컬 learning 마이그레이션 리비전 v10 → v12 |

### 결정

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 게시 중 수정 | 미션(V7)과 같은 버전 방식. `weekly_theme_version`을 두고 테마 행에 `current_version_id`·`published_version_id`·`review_version_id`. 학생 조회·시작 검사는 게시본, 관리자 편집은 현재본, 재검토·재게시 때 교체하고 상태는 `PUBLISHED` 유지 | api-spec 2.8 "게시 중 수정은 재검토". 상태만 두면 수정하는 순간 학생 화면이 바뀜 |
| 학년군·주 위치 | 테마 행(버전 밖). 게시 중 변경은 409 `CONFLICT` | 게시 부분 UK `(grade_band, week_start)`가 테마 행에 있어야 함. 이미 그 주 학생에게 제공 중인 테마의 주가 바뀌면 안 됨 |
| 검토·승인 | 별도 `/review` 경로 없음. 검토 요청한 버전(`review_version_id`)이 현재본일 때의 게시가 승인. 검토 중 수정은 `DRAFT` | core #387이 7경로만 프록시. 미션처럼 검토 경로를 두면 core도 바꿔야 함 |
| 학년군 검사 | 미션 게시본이 학년군 전체를 덮음(`gradeMin ≤ 학년군 최소`, `gradeMax ≥ 학년군 최대`), 초3~4는 논술 불가, 시연 전용 제외 | 학년군 안 어느 학생에게나 그 요일 문제가 열려야 함(`MissionView.isOpenTo`와 같은 규칙) |
| 오류 코드 | 허용 안 되는 전이 409 `CONFLICT`, 게시 검사 422 `WEEKLY_THEME_PUBLISH_INCOMPLETE` + `errors:[{code, message}]`(코드 6종: `DAYS_INCOMPLETE`·`MISSION_NOT_PUBLISHED`·`MISSION_DEMO_ONLY`·`GRADE_BAND_MISMATCH`·`THINKING_TYPES`·`WEEK_ALREADY_PUBLISHED`) | 웹 `publishProblems()`가 `errors[].message`를 그대로 보여 줌. 동시 게시가 부분 UK에 걸려도 같은 422 |
| 작성 중 저장 | 다섯 요일을 다 채우지 않아도 저장(요일·미션 중복과 없는 미션만 400). 다섯 요일은 게시 검사 | 미션 작성과 같음 |
| 이번 주 테마 | 그 주 게시본, 없으면 그 주 이전 최근 게시본(`reused`). 미래 주 게시본은 쓰지 않음. 학년군에 게시 테마가 없으면 404 | P23 "미게시 주는 최근 게시 테마 재사용" |
| 시작 순서 | 진행 중 시도 반환(검사 없음) → 미션 공개·범위(기존) → 테마 검사. 학년군은 시도 학년으로 정함(core와 같은 규칙) | 자정이 지나도 이어하기(P23). core는 `themeId`를 넘기지 않음(#387) |
| `THEME_DAY` | 이번 주 테마의 오늘(KST, learning 시계) 요일 문제만. 아니면 409 `THEME_DAY_CLOSED`. 이미 끝낸 문제도 그날이면 새 시도 | api-spec 2.11 |
| `THEME_REVIEW` | 토·일 + 이번 주 테마 문제 + 이번 주 그 문제 `THEME_DAY` 시도를 마무리(`finished_at`)했을 때만. 아니면 409 `THEME_REVIEW_NOT_ALLOWED` | "그 주 마무리한 문제만" |
| 요일 상태·되돌아보기 | `state`는 오늘 `OPEN`, 지난 요일 `CLOSED`, 안 온 요일 `LOCKED`(토·일은 모두 `CLOSED`). `attemptStatus`는 이번 주 그 요일 문제 최근 `THEME_DAY` 시도. `review.missions[].completed` = 마무리함, `missed` = 지난 요일인데 마무리 안 함 | 웹 `readWeeklyTheme`(`NOT_STARTED`·`IN_PROGRESS`·`COMPLETED`) |
| 완주 | 월~금 다섯 문제 각각 그 요일(KST) 안에 학습 완료(`completed_at`) | P23 "각 당일 학습 완료". 금요일 문제를 토요일 01시에 끝내면 완주 아님 |
| 열람 기록 | `theme_review_view` 학생·주당 1행, 다시 보내도 200(`firstViewThisWeek`만 false). 평일은 409 `THEME_REVIEW_NOT_ALLOWED` | #389 포인트 멱등 근거 |
| 주간 요약 | 역할 `PARENT`·`STUDENT`·`SYSTEM` + 대상 학생 scope(기록 조회와 같음). 테마는 그 주 학생 테마 시도에서 정함(주 중간에 바뀌면 마지막 요일 문제 시도의 테마), 테마 시도가 없으면 `NO_RECORD` | report는 학년군을 모름. 학생이 실제로 푼 테마를 요약 |
| 날짜 기준 | 조회·열람은 core가 넘긴 `date`, 시작 검사는 learning `Clock`(KST) | core 시작 프록시는 날짜를 넘기지 않음(#387). 둘 다 KST 오늘이라 같은 날 |

### 설계·이슈와 다른 점

- ERD 4.4 설계는 `weekly_theme`에 `title`·`intro`를 두고 `weekly_theme_day (theme_id, …)`였다. 게시 중 수정을 버전으로 두려고 테이블 1개(`weekly_theme_version`)와 컬럼 3개(`current_·published_·review_version_id`)를 더하고 제목·소개·요일 문제를 버전으로 옮김(`weekly_theme_day (theme_version_id, day_of_week)`). 순환 FK는 미션처럼 `DEFERRABLE INITIALLY IMMEDIATE`(작성 트랜잭션만 현재 버전 검사를 미룸)
- `weekly_theme.week_start` 월요일 CHECK(`ck_weekly_theme_week_start_monday`)를 더함. API도 월요일이 아니면 400
- 상태도 3.5의 "수정 요청"(검토 반려) 전이는 없다(위 결정). "검토 중 수정"으로 `DRAFT`
- 학생 응답 `days[]`·`review.missions[]`에 `title`을 더함(api-spec 2.11에 반영). 웹 목업은 `review.missions[].title`을 선택 필드로 읽음
- 관리자 응답 `AdminWeeklyTheme`에 `version`·`publishedVersion`·`reviewRequested`·`publishedAt`·`createdAt`을 더함. 웹 `AdminWeeklyTheme` 타입(`themeId, gradeBand, weekStart, title, intro, days, status, updatedAt`)은 그대로 읽힘
- 계획에 있던 `scripts/check_policy_migrations.py`는 고치지 않음: learning V3 시점에 행을 넣고 V5까지만 적용해 `context` 컬럼이 아직 없음(V11 준비 버전이 그 행을 `EXTRA`로 채움)
- 계획의 `AttemptServiceTest` 추가 사례는 고정 시계를 쓰려고 `AttemptThemeStartTest`로 나눔(같은 Testcontainers 기반)
- `scripts/tests/test_weekly_theme_contract.py`(#387)를 3자 대조로 넓힘: core `service.weeklyThemes(…)` 경로 = learning OpenAPI 관리자 7경로, core 학생 프록시 경로의 `gradeBand`·`date`, 시작 `context` 값, 게시 오류 코드 = domain

### API 변경

- learning OpenAPI 1.2.0: 학생 `GET /students/{studentId}/weekly-theme`·`POST …/review-views`·`GET …/summary`, 관리자 `/admin/weekly-themes` 5경로(조작 7개). 시작 `POST /missions/{id}/attempts`에 선택 본문 `AttemptStartRequest`, 409 `THEME_DAY_CLOSED`·`THEME_REVIEW_NOT_ALLOWED`. 조작 수 42 → 52(`test_record_exists_openapi`)
- 시도 상세·기록 응답에는 아직 `context`를 내보내지 않음(아래 한계)

### 한계

- **테마 미션 공개 중단**: 게시 테마의 미션이 나중에 공개 중단되면 그 요일 신규 시작은 409 `MISSION_NOT_AVAILABLE`(미션 검사가 먼저). 요일 목록 표시는 미션 현재본 제목으로 계속 보임
- **다른 컨텍스트 진행 중 시도**: 같은 미션에 `EXTRA` 진행 중 시도가 있으면 `THEME_DAY` 요청도 그 시도를 원래 `context` 그대로 200으로 돌려줌(진행 중 부분 UK가 학생·미션당 하나). 그 시도는 요일 상태·완주에 들어가지 않음
- **주 중간 게시·중단**: 주 중간에 게시·중단하면 그 주 테마가 바뀐다. 시도에는 당시 `theme_id`를 저장하고, 요일 상태·완주는 이번 주 테마의 미션과 이번 주 시도를 미션 ID로 맞춤
- **`context` 노출**: 시도 상세·기록 응답의 `context`(#389 포인트 완주·#391 일일 리포트 `problems[].context`)와 웹 목업 차이 정정(#395)은 후속
- **같은 트랜잭션 재조회**: MyBatis 세션 캐시라 한 트랜잭션에서 같은 조회를 다시 하면 앞 결과를 씀(요청 하나에 한 번씩만 읽어 실제 흐름에는 영향 없음, 테스트만 조정)

### 후속 (이슈 댓글 초안, 직접 달지 않음)

- #389(원장·`RewardService.earn` 머지, 사건 연결은 후속): 되돌아보기·완주 적립 근거는 `POST …/review-views` 응답 `{firstViewThisWeek, completed}`. 완주는 월~금 다섯 문제 각 요일(KST) 안 학습 완료. 학습 완료 적립 보충에 필요한 시도 `context`는 learning 시도 상세 응답에 아직 없음(후속)
- #391: 주간 요약 `GET /internal/students/{id}/weekly-theme/summary?weekStart`(SYSTEM + 학생 scope) 응답은 learning OpenAPI `WeeklyThemeSummary`. 일일 리포트 `problems[].context`는 learning 기록 응답에 `context`를 더하는 후속 작업이 필요
- #395: 관리자 응답에 `version`·`publishedVersion`·`reviewRequested`, 게시 검사 `errors[].code` 6종이 더 있음. 별도 검토(승인) 화면 없이 "검토 요청 → 게시"
- #393: 학생 응답 `days[].title`·`review.missions[].title` 채움, 학년군에 게시 테마가 없으면 404

### 검증

- learning `./gradlew clean test bootJar`(JDK 21 임시 컨테이너 + Testcontainers, develop #410 병합 뒤): 356건 모두 통과, bootJar 생성. 기존 `RecordServiceTest` 2건이 기간을 2026-11-02~08로 고정하고 완료 시각을 `now()`로 넣어 11-09부터 실패하던 것을 기간 안 고정 시각으로 고침
  - 새 테스트: `WeeklyThemeServiceTest` 7건(요일 상태·소개·재사용·404·시작 검사·되돌아보기 열람 멱등·완주 경계·주간 요약), `WeeklyThemeAdminServiceTest` 10건(버전·전이 409·검토 중 수정·게시 중 수정과 게시본·게시 검사 6종·같은 주 1개·중단 후 재사용·404/400), `AttemptThemeStartTest` 5건(THEME_DAY 저장·자정 뒤 이어하기·THEME_REVIEW·미션 검사 먼저·DB CHECK), `WeeklyThemeControllerTest`·`AdminWeeklyThemeControllerTest`, `AttemptControllerTest` 본문 `context` 사례, `StudentDeletionTest`에 `theme_review_view`
- 루트 `python -O -m unittest discover -s scripts/tests`: 192건 OK(develop #410 병합 뒤)(`test_weekly_theme_contract.py` 3자 대조 3건 추가, OpenAPI 조작 52)
- ci-db-schema 방식 `scripts/check_db_migrations.py`(일회용 PostgreSQL 17 + Flyway 컨테이너): PASS. learning V1~V12 적용, learning_db 25개 표·222개 컬럼(전체 88개·775개, #407 병합 뒤)이 ERD와 일치, learning 음성 사례 33건(테마 CHECK·FK·부분 UK·`context` CHECK 추가), 반복 마이그레이션 변화 없음
- learning 단독 실연(2026-11-09 월요일, 일회용 네트워크·PostgreSQL에 V1~V12 + 데모 미션 시드, 이 브랜치 bootJar, core가 넘기는 내부 토큰·역할·학생 범위 헤더로 직접 호출, 끝난 뒤 컨테이너·네트워크 삭제): 게시 테마 없음 404 → 작성 201 → 검토 요청 없이 게시 409 `CONFLICT` → 검토 요청·게시 200 → 같은 주 둘째 테마 422 `errors[WEEK_ALREADY_PUBLISHED]` → 학생 월요일 조회(MON `OPEN`, 소개 있음) → 오늘 `THEME_DAY` 시작 201(시도에 `THEME_DAY`·테마·2026-11-09 저장) → 화요일 문제 409 `THEME_DAY_CLOSED` → 잘못된 `context` 400 → 같은 미션 다시 시작 200 → 평일 열람 409 `THEME_REVIEW_NOT_ALLOWED` → 토·일 날짜 열람 `firstViewThisWeek` true 뒤 false → 토요일 조회 `review.open` → 다음 주 `reused` → SYSTEM 주간 요약 `OK` → 게시 중 수정(v2) 뒤 학생은 게시본 제목
  - 데모 시드 초3 미션은 학년 하나(3~3)라 G3_4 학년군 전체를 덮지 않아 그대로는 게시 검사에 걸린다. 실연 DB에서만 3~4로 넓혔다(아래 후속)
- core와 붙인 실제 흐름(core 공개 경로 → learning)은 확인하지 못함. core 쪽은 #387 테스트와 위 3자 계약 테스트로만 확인

### 후속 작업

- 데모 테마 시드: 지금 데모 미션은 학년 하나씩이라 학년군 테마를 게시할 수 없음. 학년군 전체 범위 미션 또는 데모 테마 시드가 필요
- 시도 상세·기록 응답의 `context` 노출(#389·#391), 웹 목업 차이 정정(#393·#395)

## 25. 커뮤니티 공유물·반응·열람 검사 (#386)

2026-11-06 결정 P20([서비스 기획 방향](service-direction.md) 2.2)의 learning 몫. 공개 설정·`COMMUNITY` 동의·신고·작성자 별명은 core #388(PR #403)이 먼저 develop에 들어가 있어, core `CommunityClient`가 부르는 경로·응답을 기준으로 맞췄다.

| 위치 | 내용 |
|---|---|
| V13 | `community_post`(UK `(student_id, mission_id)`·`attempt_id`, FK 미션·시도·답변, 상태 CHECK), `community_reaction`(PK `(post_id, student_id, reaction)`, UK `id`), `community_visibility`(학생당 마지막 공개 여부), 인덱스 2개. 새 표만이라 채움 단계 없음. ERD 4.3.1 Mermaid·6장·8장 |
| `community/` | `CommunityController`(내부 경로 7개·조작 8개), `CommunityService`, `CommunityRepository`·`CommunityMapper.xml`, `CommunityRules`(검토 전이·첫 상태·반응 ID) |
| `AttemptService` | `communityShareSource`(시도·첫 학습 완료 여부·마지막 답변·시도 고정 미션 버전), `hasCompleted`(열람·반응 검사). `AttemptMapper.findFirstCompleted` |
| `StudentDeletionService` | 시도 삭제 전에 `CommunityService.deleteByStudent`(같은 트랜잭션) |
| 계약 | learning OpenAPI 경로 7개·스키마, `scripts/validate_learning_community_contracts.py`(실제 응답 10종 대조, ci-contracts 단계 추가), `verify_db_schema.py` 음성 사례 6개, gitops 로컬 learning 마이그레이션 리비전 v13 |

### 결정

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| "마무리"의 뜻 | 공유·열람·반응 모두 학습 완료(`attempt.status = COMPLETED`, 돌아보기 저장)를 기준으로 함. 마무리(`finished_at`)만 한 시도는 아님 | FN-RET-02 "처음 마무리하면(학습 완료)", core가 돌아보기 저장 뒤 공유 요청 |
| 공유 대상 시도 | 그 미션을 처음 학습 완료한 시도(`completed_at`·`id` 순 첫 행)만. 그 시도가 아니면 409 `COMMUNITY_NOT_SHAREABLE`. 공유물이 이미 있으면 어떤 시도로 요청해도 그 공유물을 200 | P20 "처음 마무리한 시도", "다시 풀기는 공유하지 않음". 설정을 끈 채 처음 완료하고 나중에 켠 뒤 다시 풀어도 공유하지 않음 |
| 공유 답변 | 그 시도의 마지막 답변(`version` 최대). 응답 `answer`는 `{inputType, text, content}`: `text`는 `answer.plain_text`(입력 틀 칸 이름·선택지 이름을 붙인 원문), `content`는 입력 방식별 제출 내용. 답변 행을 조인하고 복사하지 않음 | 고르기·분류는 `content`만으로는 ID라 읽을 수 없음. web `answerText`가 `text`를 먼저 읽어 그대로 보임. 답변은 추가만이라 복사가 필요 없고 삭제 때 한 곳만 지움 |
| 표현 필터 | 공유 때 지금 `ExpressionPolicy`로 마지막 답변의 학생 글을 다시 검사, 걸리면 공유 안 함(범주만 로그) | 제출 때 통과했어도 단어 목록이 바뀔 수 있음(#205). 걸린 말·원문은 남기지 않음(NFR-SEC-05) |
| 열람 목록 | `VISIBLE`만, 열람자 본인 공유물 제외, 반응 수 없음, `ORDER BY md5(id || seed), id` + `LIMIT/OFFSET` | 같은 seed면 같은 순서·쪽 나누기 이어짐(P20 무작위·순위 없음). 본인 글을 core가 빼면 쪽 크기가 줄어 learning에서 뺌 |
| 반응 ID | `UUID.nameUUIDFromBytes("community-reaction:{postId}:{studentId}:{reaction}")`. 취소 뒤 다시 남겨도 같은 ID | core #389 사건 키(ERD 3.5.1 반응 `postId:reaction`, 학생별 UK)와 1:1이라 어느 쪽을 써도 반응을 껐다 켜서 적립을 반복할 수 없음. 무작위 ID면 하루 상한까지 반복 적립 가능 |
| 반응 검사 순서 | 공유물 잠금 → `VISIBLE` 아니면 404 → 본인 글 409 → 미완료 403. 취소는 공유물만 있으면 상태와 무관하게 허용 | 숨긴 글에 남긴 내 반응을 지울 수 없으면 안 됨. 잠금으로 신고 숨김과 반응을 차례로 처리 |
| `community_visibility` 표 추가 | core가 공개 전환으로 알린 마지막 값을 저장. 신고 검토 다시 공개 때 끔이면 `HIDDEN_SETTING`으로, 새 공유물은 끔이면 `HIDDEN_SETTING`으로 저장 | ERD 설계에는 없던 표. `HIDDEN_REPORT` 동안 설정을 끄면 공개 전환이 그 행을 건드리지 않아(설계대로), 나중에 다시 공개하면 설정 끔인데 `VISIBLE`이 됨. learning 상태만으로도 비공개를 지키려고 둠(core도 목록에서 다시 거름) |
| 검토 전이 | `HIDDEN_REPORT`는 `REMOVED`가 아니면 숨김(`HIDDEN_SETTING`에서도), `VISIBLE`은 `HIDDEN_REPORT`에서만, `REMOVED`는 끝 상태. 같은 요청 반복은 그대로, `error_report_id`는 상태를 마지막으로 바꾼 신고 | core `moderationStatus`가 계속 숨김 우선으로 다시 보냄. 공개 전환 지연 중 신고도 숨겨야 함 |
| 공개 전환 처리 | 공개 여부 행을 먼저 잠근 뒤 학생 공유물을 일괄 전환, `changed` 수 반환 | 같은 학생의 전환 요청을 줄 세움 |
| 학생 삭제 | 그 학생 공유물에 달린 반응 → 남긴 반응 → 공유물 → 공개 여부를 시도 삭제 전에. `PROFILE`·`RECORDS` 모두 | P09 "공유물·남긴 반응 파기". 공유물이 시도·답변을 FK로 참조 |

### core 계약과 다른 점

core 코드(`CommunityClient`)가 읽는 필드는 모두 맞췄고, 아래는 더한 것이다. core 쪽 수정은 없다.

- 공유 응답: api-spec은 `{postId}`만 적었으나 `{postId, created, status}`. core는 `postId`와 HTTP 상태(201·200)만 읽음
- 공유 거절: api-spec "그 밖은 공유 안 함"을 409 `COMMUNITY_NOT_SHAREABLE`(api-spec 1.3 추가)·없는 시도 404로 정함. core는 200·201 밖을 모두 공유 안 함으로 봄
- 반응 응답: api-spec `{created}`에 `postId`·`reaction`·`reactionId` 추가, 취소는 `{…, deleted}`(core는 본문을 읽지 않음)
- 목록 `answer`: core OpenAPI 설명은 "learning 마지막 답변 content 그대로"지만 `{inputType, text, content}` 객체. core는 그대로 넘기고 web `answerText`는 `text`를 읽으므로 화면은 맞음. core OpenAPI `CommunityPost.answer` 설명 문구 갱신은 core 몫으로 남김
- 목록 응답에 `page`·`size`, 본인·자녀 목록에 `studentId`, 원문 조회에 `createdAt`(core는 읽지 않음)

### 이슈와 다른 점

- 마이그레이션 번호: #385(24장)가 V11(준비)·V12(최종)를 쓰고 먼저 병합해 이 변경은 V13

- 이슈에 없던 것: `community_visibility` 표(위 결정), 반응 ID(#389 대비), 공유 때 표현 필터 재검사, learning 실제 응답 계약 검사와 ci-contracts 단계
- ERD 4.4 구현 예정 표에서 커뮤니티 두 행을 4.3.1 Mermaid로 옮김. 4.4 절 번호는 주간 테마 링크(state-diagram·이 보고서 1장) 때문에 그대로 둠

### 한계

- core와 실제로 붙인 공유 → 열람 → 반응 → 신고 숨김 흐름, web 화면 연동은 확인하지 않음(이슈 완료 조건 둘째 항목)
- `HIDDEN_REPORT` 동안 받은 공개 전환은 `community_visibility`에만 남고 상태는 바꾸지 않음. 검토가 `REMOVED`로 끝나면 그대로 끝 상태
- 공유 시점의 공개 여부는 core가 판정하고, learning `community_visibility`는 core 공개 전환 호출이 실패하면 늦을 수 있음. 이때 새 공유물이 `HIDDEN_SETTING`으로 저장될 수 있고 다음 설정 저장 때 복원됨(비공개 쪽으로 어긋남)

### 검증

- learning `./gradlew test bootJar` 통과: 366건, 실패 0(develop #385 병합 뒤), bootJar 생성. 로컬 JDK가 8이라 `eclipse-temurin:21-jdk` 임시 컨테이너와 Testcontainers로 실행. 새 `CommunityTest` 7건, `CommunityRulesTest` 3건, 확장한 `StudentDeletionTest` 4건(공유물·주고받은 반응·공개 여부까지 삭제) 포함
- 루트 계약 테스트 `python -O -m unittest discover -s scripts/tests`: 192건 OK
- ci-db-schema 방식 `scripts/check_db_migrations.py`(일회용 PostgreSQL 17.11 + Flyway 컨테이너): PASS
  - learning V1~V13 적용, 28개 테이블·240개 컬럼이 ERD와 일치, 음성 사례 39건 거부
  - 반복 마이그레이션에서 변화 없음
- `scripts/validate_learning_community_contracts.py`: `CommunityTest` 실제 응답 10종이 learning OpenAPI와 일치하고, core `CommunityClient`가 읽는 필드도 있음
- 확인하지 않은 것: 실제 core와 붙인 흐름, web 화면, 원격 CI
