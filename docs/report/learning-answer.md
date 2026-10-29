# 이슈 #24 learning 답변 제출·버전 저장

작성일: 2026-10-27. 기준: #74 머지 후 develop 3e32731 위에서 작업. [이슈 #24](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/24), [API 명세 1.3·1.4·2.2·3.1·3.8·4.1](../design/api-spec.md), [ERD 4.2](../design/erd.md), [기능 명세 FN-LRN-04·05·08~10·15·16](../design/functional-spec.md), [유스케이스 4.2](../design/usecase.md), [시퀀스 다이어그램 3.1](../design/sequence-diagram.md), [클래스 다이어그램 4.1](../design/class-diagram.md).

learning-service의 `POST /internal/attempts/{id}/answers`를 만들고, 시도 상세(`GET /internal/attempts/{id}`)의 `answers`를 채우면서 정한 내용과 근거를 기록한다. 데이터베이스 스키마는 바꾸지 않았다.

## 설계 문서 갱신

| 문서 | 변경 전 | 변경 후 | 근거 |
|---|---|---|---|
| [api-spec 4.1](../design/api-spec.md) | 답변 제출은 "`/internal/attempts/...` 2.2 경로와 1:1"에 묶여 있음 | 답변 제출 줄 추가: `Idempotency-Key`(UUID) 필수·400, 같은 키 재요청 201·다른 본문 422, 입력 방식 불일치 400, 누락 422, 마무리·완료 409, 보완 답변의 `followupId` 규칙, 초안 답 칸 비우기. 시도 상세 `answers[]` 모양 | 내부 API 호출자(core #38)가 오류 코드와 동작을 알아야 함. 이슈 #24 지침 "API 계약 변경이 필요하면 api-spec 먼저" |
| [class-diagram 4.1](../design/class-diagram.md) `AttemptService` | `requireOpen(attemptId) Attempt` | `lockForAnswer(attemptId) Attempt`, `clearSubmittedDraft(attemptId, now)` | 제출은 시도 행을 잠근 뒤 같은 키 재요청을 먼저 처리해야 함(아래 "제출 순서"). 열려 있는지 확인은 그 뒤 `Attempt`가 함 |
| class-diagram 4.1 `Attempt` | `requireOpen()` | `requireOpen()`, `requireAnswerable()` | `requireOpen`은 `COMPLETED`만 막음(state-diagram 3.2, 마무리 뒤 돌아보기 저장 때문). 답변은 마무리(`finished_at`) 뒤에도 막아야 함(P04, api-spec 1.3 `ATTEMPT_CLOSED`) |
| class-diagram 4.1 `Answer` | `next(previous, followupId, content)`, `plainText()` | `next(previous, followupId, content, plainText)`, `sameRequestAs(other)` + `AnswerContent{only, requireComplete, plainText}` | 원문을 만들려면 미션 입력 틀(칸 이름)·선택지 이름이 필요해 미션을 아는 `AnswerContent.plainText(inputType, mission)`로 옮김. 같은 키 재요청 비교는 `sameRequestAs` |
| class-diagram 4.1 관계 | `AnswerService --> AttemptService : requireOpen` | `AnswerService --> AttemptService : lockForAnswer·clearSubmittedDraft`, `AnswerService --> MissionService : 시도 고정 버전` 추가 | 입력 방식·선택지 검사는 시도에 고정된 미션 버전으로 함. answer는 mission 테이블을 직접 읽지 않음(architecture 2.2) |
| class-diagram 4.1 `AnswerService.submit` 설명 | "같은 `idempotency_key`면 기존 답변 반환" | 같은 키·같은 본문이면 기존 답변, 다른 본문이면 `422 IDEMPOTENCY_KEY_REUSED`. 행 잠금, 초안 비우기, 보완 답변 연결 규칙 한 줄 추가 | api-spec 1.3·1.4 "같은 키에 다른 요청 본문 422". 기존 문구는 다른 본문도 기존 답변을 돌려주는 것으로 읽혀 api-spec과 맞지 않았음 |
| class-diagram 4.1 되묻기 생성 조건 줄 | "`finished_at` 이후 답변 제출은 `requireOpen`에서 `ATTEMPT_CLOSED`" | "`Attempt.requireAnswerable`에서", `requireOpen`은 `COMPLETED`만 | 위 `Attempt`와 같음 |
| class-diagram 4.2 `JudgmentService` | `createPending`부터 | `unansweredLatestFollowupId(attemptId)`, `timeline(attemptId)` 추가 | 아래 "판정 쪽 최소 구현" |
| [sequence-diagram 3.1](../design/sequence-diagram.md) | learning: IN_PROGRESS 확인 → answer 저장 → judgment PENDING | 행 잠금·본인 확인 → 같은 시도·키 조회 → 409·400·422 → 되묻기 연결 확인 → answer 저장 → judgment PENDING → 초안 답 칸 비우기. 설명 줄 "learning도 시도·키로 같은 키 처리" 추가 | 구현 순서. core가 learning 응답을 받기 전에 끊겨 다시 보내도 답변은 1건이어야 함 |

## 구현에서 정한 것

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 제출 순서 | 한 트랜잭션: 시도 행 잠금(`SELECT … FOR UPDATE`)·본인 확인(없으면 404, 남의 시도 403) → 같은 시도·키 답변 조회 → 마무리·완료 409 → 입력 방식 불일치 400 → 누락 422 → 되묻기 연결 422 → 답변 저장 → 판정 PENDING → 초안 답 칸 비우기 | 같은 키 재요청은 최초 결과를 그대로 줘야 하므로(api-spec 1.4) 열림·검증보다 먼저 확인. 마무리 뒤에도 이미 저장된 요청의 재전송은 201 |
| 동시 제출 | 시도 행 잠금으로 같은 시도의 제출을 한 줄로 세움 | 잠금이 없으면 같은 키 두 요청이 모두 "기록 없음"으로 보고 넣다가 UK `(attempt_id, idempotency_key)` 위반 500, 다른 키 두 요청은 같은 버전을 계산해 UK `(attempt_id, version)` 위반 500. 잠금을 빼면 동시 테스트 2개가 `DuplicateKeyException`으로 실패함을 확인 |
| 같은 키·다른 본문 | `422 IDEMPOTENCY_KEY_REUSED` | api-spec 1.3·1.4. 비교 대상은 입력 방식·그 방식에 쓰는 필드·`followupId`·`dictatedByGuardian` |
| 재요청 응답 | 최초와 같은 `201 {answerId, attemptId, version, followupId, submittedAt, feedback:{status:"PENDING"}}` | api-spec 1.4 "최초 응답 그대로". 그 사이 판정이 끝났어도 최초 응답은 PENDING이었으므로 PENDING |
| `Idempotency-Key` | 없거나 UUID가 아니면 `400 VALIDATION_FAILED` | ERD `answer.idempotency_key uuid NOT NULL`. 프론트는 `crypto.randomUUID()`로 만듦 |
| 입력 방식 불일치 | 요청 `inputType`이 시도에 고정된 미션 버전의 입력 방식과 다르면 `400 VALIDATION_FAILED`(detail에 미션 입력 방식) | 이슈 #24 "미션 입력 방식과 불일치 시 400" |
| 누락 검사 | 서술: 글 / 풀이: 최종 답 + 비어 있지 않은 단계 1개 이상 / 논술: 주장·까닭 2개·반대 의견 답 모두 / 고르기: 미션 선택지 중 1개 / 순서: 미션 선택지 전부 한 번씩 / 분류: 미션 선택지 전부 한 번씩, 그룹 비어 있지 않음. 아니면 `422 ANSWER_INCOMPLETE`, detail은 프론트 `validateAnswer`와 같은 안내 문구 | FN-LRN-04·05, api-spec 3.8. 화면과 서버가 같은 문구를 보여 줌 |
| 분류의 그룹 | 그룹 ID가 미션 그룹 목록에 있는지는 확인하지 않음 | 미션 그룹(`categories`)을 저장할 곳이 ERD에 없음. #22에서 프론트가 추후 맞추기로 함 → #79에서 확정([판정 규칙 보고서](learning-judgment-rules.md)): `mission_version.categories`, 없는 그룹 422 |
| 저장 내용 | 입력 방식에 쓰는 필드만 `content`에 저장(`AnswerContent.only`), 메모·다른 방식 필드는 버림 | api-spec 3.8 "메모는 제출에 포함하지 않는다"(P05). 요청에 `memo`가 와도 저장하지 않음을 실제 호출로 확인 |
| 원문(`plain_text`) | 서술은 글 그대로. 풀이는 `"{입력 틀 칸 이름 또는 단계 n}: 단계"` 줄들 + `"최종 답: …"`. 논술은 `"주장: …"`·`"까닭 1: …"`·`"까닭 2: …"`·`"반대 의견에 답하기: …"`(입력 틀이 4칸이면 그 이름). 고르기·순서는 선택지 이름을 `" → "`로. 분류는 `"선택지 이름: 그룹"` 줄들 | ERD `answer.plain_text`는 판정 인용 대조용 원문(#25). 칸 이름이 있어야 판정·되묻기가 어느 칸의 말인지 앎. 시도 상세 `text`로도 보여 줌 |
| 보완 답변 연결 | 첫 답변은 `followupId` 없이. 버전 2부터는 이 시도의 가장 최근 되묻기이면서 아직 답한 답변이 없는 것의 ID만. 아니면 `422 ANSWER_INCOMPLETE`("지금은 답할 추가 질문이 없어요." / "현재 추가 질문에 연결해 주세요." / "첫 답변은 추가 질문에 연결하지 않아요.") | 이슈 #24 "해당 시도의 되묻기인지 확인", FN-LRN-09. 되묻기는 판정이 끝나야 생기고 시도당 2회까지라(P04) 판정 전 추가 제출·네 번째 답변·고르기 정답 뒤 제출이 같은 규칙으로 막힘. 프론트 목업도 직전 되묻기에만 연결 |
| 마무리·완료 | `COMPLETED`이거나 `finished_at`이 있으면 `409 ATTEMPT_CLOSED` | P04 "마무리 후 제출 불가", api-spec 1.3. 이슈 #24 "완료된 시도에는 제출 불가" |
| 판정 생성 | 답변과 같은 트랜잭션에 `judgment(PENDING, rubric_version_id = 시도의 기준표 버전, retry_count 0)` | 이슈 #24, ERD 4.2. 판정 실행은 피드백 요청(#25) |
| 제출 뒤 초안 | 같은 트랜잭션에서 초안 `content.answer`를 `{}`로 비우고 `memo`는 유지, 초안 `version` +1. 같은 키 재요청은 다시 비우지 않음. 버전 조건 없는 한 번의 `UPDATE`(`jsonb_set`) | FN-LRN-15 "초안은 제출 답변과 구분", FN-LRN-16 "새로고침 시 마지막 초안 복원·미제출 표시": 초안을 그대로 두면 제출한 답이 미제출 초안으로 다시 채워짐. 메모는 보완 답변에도 씀(P05). 다른 화면의 옛 초안 저장은 버전이 달라 409로 알게 됨(FN-LRN-17). 같은 순간의 초안 저장과 겹쳐도 행 잠금 순서대로 처리됨. 프론트 목업과 같은 동작(목업도 답 칸 비움·메모 유지·버전 +1). 사용자 결정(10/27) |
| 시도 상세 `answers` | 버전 순 `{answerId, version, submittedAt, inputType, text, followupId, content, feedback:{status, nextActions:[]}}`. `status`는 판정 처리 상태 | 프론트 `Answer` 모델(api-spec 3.7·3.8). 판정 결과·되묻기·`nextActions`는 #25 |
| 타임라인 조회 위치 | `AttemptService.get`이 `JudgmentService.timeline(attemptId)`로 읽음 | `AnswerService`가 `AttemptService`를 쓰므로(잠금·초안) `AttemptService`가 `AnswerService`를 쓰면 순환. class-diagram 4.1 `AttemptService --> JudgmentService : 체크리스트·타임라인` |
| 판정 쪽 최소 구현 | `judgment/`에 `createPending`, `unansweredLatestFollowupId`, `timeline`만 | 제출이 판정 PENDING을 같은 트랜잭션에 만들어야 하고(class-diagram `AnswerService --> JudgmentService : createPending`) 되묻기·판정 상태는 judgment 소유. 판정 실행·결과·되묻기 생성은 #25에서 이 위에 추가 |
| 시각 정밀도 | `submittedAt`은 마이크로초로 맞춤 | #23과 같음. 재요청 응답의 `submittedAt`이 최초와 같음을 확인 |

## 구현 중 발견해 고친 것

- 논술 `Essay`의 빈칸 검사 함수를 `isComplete()`로 지었더니 Jackson이 `is…` 이름을 값으로 보고 `"isComplete": true`를 `answer.content`(DB)와 시도 상세 `content`에 함께 씀. 실제 호출의 DB 확인에서 발견해 `allFilled()`로 바꾸고, 저장된 JSON 전체를 비교하는 테스트로 고침(되돌리면 실패함을 확인).
- 테스트는 한 트랜잭션이라 MyBatis가 같은 조회 결과를 기억함. #25가 만들 되묻기 행을 테스트에서 `JdbcTemplate`으로 직접 넣으면 그 기억이 비워지지 않아 "되묻기 없음"이 남음. 테스트에서만 넣은 직후 `SqlSessionTemplate.clearCache()`. 실제 요청은 요청마다 트랜잭션이 달라 해당 없음.

## 프론트 목업과 다른 점 (프론트 담당 확인)

| 항목 | 프론트 목업 | 구현 | 근거 |
|---|---|---|---|
| 답할 되묻기가 없을 때 추가 제출 | `409 ATTEMPT_CLOSED` ("현재는 답변을 더 제출할 수 없어요.") | `422 ANSWER_INCOMPLETE` ("지금은 답할 추가 질문이 없어요.") | api-spec 1.3 `ATTEMPT_CLOSED`는 완료·마무리한 시도. 화면은 `canAddAnswer`로 제출 버튼을 미리 숨겨 보통 보이지 않음 |
| 시도 상세 `answers[].text` | 풀이 `"답: 6\n1. …"`, 논술 칸 이름 없이 줄바꿈, 분류 `"c1: g1"` | 풀이는 입력 틀 칸 이름 + `"최종 답: …"`, 논술은 칸 이름 붙임, 분류는 선택지 이름 | 판정 입력 원문과 같은 값 (`plain_text`) |
| 제출 뒤 초안 `answer` | `blankAnswer(inputType)`(예: `{inputType, text:""}`) | `{}` | #23과 같이 프론트 `draftDto`가 빈 answer를 기본값과 합쳐 처리 |
| `Idempotency-Key` | 있기만 하면 됨 | UUID여야 함 | ERD `uuid`. 프론트는 `crypto.randomUUID()` 사용 |
| 입력 방식 없음·다름 | 미션 입력 방식으로 채워 처리 | `400 VALIDATION_FAILED` | 이슈 #24 |

## core에 전달할 것 (#38, 20220348-kim)

- `POST /attempts/{id}/answers`의 `Idempotency-Key`를 learning에도 그대로 넘김. learning도 같은 키를 1건으로 처리하므로, core가 learning 응답 전에 끊겨 다시 보내도 답변은 1건.

## 검증

- `./gradlew test`: 68개 통과, 실패·생략 0개. 새로 추가 23개: `AnswerContentTest` 4, `AnswerServiceTest` 12, `AnswerConcurrencyTest` 2, `AnswerControllerTest` 5. `AttemptControllerTest`의 시도 상세 테스트는 `answers` 모양까지 확인하게 바꿈.
- 이슈 #24 완료 조건
  - 같은 키 동시 2회 → 답변 1건: `AnswerConcurrencyTest` 같은 키로 동시 8개 → 답변·판정 1건, 8개 모두 같은 답변. 다른 키로 동시 8개 → 버전 1만 1건, 나머지 7개 `422`. 요청마다 커밋해야 해서 #23처럼 별도 PostgreSQL 컨테이너 사용
  - 시도 행 잠금을 빼면 두 테스트 모두 `DuplicateKeyException`으로 실패, 되묻기 연결 검사를 빼면 `AnswerServiceTest` 3개, 초안 비우기를 빼면 1개 실패함을 확인
- 버전 저장(FN-LRN-08·09): v1 → v2 → v3을 낸 뒤 v1 행 전체(`row_to_json`)가 처음과 같고, 시도 상세에 버전 순으로 세 답변이 보임. 답변을 고치거나 지우는 SQL은 없음. 저장할 때 이전 버전 원문을 덮어쓰도록 바꾸면 이 테스트가 실패함을 확인
- 입력 방식 6종을 저장 후 다시 읽어도 같은 키 재요청이 같은 답변으로 판단됨: `AnswerServiceTest`(6종, 분류는 시드에 없어 테스트 미션으로)
- 시드 데이터로 로컬 앱 실제 호출 (확인 후 만든 시도·답변·판정·되묻기 삭제):

| 요청 | 결과 |
|---|---|
| 서술(2번) 초안 저장 후 제출(요청에 `memo` 포함) | 201, version 1, `feedback.status` PENDING, 저장 내용은 `{"text": …}`만 |
| 같은 키 재요청 / 같은 키 다른 본문 | 201 같은 `answerId`·`submittedAt` / 422 `IDEMPOTENCY_KEY_REUSED` |
| 판정 전 다른 키로 추가 제출 | 422 `ANSWER_INCOMPLETE` "지금은 답할 추가 질문이 없어요." |
| 시도 상세 | `answers` 1개(PENDING), 초안 version 2·`{answer: {}, memo: "내 메모"}` |
| 다른 화면의 옛 초안 저장(`If-Match: "1"`) | 409 `ATTEMPT_DRAFT_CONFLICT`, latest version 2 |
| 고르기(1번)·순서(4번)·논술(12번)·풀이(14번) 누락 | 각각 422와 프론트와 같은 안내 문구 |
| 같은 미션들 제출 + 같은 키 재요청 | 201, 같은 답변 |
| 시도 상세 `text` | 논술 "주장: … / 까닭 1: … / 까닭 2: … / 반대 의견에 답하기: …", 풀이 "① 무엇을 구하나요?: … / … / 최종 답: 32㎡", 순서 "파랑 → 빨강 → 노랑" |
| 서술 미션(3번)에 고르기 제출 | 400 `VALIDATION_FAILED` "미션 입력 방식: NARRATIVE" |
| `Idempotency-Key` 없음 / `abc` | 400 / 400 |
| 다른 학생 | 403 `FORBIDDEN` |
| 되묻기(직접 넣음) 뒤 연결 없이 / 연결해 제출 | 422 "현재 추가 질문에 연결해 주세요." / 201 version 2, `previous_answer_id`·`followup_id` 연결 |
| 마무리(`finished_at`) 뒤 새 제출 / 이미 보낸 키 | 409 `ATTEMPT_CLOSED` / 201 같은 답변 |
| DB | 답변 6건 모두 판정 PENDING, 풀이는 `dictated_by_guardian` true, 논술 content는 essay 세 필드만 |

## 후속

- #25 피드백: 판정 실행·결과 저장·되묻기 생성, 시도 상세 `answers[].feedback`의 결과·되묻기와 `nextActions`
- 답변 길이 상한: 문서에 없음. 판정 입력 크기(P12)와 함께 정함
- 분류 그룹 ID 확인: 미션 그룹(`categories`) 저장 위치가 정해지면 추가 → #79에서 확정([판정 규칙 보고서](learning-judgment-rules.md))
