# learning 학습 서비스

계약은 [API 명세](../design/api-spec.md) 2.2·3.1~3.8·4.1과 [learning OpenAPI](../../contracts/openapi/learning-service.yaml), 판정 상태는 [상태 다이어그램](../design/state-diagram.md) 3장.

## 1. 미션 조회 (#22)

- 학생 확인: `X-User-Role: STUDENT`이고 `X-Student-Scope`에 학생 1명일 때만(`UserContext.requireSelfStudent()`, 다른 학생 Controller도 공용). 학년 `grade`(3~6)·시연 여부 `demo`(기본 false)는 core가 붙임
- 학생용 객체는 `MissionView`(정답·예시 답·기준표 필드 없음). 노출 규칙은 `MissionView.isOpenTo(grade, demo)` 한 곳(학년 범위, 논술 초5~6, `demo_only`는 demo일 때만)
- 상세는 목록과 같은 범위. 비공개·범위 밖 409 `MISSION_NOT_AVAILABLE`, 없으면 404
- 수행 상태는 `MissionRepository`가 미션별 가장 최근 시도로 읽음(없으면 `NOT_STARTED`). `AttemptService`를 부르면 순환이라 Repository에서 직접
- 진행 중 시도는 시작 당시 미션 버전을 유지(P07). 목록·상세는 현재 공개 버전
- 2026-11-06 결정([서비스 기획 방향](planning.md#3-서비스-기획-방향-리텐션일일-리포트-2026-11-06-p20p25)): 학생 기본 경로가 주간 테마 당일 문제로 바뀌고 이 목록은 추가 문제(`EXTRA`) 고르기로 쓴다. 테마·요일 검사는 learning `theme`(24절, [API 2.11](../design/api-spec.md), [ERD 4.2.1](../design/erd.md#421-주간-테마-p23-385-v11v12))

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
| 초안 저장 잠금 | 시도 행을 잠그고(`lockOwned`) 열림 확인 후 저장 | 마무리·돌아보기와 같은 순서로 직렬화([점검 기록 B14](testing-ci.md#5-develop-종합-점검-원장-16회차)) |
| 쓰기 막는 때 | `COMPLETED` 시도의 초안·생각 열기는 409 `ATTEMPT_CLOSED`. 마무리 뒤 막는 것은 답변 제출 | state-diagram 3.2, P04 |
| 생각 열기 | 열지 않은 질문을 `seq` 순으로, 다 열면 마지막 질문 반복, 열 때마다 `hint_usage` 기록. 질문 없는 미션 404 | 도움 이용 집계 근거(P08) |
| 하루 미션 한도 | learning은 확인하지 않음 | core 책임. #210 결정으로 Redis가 아닌 PostgreSQL(`mission_daily_usage`, 무료 하루 1개 #387 구현 → 2026-11-10 개정 core #485부터 무료 테마 문제는 한도 없음·무료 `EXTRA` 재활성 때만). 무료 테마 문제 주 5개는 learning 누적 공개 규칙(#484) |

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
- P20·P21([서비스 기획 방향](planning.md#3-서비스-기획-방향-리텐션일일-리포트-2026-11-06-p20p25)): 돌아보기 저장(학습 완료) 성공 뒤 core가 포인트를 적립하고(core #389 구현, 미션은 시도 상세로 확인), 커뮤니티 공개가 켜진 학생이면 learning에 공유를 요청한다(#388 구현, 학생·미션당 1개, 처음 마무리한 시도의 마지막 답변). 시작 요청 `context`가 `THEME_DAY`면 신규 시도만 요일 검사

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

#244: 기록 응답 `judgment.corrected`를 추가(최신 정정이 있으면 true). 정정은 결과만 바꾸고 요소는 원판정 그대로라 report가 요소 지표에서 뺄 때 씀. 전체 내용은 [support-admin](core-gateway.md#21-신고문의공지도움말-46) 「정정 영향 판정과 표시」

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

core가 자녀 삭제·탈퇴를 확정하면 `student.deleted`를 보내고, learning·report 두 곳의 완료 보고가 모두 와야 삭제 요청이 `COMPLETED`가 됨(api-spec 5.6). learning에 소비자가 없어 삭제·탈퇴가 끝나지 않던 문제([점검 기록 B3](testing-ci.md#5-develop-종합-점검-원장-16회차))를 고침. 클래스 다이어그램 4.3 이름(`StudentDeletedConsumer`·`StudentDeletionService`·`CoreClient`·`DeletedStudentRepository`·`ProcessedEventRepository`·`AttemptService.deleteByStudent`) 그대로, DB 변경 없음(큐는 `definitions.json`, 표는 V3)

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

[점검 기록](testing-ci.md#5-develop-종합-점검-원장-16회차) A3: learning domain 6개 파일이 `HttpStatus`(5개)·Jackson `@JsonInclude`(`Support.kt`)를 참조해 아키텍처 2.1 "Domain은 프레임워크 의존 금지"와 다름. 확인 필요 항목(domain의 HttpStatus 허용 여부)은 허용하지 않는 쪽으로 정함(core #168과 같은 결정 대상). 설계 문서의 원칙은 그대로이고, API 응답(code·status·본문)은 바뀌지 않음

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| domain 오류 | domain은 `BusinessException(ErrorKind.CONFLICT, code, …)`처럼 오류 종류(`INVALID`·`CONFLICT`·`UNPROCESSABLE`)만 넘기고, 400·409·422 변환은 `_common/exception`의 `BusinessException` 보조 생성자가 함. domain 5개 파일 10곳(`AnswerContent`·`Attempt`·`Judgment`·`Mission`·`Period`, `MissionPublishIncompleteException` 포함) | 아키텍처 2.1(domain 의존 금지)·2.3(예외 → 응답 변환은 `_common/exception`), 이슈 "새 계층·공통 라이브러리 만들지 않음" |
| 별도 domain 예외를 두지 않은 이유 | 같은 code(`ATTEMPT_CLOSED`·`ANSWER_INCOMPLETE`·`REVEAL_CONDITION_UNMET`·`JUDGMENT_STATE_CONFLICT`)를 service도 던짐. 예외 타입을 나누면 처리기·테스트 약 40곳이 "어느 층에서 던졌나"에 따라 갈리고, 기존 테스트가 하던 HTTP 상태 확인을 잃음 | 이슈 완료 조건 "오류 응답 code·status 변화 없음"을 기존 테스트 그대로 검증 |
| 신고 대상 응답 | `@JsonInclude(NON_NULL)`을 domain `SupportTarget`에서 새 응답 DTO `SupportTargetResponse`(`judgment/controller/SupportResponses.kt`)로 옮김. `SupportController.target`이 변환해 반환 | 이슈 해야 할 일 3, 기존 `AttemptResponses`·`MissionResponses` 방식 |

- 설계와 다른 점: 없음. class-diagram 4.2 `SupportController.target` 반환 타입만 `SupportTargetResponse`로 고침. 공통 `BusinessException` 그림(class-diagram 1장, core와 공유)은 필드가 그대로라 손대지 않음. OpenAPI 스키마 이름 `SupportTarget`은 응답 모양이 같아 그대로
- 한계: 예외 객체는 실행 중에 HTTP 상태를 들고 있음(domain 코드는 모름). 오류 종류는 지금 domain에서 쓰는 세 가지뿐이고, 새 종류가 필요하면 `ErrorKind`와 변환을 함께 늘림
- #249(11/02): 위 한계를 해소함. domain은 HTTP 상태가 없는 `DomainException(kind, code, …)`을 던지고, 상태 변환은 `_common/exception`의 `statusOf` 한 곳, 처리기·service 테스트는 `httpStatusOf`·`errorCodeOf`로 두 예외를 같게 다룸. 위 "별도 domain 예외를 두지 않은 이유"의 걱정(처리기·테스트 분리, HTTP 상태 확인 상실)을 이렇게 피함 ([#249 절](core-gateway.md#domain-예외-168249))

## 14. 공통 예외·초안 저장 경합 테스트 (#137)

[점검 기록](testing-ci.md#5-develop-종합-점검-원장-16회차) 1회차 테스트 공백의 learning 테스트 공백을 채움. 테스트만 추가했고 코드·설계·API 계약은 바꾸지 않음

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

10/29 멘토링과 11/1 결정([기획 1절](planning.md#1-1029-오프라인-멘토링-결정후속))에 따라 학생 답변(최초·보완)에 표현 검사를 넣음. 막는 답변은 저장·판정 요청 없이 `422 ANSWER_INAPPROPRIATE`. 계약은 [API 명세](../design/api-spec.md) 1.3·4.1.

### 기준과 범주

| 범주(`ExpressionCategory`) | 근거 | 처리 |
|---|---|---|
| `PROFANITY` 욕설·비속어 | 청소년 보호법 시행령 [별표 2] 2.차, 방송심의에 관한 규정 제51조 제3항 | 항상 차단 |
| `SEXUAL` 성적 표현 | [별표 2] 2.가·나·라, 같은 규정 제35조 제2항 | 항상 차단 |
| `HATE` 혐오·차별 | KISO 혐오표현 자율정책 가이드라인 제2조 | 미션 본문에 나온 말이면 허용 |
| `THREAT` 남을 향한 위협·자해 조장 | [별표 2] 2.바·사 | 항상 차단. 자기 감정 표현("죽고 싶다")은 막지 않음 |
| `PERSONAL_INFO` 연락처(휴대전화·이메일) | 유사 서비스(Roblox·Scratch)의 연락처 공유 금지(사용자 결정) | 항상 차단 |

- 응답 `title`은 "고쳐야 할 말이 있어요", `detail`은 범주별 안내. 걸린 말·원문은 응답·로그에 넣지 않음(로그는 `attemptId`·`category`만)
- [별표 2]의 나머지 항목과 약물·폭력 묘사는 글의 내용을 봐야 해서 단어로 다루지 않음(교과 답변 "담배는 몸에 해롭다"가 막히지 않게)

### 목록 출처 (`backend/learning-service/src/main/resources/answer-filter/`)

| 출처 | 결정 |
|---|---|
| [korcen](https://github.com/Tanat05/korcen) 2026판(MIT)·2023판(Apache 2.0) | 데이터·전처리 규칙만 JSON으로 옮김(`korcen.json`). 2023판은 2026판에서 빠진 `씨발`·`존나` 등 보충 |
| 국립국어원 우리말샘 Open API(CC BY-SA) | 뜻풀이가 "욕하여·비속하게 이르는 말"로 끝나는 일반어 61개 + 데이터로 확인한 7개(`urimalsaem.json`) |
| 팀 조정(`team.json`) | 뺀 패턴 18, 오탐 예외 74, 맥락 단어 `새끼`와 항상 막는 결합형 8, 철자 변형 24, 위협 14. 근거 수치 포함 |
| KISO KSS, LDNOOBW, 라이선스 없는 목록, AI Hub 윤리검증 | 쓰지 않음(학생 원문 외부 전송·라이선스·용도 제한) |

- 원칙(사용자 결정): 팀이 낱말을 지어내지 않음. 더하는 말은 출처나 측정 데이터에 실제로 나온 것만, 빼는 말은 겹치는 정상 문장 예와 횟수를 남김
- 뺀 패턴은 정상 문장과 겹치는 것(`보지`: 책을 보지, `세끼`: 하루 세끼 등). `바보`·`멍청이`는 비속어가 아닌 놀림말이라 넣지 않음
- 맥락 단어 `새끼`: 동물 새끼 뜻이 있어 미션 본문에 나오면 허용하되 결합형 8개는 항상 차단

### 검사 흐름 (`ExpressionPolicy`)

1. 대상은 학생이 쓴 칸(`AnswerContent.writtenTexts`)이고 칸마다 따로 검사. 원문과 "우회 보기"(전각 → 보통 글자, 한글 옆 영문 한 글자 → 글자 이름, 풀어 쓴 자모 → 글자) 두 글을 검사
2. 정규화(korcen 전처리): 주소 지우기 → 소문자 → 비슷한 글자 → 띄어쓰기 지우기
3. korcen 범주별 치환 → 오탐 예외 지우기 → 부분 일치. 한글·자모만 둔 보기는 `시1발`을 잡으려고 추가
4. `HATE`와 맥락 단어는 같은 말이 미션 본문에 나오면 제외. 연락처는 이메일 형식과 휴대전화(구분 기호·한글 숫자 정규화)
5. 위치: `AnswerService.submit`의 누락 검사 다음·되묻기 연결 검사 전. 외부 호출 없음

막지 않는 우회: 영문 자판 위치대로 친 글(`qudtls`, 정상 영문 오탐이 훨씬 많음), 말로 쓴 이메일·집 전화번호, 정상 낱말과 겹치는 욕(`졸라`: 엄마를 졸라서).

### 측정

| 데이터 | 결과 |
|---|---|
| Curse-detection-data 욕설 표시 2,044문장 | 59.8% 차단(라벨에 욕 없는 모욕·비꼼이 섞임. 명시적 욕 표본은 약 94~95%) |
| Curse 정상 표시 3,781문장 | 1.3% |
| NSMC 리뷰 50,000문장 | 2.06%(대부분 실제 욕, 정상 글 오탐 약 0.1%) |
| 데모 문장 491·학생 글 함정 약 80문장 | 0 |

측정 데이터는 성인 인터넷 글이라 초중등 답변과 다르다. 데모 문장과 학생 글 함정을 `ExpressionPolicyTest`로 고정했다. 생성·측정 스크립트와 원자료는 저장소 밖.

### 결정 (11/01~11/02)

- 외부 AI 없음. 제출 전 검수 LLM도 넣지 않음: 막을 글도 LLM으로 보내게 되어 "저장·판정 요청 없이 차단"과 어긋나고 연락처가 LLM으로 넘어감 → 후속 이슈
- 서버만 검사(단어 목록을 웹 번들에 넣지 않음)
- 초안(`answer`·`memo`)과 돌아보기 글은 검사하지 않음(초안은 학생 본인만 보고 제출에 성공하면 비워짐)

### 한계·확인 필요

- 욕 없는 모욕·비꼼·돌려 말한 성적 표현·특정 친구 놀림은 단어로 못 막음
- 낱자 `ㅗ`는 korcen 손가락 욕 패턴이라 낱자를 섞어 쓴 글이 걸림
- 초안 자동 저장·돌아보기 글에는 걸리는 말이 남을 수 있음
- 학생 자기 감정 표현("죽고 싶다")의 보호자 알림 여부는 별도 기능으로 검토 필요
- korcen의 MIT·Apache는 코드 라이선스라 단어 데이터의 출처까지 보증하지 않음

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

기준표 요소 code가 미션마다 자유 값이라 미션이 달라지면 같은 요소인지 알 수 없었다. 요구사항 FBF-38·FAC-09·기획서 5.3(4)(같은 유형 미션끼리 요소 비교)를 채우려고 표준 코드를 정했다. 구현은 #344·#353(learning), #356(web).

### 결정 (11/03)

| 항목 | 결정 | 근거 |
|---|---|---|
| FAC-09 "같은 기준표" | 유형별 평가 요소로 해석 | FAC-09가 "유형/학년군"을 함께 적음 |
| 요소 3종류 | 유형 공통(표준 코드)·성취기준 고유(`e`+숫자)·정답(`ANSWER_KEY`·`FINAL_ANSWER`) | 기획서 5.3(2), 새 컬럼 없이 `FINAL_ANSWER` 선례 |
| 공통 설명 | 표준 코드마다 한 줄 정의, 미션 요소 설명은 그 구체화 | 판정 프롬프트는 그대로(LLM은 요소 이름·설명으로 판정하고 code는 받지 않음) |
| 분석하기 | 기획서 2요소 그대로 | 블룸 개정 분류에서 분류·비교는 "이해", "분석"은 부분 사이의 관계까지. 비교·분류는 기초 사고력 쪽(후속) |
| 돌아보기 | 바뀐 생각·바뀐 까닭·생각 과정/경험과 연결 **[기획서 변경]** | 시드가 모두 이 구성. 기획서 ① "자기 생각 과정"은 미션 질문이 묻지 않아 세 번째 요소에 넣음 |
| 충족률·보완률 분모 | 필수 요소만, 들어가면 좋은 생각은 따로 **[기획서 변경]** | 분모에 넣으면 정답인데 충족률이 100%가 아님 |
| 정답 예약 코드 | `ANSWER_KEY` 하나로 고르기·순서·분류 | 세 입력 방식은 규칙 판정. 이름은 판정 출처 `source_type`과 같게 |
| 따져 보기 논술 | `EVALUATE_CLAIM`·`EVALUATE_EVIDENCE`·`EVALUATE_PERSPECTIVE` 필수 | 기획서 5.3(3) 논증 요소 충족률 |
| 기록 응답 필드 | 공통 `Element`에 `code`·`goodThought` | report 지표에 빠진 것은 이 둘뿐 |
| 검사 위치 | 저장 때 code 모양 400, 게시 때 유형·입력 방식 맞춤 422 `rubric.elements.code` | 저장 때는 미션 유형을 모름(미션 내용 `PATCH`와 기준표 `PUT`이 따로) |
| DB CHECK | 두지 않음 | 이전 기준표 버전은 불변이라 자유 code가 남고, 미션 유형이 다른 테이블에 있음 |

### 표준 코드와 근거

| 유형 | 코드 | 요소 | 근거 |
|---|---|---|---|
| 분석하기 | `ANALYZE_RELATION` | 원인·특징·관계 | 기획서 5.3(1) ①, 블룸 "분석" |
| | `ANALYZE_REASON` | 까닭 잇기 | 기획서 5.3(1) ② |
| 따져 보기 | `EVALUATE_CLAIM` | 주장 | VALUE Critical Thinking "Student's position" |
| | `EVALUATE_EVIDENCE` | 근거 | 같은 루브릭 "Evidence" |
| | `EVALUATE_PERSPECTIVE` | 다른 관점·반론 | 같은 루브릭 "Others' points of view" |
| 새로 만들기 | `CREATE_NEW` | 새로운 생각 | VALUE Creative Thinking "Innovative Thinking" |
| | `CREATE_WHY` | 왜 나은지 | 같은 루브릭 "Solving Problems" |
| | `CREATE_CONNECT` | 연결·변형 | 같은 루브릭 "Connecting, Synthesizing, Transforming" |
| 문제 해결하기 | `SOLVE_DEFINE` | 문제 정하기 | VALUE Problem Solving "Define Problem" |
| | `SOLVE_PLAN` | 방법 세우기 | "Identify Strategies"·"Propose Solutions" |
| | `SOLVE_CHECK` | 결과 확인 | "Evaluate Outcomes" |
| 돌아보기 | `REFLECT_CHANGE` | 바뀐 생각 | 기획서 5.3(1) ②, VALUE Lifelong Learning "Reflection" |
| | `REFLECT_REASON` | 바뀐 까닭 | 시드 M05·M10·M15 |
| | `REFLECT_CONNECT` | 생각 과정·경험과 연결 | 기획서 5.3(1) ①, "Reflection: Reviews prior learning" |

- 블룸은 생각 방식의 분류이고 VALUE는 대학생용이라, 학년 수준은 미션마다 연결한 성취기준이 맞춤
- 뺀 VALUE 항목: Curiosity·Initiative 등(긴 기간의 행동이라 답 구절로 판정 어려움), Transfer(돌아보기의 다짐은 실제 적용이 아님)
- 시드 20문항 요소 56개: 표준 44·정답 7·고유 5. 같은 행의 code만 바꿔 지난 판정은 `rubric_element_id`로 이어짐
- `rubric_element.code` 주석에 `A|B` 모양을 쓰면 `verify_db_schema.py`가 CHECK 허용 값으로 읽어 CI가 실패함(`·`로 구분)

### 한계

- #262 전에 만든 미션의 자유 code는 미션을 넘는 지표에서 빠짐
- 표준 요소는 사람 검증(P11) 전이라 AI 판정은 시범 표시
- 후속: 기초 사고력(`mission_version.basic_skills`) 연결, 성취수준 문장 연결

## 21. 성취기준·성취수준 표와 미션 초안 흐름 문서·계약 (#336)

기획서 6.2(미션 제작 방법)·5.3(2)와 요구사항 FAD-03·FAD-08·FAC-18·FFJ-10·FBN-09가 설계에 없던 것을 반영했다. 구현은 learning #353(22절)·ai #354([ai 9장](ai.md#9-미션-초안-생성자동-검사-336-설계-354-구현))·core #355(23절)·web #356([frontend 12절](frontend.md#12-356-관리자-성취기준-고르기성취수준-단계미션-초안-화면-2026-11-09)).

### 결정 (11/04)

| 항목 | 결정 | 근거 |
|---|---|---|
| 성취기준 표 범위 | 2022 개정 현행 765개 전체(초1~중3) | FAD-08, 학년 확장. 데이터가 작음 |
| 이용 조건 | 고시 원문(성취기준 문장)은 넣고, 평가원 성취수준 문장은 이용 조건 확인 전까지 넣지 않음 **[팀 확인 필요]** | 저장소가 공개라 시드에 넣으면 공개됨 |
| 2026.1 일부개정 25개 | 넣지 않음 | 12개 코드가 현행과 코드는 같고 문장이 달라 코드를 키로 쓸 수 없음. 2028년 적용, 초1~2만 |
| 생성 방식 | 비동기: 요청은 `GENERATING`으로 저장하고 202, learning 주기 작업이 생성 1회씩 반복 | 동기 요청 안에서 재시도까지 끝낼 수 없음 |
| 성취수준 단계 | 성취기준마다 관리자가 고르고 `achievementStandards`(문자열 배열)는 그대로 둔 채 `achievementLevels`를 따로 둠 | 배열을 객체로 바꾸면 web·OpenAPI·테스트가 깨짐 |
| 시드 20문항 | `source = MANUAL`, 성취수준 단계·요소 `standardCode`는 비우고 APM 검수 때 채움 | 추측으로 채우지 않음 |
| "행동" | 칸을 두지 않고 검토 항목으로 | 현행 765개 중 79%가 동작을 여러 개 이어 값 하나로 정하기 어려움 |

### 설계에서 정한 것

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 검사 분담 | ai: 필수 항목·질문 길이·정답·금지어·예시 답 노출. learning: 성취기준 실재·요소 code 규칙·`standardCode`·입력 방식 모양 | 각자 가진 코드 재사용 |
| 반복 위치 | ai는 호출 1번에 생성 1회, 반복은 learning | ai 안에서 3회 반복하면 learning→ai 대기를 넘음 |
| 서킷 | learning 초안용 ai 호출은 별도 서킷 `ai-mission-draft` | 초안 실패가 학생 판정을 막지 않게 |
| 실패 상태 | 상한에서 마지막 실패가 검사면 `CHECK_FAILED`, AI 호출이면 `FAILED` | FAC-18 |
| 생성 방식 기록 | `mission.source`(`MANUAL`·`LLM_DRAFT`), 초안 연결은 `mission_draft.mission_id` 한쪽 | 미션이 처음 만들어진 방식이라 버전마다 바뀌지 않음 |
| 성취기준 FK | 두지 않고 게시 검사 | jsonb 배열. 교육과정이 바뀌어 표를 다시 넣을 때 지난 버전이 막히지 않게 |
| 다시 만들기 | 새 초안 요청(실패한 초안을 되살리지 않음) | 시도 기록이 초안마다 남음 |
| 장면 | 초안의 `sceneNote`는 초안에만 두고 미션에 저장하지 않음 | |
| 표준 요소 입력 | learning이 그 유형 코드·공통 설명을 ai에 보냄 | 코드 목록을 learning 한 곳에만 |

### 기준안 (확정 필요)

| 값 | 기준안 | 정할 사람 |
|---|---|---|
| 생성 시도 상한 | 3회(첫 생성 포함) | 김동섭(P19) |
| 학년별 질문 길이 | 전 학년 200자(시드 질문 길이 67~193자) | 김동섭(P19, FAD-06) |
| 생성 주기 / 리스 | 10초 / 90초 | learning 구현 담당 |
| 채택 때 요소 배점 | 1 | APM |

성취기준 표(`standards_2022.csv`): 현행 학년군별 초1~2 100·초3~4 162·초5~6 169·중1~3 334. 성취수준 단계는 초 3단계(A~C), 중 5단계(A~E). 원자료 코드는 대괄호 포함이지만 표와 시드는 대괄호 없이 저장.

한계: 성취수준 문장을 넣기 전에는 요소·초안을 성취기준 문장으로만 구체화(이용 조건이 확인되면 `levels`만 채우면 됨). 범위 밖은 시범 풀이 기록(FAR-09), 요소 기반 추천(FBF-38), 리포트의 연결 성취기준 표시.

## 22. 성취기준 표·미션 초안 구현 (#353)

21절 설계의 learning 몫. V10 `achievement_standard`·`mission_draft`, `mission.source`, `mission_version.achievement_levels`, `rubric_element.standard_code`. 시드 `db/seed/achievement_standards.sql`(765행, 코드가 키라 다시 넣으면 덮어씀).

### 결정

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 채택 미션 칸 | 교과는 첫 성취기준의 교과, 입력 틀은 입력 방식별 고정 틀, 장면 그림·단위는 비움 | 초안 출력에 `subject`·`inputTemplate`·`answerUnit`이 없음 |
| learning 검사 | 채택할 미션·기준표를 게시 검사에 그대로 넣고 누락을 `ELEMENT_CODE`·`STANDARD_CODE`·`SHAPE`로 바꿈 | 채택한 초안이 검토만 거치면 게시 규칙을 통과 |
| 성취기준 학년군 검사 | 미션 학년 범위가 고른 성취기준 각각의 `grade_band` 안. 초안 요청 400, 게시 422 | 초3 미션에 `6국…`을 골라도 생성·게시되던 문제 |
| 다음 생성의 이전 실패 | 지금까지 모든 시도의 실패 사유 전달 | 앞에서 고친 문제가 다시 나오지 않게 |
| 한 주기 생성 수 | 레플리카마다 주기(10초)에 초안 1개. 점유는 `FOR UPDATE SKIP LOCKED` + 조건 재확인 UPDATE | |
| 미션 초안 시간 (P12 예외) | ai LLM 60초 1회·마감 63초, learning ai 클라이언트 대기 70초(`app.mission-draft.ai-read-timeout`). 생성 리스 90초 안 | 논술 초안이 15초 제한에 막혀 모두 `FAILED`였음. 실측 15~31.7초. 주기 작업이라 기다리는 사람이 없음 |
| 스케줄러 스레드 | `spring.task.scheduling.pool.size: 3` | 기본값 1이면 초안 생성 동안 고착 판정 탐지·이벤트 정리가 밀림 |
| `mission.source` SQL DEFAULT | 두지 않고 V10에서 기존 행을 채운 뒤 NOT NULL | ERD "DEFAULT 없음" 규칙 |

### 한계

- **배포 순서**: ai를 먼저 배포. learning이 먼저 나가면 초안 요청이 AI 호출 실패 3회로 `FAILED`
- **성취기준 시드를 먼저 넣어야 게시 가능**: 게시 검사가 성취기준 표를 읽으므로 V10 적용 뒤 시드를 넣기 전에는 모든 미션의 게시가 막힘
- **대괄호 성취기준 코드**: `[6국01-02]`처럼 넣은 미션은 표에 없어 게시가 막힘(다시 골라야 함)

테스트: `MissionDraftServiceTest`, `MissionDraftConcurrencyTest`(레플리카 4곳 동시 생성 1회), `DemoSeedPublishTest`.

## 23. core 성취기준·미션 초안 프록시와 사용량 MISSION_DRAFT (#355)

21절의 core 몫.

- 공개 경로 `GET /admin/achievement-standards`, `POST·GET /admin/mission-drafts`, `GET …/{draftId}`, `POST …/adopt`·`…/discard` → learning `/internal/admin/…` 같은 경로(CONTENT)
- 컨트롤러는 새 `AdminMissionDraftsController`. `AdminMissionsController`에 넣으면 `test_admin_missions_contract`의 경로 대조가 흐려짐
- 감사: 요청·버리기는 `target_type = MISSION_DRAFT`·응답 `draftId`, 채택의 결과 감사는 응답 `missionId`(`target_type = MISSION`, detail `draftId`). action `MISSION_DRAFT_{REQUEST,ADOPT,DISCARD}` + `_REQUESTED`·`_SUCCEEDED`·`_REJECTED`·`_UNKNOWN`
- 응답에 초안·미션 ID가 없거나 다르면 503 `LEARNING_INVALID_RESPONSE` + `_UNKNOWN`, 다시 부르지 않음(결과를 모르는데 다시 부르면 초안이 두 번 생길 수 있음)
- learning `VALIDATION_FAILED`·`NOT_FOUND`·`CONFLICT`·`FORBIDDEN`은 기존 허용 목록 그대로 전달하고 공급자 문장은 버림
- 쿼리 검사: core는 `page`·`size`·초안 `status`·문자 길이만, `gradeBand`·`subject`·`q` 값은 learning이 검사(학년군 이름 목록을 한 곳에만)
- 사용량 `MISSION_DRAFT`를 core `CallType`·이벤트 스키마·OpenAPI·ERD·scoring 발행 목록에 ai와 같은 순서로 추가(V28)
- 계약 지문 파일은 그대로 두고 테스트에서 승인 변경만 빼고 비교(지문 파일을 다시 만들면 다른 변경도 묻힘)
- DLQ: ai 배포 뒤 이 변경 전까지 나온 `MISSION_DRAFT` 사용량 메시지는 DLQ에 있음. 다시 넣으면 기록됨(`event_id` UK)

테스트: `AdminOperationsIntegrationTest`, `scripts/tests/test_admin_mission_drafts_contract.py`.

## 24. 주간 테마·요일 문제·되돌아보기 (#385)

P23의 learning 몫. 2026-11-10 개정(#483: 누적 공개·토요일까지 풀기·일요일 닫힘·즉시 엔딩·당일 풀이/개근/주간 완주)은 learning #484에서 다루며, 아래 요일 열림 규칙은 #385 구현 당시 기준이다. core 몫은 [core 18절](core-gateway.md#18-무료-테마-주-5문제추가-문제-프리미엄-전용프리미엄-일요일당일-풀이주간-완주-포인트-485-2026-11-10).

구성: V11·V12(`weekly_theme`·`weekly_theme_version`·`weekly_theme_day`·`theme_review_view`, `attempt.context`·`theme_id`·`theme_week_start`), `theme/` 패키지, 학생 `/internal/students/{id}/weekly-theme…` 3경로, 관리자 `/internal/admin/weekly-themes…` 7경로. 요일 판정용 `Clock.system(Asia/Seoul)` 빈.

### 결정

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 게시 중 수정 | 미션과 같은 버전 방식(`current_`·`published_`·`review_version_id`). 학생은 게시본, 관리자는 현재본, 재게시 때 교체 | 상태만 두면 수정하는 순간 학생 화면이 바뀜 |
| 학년군·주 위치 | 테마 행(버전 밖). 게시 중 변경은 409 | 게시 부분 UK `(grade_band, week_start)` |
| 검토·승인 | 별도 `/review` 경로 없음. 검토 요청한 버전이 현재본일 때의 게시가 승인. 검토 중 수정은 `DRAFT` | core가 7경로만 프록시 |
| 학년군 검사 | 미션 게시본이 학년군 전체를 덮어야 함. 초3~4는 논술 불가, 시연 전용 제외 | 학년군 안 어느 학생에게나 문제가 열려야 함 |
| 오류 코드 | 전이 불가 409 `CONFLICT`, 게시 검사 422 `WEEKLY_THEME_PUBLISH_INCOMPLETE` + `errors:[{code, message}]`(6종: `DAYS_INCOMPLETE`·`MISSION_NOT_PUBLISHED`·`MISSION_DEMO_ONLY`·`GRADE_BAND_MISMATCH`·`THINKING_TYPES`·`WEEK_ALREADY_PUBLISHED`) | 웹이 `errors[].message`를 그대로 표시 |
| 이번 주 테마 | 그 주 게시본, 없으면 이전 최근 게시본(`reused`). 학년군에 게시 테마가 없으면 404 | P23 |
| 시작 순서 | 진행 중 시도 반환(검사 없음) → 미션 공개·범위 → 테마 검사 | 자정이 지나도 이어하기 |
| `THEME_DAY` | 이번 주 테마의 오늘(KST) 요일 문제만. 아니면 409 `THEME_DAY_CLOSED` | #484에서 누적 공개로 바뀜 |
| `THEME_REVIEW` | 그 주 그 문제 `THEME_DAY` 시도를 마무리했을 때만. 아니면 409 `THEME_REVIEW_NOT_ALLOWED` | |
| 개근(칸 `completed`) | 월~금 다섯 문제 각각 그 요일(KST) 안에 학습 완료 | 금요일 문제를 토요일 01시에 끝내면 개근 아님. 주간 완주(`finished`)는 #484 |
| 열람 기록 | `theme_review_view` 학생·주당 1행, 다시 보내도 200(`firstViewThisWeek`만 false) | 포인트 멱등 근거 |
| 주간 요약 | `GET …/weekly-theme/summary?weekStart`. 테마는 그 주 학생 테마 시도에서 정하고 없으면 `NO_RECORD` | report는 학년군을 모름 |
| 날짜 기준 | 조회·열람은 core가 넘긴 `date`, 시작 검사는 learning `Clock` | 둘 다 KST 오늘 |

- ERD 설계와 달리 `weekly_theme_version` 테이블을 더하고 제목·소개·요일 문제를 버전으로 옮김. 순환 FK는 `DEFERRABLE INITIALLY IMMEDIATE`
- `weekly_theme.week_start` 월요일 CHECK. 학생 응답 `days[]`·`review.missions[]`에 `title`, 관리자 응답에 `version`·`publishedVersion`·`reviewRequested`

### 한계

- **테마 미션 공개 중단**: 게시 테마의 미션이 공개 중단되면 그 요일 신규 시작은 409 `MISSION_NOT_AVAILABLE`
- **다른 컨텍스트 진행 중 시도**: 같은 미션에 `EXTRA` 진행 중 시도가 있으면 `THEME_DAY` 요청도 그 시도를 원래 `context`로 돌려줌. 그 시도는 요일 상태·개근에 들어가지 않음
- **주 중간 게시·중단**: 그 주 테마가 바뀜. 시도에는 당시 `theme_id`를 저장
- **데모 테마 시드 없음**: 데모 미션은 학년 하나씩이라 학년군 테마를 게시할 수 없음. 확인할 때는 DB에서 학년 범위를 넓힘
- MyBatis 세션 캐시라 한 트랜잭션에서 같은 조회를 다시 하면 앞 결과를 씀(테스트 작성 시 주의)

테스트: `WeeklyThemeServiceTest`, `WeeklyThemeAdminServiceTest`, `AttemptThemeStartTest`, `scripts/tests/test_weekly_theme_contract.py`(core ↔ learning OpenAPI 3자 대조).

## 25. 커뮤니티 공유물·반응·열람 검사 (#386)

P20의 learning 몫. 공개 설정·`COMMUNITY` 동의·신고·작성자 별명은 core([auth-account 10절](auth-account.md#10-커뮤니티-공개-설정과-community-선택-동의-388-p20)).

구성: V13 `community_post`(UK `(student_id, mission_id)`)·`community_reaction`·`community_visibility`, `community/` 패키지(내부 경로 7개).

### 결정

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| "마무리"의 뜻 | 공유·열람·반응 모두 학습 완료(`attempt.status = COMPLETED`, 돌아보기 저장) 기준 | FN-RET-02 |
| 공유 대상 시도 | 그 미션을 처음 학습 완료한 시도만. 아니면 409 `COMMUNITY_NOT_SHAREABLE`. 공유물이 이미 있으면 그 공유물을 200 | 설정을 끈 채 처음 완료하고 나중에 켠 뒤 다시 풀어도 공유하지 않음 |
| 공유 답변 | 그 시도의 마지막 답변. 응답 `answer`는 `{inputType, text, content}`. 답변 행을 조인하고 복사하지 않음 | 고르기·분류는 `content`만으로는 ID라 읽을 수 없음. 삭제 때 한 곳만 지움 |
| 표현 필터 | 공유 때 지금 `ExpressionPolicy`로 다시 검사, 걸리면 공유 안 함 | 제출 뒤 단어 목록이 바뀔 수 있음 |
| 열람 목록 | `VISIBLE`만, 열람자 본인 공유물 제외, 반응 수 없음, `ORDER BY md5(id || seed), id` | 같은 seed면 같은 순서·쪽 나누기 유지(무작위·순위 없음) |
| 반응 ID | `UUID.nameUUIDFromBytes("community-reaction:{postId}:{studentId}:{reaction}")` | core 포인트 사건 키와 1:1이라 껐다 켜서 적립을 반복할 수 없음 |
| 반응 검사 순서 | 공유물 잠금 → `VISIBLE` 아니면 404 → 본인 글 409 → 미완료 403. 취소는 상태와 무관하게 허용 | 숨긴 글에 남긴 내 반응을 지울 수 있어야 함 |
| `community_visibility` 표 | core가 알린 마지막 공개 여부를 저장. 신고 검토 다시 공개 때 끔이면 `HIDDEN_SETTING` | `HIDDEN_REPORT` 동안 설정을 끄면 나중에 다시 공개할 때 `VISIBLE`이 되는 문제 방지 |
| 검토 전이 | `HIDDEN_REPORT`는 `REMOVED`가 아니면 숨김, `VISIBLE`은 `HIDDEN_REPORT`에서만, `REMOVED`는 끝 상태 | |
| 학생 삭제 | 공유물에 달린 반응 → 남긴 반응 → 공유물 → 공개 여부를 시도 삭제 전에 | P09. 공유물이 시도·답변을 FK로 참조 |

- api-spec보다 응답에 더한 필드: 공유 `{postId, created, status}`, 반응 `{…, reactionId}`, 목록 `page`·`size`. core는 읽는 필드만 사용
- 한계: core 공개 전환 호출이 실패하면 `community_visibility`가 늦을 수 있음(새 공유물이 `HIDDEN_SETTING`으로 저장될 수 있고 다음 설정 저장 때 복원, 비공개 쪽으로 어긋남)
- 테스트: `CommunityTest`, `CommunityRulesTest`, `scripts/validate_learning_community_contracts.py`(실제 응답 10종 ↔ OpenAPI)

## 26. 주간 테마·커뮤니티 실서버 확인 (#424, 2026-11-10)

local kind에서 core·learning·ai·report를 실제로 붙여 확인. 데모 미션 학년 범위는 kind DB에서만 5~6으로 넓힘(저장소 시드는 그대로).

- 확인: 테마 작성 → 검토 요청 → 게시, 학생 요일 상태(`intro`는 월요일에만 채움), 오늘 문제 시작 → 답 → 실제 AI 피드백 → 마무리 → 돌아보기, 공유(보호자 COMMUNITY 동의 + 친구 공개), 다른 학생 열람(`seed` 쿼리 필요), 반응, 신고 즉시 `HIDDEN_REPORT`, 동의 철회 뒤 "다시 공개"로 처리해도 `HIDDEN_SETTING` 유지
- 미확인: 주말 되돌아보기 열람, 월~금 개근

## 27. report 집계 입력 판정 모델 점수 (#478, 2026-11-10)

리포트 설명(에픽 #473)의 대상 선정 입력으로 report가 답변별 M2 점수를 받는다. 저장값(`judgment.model_scores`)을 그대로 넘기며 새 컬럼은 없다.

| 항목 | 결정 | 이유 |
|---|---|---|
| 노출 조건 | `GET /internal/records/students/{id}/attempts?includeModelScores=true`일 때만 `answers[].feedback.judgment.modelScores` 키를 넣음 | 같은 경로를 core 대시보드와 ai 분석 대화 도구도 읽음. 늘 넣으면 점수가 학부모 화면과 외부 LLM 요청에 섞임 |
| 호출 권한 | `X-User-Role: SYSTEM`만, 그 밖은 `403 FORBIDDEN` | learning에서도 한 번 더 막음 |
| 값 | 저장 JSON 원문(`{m2, m1, skipped}`), M2를 부르지 않았으면 `null`. 처리 중·실패 답변은 키 없음 | 점수 해석·선정은 report 몫 |

`daily-attempts`·기록 상세·evidence에는 넣지 않는다. 테스트: `RecordControllerTest`, `RecordServiceTest`.

## 28. 교육과정 지식 RAG 계약 고정 (#464, 에픽 #463, 2026-11-11)

하위 이슈 #465~#471이 서로 기다리지 않도록 형식·테이블·내부 API·샘플·가짜 구현을 먼저 정했다. 모든 값은 **기준안(팀 확인 전)**이다. ai 쪽(C6·C7·모델·가짜)은 [ai 15장](ai.md#15-교육과정-지식-rag-계약-464-2026-11-11), 실제 추출은 [knowledge](knowledge.md).

| 계약 | 위치 |
|---|---|
| C1 추출 레코드 | `scripts/knowledge/schema/curriculum-record.schema.json` |
| C2 조각·판 테이블, C3 관계 테이블, C9 판 규칙 | [ERD 4.5](../design/erd.md#45-교육과정-지식-rag-463-계약-464-구현-466) |
| C4 관계 확인 파일 | `scripts/knowledge/schema/relation-review.schema.json` |
| C5 learning 지식 내부 API | [api-spec 4.1.2](../design/api-spec.md#412-교육과정-지식-내부-api-463-계약-464-c5-구현-469), learning OpenAPI `/knowledge/*` |
| C8 평가셋 | `scripts/knowledge/schema/eval-record.schema.json` |
| 샘플 | `scripts/knowledge/samples/`(레코드 215줄, 확인 파일 29행, 평가셋 9줄) |

| 항목 | 결정·기준안 | 근거 |
|---|---|---|
| 영역 레코드 나누기 | `scope`: 국어·수학·도덕 `BOTH`, 사회·과학은 내용 체계 영역(`CONTENT_SYSTEM`)과 성취기준 단원(`STANDARD_GROUP`)을 따로 | 원문에서 사회·과학은 영역과 단원이 다르고 고려 사항은 단원마다 있음 |
| 내용 요소 학년·학기 | C1 레코드에 두지 않고 적재 때 확인된 covers로 계산 | covers는 사람 확인 결과라 추출 단계에서 알 수 없음 |
| 조각 칸 추가 | `knowledge_chunk.record`(C1 원본), `knowledge_dataset.embedding_model`·`embedding_dimensions` | 다른 모델·차원 벡터를 막으려고 |
| 선수 FK | `prerequisite_code`는 조각 FK 없이 성취기준 표 코드 검사 | 앞 학기 선수가 저장소 범위 밖일 수 있음 |
| 대체 사유 | 근거 없음은 200 `reason`(`NO_ACTIVE_DATASET` 등 5개), 오류는 400·409·500 | "근거 없이 기존 방식"을 오류 처리와 구분 |
| 인증 | 내부 토큰 + `X-User-Role: SYSTEM`, 학생 범위 없음 | 학생 정보를 받지 않음 |
| `learned` | 개념 1~20개 묶음 요청 | 테마 검사가 낱말 여러 개를 한 번에 확인 |
| 판 이름 | `kn-YYYYMMDD-NN` | 같은 날 여러 번 적재해도 겹치지 않게 |
| 구현 전 표시 | OpenAPI `x-implementation-status: planned-issue-…`. 표시된 경로는 컨트롤러 대조 시험에서 제외 | #27 선례 |

- 넣지 않는 자료: 평가원 성취수준 자료, 교육청 수업-평가 자료 문장(코드↔학기 대응만 사용), 블룸·VALUE 원문·번역
- 고시 개정 확인(2026-11-11): 제2026-1호 일부개정과 제2022-33호의 초3~6 대상 교과 성취기준 331개 문장이 같음
- 시험: `scripts/tests/test_knowledge_contracts.py`

## 29. 교육과정 지식 저장소 (#466, 에픽 #463, 2026-11-11·12)

#464 계약(C2·C3·C9)대로 `learning_db`에 지식 판·조각·관계 테이블과 판 적재·활성화·제거를 만들었다. 2026-11-11 팀 결정(에픽 #463)으로 미션·테마 생성에 벡터 검색·임베딩을 쓰지 않게 되어, 지식 표는 성취기준·생각 유형 **코드 조회용 관계형 표**로 정리했다(V17).

- 테이블: learning V14 `knowledge_dataset`·`knowledge_chunk`·`knowledge_standard_semester`·`knowledge_fits`·`knowledge_prerequisite`·`knowledge_covers`. V17이 임베딩 칸(`knowledge_chunk.embedding vector(1536)`)·HNSW 인덱스·`knowledge_dataset.embedding_model`·`embedding_dimensions`를 지움
- 판 관리 API: `/internal/admin/knowledge/datasets…`([api-spec 4.1.3](../design/api-spec.md#413-교육과정-지식-판-관리-466)), 운영 스크립트 `scripts/knowledge/manage_datasets.py`
- 조회 API: #469 코드 조회(`standards?codes`, `thinking-types/{type}`)가 `ACTIVE` 판 하나만 읽음
- `vector` 확장은 관리자 bootstrap([DB 개발 가이드 8.7](db-dev-guide.md#87-learning_db-vector-확장-466)). 지금 쓰는 칸은 없지만 V14를 처음부터 적용할 때 필요

| 항목 | 결정 (동섭 2026-11-11) | 근거 |
|---|---|---|
| 관리 API 접근 | learning 내부 관리 경로 + 운영 스크립트, `SYSTEM` 역할. core 프록시·관리자 화면 없음 | 판 적재는 개발자·운영자 작업 |
| 적재 실행 | 동기 요청(스크립트가 10분까지 대기) | 실패하면 판이 `LOADING`으로 남는 C9 규칙으로 충분 |
| 임베딩 | 만들지 않음(V17, 2026-11-12 정리) | 생성은 학기 대응표·성취기준 코드 규칙으로 고름(에픽 #463 결정). 처음 구현(V14)의 `app.knowledge.embedding`·임베딩 재사용·활성화 전 임베딩 검사는 지움 |

- 활성화는 적재와 분리. 적재 때 활성 판을 `source.previousVersion`에 두고, 활성화 때 활성 판이 바뀌었으면 409
- 같은 관계 여러 행은 `reviewedAt`이 늦은 행. 이전 판에서 옮긴 관계보다 늦은 `REJECT`는 그 관계를 뺌
- `content_hash`는 판을 바꿀 때 옮긴 관계의 끝 본문이 바뀌었는지 판정하는 데만 씀(바뀌면 다시 확인할 목록)
- 실패한 `LOADING` 판은 지우지 않음(하루 99개 상한)
- 샘플 확인 파일(reviewer `SAMPLE`)은 적재가 거부. kind 샘플 적재는 확인 파일 없이
- 정렬 주의: Debian glibc는 `초1~2`가 `중1~3`보다 앞. 시험의 학년군 정렬은 `COLLATE "C"`로 고정
- learning 마이그레이션을 적용하는 검증 스크립트는 pgvector 이미지 사용(V14가 `vector` 타입)
- 시험: `KnowledgeRulesTest`(조각 해시·covers 학년·학기가 ai `fake.py`와 같음, 관계 규칙), `KnowledgeDatasetServiceTest`(적재·재적재 멱등·교체·제거·관계 옮기기), `scripts/tests/test_knowledge_manage_datasets.py`

### 실제 추출본 적재 (kind, 2026-11-12)

#465 `curriculum-v1`(교육부 고시 제2022-33호 별책 5~9, 1,341건)을 공유 kind에 적재·활성화했다. 사람 확인 관계(#468 확인 파일)는 아직 없어 학기 관계만 들어갔다.

| 항목 | 값 |
|---|---|
| 판 | `kn-20261112-01` `ACTIVE`(이전 샘플 판 `kn-20261111-01`은 `RETIRED`) |
| 원문 문서 | 5(국어·도덕·사회·수학·과학 교과 별책) |
| 조각 | 1,341 = 성취기준 331·영역 114·내용 요소 886·교과 지침 5·생각 유형 5 |
| 성취기준(교과) | 과학 102·수학 92·국어 64·사회 49·도덕 24 |
| 학기 관계 | 425 = 3-1 56·3-2 56·4-1 58·4-2 54·5-1 47·5-2 50·6-1 53·6-2 51 |
| 사람 확인 관계 | fits 0·prerequisite 0·covers 0(#468 확인 전). 내용 요소 학년·학기는 covers가 들어오면 채워짐 |
| 소요 시간 | 적재·활성화 5초(운영 스크립트 기준) |
| 표 크기 | `knowledge_chunk` 25 MB(V14 임베딩 칸 포함 시점. V17 적용 뒤 줄어듦) |

- 확인: 성취기준 문장 331개가 `achievement_standard`와 같아 적재가 멈추지 않음. 코드 조회 `4수01-06`·`6국01-02` 본문, 3-1 수학 성취기준 18개
- 이 적재는 V17 전 배포본(가짜 임베딩 `fake-bigram-v1` 설정)으로 했다. V17이 임베딩 칸을 지워도 조각·관계 행은 그대로 남는다
- 원래 계획한 실제 OpenAI 임베딩(토큰 약 187,000개·요청 21회·약 0.004달러)은 팀 결정에 따라 부르지 않았다. 국어 교과 지침 조각 하나(11,445자)가 임베딩 상한(8,000자)을 넘는 문제도 임베딩을 쓰지 않아 없어졌다

## 30. 지식 관계 후보 생성과 사람 확인 (#468, 에픽 #463, 2026-11-11)

고시 자료로 자동으로 만들 수 없는 관계 세 가지(맞는 생각 유형 FITS·선수 PREREQUISITE·다루는 내용 요소 COVERS)의 후보를 만들고, 사람이 확인한 행만 관계 테이블에 넘기는 도구. 초3·초4 전체 사람 확인과 수락률 정리는 실제 레코드로 같은 도구를 써서 진행한다.

| 항목 | 결정 | 근거 |
|---|---|---|
| LLM 호출 | ai-service `create_llm` 재사용, ai-service 환경(`uv run`)에서 실행. 사용량은 표준 오류에만 남김 | 구조화 출력·재시도를 다시 만들지 않음 |
| 사람 확인 | 두 명. 1차 파일 + 교차 파일 → `compare`로 다른 행 → 합의해 차이 0 → `validate --final` → 적재 | 사용자 결정 |
| 선수 범위 | 같은 교과·학기가 앞선 **초3~6** 성취기준만. 3-1은 선수 후보 없음 | 초1~2는 지식 자료 밖 |
| 앞 학기 | 선수의 마지막 학기 < 이 성취기준의 첫 학기. 학기 정보가 없으면 후보·수락 불가 | |
| COVERS 범위 | 같은 교과·같은 고시 학년군 내용 요소 전체에서 유사도 상위 3(`--top`) | 사회·과학 성취기준 `domainId`는 단원이라 내용 체계 영역과 이어지지 않음 |
| 선수 겹침 | 확인된 COVERS(`--covers`) 또는 이번 COVERS 상위로 겹침 많은 순 상위 10개를 LLM에 주고 0~3개 | 내용 요소가 겹치는 것 우선 |
| evidence 형식 | 부분을 ` \| `로 잇고 `문장: `·`해설: `로 시작하는 부분은 원문 그대로. `validate`가 부분 문자열 검사 | |
| FITS 거르기 | 유형·요소 코드가 틀리거나 인용이 원문에 없으면 버림, 최대 2개 | 근거 없는 유형은 내지 않음 |

```
cd backend/ai-service
uv run python ../../scripts/knowledge/relation_candidates.py --records R --dataset-version kn-YYYYMMDD-NN \
    --embedding http --out ../../scripts/knowledge/relations-reviewed/kn-YYYYMMDD-NN-candidates.csv
python scripts/knowledge/review_relations.py validate FILE --records R [--final]
python scripts/knowledge/review_relations.py compare FIRST CROSS
python scripts/knowledge/review_relations.py stats FILE --records R
python scripts/knowledge/review_relations.py coverage FILE --records R
python scripts/knowledge/manage_datasets.py load --records R --reviews FIRST --dataset D
```

- `--embedding fake`(기본)는 가짜 벡터, `http`는 ai `POST /internal/embeddings`(`AI_URL`·`INTERNAL_TOKEN`, ai에 `EMBEDDING_PROVIDER=openai`와 키 필요)
- `--final`은 미확인 행·`SAMPLE` 확인자 거부. 적재가 돌려주는 `recheck` CSV도 같은 절차로 다시 확인
- LLM 입력은 성취기준 문장·해설, 생각 유형 지침, 내용 요소 글뿐(학생 정보 없음)
- 한계: 실제 LLM 프롬프트 품질은 아직 재지 않음. 첫 실제 실행의 1차 확인 수락률로 보고 프롬프트 판(`relation-candidates-v1`)을 올림. 가짜 벡터는 품질 지표가 아님
- 시험: `scripts/tests/test_knowledge_relations.py`

## 31. 테마 초안 작업·학년별 테마·이야기 열람 (#438)

에픽 #436(주간 테마 LLM 생성과 시작·종료 화면)의 learning 몫. ai 생성 그래프는 #437([ai 17장](ai.md#17-주간-테마-초안-생성-437)), core 프록시·사용량은 #439([core 15절](core-gateway.md#15-테마-초안-관리자-프록시이야기-열람-프록시사용량-theme_draft-439)), web은 #440·#441. 계약은 api-spec 1.3·4.1, learning OpenAPI 1.3.0.

구성: V15(준비·복사)·V16(확정) `weekly_theme.grade`, 버전·요일의 이야기·S3 키·움직임·정답 구조·대화·생각 열기 위치 칸, `theme_story_view`, `theme_draft`, `mission.source` `LLM_THEME`, `mission_version.scene_motion`. `theme/`의 초안 도메인·스케줄러·ai 클라이언트, `_common/storage/AssetUrls`.

### 학년별 테마

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 학년 | `G3`·`G4`·`G5`·`G6`. 시도 학년 → 테마 학년은 `min(학년, 6)`. 게시 부분 UK `(grade, week_start)` | 담당자 결정 2026-11-10, P26 |
| 기존 학년군 테마 | `G3_4` 행은 `G3`로 바꾸고 같은 내용의 `G4` 복사본(새 ID)을 V15가 만듦. `G5_6` → `G5`·`G6`. 기존 시도·열람 기록의 `theme_id`는 원래 행 | 원래 행을 남기면 FK를 바꾸지 않아도 됨 |
| 마이그레이션 순서 | 옛 게시 UK를 먼저 지운 뒤 복사(복사본도 `grade_band`가 같아 UK에 걸림). 순환 FK는 `SET CONSTRAINTS … DEFERRED` | |
| 복사본 ID | `md5(원래 id \|\| ':G4')::uuid` | 어느 환경에서 돌려도 같은 ID라 테스트로 확인 가능 |
| 전환 호환 | 학생 경로 세 개만 `grade`가 없으면 `gradeBand`(`G3_4` → `G3`, `G5_6` → `G5`)로 읽음. 관리자 경로는 `grade`만 | 학생 테마 조회가 끊기지 않게 |
| 게시 검사 | 미션 학년 범위가 테마 학년을 포함, 초3·초4 논술 불가. 오류 코드 `GRADE_BAND_MISMATCH` → `GRADE_MISMATCH` | 웹은 `errors[].message`만 표시 |

### 이야기·정답 구조·장면

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 이미지·영상 URL | DB에는 ai가 올린 S3 키, 응답 때 learning이 presigned URL로 변환(AWS SDK S3 presigner). core는 그대로 전달 | 리포트 PDF와 같은 방식. core에는 S3 연결이 없음 |
| URL 유효기간 (기준안) | 1시간(`app.assets.url-ttl`) | 학생이 화면·영상을 보는 동안 열려 있어야 함 |
| presign 대상 | ai 키(`theme-drafts/`로 시작)만. 그 밖의 값은 저장 값 그대로. 버킷 설정이 없으면 ai 키는 null | 관리자가 장면 칸을 자유 글로 넣어 형식을 알 수 없음 |
| 변환 위치 | `MissionService` 학생용 조회 한 곳. 관리자 미션 응답 `sceneUri`는 저장된 키 그대로(테마 편집 응답에는 미리보기 URL 칸을 따로) | 웹이 관리자 응답을 그대로 다시 저장하므로 URL로 바꾸면 만료되는 URL이 저장됨 |
| 문제 전 영상 위치 | 테마 요일 칸(`weekly_theme_day.video_uri`), 응답은 시도의 `themeScene.videoUrl`. ai는 `INTRO`·`OUTRO` 영상만 만들어 채택 테마에서는 null, 관리자가 넣을 때만 사용 | 같은 미션이 학년별 테마 여럿에 들어갈 수 있어 미션 응답에 넣으면 어느 테마 영상인지 정할 수 없음 |
| 정답 구조 공개 | 요일 단서는 그 요일이 `OPEN`·`CLOSED`일 때. 종료 이야기·정답·결정적 단서·종료 장면은 엔딩 상태일 때만. 엔딩 판단은 `ThemeEnding` 한 곳(#484 전까지 토·일) | 엔딩 규칙(#483)은 #484 몫. 판단 자리만 두면 #484는 판단만 바꾸면 됨 |
| 시작 이야기 | 그 주 처음 들어왔을 때 한 번(월~토). `intro`는 매일 채움 | 월요일에 안 온 학생도 이야기를 처음부터 봄 |
| 이야기 열람 | `POST …/weekly-theme/story-views {kind}` → `{kind, firstViewThisWeek}`. INTRO는 일요일, OUTRO는 엔딩 상태가 아니면 409 `THEME_STORY_NOT_ALLOWED` | |
| `answer_clue` | 채택 때 `rulesOut`이 비지 않은 마지막 요일의 `clue`로 채움 | ai 응답에 칸이 없어 단서 구조에서 계산 |
| 정답 구조 저장 검사 | `rulesOut`이 비지 않은 날은 그때까지 남은 후보를 적어도 하나 새로 뺌 | 결정적 단서 계산의 전제 |
| 생각 열기 위치 | `x`·`y` 0~100, `seq`는 그날 미션 기준표의 생각 열기 순번, 중복 금지. 위반 400 | |
| 관리자 수정의 이어받기 | 이야기·정답 구조·요일 칸이 본문에 없거나 null이면 현재 버전 값을 이어받고, 빈 값(""·[]·{})이면 비움. 생각 열기 위치는 그 요일 미션이 같을 때만 | 지금 관리자 웹은 새 칸을 보내지 않아 전체 교체면 LLM 테마 내용이 사라짐 |
| 장면 움직임 보존 | 관리자 미션 수정 본문에 `sceneMotion`이 없으면 `sceneUri`가 같을 때만 이전 값을 이어받음 | 관리자 미션 계약을 바꾸지 않으려고 |
| 움직임 형식 | ai 형식 v1(`ThemeMotion`)을 칸 검사 없이 그대로 저장·전달 | `spots.line`은 ai가 단서 결론·정답 이름을 걸러 미리 드러나지 않음 |
| 길이·개수 상한 (기준안) | S3 키 500자, 큰 질문 200자, 후보·정답 100자·10개, 단서 200자, 대화 20줄, 생각 열기 위치 10개, 종료 이야기 2000자. 상수는 도메인 `ThemeLimits` | |

### 테마 초안

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 상태·다시 생성 | 미션 초안과 같은 전이. 다시 생성은 같은 입력으로 새 초안(`source = ADMIN`), 원래 초안은 그대로. `GENERATING`·`ADOPTED`는 409 | 자동 초안 부분 UK와 부딪히지 않음 |
| 자동 생성 성취기준 (기준안) | 그 학년이 속한 학년군 표에서 `SOLVE`는 수학, 나머지는 국어. 같은 학년 최근 4주 초안에 쓴 코드는 빼고 무작위 1개. 초3·초4 따져 보기는 서술 | P15 국어 우선, 문제 해결하기 수학 예외 |
| 빈 유형·빈 주제 | 관리자가 고르지 않은 유형은 자동 규칙으로 채워 `input`에 저장. 주제가 비면 주제 씨앗으로 채움 | ai 요청은 유형 5개가 다 있어야 함 |
| 주간 자동 | 수요일 03:00 KST(`app.theme-draft.weekly-cron`)에 다음 주 초안. 그 학년·주에 게시 테마가 있으면 만들지 않음. 학년마다 실패 격리 | 쓰지 않을 초안에 ai 비용을 쓰지 않게 |
| 상한·대기 (기준안) | 생성 시도 3회, ai 마감 15분, learning→ai 대기 16분(`app.theme-draft.ai-read-timeout`), 리스 18분, 생성 주기 10초 | 실측 후 조정 |
| 서킷 | `ai-theme-draft`. 느린 호출 설정 없음 | 테마 실패가 다른 호출을 막지 않게 |
| 스레드 | `spring.task.scheduling.pool.size` 5. ai 호출은 트랜잭션 밖(16분 동안 DB 연결을 잡지 않음) | 긴 ai 대기가 고착 판정 탐지를 밀지 않게 |
| learning 검사 | 요일·유형 배치(월 `ANALYZE`·화 `EVALUATE`·수 `CREATE`·목 `SOLVE`·금 `REFLECT`), 미션 5개 게시 규칙(`DraftRules.learningFailures`), 정답 논리, 글 길이. 대화·장면 키 모양은 보지 않음 | 채택한 테마를 관리자 화면에서 다시 저장할 때 400이 나지 않게 |
| 실패 기록 | `check_results[].failures[].stage`: ai `THEME`·`MISSION`·`REVIEW`·`IMAGE`, learning `LEARNING`, 호출 실패 `AI_CALL`. ai에 보내는 `previousFailures`는 learning 실패를 `THEME`·`MISSION`으로 바꾸고 AI 호출 실패와 사유가 빈 묶음은 뺌. `MISSION` 사유는 `<요일> <검사 코드> <자세히>` | ai 요청 `stage`는 네 값 enum이고 `reasons`는 1개 이상이라 어기면 422로 같은 초안이 계속 실패 |
| ai `failure`가 있을 때 | learning 검사 없이 ai 실패만 기록, 받은 결과는 `output`에 저장 | 관리자가 실패한 초안도 볼 수 있게 |
| 자동으로 못 채울 때 | 관리자 요청은 409(성취기준 표가 비어 있음), 주간 자동은 그 학년만 건너뜀 | 요청 값이 아니라 서버 데이터 문제 |
| 채택 | 미션 5개 `DRAFT`(`source = LLM_THEME`, 학년 범위 = 테마 학년, 요소 배점 1)와 테마 `DRAFT`를 한 트랜잭션. `MissionService.createFromDraft`에 출처 인자를 더해 재사용 | |
| 응답 장면 | 생성 결과가 있으면 장면 7개를 INTRO·MON~FRI·OUTRO 순으로 항상 넣음(값이 없으면 null) | 웹이 고정 순서로 그릴 수 있게 |
| 기능 간 호출 | 성취기준은 `MissionService.standards`, 게시 여부는 `WeeklyThemeAdminService.publishedExists`. 테마 ai 요청 타입은 `theme/client`에 따로(`AiThemeStandard`·`AiThemeElementCode`) | 기능 간 호출은 상대 기능의 service로만, client는 다른 기능 client를 참조하지 않음 |

### 주제 씨앗 (2026-11-11)

주제가 비면 ai가 공원·탐정으로 쏠려(#437 실측) learning이 주제 씨앗을 골라 `topic`에 넣는다. 계약 변경 없음.

- 형식: `뭉치 역할: <역할(차림)> / 장소: <장소> / 찾는 대상: <대상>`. 목록 24개(`ThemeTopicSeeds.ALL`, 기준안). 찾는 대상은 잃어버린 물건·길 잃은 동물만(사람 탓 줄거리 없음)
- 주간 자동은 항상, 관리자 요청은 `topic`을 비웠을 때. 관리자가 쓴 주제와 다시 생성은 그대로
- 같은 학년에서 쓴 씨앗은 목록 개수만큼의 주 동안 제외(초안 상태 무관). 같은 주 다른 초안의 씨앗도 제외. 남는 게 없으면 가장 오래전에 쓴 것
- 계절(기준안): 봄 3~5월·여름 6~8월·가을 9~11월·겨울 12~2월. 계절이 맞지 않는 씨앗 4개는 그때만

### 자동 성취기준의 한계와 다음 설계

- 학년군 표에서 고르므로 초3 테마에 4학년 내용이 뽑힐 수 있음(#437 실측에서 초3 통과율이 가장 낮았던 원인 중 하나). 성취기준 표에는 학년·학기 칸이 없어 지금은 거를 수 없고, 관리자가 성취기준을 지정하면 피할 수 있음
- 후보 풀 설계(기준안): 지식 RAG 적재 뒤 learning 지식 서비스(#469)에서 그 학년·학기(`knowledge_standard_semester`)와 유형(`knowledge_fits`) 성취기준을 받고, 없거나 장애면 학년군 표로 대체. ai 요청 계약은 그대로
- 학기 규칙(기준안): `weekStart`가 3월 1일~8월 15일이면 1학기, 그 밖은 2학기
- 국어는 두 학년 공통 코드가 많아 코드로는 학년 수준을 거를 수 없음 → `learned`(#469)와 ai 검토가 맡음
- 확인 필요: 주제와 가까운 성취기준을 고르려면 C5 `theme-candidates`를 부르는 쪽이 ai에서 learning으로 바뀜(#469 담당과 확인)

### 남은 확인

- 정답 고르기 위치·저장·엔딩 판정은 #484. core는 `sundayTheme`을 보내지만 #438은 읽지 않음(일요일 열림 판단도 #484)
- 인프라: learning에 S3 역할이 없음. `theme-drafts/*` 읽기 역할(presign 서명용)과 버킷 이름(ai 쓰기 버킷과 같아야 함), 로컬은 브라우저가 닿는 MinIO 주소
- presigned URL 한계: 응답마다 주소가 바뀌어 브라우저 캐시가 맞지 않음. 임시 자격 증명으로 서명하면 1시간보다 일찍 만료될 수 있음. 만료 403은 웹이 이번 주 테마를 다시 받아 처리(#440)
- 주간 자동 시각에 learning이 모두 내려가 있으면 그 주 자동 초안이 생기지 않음(관리자 요청으로 대신)
- api-spec 2.8·2.11 공개 줄 문구(학년, 새 응답 칸, INTRO 월~토·OUTRO 엔딩)는 core PR에서 맞춤
- #437 그래프와 실제로 붙인 확인은 병합 뒤 kind에서 core와 함께

테스트: `ThemeGradeMigrationTest`, `ThemeAnswerRulesTest`, `AssetUrlsTest`, `ThemeDraftServiceTest`, `ThemeDraftConcurrencyTest`(레플리카 4곳, 느린 ai 대기 중 내부 API 즉시 응답), `ThemeDraftAiStubFlowTest`, `ThemeTopicSeedsTest`, `scripts/tests/test_theme_drafts_contract.py`.

## 32. 일일 리포트 완료일 조회 지원 (#391)

`/internal/records/students/{studentId}/daily-attempts`는 같은 KST 날짜의 COMPLETED 시도를 완료 시각으로 찾는다. 기존 제출일 기준 P08 목록은 유지한다. 기존 RecordPage/원문 제외 정책·학생 scope·삭제 표식을 재사용하며 새 DB 컬럼은 없다. 전날 제출·오늘 완료, 진행 중 제외, 다른 학생 제외를 서비스 DB 테스트로 검증한다. 테마·context 자체 구현은 #385 범위다.

### #391 후속 반영

기록 목록·상세·daily-attempts에 실제 `attempt.context`를 추가했다. 주간 요약은 `WeeklyThemeReportService`가 #207 비교 로직을 재사용해 `reviewRetries[].comparison`에 상태와 요소 변화만 담는다. 학생 범위를 검사하고, 미마무리 시도는 null이며 원문·인용은 전달하지 않는다. 위 #385 이력의 기록 context 후속은 이 변경으로 완료했고 학생 시도 상세 context는 이번 범위 밖이다.

## 33. 지식 검색 내부 API (#469, 2026-11-11)

### 최신 develop 반영과 범위 확인 (2026-11-12)

- 병합 후 스크립트·계약 검사 294개 실행: 최초 291개 통과·2개 localhost 접근 권한 오류·1개 조건부 제외. 해당 적재 도구 묶음 4개를 권한 조정 후 재실행해 모두 통과했다. 최종 검증 대상 기준 293개 통과·1개 제외다. Docker 엔진이 실행되지 않아 이번에는 learning DB 통합 테스트를 재실행하지 않았다.

- 문서 통합 PR #542를 포함한 develop `70a94db9`를 반영했다. 기존 31·32절(테마 초안·일일 기록)은 보존하고 이 기록은 33절로 이동했다. 아래 11/11 테스트 수치는 당시 결과이며 이번 병합 후 재실행 결과와 구분한다.
- #465 실제 추출본 `curriculum-v1.jsonl` 1,341건이 PR #532로 들어왔다. 아래의 실제 추출본 대기는 해소됐다. 사람 확인 관계 결과와 실제 적재본 최종 질의 검증은 별도다.
- [에픽 #463의 11/11 팀 결정](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/463#issuecomment-6797018586)은 생성에 벡터 검색을 사용하지 않는 것이다. [#469 코멘트](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/469#issuecomment-6797026238)는 코드 조회 2개를 남기고 벡터 API 3개를 중단하는 범위 조정을 제안한다. 이슈 원문 체크박스는 아직 다섯 API 기준이므로 임의로 완료 처리하거나 API를 삭제하지 않았다.
- #466 적재·활성화는 여전히 임베딩 누락을 거부한다. 임베딩 없는 코드 조회용 적재 방식은 [#466 확인 사항](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/466#issuecomment-6797026943)과 맞춰야 한다. 샘플·가짜 임베딩 시험을 실제 검색 품질 승인으로 간주하지 않는다.


### 계약과 범위

#464 PR #524의 계약 커밋 `f56d9458`을 기준으로 C5 다섯 경로를 learning에 구현한다. `standards`, `thinking-types/{type}`, `search`, `theme-candidates`, `learned`의 요청·응답은 [api-spec 4.1.2](../design/api-spec.md#412-교육과정-지식-내부-api-463-계약-464-c5-구현-469)와 learning OpenAPI를 따른다. 내부 토큰과 SYSTEM 역할을 확인하며 학생 정보는 받지 않는다. learning에서 ai를 호출하거나 질의 벡터를 생성하지 않는다.

- `learned`는 단일 벡터 대신 개념 1~20개의 `{text, vector}` 묶음을 받는다. 코드 1~10개, 검색 k 기본 5·최대 20, 테마 유형당 기본 3·최대 10, 최소 유사도 기본 0.7은 C5 기준을 유지한다.
- 요청의 미정의 칸·잘못된 타입·범위를 거부한다. 벡터의 비유한 수치와 코사인 계산이 불가능한 0벡터를 검사하고 활성 판과 모델·차원이 다르면 409 `KNOWLEDGE_EMBEDDING_MISMATCH`다.
- ACTIVE 판 하나와 그 판의 관계만 조회한다. 한 요청의 여러 조회는 같은 읽기 스냅숏을 써 판 교체 중 서로 다른 판의 본문·근거가 섞이지 않게 한다.
- 같은 필터 안은 OR, 필터끼리는 AND이며 빈 필터는 생략과 같다. 교과·유형 지침은 학년·학기 필터를 받지 않는다. 테마 후보는 유형마다 k개를 구하고 성취기준 본문과 확인된 covers의 최대 유사도를 사용한다.
- 선수 관계는 `WITH RECURSIVE`로 추적한다. 현재 찾은 내용 요소를 다룬다는 확인된 covers와 학기가 있는 성취기준만 배움 근거다. 다른 개념의 선수 학기를 현재 개념의 학기로 대신하지 않으며 순환은 중복 제거로 종료한다. 학기 없는 저장소 밖 선수 관계에서 학기를 추정하지 않는다.
- 질의는 기본 2초의 예산을 사용한다. 각 SQL에 남은 시간을 적용하고 여러 개념을 순서대로 조회할 때도 같은 전체 예산을 쓴다. DB 연결 확보 대기도 경과 시간에 포함하지만 공유 연결 풀의 블로킹 대기를 이 예산으로 강제 중단하지는 못한다. 결과·오류·시간 초과와 소요 시간은 고정된 작업 이름으로 기록하고 질의 본문·벡터·학생 정보는 로그에 남기지 않는다. 시간 초과는 500 `INTERNAL_ERROR`이며 근거 없음인 200 응답으로 바꾸지 않는다.

### 배포와 통합 선행

production vector 확장·C2/C3 테이블 Flyway·적재·활성 판 교체는 #466 소유다. #469는 해당 마이그레이션을 복제하거나 기존 마이그레이션을 고치지 않는다. 배포 전 #466의 확장과 테이블을 적용해야 하며, 활성 판이 없는 정상 테이블은 다섯 API 모두 200 `NO_ACTIVE_DATASET`으로 응답한다. 스키마 자체가 없는 배포 상태를 데이터 없음으로 숨기지 않는다.

개발 검증은 일회용 pgvector PostgreSQL에서 실제 Flyway V14 테이블과 #464 샘플을 사용한다. 초기 시험용 DDL은 #466 병합 후 삭제했다. 샘플 관계의 검토자는 격리 자동 시험에서만 `TEST_FIXTURE`로 바꿔 적재하고 실제 사람 확인으로 취급하지 않는다. 원본 `reviewer=SAMPLE`과 검토자·검토일이 없는 관계는 조회에서도 제외한다. #466·#467 구현은 병합됐으며, #465 실제 추출본과 #468 사람 확인 관계가 제공되면 실제 적재본의 주제 3개·코드 5개·범위 확인 5개 결과와 지연, 유사도·k 보정을 검증한다. `HOLD`의 생성 측 처리는 #470과 확인한다.

### 검증

- `KnowledgeApiIntegrationTest` 22개, `KnowledgeConcurrencyIntegrationTest` 2개 통과. PostgreSQL 17 / pgvector 0.8.7에서 샘플 215개를 적재해 실제 controller→service→MyBatis→DB 경로를 실행했다. 정수 JSON 벡터, 기본 k, 엄격한 타입·null 검사, 내부 인증, 필터 조합, 학기·유형, ACTIVE 판 격리, 최소 유사도, 순환 선수 관계, 동일 개념 근거만 인정하는 판정을 포함한다.
- 실제 HTTP JSON 18개(정상 5개·대체 사유 9개·오류 4개)가 OpenAPI 검증을 통과했다. 근거의 판 필드를 지우거나 정상 응답을 빈 결과로 바꿨을 때 검증기가 실패하는 것도 확인했다. CI에서 이 응답을 재생성하고 검사한다.
- learning 전체 `test bootJar`: 69개 시험 묶음, 400개 통과·실패/건너뜀 0개, 실행 JAR 빌드 성공. 기존 커뮤니티·테마 요약 응답 계약 검사도 통과했다. 저장소 스크립트 시험은 251개 중 250개 통과·기존 조건부 1개 건너뜀, ai 지식 계약 시험 29개 통과다.
- 최신 develop `c26c0ca4`(#522·#524·#525 병합 포함)을 #469 브랜치에 충돌 없이 병합한 뒤 지식·커뮤니티·테마 비교 통합 시험 34개와 세 응답 계약 검사를 다시 통과했다. 병합 후 저장소 스크립트는 252개 중 251개 통과·기존 조건부 1개 건너뜀이다. learning 소스 변경이 없어 기존 실행 JAR은 유효하다.
- 실제 DB 배타 잠금을 유지한 채 요청이 500으로 종료되고 잠금 해제 후 다음 요청이 200으로 복구됐다. 서비스 로그의 소요 시간은 2,110ms였다. 2초는 SQL 취소 예산이며, 취소 전달·트랜잭션 정리와 공유 풀 대기까지 포함한 HTTP 응답의 절대 상한을 뜻하지 않는다.
- 조회가 chunk 잠금에서 기다리는 동안 활성 판과 기존 본문을 함께 변경했다. 진행 중인 응답의 본문·참조는 모두 이전 스냅숏을 유지했고 다음 요청은 새 판을 반환했다.

2026-11-11 로컬 단독 지식 테스트에서 성공 로그를 집계한 값이다. 정상·근거 없음 응답을 함께 포함하며 별도 워밍업을 제거하지 않았다. 합성 벡터를 사용한 기능 시험 수치로, 실제 데이터의 검색 품질·부하 성능 측정을 대신하지 않는다.

| 작업 | 성공 호출 수 | 서비스 로그 최소~최대 |
|---|---:|---:|
| standards | 8 | 6~21ms |
| thinking_type | 6 | 6~32ms |
| search | 14 | 5~69ms |
| theme_candidates | 9 | 6~39ms |
| learned | 12 | 7~77ms |

설정은 `app.knowledge.query-timeout-ms`(기본 2000, 범위 1~2000), `search-default-k`(5), `theme-default-k`(3), `min-similarity`(0.7)이며 뒤 세 항목도 `app.knowledge` 아래에 둔다. 실제 적재 후 측정값으로 조정한다.

### 실제 저장소·임베딩 연동 검증 (공개 샘플, 2026-11-11)

develop `2af290c1`(#526·#527·#529·#531 포함)을 통합했다. #466 적재용 `KnowledgeMapper`는 그대로 유지하고 조회용은 `KnowledgeQueryMapper`로 분리했다. 실제 V14 마이그레이션과 성취기준 시드에서 관리 API 적재→활성화→다섯 조회, 동일 자료 재적재, 판 교체 후 새 본문·참조 반환까지 시험한다. `KnowledgeIngestionQueryIntegrationTest` 2개를 포함한 지식 관련 시험 40개가 통과했다.

통합 후 learning 전체 `test bootJar`는 72개 시험 묶음·416개 모두 통과(실패·건너뜀 0개), 실행 JAR 빌드 성공이다. 지식 HTTP JSON 18개와 기존 커뮤니티·테마 요약 응답 계약 검사도 통과했다. 저장소 스크립트 시험은 272개 중 271개 통과·기존 조건부 1개 건너뜀, ai 지식·임베딩 시험은 55개 통과다. 위 초기 검증 기록보다 이후 결과다.

별도 일회용 DB에 V1~V14 SQL과 성취기준 시드를 적용하고, 실제 learning JAR·ai C6 라우터·OpenAI 제공자를 HTTP로 연결했다. ai는 임베딩 라우터·내부 인증·오류 처리·제공자를 격리 실행했으며 사용량 메타데이터는 로컬에 기록했다. 이번 실행에 AMQP/core 사용량 저장 검증은 포함하지 않았다.

- 데이터: `curriculum.sample.jsonl` 215개, `text-embedding-3-small` 1536차원. 임베딩 4회로 적재했고 적재 소요 시간은 5,609ms였다.
- `reviewer=SAMPLE`을 실제 확인자로 바꾸지 않았다. 이번 HTTP 실행은 사람 확인 관계 없이 적재했으므로, 실제 관계를 통한 후보·배움 판단 품질 검증이 아니다.
- 활성 판 `kn-20261111-01`에서 코드 5개·주제 3개·개념 5개를 조회했다. 13건 모두 HTTP 200이며 모델·차원·근거 판 일관성 검사를 통과했다. 아래 값은 각 요청 한 번의 클라이언트 경과 시간으로, 워밍업을 따로 제거하지 않았다.

| 요청 | 개수 | 관측 결과 | 소요 시간 최소~최대 |
|---|---:|---|---:|
| 성취기준 코드 | 5 | 요청한 코드 모두 조회 | 19.369~99.235ms |
| 주제 후보 | 3 | 기본 0.7 기준에서 모두 `BELOW_THRESHOLD`, 유형별 `NO_CANDIDATE` | 13.442~66.679ms |
| 배움 확인 | 5 | 모두 `HOLD` + `BELOW_THRESHOLD` | 9.980~149.969ms |

추가로 같은 성취기준 본문을 실제 모델로 임베딩해 검색했을 때 해당 코드가 1위(유사도 0.99999963)였고, 생각 유형 지침도 조회됐다. 동일 자료 재적재는 215개 임베딩을 전부 재사용해 외부 임베딩 호출이 0회였다. 전체 검증의 제공자 호출은 6회·입력 31,856토큰이었다. 응답은 정상이어도 위 후보 없음·보류를 검색 품질 통과로 세지 않는다. 현재 0.7 기준값은 실제 정답표를 확보한 뒤 보정해야 한다.

조회 예시와 관측 기록기는 `scripts/knowledge/samples/query-examples.sample.json`, `scripts/knowledge/query_examples.py`다. 실행 중인 서비스 주소와 내부 토큰 환경 변수 `INTERNAL_TOKEN`을 준비한 뒤 다음처럼 실행한다. 실제 검증 때는 `--cases`를 실제 자료·검토 범위에 맞춘 파일로 바꾼다.

```sh
python scripts/knowledge/query_examples.py --learning-url http://127.0.0.1:8081 --ai-url http://127.0.0.1:8000 --cases scripts/knowledge/samples/query-examples.sample.json --output knowledge-observations.json
```

기록에는 실제 응답·지연·사용한 모델/판과 오류 시 부분 결과를 남긴다. `dataClassification`은 사용자가 입력한 표식이며 검토 인증이 아니다. `qualityAssessment`는 `not_evaluated`로 남기고, 이 기록만으로 실제 적재본 완료 조건을 자동 체크하지 않는다. 실험용 서버·DB는 실행 후 정리했다.

### 해야 할 일

- [x] `GET /internal/knowledge/standards`: 성취기준 문장·해설, 영역, 교과 지침, 유형·내용 요소 관계 조회
- [x] `GET /internal/knowledge/thinking-types/{type}`: 생각 유형 출제 지침 조회
- [x] `POST /internal/knowledge/search`: 벡터·교과·학년·학기·유형 필터, k, 최소 유사도 검색
- [x] `POST /internal/knowledge/theme-candidates`: 학기·생각 유형별 후보와 점수, 후보 없음 사유 반환
- [x] `POST /internal/knowledge/learned`: 배움·아직 안 배움·보류 판정과 `WITH RECURSIVE` 선수 관계 확인
- [x] C5 대체 사유 코드와 근거 참조 반환
- [x] 시간 상한과 지연 기록 구현(SQL 2초 예산·잔여 시간 취소, 공유 풀 대기 및 응답 정리 한계는 위 설명 참고)
- [x] 샘플 DB에서 다섯 API·필터·학기·유형·기준 미만·ACTIVE 판 조회 시험

### 완료 조건

- [x] 다섯 API 시험 통과(샘플)
- [ ] 통합 후 실제 적재본으로 주제 3개·코드 5개·범위 확인 5개의 결과와 지연 기록

#466 저장소와 #467 실제 임베딩 연결은 공개 샘플로 검증했다. 남은 입력은 #465 실제 교육과정 JSONL과 #468 사람 확인 관계 CSV다. 이를 #466으로 적재·활성화한 뒤 #467의 같은 모델·차원 질의 벡터로 실제 자료의 결과와 지연을 기록한다. 필요한 산출물의 제공이 조건이며, 관련 이슈 전체 종료 자체를 기다리는 조건은 아니다.

### 확인 필요

- [ ] 유사도 기준·k·시간 상한을 실제 데이터 실측 후 조정
- [ ] `learned`의 보류(`HOLD`)를 생성 쪽에서 어떻게 처리할지 #470과 확인

learning의 `HOLD`·사유 반환은 검증 완료이며, 생성 측 검토 모델 전달 흐름은 연계 확인이 필요하다.

샘플 구현·검증 완료이며, 실제 적재본 통합 조건까지 충족한 이슈 전체 완료 상태는 아니다.
