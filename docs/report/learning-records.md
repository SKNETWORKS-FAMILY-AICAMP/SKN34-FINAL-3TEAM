# 이슈 #27 learning 학습 기록 조회 내부 API

작성일: 2026-10-28. 기준: #26 브랜치(`feature/learning-reflection`) 위에서 작업, #89 머지 후 develop 47e5ffe(#89·#90·#91·#98·#100, learning 코드 변경 없음)를 병합. [이슈 #27](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/27), [API 명세 1.1·1.5·1.6·2.3·3.4·3.9·4.1](../design/api-spec.md), [기능 명세 1.4 P08·FN-DSH-06~11·FN-RPT-02~06·FN-AGT-04·07·FN-ADM-02](../design/functional-spec.md), [ERD 4.2·4.3](../design/erd.md), [클래스 다이어그램 4.3](../design/class-diagram.md), [시퀀스 다이어그램 4](../design/sequence-diagram.md).

learning-service의 `/internal/records/*`·`/internal/stats`(학부모 대시보드, 분석 에이전트 도구, 주간 리포트가 같이 쓰는 조회)를 만들면서 정한 내용과 근거를 기록한다. 데이터베이스 스키마는 바꾸지 않았다.

## 설계 문서 갱신

| 문서 | 변경 전 | 변경 후 | 근거 |
|---|---|---|---|
| [api-spec 4.1](../design/api-spec.md) | 경로 6개와 한 줄 설명 | 경로마다 응답 모양(3.9·3.4·1.6 형식), 지표 4개, 시도 상세 경로 추가, 기록 조회 공통(역할·범위·KST 기간·기본 7일·집계 대상·상태·메모 제외) | 이슈 지침 "API 계약 변경이 필요하면 api-spec 먼저". core가 응답을 그대로 프록시(sequence-diagram 4)하므로 learning 응답이 곧 학부모 화면 계약 |
| [class-diagram 4.3](../design/class-diagram.md) | `countAttempts`·`findAttemptsWithTimeline`, `Metric.count(label, count, period)`, `RecordService --> RecordRepository`만, 구현 상태 "미구현" | `findEligible`·`findAnswerPairs`·`isRecorded`·`findEvidence`·`stats`, `attempt(studentId, attemptId)`, `Metric.count(label, count, formula, period)`, `RecordService --> AttemptService : 기록 목록·상세`, 처리 설명, 구현 상태 | 아래 "사용자 결정"·"설계와 다른 점" |
| [contracts/openapi/learning-service.yaml](../../contracts/openapi/learning-service.yaml) | 기록 경로는 `exists`만 | 기록 경로 7개(요약·유형·목록·상세·전후 변화·근거·운영 집계)와 스키마(`Metric`·`QueryState`·`RecordPeriod`·`RecordAttempt` 등) | #92(D6) 대조 테스트가 learning 컨트롤러 경로와 yaml 경로가 같아야 통과. 경로 수 12 → 19. 맨 위 설명의 역할 문구(기록 조회 PARENT·STUDENT·SYSTEM, 운영 집계 ADMIN·SYSTEM)도 갱신 |
| api-spec 5.4(#37 기록 존재 확인) | "#27 전체 목록·상세·통계 API는 별도 범위다" | #27에서 4.1 "기록 조회"로 추가했다(같은 실패·삭제 제외 기준) | 구현됨 |

## 사용자 결정 (10/28, 설계와 다르게 한 것은 모두 확인받음)

| 항목 | 결정 | 이유 |
|---|---|---|
| 기록 목록·상세의 시도 모양 | `RecordService`가 학생 시도 상세(`AttemptService.get`)를 재사용하고 응답에서 초안(메모 포함)만 뺌. class-diagram에 `RecordService --> AttemptService` 추가 | 프론트 `PublicAttempt = Attempt − draft`. 설계대로 `RecordRepository`로만 만들면 시도 상세·피드백·체크리스트 조립이 두 벌이 되어 모양이 어긋날 위험 |
| 시도 상세 내부 경로 | `GET /internal/records/students/{studentId}/attempts/{attemptId}` 추가 | 학부모 `GET /children/{childId}/attempts/{attemptId}`(api-spec 2.3)에 대응하는 내부 경로가 4.1에 없었음 |
| 까닭을 잇는 말 목록 | 프론트 목업 목록 `왜냐하면·때문·그래서·따라서`를 임시로(아래 "임시로 정한 것") | P08 "고정 목록"인데 목록이 문서에 없음 |
| `RecordRepository` 메서드 | `findEligible` 하나로 요약·유형별 활동·목록이 같은 집계 대상을 씀, 상세용 `isRecorded`, 운영 집계 `stats` | 같은 집계 기준 SQL을 한 곳에 둬 숫자가 서로 어긋나지 않게. 목록 상세는 위 결정으로 `findAttemptsWithTimeline`이 필요 없어짐 |
| `Metric.count`의 계산식 | `count(label, count, formula, period)` | 기능 명세 1.3 "모든 건수·비율은 기간·분자·분모·계산식·출처 유형을 함께 제공", api-spec 1.6·프론트 `Metric.formula` 필수 |

## 정한 것 (설계를 따르거나 설계에 없던 값을 채운 것)

| 항목 | 정한 내용 | 근거 |
|---|---|---|
| 집계 대상 | 기간 안에 처리 실패가 아닌(`judgment`가 없거나 `FAILED`가 아닌) 답변 제출이 있는 시도, 완료·미완료 모두, 삭제 학생(`deleted_student`) 제외. 초안만 있는 시도는 제외 | P08, FN-RPT-02(기간을 걸친 학습은 해당 기간마다). #37 기록 유무와 같은 실패·삭제 기준 |
| 시도별 사실 | 완료(`completed_at`), 최초 답변 전 생각 열기 열람, 되묻기 받음(`followup.created_at`), 보완 답변(되묻기에 답한 답변) 제출, 최근 답변 시각은 **조회 종료일까지** 일어난 것만 | P08 "도움 없이 시작한 비율 = 최초 답변 전 도움 열람 없는 시도", ERD 4.2 하단(`hint_usage.opened_at` vs 최초 `answer.submitted_at`). 시도가 집계 단위. 지난 기간을 조회해도 그 뒤의 답변·완료로 값이 바뀌지 않게(FN-RPT-02, report #51 4.1.1) |
| summary 지표 | ① 학습한 활동: 집계 대상 시도 수(건수) ② 완료한 활동: 완료 / 집계 대상 ③ 도움 없이 시작한 활동: 최초 답변 전 생각 열기를 열지 않은 시도 / 집계 대상 ④ 되묻기 후 생각을 더한 활동: 보완 답변 제출 시도 / 되묻기 받은 시도 | ① FN-DSH-07 학습 건수 ② P08 "완료 여부 별도 표시" ③ P08 ④ api-spec 1.6 예시 |
| 상태 | 응답 전체와 건수 지표는 집계 대상 수, 비율 지표는 분모로: 0건 `NO_RECORD`, 1~4건 `INSUFFICIENT_SAMPLE`(비율 `value: null`, 개수만), 5건 이상 `OK` | P08, api-spec 1.5·1.6, 이슈 완료 조건 |
| 기간 | `from`·`to`는 KST 날짜 양 끝 포함, 시각 비교는 `[from 00:00, to 다음 날 00:00)` KST. 둘 다 없으면 오늘 포함 최근 7일, `to`만 있으면 그날까지 7일, `from`만 있으면 7일 뒤(오늘을 넘지 않게)까지, `from > to`면 400. 응답 `period`는 실제 조회 기간 | api-spec 1.1, P06(기본 기간 최근 7일·오늘 포함) |
| 역할·범위 | 학생 경로는 `PARENT`·`STUDENT`·`SYSTEM`, 대상 학생이 `X-Student-Scope`에 없으면 403(UUID 비교). 근거 조회는 답변마다 학생 범위 확인. 운영 집계는 `ADMIN`·`SYSTEM`, 학생 범위 없음 | class-diagram 4.3 "모든 경로에서 requireStudent 먼저", architecture 2.3, FN-ADM-02. #37 기록 유무와 같은 역할 |
| 학생 필드 | 응답의 학생 ID는 `childId` | core가 그대로 프록시하고 api-spec 3.9·프론트 타입이 `childId` |
| thinking-types | 다섯 유형 모두, 유형마다 기간 안 시도 `[{attemptId, title}]`, 없으면 `NO_RECORD`, 있으면 `OK`. 유형 요약 문장(`summary`)은 넣지 않음 | FN-DSH-08 "미관찰, 점수·능력 부족으로 해석 금지", 문장은 리포트·ai 몫 |
| 목록 | 1.1 봉투 + `childId·state·period·inclusionRule`, 최근 답변 순, 항목의 `answers`는 1번부터 조회 종료일까지(시작일 이전 버전 포함, 시도 상태·마무리 공개·돌아보기는 지금 상태), `page` 0 이상·`size` 1~100(기본 20, 아니면 400) | api-spec 1.1·3.9 |
| 상세 | 이 학생의 시도이고 처리 실패만 있는 시도가 아니면 목록 항목과 같은 모양, 아니면 404(기간 무관) | 목록에 나오지 않는 시도는 상세도 없음 |
| changes | 조회 종료일까지 보완 답변이 있는 시도마다 최초 vs 종료일 이전 마지막 답변, `followup`은 마지막 답변이 답한 되묻기 질문, `counts`는 `[최초, 마지막]` | P08 "시도당 최초 vs 마지막 답변", api-spec 3.4 `changes` 예시 |
| 전후 변화의 수 | 글자 수(공백 포함, 코드 포인트), 문장 수(`.` `?` `!`·줄바꿈으로 나눈 비지 않은 덩어리), 까닭을 잇는 말 나온 횟수. **학생이 쓴 칸 내용만**(서술 글, 풀이 단계·최종 답, 논술 네 칸) 셈. 보여 주는 원문(`text`)은 칸 이름을 붙인 `plain_text` 그대로 | P08 계산 규칙. `plain_text`의 칸 이름("① 무엇을 구하나요?:")을 세면 학생이 쓰지 않은 글자와 `?`까지 셈 |
| evidence | `{items}` 요청 순서대로, 원문은 `plain_text`. 없는 답변(삭제로 지워진 기록 포함)·삭제 학생은 `available: false`, 원문·제목 없음. 범위 밖 학생의 답변이 섞이면 403. `answerIds`는 쉼표로 나눈 UUID 1~100개(아니면 400) | api-spec 1.6·3.9 "삭제된 항목은 quote를 재사용하지 않음", P09 물리 삭제 + 표식 |
| stats | `{period, inclusionRule, attempts, completedAttempts, students}`, 집계 대상 기준(완료는 종료일까지), 학생 원문 없음 | FN-ADM-02 "학습 시도·완료 건수". 대화·리포트 처리 현황은 core 몫 |
| 메모·초안 | 어떤 응답에도 넣지 않음 | P05, 이슈 지침 |
| MyBatis 캐시 | 기록 조회 SELECT는 `flushCache="true" useCache="false"` | 같은 트랜잭션에서 같은 조회를 다시 해도 최신 행을 읽게. #37 기록 유무와 같은 설정 |

## 임시로 정한 것

| 항목 | 값 | 확정할 곳 |
|---|---|---|
| 까닭을 잇는 말 | `왜냐하면`·`때문`·`그래서`·`따라서`(부분 문자열 횟수, `TextCounts.REASON_CONNECTIVES` 한 곳) | P08 고정 목록 확정(팀). api-spec 3.9에도 "목업만 이 목록, 서버 확정 목록이 아님"으로 남아 있음 |

## 기존 파일 수정

| 파일 | 변경 | 근거 |
|---|---|---|
| `contracts/openapi/learning-service.yaml` | 기록 경로 7개·스키마 추가 | 위 "설계 문서 갱신" |
| `scripts/tests/test_record_exists_openapi.py` | learning 컨트롤러 경로 수 12 → 19 | 경로 목록은 yaml과 그대로 대조 |

`attempt/`·`judgment/` 코드는 바꾸지 않았다(시도 상세는 `AttemptService.get`을 그대로 부름).

## 확인 필요 (통합 때)

| 항목 | 내용 | 대상 |
|---|---|---|
| ④ 지표의 분모 | 프론트 목업 "생각을 덧붙인 활동"은 분모가 집계 대상 전체, 서버는 api-spec 1.6대로 되묻기 받은 시도 | 프론트 |
| 근거 없는 항목 | `available: false`이면 `attemptId`가 `null`일 수 있음(삭제로 지워진 답변). 프론트 `Evidence.attemptId`는 필수 | 프론트 |
| 목록 상태 | 목록도 `state`를 집계 대상 수로 줌(1~4건이면 `INSUFFICIENT_SAMPLE`) | 프론트 |
| 돌아보기 난이도 | 목록 항목의 `reflection.difficulty`는 코드(`EASY·NORMAL·HARD`). api-spec 3.4 리포트 예시는 `"보통"` | report·ai·프론트(#26 리포트와 같음) |
| 까닭을 잇는 말 | 위 임시 목록 확정 | 팀 |
| core 연결 | core는 지금 기록 유무(`exists`)만 부름. 학부모 대시보드·근거·운영 집계 프록시는 core 이슈에서 이 계약으로 | core |
| core #40 예정 계약 (`feature/core-dashboard-queries`, `planned-issue-27`) | 학생 대시보드 `home`·`thinking-activities` 경로를 #27에서 만들지, 역할별 `studentId`(학생)/`childId`(학부모) 필드, 학생 목록 `status` 필터, 상세의 `state`·`period`·`from`·`to`, `from`·`to`는 둘 다 또는 둘 다 없음, 학생 범위 1명, 병합 순서. 10/28 질문 보냄, 답을 받아 반영 | core(kimdongseop) |
| report #51 예정 입력 (`report-*` 브랜치 api-spec 4.1.1) | 조회 종료일 기준은 반영함(위 "시도별 사실"·"목록"·"changes"). 남은 것: 시도 항목 `hintUsages:[{openedAt}]`·`completedAt`·`reflection.createdAt` 추가, 그 기간에 쓴 돌아보기만·미작성 `written:false`, `changes` 페이지 봉투, 삭제 표식 항목 필요 여부, 병합 순서. 10/28 질문 보냄 | report(inyoung9629) |
| 다른 브랜치와 파일 충돌 | `core-dashboard-queries`는 api-spec·대조 테스트와 충돌, learning OpenAPI는 같은 경로가 두 번 들어감. `report-metrics`·`report-narrative`·`report-deletion`은 api-spec과 충돌. #27을 먼저 머지하고 각 브랜치가 실제 계약으로 정리하는 순서를 제안 | core·report |

## 검증

- `./gradlew clean test bootJar`: 172개 통과(새로 20개: `RecordServiceTest` 12·`RecordControllerTest` 5·`RecordDomainTest` 3, Testcontainers PostgreSQL). `scripts/tests` 46개 통과(OpenAPI 경로 대조 19개). 기능 커밋을 각각 따로 꺼내 테스트해 모두 통과(도메인·저장소·서비스·내부 API 순으로 155·155·166·171개, 커밋마다 scripts/tests도 통과. #26 문서 수정 병합은 learning 코드를 바꾸지 않음)
- 이슈 #27 완료 조건
  - 0건·1~4건·5건 이상 케이스별 `state`: 0건 `NO_RECORD`, 4건 `INSUFFICIENT_SAMPLE`(비율 `value: null`), 5건 `OK`(완료 1/5 → 0.2)
  - 범위 밖 학생 403: 범위에 없는 학생·범위 헤더 없음·허용하지 않는 역할(`ADMIN`·`CONTENT`) 403, 근거에 범위 밖 학생의 답변이 섞이면 403, 운영 집계는 학부모 403
- 그 밖의 경로: 집계 대상(기간 밖·초안만·처리 실패만 제외, 미완료 포함), 조회 종료일 기준(이번 주 조회에 다음 주 보완 답변·완료·되묻기가 섞이지 않고 다음 주 조회는 1번부터), KST 경계(끝 날짜 23:59 포함·다음 날 0:00 제외·시작 날짜 0:00 포함), 도움 없이 시작(최초 답변 뒤 열람은 도움 없이 시작으로 셈), 생각을 더한 활동(분모 = 되묻기 받은 시도), 다섯 유형·미관찰, 목록 페이지·최근 답변 순, 상세 404(다른 학생·처리 실패만), 전후 변화(최초 vs 마지막, 마지막 답변이 답한 되묻기, 풀이 단계는 칸 이름을 빼고 셈), 근거(요청 순서, 없는 답변·삭제 학생 `available:false`·원문 없음), 삭제 학생 요약 `NO_RECORD`, 운영 집계, 입력 오류 400(날짜 형식·`from > to`·페이지·`answerIds`), JSON 모양(`childId`·`period{from,to}`·목록에 `draft` 없음)
- 보호 장치를 하나씩 빼면 테스트가 실패함을 확인(22개): 처리 실패만 있는 시도 제외, 기간 안 답변만, 끝 날짜 포함, KST 기준, 삭제 학생 제외, 분모 5 미만 비율 없음, 최초 답변 전 도움만, 생각을 더한 활동 분모, 근거 범위 검사, 삭제 학생 근거 원문 없음, 학생이 쓴 칸만 셈, 상세는 이 학생의 기록만, 역할 검사, 학생 범위 검사, 목록에서 초안 빼기, 페이지 범위, 종료일 기준 6개(완료·되묻기 받음·보완 답변·전후 변화 마지막 답변·운영 집계 완료·목록 답변)
- compose 실제 확인(`docker compose up -d --build learning-service ai-service`, OpenAI `gpt-6.1-terra`, core 없이 learning `/internal/*` 직접 호출, 확인 후 만든 시도 2건만 삭제·컨테이너 정지):

| 단계 | 결과 |
|---|---|
| 학생 기록 만들기 | 서술형(시드 2번): 답변 → 피드백 `PARTIAL`·`TELL_MORE` → 보완 답변 → 피드백 `PARTIAL`. 고르기(시드 1번): 생각 열기 → 정답 → 마무리 → 돌아보기(`EASY`) |
| summary(학부모) | `INSUFFICIENT_SAMPLE`, 기간 오늘 포함 7일. 학습한 활동 2, 완료한 활동 1/2, 도움 없이 시작한 활동 1/2(고르기는 답하기 전 생각 열기), 되묻기 후 생각을 더한 활동 1/1, 비율은 모두 `value: null` |
| thinking-types(학부모) | `ANALYZE`·`EVALUATE`만 `OK`(각 미션 제목), 나머지 세 유형 `NO_RECORD` |
| attempts·상세(학부모) | 2건, 최근 답변 순, 항목에 `draft` 없음, 고르기 상세 `revealKind: ANSWER`·돌아보기 `{EASY, null}` |
| changes(시스템) | 1건(서술형), 마지막 답변이 답한 되묻기, `chars [16, 46]`·`sentences [1, 2]`·`reasonConnectives [0, 3]` |
| evidence(시스템) | 보완 답변 원문 `available: true`·미션 제목, 없는 답변 `available: false` |
| 범위·역할 | 범위 밖 학생 summary 403, 학부모 stats 403 |
| stats(관리자) | `attempts 2`·`completedAttempts 1`·`students 1`, 학생 원문 없음 |

## 후속

- 목록은 항목마다 학생 시도 상세를 다시 읽어(`AttemptService.get`) 쪽당 조회가 늘어남(기본 20건). 대시보드 실사용에서 느리면 묶어 읽는 조회로 바꿀 것
- 학생 기록 삭제 소비(`StudentDeletedConsumer`·`StudentDeletionService`, P09)는 이 이슈 범위 밖이라 미구현. 삭제 뒤 조회는 삭제 표식(`deleted_student`)과 행이 없는 상태로 위 규칙대로 동작
