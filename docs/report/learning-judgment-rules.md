# 이슈 #79 learning 판정 규칙 확정 (수학 단위·풀이 단계 결합·분류)

작성일: 2026-10-28. 기준: #105 머지 후 develop 1208ead(#106 포함) 위에서 작업. [이슈 #79](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/79), [기능 명세 FN-LRN-04·FN-JDG-01·02](../design/functional-spec.md), [상태 다이어그램 3.3](../design/state-diagram.md), [API 명세 2.2·3.8·4.1](../design/api-spec.md), [ERD 4.1](../design/erd.md), [#25 피드백 보고서](learning-feedback.md) "임시로 정한 것"·"후속".

#25에서 설계에 규칙이 없어 임시로 두거나 넣지 않은 판정 규칙 세 가지(수학 단위, 풀이 단계 결합, 분류 정답 키)를 확정했다. 이슈 지침대로 설계 문서를 먼저 고친 뒤 구현했다.

## 설계 문서 갱신

| 문서 | 변경 전 | 변경 후 | 근거 |
|---|---|---|---|
| [기능 명세](../design/functional-spec.md) FN-JDG-02 | 분수·소수·한글 분수 동치만 | 단위는 비교하지 않음(정답 키는 수만, 단위는 미션 답 단위로 답 칸 뒤 고정), 풀이 단계는 풀이와 최종 답을 합쳐 판정하고 최종 답 결과를 "최종 답" 요소로 기록 | 아래 "사용자 결정" |
| 기능 명세 FN-LRN-04 | 선택지·순서·분류 활동 | 분류는 미션 그룹에 넣는 정답이 정해진 분류, 아이가 기준을 정하는 분류(기획서 5장 "분류 기준")는 서술 미션으로 이유를 판정. 없는 그룹 배정도 보완 안내 | 아래 "사용자 결정" |
| [state-diagram 3.3](../design/state-diagram.md) | 풀이 단계 결합은 "#25에서 정한 임시 규칙" | 결합 규칙(표 그대로)과 최종 답 요소 기록, "임시" 삭제 | FN-JDG-02 |
| [ERD 4.1](../design/erd.md) | `mission_version`에 분류 그룹·답 단위 자리 없음 | `categories jsonb`·`answer_unit varchar`(NULL 허용), `rubric_element.code = 'FINAL_ANSWER'` 예약, #79 비고 | 아래 "사용자 결정" |
| [API 명세](../design/api-spec.md) 2.2·3.8·4.1 | 미션 상세에 `categories` 미제공(#79 결정 전), 풀이 판정 설명 | 미션 응답에 `categories`·`answerUnit`, 풀이 최종 답은 수만·단위 비교 안 함, 관리자 미션 버전에 `answerUnit?`, 4.1 미션 조회 줄 | 학생 화면이 그룹 이름·단위를 받아야 함 |
| [class-diagram 4.2](../design/class-diagram.md) 처리 순서 2·3 | 풀이 단계 합침, 유출 검사용 정답(선택지 이름·정답 순서·최종 답) | 최종 답 요소는 ai 요청에서 빼고 정답 키 결과로 기록, 유출 검사용 정답에 답 단위·"선택지 이름: 그룹 이름" | 위 결정 |
| [contracts/openapi/learning-service.yaml](../../contracts/openapi/learning-service.yaml) | `Mission`에 두 필드 없음 | `categories`·`answerUnit` 필수 필드 추가 | 위와 같음 |

## 사용자 결정 (10/28)

| 항목 | 결정 | 이유 |
|---|---|---|
| 수학 단위 | 단위는 비교하지 않음. 정답 키에는 수만 넣고, 단위는 미션에 저장해 답 칸 뒤에 고정해 보여 줌(빈칸 채우기). 학생이 단위를 써도 앞쪽 수만 비교 | 단위 누락·환산 규칙을 새로 만들지 않고 화면에서 단위를 정해 줌. 이슈 "확인 필요"(단위 비교 여부)의 답 |
| 단위 저장 위치 | `mission_version.answer_unit` 칸 추가, 미션 응답 `answerUnit` | 답 칸 뒤에 고정하려면 화면이 단위를 받아야 함 |
| 최종 답 체크리스트 | 넣음. 풀이 단계 기준표에 "최종 답" 요소(`code = 'FINAL_ANSWER'`)를 두고 ai에 보내지 않고 정답 키 결과로 기록 | 최종 답이 틀려 `PARTIAL`인데 체크리스트는 풀이 요소만 있어 "다 맞았는데 부분 정답"으로 보이던 문제(#25 리포트) |
| 분류 | `mission_version.categories` 칸 추가, 그룹 이름 제공·없는 그룹 422·유출 검사 정답 전달. 분류 입력은 정답이 정해진 분류, 아이가 기준을 정하는 분류는 서술 미션 | api-spec 관리자 미션 계약(`versions[].categories?`)과 프론트 관리자 화면이 이미 미션 버전에 그룹을 둠. 기획서 5장은 "분류 기준"을 정답이 여러 개인 문항(이유를 봄)으로 둬 정답 키 판정과 다른 문항 |
| 마이그레이션 | learning `V6__mission_categories_and_answer_unit.sql`을 새로 추가, 기존 V1~V5는 수정하지 않음, ERD 같이 갱신 | 팀 선례(core V8·V9·V12·V13을 기능 이슈에서 추가, ERD "기존 마이그레이션은 수정하지 않는다"), CI `ci-db-schema`가 ERD와 대조 |

## 정한 것 (설계를 따르거나 설계에 없던 값을 채운 것)

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 풀이 단계 결합 | state-diagram 3.3 표 그대로: 최종 답 동치 + 풀이 `CORRECT` → `CORRECT`, 최종 답 불일치 + 풀이 `RETHINK` → `RETHINK`, 한쪽만 → `PARTIAL`, ai 보류 → 보류(최종 답 결과는 쓰지 않음) | 표는 #25부터 설계에 있었고 기능 명세에 없어 "임시"였음. FN-JDG-02에 적어 확정 |
| 최종 답 요소 기록 | `FINAL_ANSWER` 요소는 ai 판정 요청에서 빼고(`Rubric.aiElements`), 결합 뒤 `verified = true`·`sourceType = ANSWER_KEY`·근거 글자는 학생이 쓴 최종 답으로 저장, 최종 답이 맞을 때만 충족. 보류면 남기지 않음(보류는 요소를 저장하지 않음, #6 B안) | 고르기 정답 키 근거 기록(`withAnswerKey`)과 같은 방식. 되묻기 요청에는 최종 답 요소도 보내 LLM이 답을 다시 보게 함(실제 확인: "60÷2를 다시 계산해 보면?") |
| 최종 답 요소 표시 | `rubric_element.code`의 예약 값 `FINAL_ANSWER` | 컬럼을 늘리지 않음. 코드는 기준표 버전 안에서만 쓰는 값 |
| 유출 검사 정답 | 수학은 최종 답에 답 단위를 붙인 값(`30 m²`, 지금까지와 같은 글자), 분류는 "선택지 이름: 그룹 이름" 목록 | ai는 정답 문자열이 질문에 그대로 있는지 보고 같은 목록을 "쓰지 말 표현"으로 LLM에 줌. 그룹 이름만 보내면 화면에 보이는 그룹을 언급하는 질문까지 막힘 |
| 답변 원문(`plain_text`) | 풀이 최종 답에 답 단위를 붙임(이미 단위로 끝나면 그대로), 분류는 "선택지 이름: 그룹 이름" | 학부모 기록·근거 원문에서 단위·그룹 이름이 보이게 |
| 분류 검사 | 모든 선택지를 미션 그룹(`categories`)에 한 번씩, 없는 그룹이면 422 `ANSWER_INCOMPLETE` | api-spec 3.8 "미정 그룹·항목·중복 배정은 422" |
| 미션 응답 | `categories`는 분류가 아니면 `[]`, `answerUnit`은 없으면 `null` | 선택지·입력 틀과 같은 방식(빈 배열) |
| 시드 수학 3문항 | 정답 키를 수만(`420`·`30`·`104`), 답 단위(`원`·`m²`·`cm³`), 기준표에 "최종 답" 요소 추가(배점 1, 필수, `judge_verified = false`) | 위 결정. 금지어(`420`·`30`·`104`)는 그대로 |

## 기존 파일 수정

| 파일 | 변경 | 근거 |
|---|---|---|
| `backend/learning-service/db/seed/demo_missions.sql` | 위 "시드 수학 3문항", 적용 안내를 V1~V6으로 | #22 시드, 새 규칙에 맞춤 |
| `answer/domain/AnswerContent.kt` | 분류 그룹 검사, 원문에 그룹 이름·답 단위 | 위 "정한 것" |
| `judgment/facade/FeedbackFacade.kt` | ai에 최종 답 요소 빼기, 결합 뒤 최종 답 요소 기록, 유출 검사 정답 | 위 "정한 것" |
| `mission/` | `MissionView.categories`·`answerUnit`, `Category`, `CategoryListTypeHandler`, 미션 조회 SQL, 응답 필드, `Rubric.aiElements`·`finalAnswerElements` | 위 "정한 것" |
| `contracts/openapi/learning-service.yaml` | `Mission` 두 필드, 미션 상세 설명 | 위 "설계 문서 갱신" |
| 테스트 | `TestRows`(그룹·단위·최종 답 요소), `AnswerServiceTest`(분류 문항에 그룹 추가) | 새 검사에 맞춘 데이터 |
| 이전 리포트 | [#22](learning-mission.md)·[#24](learning-answer.md)·[#25](learning-feedback.md)의 관련 줄에 "#79에서 확정" 표시 | 당시 기록은 그대로 두고 결론만 연결 |

## 확인 필요

| 항목 | 내용 | 대상 |
|---|---|---|
| 답 칸 뒤 단위 | 미션 응답에 `answerUnit`이 생김. 학생 풀이 화면의 최종 답 칸 뒤에 고정해 보여 줘야 함(지금 목업은 단위 없는 빈칸) | 프론트 |
| 분류 그룹 | 미션 응답 `categories`를 지금 프론트 타입(`categories?`)과 같은 모양으로 제공. 목업 분류 문항과 실제 응답이 같아짐 | 프론트 |
| 체크리스트·자기 평가 | 수학 문항에 "최종 답" 항목이 하나 더 생김 | 프론트 |
| DB 스키마 | learning V6로 `mission_version`에 칸 2개 추가 | DB 담당(inyoung9629)에게 알림 |
| 미션 공개 검사 | 분류는 그룹 1개 이상, 풀이 단계는 최종 답 요소 외 요소 1개 이상(ai는 요소 0개를 받지 않음), `FINAL_ANSWER`는 풀이 단계에만 | #81 |

## 검증

- `./gradlew test`: 186개 통과(새 3개: 풀이 최종 답 요소, 보류면 최종 답 요소 없음, 분류 그룹·유출 검사), 기존 테스트에 그룹·단위·원문 검사 추가. `scripts/tests` 54개 통과
- 기능 커밋을 각각 따로 꺼내(worktree) 테스트: 미션 그룹·단위 183개, 분류 답변 183개, 풀이 최종 답·유출 검사 186개, 리포트까지 186개, 커밋마다 `scripts/tests` 54개 통과
- 보호 장치를 하나씩 빼면 테스트가 실패함을 확인(11개): 최종 답 요소는 ai에 안 보냄, 최종 답 요소 기록, 맞을 때만 충족, 보류 유지(조기 반환), 분류는 미션 그룹만, 분류 유출 검사 정답, 수학 유출 검사에 단위, 풀이 원문에 단위, 분류 원문은 그룹 이름, 미션 조회에 그룹·단위. "보류면 최종 답 요소 없음"은 결합에서 빼도 `Judgment.hold`가 요소를 저장하지 않아 두 겹으로 막혀 있음
- compose 실제 확인(`docker compose up -d --build learning-service ai-service`, learning 스키마 5 → 6 적용, 시드 다시 적용, 실제 OpenAI `gpt-6.1-terra`, 만든 시도 1건만 삭제·컨테이너 정지):

| 단계 | 결과 |
|---|---|
| 미션 상세(초5 사다리꼴 넓이) | `answerUnit: "m²"`, `categories: []` |
| 풀이 맞고 답 `28` | 9.6초 `PARTIAL`, 요소 문제 파악·방법 세우기 충족, 결과 확인 미충족, **최종 답 미충족(근거 `28`, `ANSWER_KEY`)**, 되묻기 `TELL_MORE` "60÷2를 다시 계산해 보면 어떤 값이 나올까?" |
| 답 `30`으로 보완 | 10.2초 `CORRECT`, 최종 답 충족(`30`) |
| 마무리 | 체크리스트에 "최종 답" 포함, 정답 공개 `... 최종 답: 30 m²` |
| 답 원문 | `최종 답: 28 m²`, `최종 답: 30 m²`(단위 붙음) |

- DB 스키마 대조: [재현 방법](db-schema-validation.md#재현-방법)대로 개발 DB와 분리한 compose 프로젝트(`db-schema-check`, postgres 포트 미공개)에 빈 DB를 만들고 core v13·learning v6·report `20261026_01`을 적용한 뒤 `verify_db_schema.py --project`로 대조: learning_db 19개 테이블·158개 칸이 ERD와 일치, 3개 DB 제약 위반 57건 거부, CHECK 값 65개·인덱스 23개 일치(PASS). 마이그레이션 재실행은 추가 적용 없음. ERD에서 `answer_unit` 줄을 빼면 `unexpected=[('mission_version', 'answer_unit')]`로 실패함도 확인 후 되돌림. 확인 뒤 프로젝트·볼륨 삭제
- CI `ci-db-schema`와 같은 단계(report-service `.venv`에 `uv sync --frozen --no-dev`·`jsonschema==4.26.0`, 임시 `postgres:17.11-alpine`): `python -O -m unittest discover -s scripts/tests` 통과, `python -O scripts/check_db_migrations.py` PASS(적용 → ERD 대조 → 재실행 시 core·learning `migrationsExecuted=0`·이력 불변 → report downgrade/upgrade → 다시 대조, 11.8초). 임시 컨테이너·네트워크 삭제

## 후속

- 분류 문항 시드: 지금 시드에 분류 문항이 없어 실제 확인은 단위 테스트로만 함
- 기획서 5장 "분류 기준"처럼 아이가 기준을 정하는 문항은 서술 미션으로 만들 때 기준표 요소("나눈 기준을 말함", "기준이 보기의 사실에 맞음")로 판정
