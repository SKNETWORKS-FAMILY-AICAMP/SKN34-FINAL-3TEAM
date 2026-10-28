# 이슈 #26 learning 마무리·돌아보기·자기 평가

작성일: 2026-10-28. 기준: #78 머지 후 develop e728a64 위에서 작업, PR 전 develop 40a2501(#83 core 피드백 SSE, learning 코드 변경 없음)을 병합. [이슈 #26](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/26), [API 명세 1.3·1.5·2.2·3.8·4.1](../design/api-spec.md), [ERD 4.2](../design/erd.md) `reflection`·`self_assessment`, [기능 명세 FN-LRN-11~14](../design/functional-spec.md), [유스케이스 4.5](../design/usecase.md), [시퀀스 다이어그램 3.3](../design/sequence-diagram.md), [상태 다이어그램 3.2](../design/state-diagram.md), [클래스 다이어그램 4.1](../design/class-diagram.md).

learning-service의 `POST /internal/attempts/{id}/finish`·`/reflection`·`/self-assessment`를 만들고, 시도 상세에 마무리 뒤 공개 내용과 돌아보기를 붙이면서 정한 내용과 근거를 기록한다. 데이터베이스 스키마는 바꾸지 않았다.

## 설계 문서 갱신

원래 구조(클래스·관계·메서드 이름, sequence-diagram 3.3 순서)는 그대로 두고 빠진 값과 설명만 채웠다.

| 문서 | 변경 전 | 변경 후 | 근거 |
|---|---|---|---|
| [api-spec 1.5](../design/api-spec.md) | 상태 코드값 표에 난이도 없음 | `돌아보기 난이도`: `EASY` 쉬웠어 · `NORMAL` 보통 · `HARD` 어려웠어 | 1.5는 API 값을 영문 코드 + 한글 이름으로 정하고(판정 결과·생각 유형·입력 방식 등), ERD·DDL `reflection.difficulty`는 `EASY·NORMAL·HARD`만 허용. 한글(쉬웠어·보통·어려웠어)은 FN-LRN-12·usecase 4.5의 화면 이름 |
| api-spec 4.1 | `/internal/attempts/...`는 "2.2 경로와 1:1"만 | 마무리·돌아보기·자기 평가의 요청·응답·오류, 시도 상세의 `reveal`·`revealKind`·`checklist`·`reflection` | core가 그대로 전달할 응답 모양이 필요 |
| [sequence-diagram 3.3](../design/sequence-diagram.md) | 돌아보기 요청 `{difficulty, changedText}`, 잠금 없음 | `{difficulty, text}`(api-spec 2.2와 같게), 마무리·돌아보기의 시도 행 잠금, 마무리 다시 요청, 자기 평가 409 | api-spec 2.2와 프론트가 `text`. 필드 이름 `changedText`는 ERD 컬럼(`changed_text`)을 따른 것으로 보임 |
| [class-diagram 4.1](../design/class-diagram.md) | `Attempt.finish·complete`, `FinishPolicy.canFinish`, 서비스 메서드 이름만 | `Attempt.requireFinished()` 추가, `finish`·`saveReflection`·`saveSelfAssessment` 처리 순서와 공개 내용, `AttemptRepository` 메서드 | 아래 "설계와 다른 점" |
| [state-diagram 3.2](../design/state-diagram.md) | 마무리 행에 다시 요청 없음 | 다시 요청하면 기록 없이 같은 결과, 자기 평가는 마무리 뒤·완료 전 | 아래 "정한 것" |
| class-diagram 4.2, sequence-diagram 3.2 | `saveResult`가 시도를 다시 확인하지 않음 | `saveResult`가 시도 행을 잠그고 다시 확인해 마무리된 시도에는 되묻기를 저장하지 않음 | 아래 "마무리 경합" |

## 정한 것 (설계를 따르거나 설계에 없던 값을 채운 것)

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 마무리 조건 | 시도 안에 판정 `DONE` 1회 이상(결과 무관, 보류 포함). 대기·처리 중·실패만 있거나 답변이 없으면 `409 REVEAL_CONDITION_UNMET`. 되묻기에 답하지 않아도 마무리 가능 | P04, class-diagram `FinishPolicy.canFinish`, api-spec 2.2 "되묻기에 답하지 않고 `FINISH` 가능" |
| 처리 순서 | 시도 행 잠금·본인 확인 → 타임라인 → `FinishPolicy.canFinish` → `Attempt.finish(now)` → `finished_at` 기록 → 공개 내용 | sequence-diagram 3.3 순서. 엔티티가 판단하고 Repository가 조건부 UPDATE(`WHERE status='IN_PROGRESS' AND finished_at IS NULL`)로 저장하는 점은 #23 초안·#25 판정과 같음 |
| 마무리 다시 요청 | 이미 마무리했으면 기록을 바꾸지 않고 같은 결과(완료한 시도도) | 프론트 실제 어댑터는 마무리 뒤 시도 상세를 다시 읽고, 같은 요청이 두 번 와도 결과가 같아야 함. 상태 다이어그램의 완료 뒤 409 대상(답변·초안·도움·돌아보기)에 마무리는 없음 |
| 공개 내용 `reveal` | 시도에 고정된 기준표 버전의 `example_answer` | FN-LRN-11 "닫힌 문제는 정답, 열린 문제는 예시 답". 데모 시드(#22)의 닫힌 문제 예시 답은 "정답: … (해설)"로 써 있어 그대로 정답 공개가 됨. 예시 답이 없는 기준표면 `null` |
| `revealKind` | 고르기·순서·분류·풀이 단계 `ANSWER`, 서술·논술 `EXAMPLE` | api-spec 3.8 `ANSWER|EXAMPLE`, FN-LRN-11 닫힌·열린 문제. 풀이 단계는 정답(`answer_key.finalAnswer`)이 있는 문제. 프론트 목업(`demoGateway.ts`)과 같음 |
| 체크리스트 | 기준표 요소 전체를 기준표 순서로. 이 시도의 처리 완료 판정 중 **원문 구절과 함께 충족된 적이 있는** 요소만 체크하고 가장 최근 구절·출처를 표시, 아니면 `satisfied:false`·`quote:null`·`sourceType:null` | api-spec 3.8 "Element는 3.2 형식, 체크는 satisfied와 원문 인용 존재가 모두 확인된 요소만", FN-LRN-11 "근거 구절이 실제 확인된 요소만 체크하고 그 구절 표시". 보완 답변의 ai 판정은 그 답변 글만 보므로(#25) 마지막 답변만 쓰면 앞 답변에서 확인된 요소가 빠짐 |
| "들어가면 좋은 생각" | 체크리스트·자기 평가 대상은 기준표 요소 전체 | 기획서 4.2 "정답·예시 답과 '들어가면 좋은 생각' 체크가 열리고", api-spec 3.8 `checklist: Element[]`, 프론트 목업 모두 요소 전체. ERD `rubric_element.good_thought`("들어가면 좋은 생각", 필수 아님 표시)만으로 좁히면 고르기 미션(요소 1개, 필수)은 체크리스트가 비게 됨 |
| 체크리스트 시점 | 읽을 때 처리 완료 판정으로 계산. 마무리 뒤에 판정이 끝난 답변(마무리 전에 제출한 답변)이 있으면 시도 상세의 체크리스트에 더해짐 | 저장된 판정이 근거. 마무리 결과를 따로 저장하는 테이블은 ERD에 없음 |
| 돌아보기 요청 | `{difficulty, text}`. `difficulty`는 `EASY·NORMAL·HARD` 필수(없거나 값 밖이면 `400 VALIDATION_FAILED`), `text`는 선택이고 빈 글이면 `null`로 저장(`changed_text`) | P04 "난이도 필수·달라진 점 선택", api-spec 1.5(위)·2.2, DDL CHECK. ERD·DDL은 `difficulty` NULL 허용이지만 P04가 필수라 API에서 막음(스키마는 바꾸지 않음) |
| 돌아보기 처리 | 시도 행 잠금 → `Attempt.complete(now)`(완료 뒤 `409 ATTEMPT_CLOSED`, 마무리 전 `409 REVEAL_CONDITION_UNMET`) → 같은 트랜잭션에 `reflection` 저장 + `IN_PROGRESS → COMPLETED`·`completed_at` | sequence-diagram 3.3, state-diagram 3.2·9장. 동시에 보내도 잠금으로 하나만 완료 |
| 돌아보기 응답 | `200 {attemptId, status:"COMPLETED", reflection:{difficulty, text}}`. 완료 시점(`completed_at`)은 저장하고 시도 상세·기록 조회에서 확인 | sequence-diagram 3.3 "200 학습 완료", class-diagram `saveReflection(attemptId, command)`(반환 없음) 그대로 |
| 자기 평가 시점 | 마무리 뒤·완료 전 (마무리 전 `409 REVEAL_CONDITION_UNMET`, 완료 뒤 `409 ATTEMPT_CLOSED`) | sequence-diagram 3.3에서 마무리 뒤·돌아보기 전 선택 단계, 완료 뒤 쓰기는 409(state-diagram 3.2) |
| 자기 평가 요청 | `{checks:[{elementId, checked}]}`. 비었거나 같은 요소가 두 번이거나 이 시도 기준표에 없는 요소면 `400 VALIDATION_FAILED`. 일부 요소만 보내도 됨, 다시 보내면 `checked`만 바꿈(UK `(attempt_id, rubric_element_id)`) | class-diagram `saveSelfAssessment(attemptId, checks)`, ERD UK. 사용자 결정(10/28) |
| 자기 평가 응답 | 기준표 요소마다 `{elementId, label, selfChecked(체크하지 않은 요소는 null), aiChecked(체크리스트의 체크), quote}` 배열 | FN-LRN-13 "AI 확인 항목과 나란히", class-diagram 반환형 `List`. api-spec 1.1 목록 봉투는 `page`·`size`로 조회하는 목록 규칙이라 해당 없음. 답변·판정 행은 바꾸지 않음(테스트로 확인) |
| 시도 상세 | `reveal`·`revealKind`·`checklist`는 마무리 뒤에만, `reflection{difficulty, text}`은 돌아보기 뒤에만, 그 전에는 `null` | api-spec 3.8 "finish 성공 후에만", api-spec 3.8 학생 홈 "마무리 전에 제공하지 않음". 프론트 실제 어댑터는 마무리 전에 이 값이 있으면 거부하고, finish·reflect 뒤 시도 상세를 다시 읽음 |
| 잠금 | 마무리·돌아보기·자기 평가 모두 `AttemptRepository.lockById`(답변 제출 #24와 같은 시도 행) | 같은 시도의 쓰기를 한 줄로 세움. 잠금 순서는 모두 "시도 → 판정" |

## 마무리 경합 (#26 이슈 코멘트)

PR #78(#25) 리뷰에서 #26으로 나뉜 항목: 피드백은 ai 호출 **전에** 읽은 시도로 되묻기 여부를 정해, 판정이 `RUNNING`인 동안 마무리하면 마무리된 시도에 되묻기가 저장될 수 있었다(응답 `nextActions`는 읽는 시점 상태라 `[]`, 행만 남음). 코멘트의 두 방법 중 두 번째를 따랐다.

| 방법 | 결정 | 근거 |
|---|---|---|
| finish가 같은 시도에 `RUNNING` 판정이 있으면 기다리거나 거절 | 하지 않음 | 마무리 조건은 "판정 `DONE` 1회 이상"(P04, `canFinish`)뿐이라 새 조건이 붙음 |
| `saveResult` 직전에 시도를 다시 확인 | 반영 | `JudgmentService.saveResult` 트랜잭션 처음에 시도 행을 `FOR UPDATE`로 잠그고 마무리·완료 전인지 다시 읽어, 닫혔으면 판정·요소만 저장하고 되묻기는 저장하지 않음. 마무리도 같은 행을 잠가 저장과 차례로 처리됨(저장이 먼저면 되묻기가 있는 채로 마무리, 마무리가 먼저면 되묻기 없이 저장). 시그니처는 그대로 |

#25에서 한때 이 PR에 넣었다가 리뷰대로 되돌린 커밋(`e03eff0`·`9237859`)을 다시 가져와, 경합 테스트는 SQL 대신 실제 `AttemptService.finish`로 마무리하도록 바꿨다(첫 답변 `DONE` → 되묻기에 답한 보완 답변을 판정하는 중에 마무리).

## 설계와 다른 점

| 설계 | 구현 | 이유 |
|---|---|---|
| `Attempt --> FinishPolicy` | 서비스가 `FinishPolicy.canFinish(timeline)`를 부른 뒤 `Attempt.finish(now)` | `Attempt.finish(now)` 시그니처는 타임라인을 받지 않음. sequence-diagram 3.3도 "타임라인 조회 → canFinish → finished_at 기록" 순서. 시그니처를 바꾸지 않고 순서를 따름 |
| `Attempt`: `requireOpen`·`requireAnswerable`·`finish`·`complete` | `requireFinished()` 추가 | 돌아보기(`complete`)와 자기 평가가 같은 확인(완료 뒤 `ATTEMPT_CLOSED`, 마무리 전 `REVEAL_CONDITION_UNMET`)을 씀. `requireAnswerable`과 같은 방식 |
| `AttemptRepository <<repository>>` (메서드 없음) | `finish`·`complete`·`insertReflection`·`findReflection`·`saveSelfAssessments`·`findSelfAssessments` | 돌아보기·자기 평가 Repository는 설계에 없어 #23 생각 열기 기록처럼 `AttemptRepository`에 둠 |

## 기존 파일 수정

| 파일 | 변경 | 근거 |
|---|---|---|
| `judgment/service/JudgmentService.kt`, `judgment/repository/JudgmentRepository.kt`·`JudgmentMapper.kt`, `mybatis/judgment/JudgmentMapper.xml` | `saveResult`가 시도 행을 잠그고 다시 확인(`lockAttemptOpen`) | 위 "마무리 경합". #26 작업 위치(`attempt/`) 밖이지만 이슈 코멘트가 정한 두 번째 방법 |
| `judgment/facade/FeedbackConcurrencyTest.kt` | 경합 테스트 2개(실제 마무리, 마무리가 잠근 동안 저장이 기다림) | 위와 같음 |
| `attempt/service/AttemptService.kt` | `lockForAnswer`가 같은 잠금(`lockOwned`)을 씀 | 마무리·돌아보기·자기 평가와 같은 잠금. 동작 같음 |
| 테스트 `TestRows.kt` | `judged(answerId, elements, result)`: 판정을 처리 완료로 직접 만듦 | 판정 실행은 피드백 API(#25)라 마무리 테스트에서는 저장된 판정만 필요 |

## 프론트 확인 (프론트 담당)

| 항목 | 프론트 타입·목업 | 구현 | 근거 |
|---|---|---|---|
| 돌아보기 난이도 | `Reflection.difficulty: '쉬웠어' \| '보통' \| '어려웠어'`, 보내는 값도 한글 | `EASY·NORMAL·HARD`만 받음(한글은 `400`), 시도 상세 `reflection.difficulty`도 코드 | api-spec 1.5 코드값 규칙, DDL CHECK. 화면은 코드 → 한글로 바꿔 표시 |
| 달라진 점 없음 | `text: string` | 빈 글이면 `text: null` | 없는 값은 `null`(#25와 같음). 화면은 이미 `text \|\| '별도 문장 없음'` |
| 체크리스트 | 목업은 마지막 답변의 요소만 | 모든 답변의 처리 완료 판정을 합침 | 위 "체크리스트" |
| 자기 평가 | 타입·화면 없음 | 요청 `{checks:[{elementId, checked}]}`, 응답 배열 `[{elementId, label, selfChecked, aiChecked, quote}]` | 새 계약 |
| 마무리·돌아보기 응답 본문 | 쓰지 않고 시도 상세를 다시 읽음 | 마무리 `{attemptId, finishedAt, reveal, revealKind, checklist}`, 돌아보기 `{attemptId, status, reflection}` | 다시 읽어도 같은 값 |
| 오류 | 목업은 난이도 오류도 `REVEAL_CONDITION_UNMET` | 난이도 오류는 `400 VALIDATION_FAILED`, 마무리 전 `409 REVEAL_CONDITION_UNMET`, 완료 뒤 `409 ATTEMPT_CLOSED` | api-spec 1.3 |

report 담당 확인: api-spec 3.4 주간 리포트 예시 `reflections[].difficulty`가 `"보통"`(한글). learning 기록 조회(#27)는 코드(`NORMAL`)를 줄 예정이라, 리포트·ai 문장 생성이 코드를 받아 한글로 바꿀지 확인 필요.

## 검증

- `./gradlew clean test bootJar`: 152개 통과, 실패·생략 0개. 새로 추가 22개: `AttemptFinishTest` 12(Testcontainers), `AttemptControllerTest` 4, `AttemptConcurrencyTest` 2(별도 컨테이너, 실제 커밋), `ChecklistTest` 2, `FeedbackConcurrencyTest` 2(경합). `docker build` 성공, 배포 JAR에 WireMock 없음. 기능 커밋을 각각 따로 꺼내 테스트해 모두 통과(도메인·저장·서비스·API·체크리스트 테스트·마무리 경합·동시 마무리 테스트 순으로 130·130·143·147·149·151·152개. develop(#83) 병합은 learning 코드를 바꾸지 않았고, 돌아보기 반환 정리(`08d3e33`) 뒤 152개).
- 이슈 #26 완료 조건
  - 판정 없이 finish 시 409: 답변 없음, 판정 `PENDING`·`RUNNING`·`FAILED`만 있을 때 모두 `409 REVEAL_CONDITION_UNMET`, `finished_at`은 그대로
  - 완료 후 답변·초안 변경 불가: 돌아보기 뒤 답변·초안·생각 열기·돌아보기·자기 평가 모두 `409 ATTEMPT_CLOSED`(마무리 뒤 답변 제출도 409)
- 그 밖의 경로: 보류만 있어도 마무리, 되묻기에 답하지 않아도 마무리, 닫힌 문제 `ANSWER`·열린 문제 `EXAMPLE`, 체크리스트 합치기(v1 주장·v2 근거 → 둘 다 체크, 가장 최근 구절, 충족이어도 구절이 없으면 체크하지 않음), 마무리 다시 요청 같은 결과, 시도 상세 공개 시점, 돌아보기 저장과 완료 시점·빈 글 null, 한글·없는 난이도 400, 자기 평가 저장·다시 보내면 변경·답변·판정 행 그대로(`row_to_json` 비교), 자기 평가 400(빈 목록·중복·기준표 밖), 다른 학생 403
- 동시 요청(별도 PostgreSQL 컨테이너, 실제 커밋): 같은 시도에 마무리 8개 → 모두 같은 결과·마무리 시각 하나, 돌아보기 8개 → 1개 완료·7개 `409 ATTEMPT_CLOSED`·돌아보기 1행
- 마무리 경합: 보완 답변의 되묻기 응답을 늦추는 사이 실제 `finish` → 판정 `DONE`, 되묻기 0행, `nextActions: []`. 다른 트랜잭션이 시도 행을 잠근 동안 판정 저장이 잠금을 기다리고, 마무리 커밋 뒤 되묻기 없이 저장
- 보호 장치를 하나씩 빼면 테스트가 실패함을 확인(15개): 마무리 조건, 체크리스트 합치기, 구절 있는 충족만 체크, 가장 최근 구절, 자기 평가는 마무리 뒤, 돌아보기는 마무리 뒤, 돌아보기 시도 잠금, 마무리 시도 잠금, 마무리 다시 요청, 자기 평가 중복·기준표 밖 요소, 빈 달라진 점 null, 마무리 전 공개 안 함, 판정 저장 때 다시 확인, 판정 저장 때 시도 잠금
- compose 실제 확인(에픽 #21 완료 조건, `docker compose up -d --build learning-service ai-service`, OpenAI `gpt-6.1-terra`, core 없이 learning `/internal/*` 직접 호출, 확인 후 만든 시도 2건만 삭제·컨테이너 정지, 최종 코드 08d3e33):

| 미션 | 흐름과 결과 |
|---|---|
| 서술형(시드 2번 "쉬는 시간을 늘린다면?") | 시작 201 → 답변 전·피드백 전 마무리 409 → 피드백 200 8.0초 `CORRECT`(주장·근거 충족, 다른 관점 미충족)·`ONE_STEP_MORE` → 마무리 전 돌아보기 409 → 보완 답변 피드백 200 9.7초 `PARTIAL`(근거·다른 관점 충족, 주장 미충족)·`TELL_MORE` → 마무리 200 `EXAMPLE`, 체크리스트 세 요소 모두 체크(주장은 v1 구절, 근거·다른 관점은 v2 구절) → 다시 마무리 같은 결과 → 마무리 뒤 답변 409 → 자기 평가 200(세 요소 자기 체크, AI 확인 나란히) → 한글 난이도 400 → 돌아보기 200 `{attemptId, status:"COMPLETED", reflection}` → 돌아보기 다시 409 → 시도 상세 `COMPLETED`·체크리스트 마무리 결과와 같음·돌아보기·`nextActions []` → 초안·자기 평가 409 |
| 고르기(시드 1번 "한 화분만 시든 까닭") | 시작 → 정답 `c2` 피드백 200 0.03초 `CORRECT`·되묻기 없음·`[FINISH]`(규칙 판정, 모델 없음) → 마무리 200 `ANSWER` "정답: 물을 받지 못해서…", 체크리스트 "원인 찾기" 체크(`ANSWER_KEY`, 고른 답) → 돌아보기(난이도만) 200 `COMPLETED`·`text: null` → 시도 상세 같음 |

- 체크리스트 합치기가 실제로 필요한 경우: 위 실행에서 보완 답변은 주장을 충족하지 않았지만(보완 답변 글만 판정) 체크리스트는 첫 답변의 주장 구절을 유지함. 같은 흐름의 앞선 실행(리뷰 반영 전 코드)에서는 보완 답변이 `HELD`(요소 없음)였고, 이때도 첫 답변의 요소를 유지함. 같은 답에도 ai 판정이 실행마다 다른 점은 #22·#25에서 본 것과 같음(사람 검증 P11, 판정 규칙 #79)

## 후속

- 공개 검사(#81): 닫힌 문제의 정답은 예시 답 글로 보여 주므로(위 "공개 내용") 예시 답에 정답이 들어가야 함(시드 7개는 모두 "정답: …" 또는 "최종 답: …" 포함). 예시 답이 없는 기준표는 `reveal`이 `null`. 공개 전 예시 답 필수(닫힌 문제는 정답 포함)를 공개 검사에 넣을지 같이 정하면 좋음. 정답 키(`answer_key`)로 정답 글을 만드는 방법은 예시 답과 정답이 두 번 보이고, 분류 그룹 이름 저장 위치가 정해지지 않아(#79) 쓰지 않음
- 달라진 점 길이 상한: 문서에 없어 두지 않음(답변 길이 상한과 함께 후속, #24 리포트)
- 학습 기록 조회(#27): 돌아보기 원문(`difficulty` 코드·`text`)과 완료 시점을 기록 조회 응답에 포함
