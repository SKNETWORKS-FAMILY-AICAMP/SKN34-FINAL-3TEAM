# 이슈 #23 learning 학습 시도·초안 자동 저장·생각 열기

작성일: 2026-10-27. 기준: `develop`의 `1b60085`와 #22 브랜치(`feature/learning-mission`, PR #62) 위에서 작업. [이슈 #23](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/23), [API 명세 1.4·2.2·3.6·4.1](../design/api-spec.md), [ERD 4.2](../design/erd.md), [상태 다이어그램 3.1·3.2](../design/state-diagram.md), [시퀀스 다이어그램 3.1](../design/sequence-diagram.md), [클래스 다이어그램 4.1](../design/class-diagram.md).

learning-service의 `POST /internal/missions/{id}/attempts`, `GET /internal/attempts/{id}`, `PUT /internal/attempts/{id}/draft`, `POST /internal/attempts/{id}/hints`를 만들면서 정한 내용과 근거를 기록한다. 데이터베이스 스키마는 바꾸지 않았다.

## 설계 문서 갱신

| 문서 | 변경 전 | 변경 후 | 근거 |
|---|---|---|---|
| [api-spec 4.1](../design/api-spec.md) | 시도 시작은 "`/internal/attempts/...` 2.2 경로와 1:1"에 묶여 있음 | 시도 시작 줄 추가: `?grade&demo`, 진행 중 시도 `200`·새 시도 `201`. 생각 열기 응답 `{question, seq, total}`, 질문 없는 미션 `404` | 시작도 미션 조회와 같이 공개·학년·시연 범위를 확인해야 하고, 학년·시연 여부는 core만 앎 (#22와 같은 계약) |
| [class-diagram 4.1](../design/class-diagram.md) | `AttemptController.start(missionId)`, `AttemptService.start(studentId, missionId)` | `start(missionId, grade, demo)`, `start(studentId, missionId, grade, demo)` | 위와 같음 |
| class-diagram 4.1 `MissionService` | `currentVersions(missionId)`까지 | `getVersion(missionVersionId)`, `hintQuestions(rubricVersionId)` 추가 | 시도 상세는 시작 당시 버전의 미션을, 생각 열기는 기준표 버전의 질문을 보여 줌. attempt는 mission 테이블을 직접 읽지 않고 `MissionService`로만 씀 (architecture 2.2, `AttemptService --> MissionService : 공개 미션·당시 버전`) |
| [sequence-diagram 3.1](../design/sequence-diagram.md) | 공개·학년 범위 확인 → 진행 중 시도 반환 → 새 시도 | 진행 중 시도 확인 → 있으면 반환, 없을 때만 공개·학년·시연 범위 확인 → 시도 + 빈 초안(version 0) 저장 | 확인을 먼저 하면 공개 중단·학년 변경 뒤 진행 중 시도로 돌아갈 때 409가 남. state-diagram 3.1 "기존 시도는 당시 버전 유지"와 맞춤 |

## 구현에서 정한 것

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 시작 응답 코드 | 새 시도 `201`, 진행 중 시도 `200` | sequence-diagram 3.1이 새 시도에만 `201`. core가 하루 미션 한도(P13)를 셀 때 `201`만 세면 이어하기가 한도를 쓰지 않음 |
| 동시 시작 | `INSERT … ON CONFLICT (student_id, mission_id) WHERE status = 'IN_PROGRESS' DO NOTHING` 후 0행이면 먼저 커밋된 시도를 읽어 반환 | ERD 부분 UK `uq_attempt_in_progress`, 이슈 #23 "동시 요청 시 부분 UK 충돌 → 기존 시도 반환" |
| 완료한 미션 | 다시 시작하면 새 시도 | 부분 UK가 진행 중 시도만 막음. 목록 상태는 가장 최근 시도(#22) |
| 첫 초안 | 시도를 만들 때 같은 트랜잭션에서 빈 초안(version 0, `{answer: {}, memo: ""}`)을 함께 만듦. 저장은 항상 `UPDATE … WHERE version = :ifMatch` | ERD 4.2 "시도당 1행, `UPDATE … WHERE version = :ifMatch`", sequence-diagram 3.1. 행이 늘 있어 충돌 시 최신 초안을 항상 돌려줄 수 있음. 프론트는 초안이 없을 때도 version 0으로 시작함 |
| 초안 응답 | version 0(저장한 적 없음)은 `savedAt` 없음 | 시작 시각을 "마지막 저장 시점"으로 보여 주지 않음 (FN-LRN-16) |
| `If-Match` | `"7"`·`7`·`W/"7"` 허용, 없거나 0 이상 정수가 아니면 `400 VALIDATION_FAILED`. 응답 `ETag`는 `"8"` | api-spec 1.4. 프론트는 처음 `0`, 이후 서버 `ETag`를 보냄 |
| 초안 충돌 | `409 ATTEMPT_DRAFT_CONFLICT` + `latest{version, content, savedAt}` + 최신 `ETag`. 덮어쓰지 않음 | api-spec 3.6, FN-LRN-17. `latest`는 attempt 전용 `DraftConflictException`을 `AttemptController`에서 변환해 공통 예외 처리를 바꾸지 않음 |
| 초안 내용 | `{answer, memo}` 저장, answer 형식은 검사하지 않음 | 작성 중 내용이라 입력 방식별 검증은 답변 제출(#24). memo는 학생 본인 조회에만 (P05) |
| 쓰기 막는 때 | `COMPLETED` 시도의 초안 저장·생각 열기는 `409 ATTEMPT_CLOSED` | state-diagram 3.2 "COMPLETED 시도에 답변·초안·도움·돌아보기 쓰기 → 409". 마무리(`finished_at`) 뒤 막는 것은 답변 제출(P04, #24) |
| 생각 열기 순서 | 아직 열지 않은 질문을 `seq` 순으로 하나씩, 다 열었으면 마지막 질문을 다시 주고 열 때마다 `hint_usage` 기록 | `hint_usage`가 질문 하나씩 기록하는 구조. 열람 시점이 도움 이용 집계 근거(FN-LRN-06, P08) |
| 질문 없는 미션 | `404 NOT_FOUND` | 데모 미션은 모두 2개. 관리자 작성 미션 대비 |
| 시도 상세 | 프론트 `Attempt` 모양(`attemptId`, `studentId`, `mission`, `status`, `finishedAt`, `answers`, `helped`, `draft`) + `nextActions`. `mission`은 시도에 고정된 버전, `answers`·`nextActions`는 #24·#25 전이라 빈 목록 | api-spec 2.2·3.7·3.8. #22 후속 "진행 중 시도는 시작 당시 버전 유지" 처리 |
| 본인 확인 | 시도의 `student_id`가 `X-Student-Scope` 밖이면 403 (`UserContext.requireStudent`), 없는 시도 404 | api-spec 1.2 "학생은 본인 기록만" |
| 학생 요청 확인 공용화 | #22 `MissionController`의 "학생 역할 + 학생 1명" 확인을 `_common/security/UserContext.requireSelfStudent()`로 옮겨 두 Controller가 같이 씀 | #24~#27 Controller도 같은 확인이 필요해 한 곳에 둠. #22 동작은 같음 |
| 하루 미션 한도 | learning은 확인하지 않음 | class-diagram 4.1 하단 "요금제 사용 한도(P13): core가 Redis 일 단위 카운터와 `product.limits`로 확인". 이슈 #23 "확인 필요" 답 |

## 프론트 목업과 다른 점 (프론트 담당 확인)

| 항목 | 프론트 목업 | 구현 | 근거 |
|---|---|---|---|
| 생각 열기 질문 | `mission.hint`(안내)를 돌려줌 | 기준표 버전의 생각 열기 질문(`hint_question`)을 순서대로. 안내는 미션 상세 `hint` | FN-LRN-06, ERD `hint_question` |
| 생각 열기 응답 | `{question}` | `{question, seq, total}` | 몇 번째 질문인지 표시용. 프론트는 `question`만 읽어 영향 없음 |
| 초안 저장 막는 때 | `finishedAt` 이후에도 `ATTEMPT_CLOSED` | `COMPLETED`일 때만 | state-diagram 3.2 |
| 시작 응답 코드 | 항상 `201` | 진행 중 시도는 `200` | sequence-diagram 3.1 |
| 시도 상세 초안 | 없을 수 있음 | 항상 있음(처음엔 version 0, `savedAt` 없음) | 시작 시 빈 초안 생성. 프론트 `draftDto`가 빈 answer를 기본값과 합쳐 처리 |

## core에 전달할 것 (#38, 20220348-kim)

- 시도 시작 `POST /missions/{id}/attempts`도 learning에 넘길 때 미션 조회와 같이 `grade`·`demo`를 붙임.
- 하루 미션 한도(P13)는 learning 응답이 `201`일 때만 세면 이어하기(`200`)가 한도를 쓰지 않음.

## 검증

- `./gradlew test`: 45개 통과, 실패·생략 0개. 새로 추가 21개: `AttemptRepositoryTest` 3, `AttemptServiceTest` 8, `AttemptConcurrencyTest` 2, `AttemptControllerTest` 7, `MissionRepositoryTest` 1(시도용 조회).
- 이슈 #23 완료 조건
  - 같은 미션 시작 2회 → 같은 attemptId: `AttemptServiceTest`(순서대로), `AttemptConcurrencyTest`(동시 8개, 시도·초안 각 1행). 동시 테스트는 요청마다 커밋해야 해서 롤백하는 `PostgresRepositoryTest` 대신 별도 PostgreSQL 컨테이너를 씀(repository-foundation 보고서)
  - 오래된 `If-Match`로 저장 시 409, 덮어쓰기 없음: `AttemptServiceTest`(순서대로), `AttemptConcurrencyTest`(같은 `If-Match: 0`으로 동시 8개 → 1개만 성공, 7개 409와 그 내용, 최종 초안도 그 내용), `AttemptControllerTest`. 저장 SQL에서 버전 조건을 빼면 동시 테스트가 실패함을 확인
- 저장 시각은 마이크로초로 맞춤: PostgreSQL `timestamptz`가 마이크로초까지 저장해, 그대로 두면 저장 응답(나노초)과 이후 조회의 `savedAt`이 달라짐. 테스트가 저장 응답과 조회 결과가 같은지 확인하고, 맞춤을 빼면 실패함.
- 시드 데이터로 로컬 앱 실제 호출 (확인 후 만든 시도 삭제):

| 요청 | 결과 |
|---|---|
| 1번 미션 시작 | 201, 미션 "한 화분만 시든 까닭", 초안 version 0·`savedAt` 없음, `ETag: "0"` |
| 같은 미션 다시 시작 | 200, 같은 `attemptId` |
| 초안 저장 `If-Match: "0"` | 200, version 1, `ETag: "1"` |
| 같은 `If-Match: "0"`으로 다시 저장 | 409 `ATTEMPT_DRAFT_CONFLICT`, `latest`는 version 1과 처음 저장한 내용 |
| 생각 열기 3회 | 질문 1 → 질문 2 → 질문 2, `total` 2 |
| 시도 상세 | `helped: true`, `answers: []`, `nextActions: []` |
| `DRAFT` 미션(6번) 시작 | 409 `MISSION_NOT_AVAILABLE` |
| 다른 학생이 시도 상세 | 403 `FORBIDDEN` |

Windows `curl`은 명령 줄의 한글 본문을 깨뜨려 400이 나므로 초안 본문은 UTF-8 파일로 보냄.

## 후속

- #24 답변 제출: 시도 상세 `answers`, `finished_at` 이후 제출 409(P04)
- #25 피드백: `nextActions` 값
- #26 마무리·돌아보기: `finishedAt`, `reflection`
