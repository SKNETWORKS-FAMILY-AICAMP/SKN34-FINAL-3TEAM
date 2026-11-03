# #69 판정 모델 교차 확인 (M2·M1)

문서 기준: develop `cd7d9cd`, 작업일 2026-11-03. 계약은 [api-spec 4.2.2](../design/api-spec.md#422-판정-모델-교차-확인-69-2026-11-03)를 따른다.

## 결정 (2026-11-03 담당자 확정)

| 항목 | 결정 |
|---|---|
| 불일치 기준 | M2 `scores` 평균과 LLM 결과 등급 비교. `CORRECT`인데 평균이 낮은 경계 이하, `RETHINK`인데 높은 경계 이상이면 불일치. `PARTIAL`은 불일치 아님. 경계는 설정값(서술 2.0/4.0, 논술 1.0/2.0)이며 M2 담당 확인 전 임시값 |
| 보류 적용 | `M2_CROSS_CHECK_ENABLED` 기본 `false`. 꺼져 있으면 점수·불일치 여부를 `modelScores`에 기록만 하고 결과는 바꾸지 않음 |
| scoring 장애 | `503 SCORING_UNAVAILABLE`. 5xx·시간 초과·연결 실패는 `retryable:true`, 4xx·계약 밖 응답은 `false`. 비활성으로 바꾸지 않음 |
| 입력 출처 | `question`은 mission_version.question, `keywords`·`essayType`은 learning V9 `rubric_version` 새 칸. 기준표 버전과 함께 불변 |
| 점수 저장 | ai 응답 `modelScores`를 learning이 `judgment.model_scores`에 그대로 저장. 학생 화면에 보이지 않음 |
| M1 | MVP에서는 비활성 유지. ai 호출 분기와 대역 테스트만 두고 `M1_CHECK_ENABLED` 기본 `false`. learning은 M1 입력을 아직 보내지 않음 |
| 시간 예산 | 판정 전체 마감 33초 안에서 scoring 한도 10초와 남은 시간 중 작은 값. 남은 시간이 1초 미만이면 호출하지 않고 503 |

`keywords`와 `essayType`을 `mission`이 아닌 `rubric_version`에 두었다. 두 값은 채점 입력이라 기준표와 함께 바뀌고 검토·게시되는 쪽이 맞고, 미션 버전(V7) 구조를 건드리지 않는다.

## 변경

### ai-service
- `app/clients/scoring_client.py`: `ScoringClient`. `{active:false}`만 비활성(None), 나머지 오류는 `ScoringUnavailable(retryable)`. M2 응답의 점수 키가 입력 방식(서술 9항목·논술 3영역)과 다르면 계약 밖 응답으로 처리
- `app/judgment/cross_check.py`: M2·M1 요청 본문 구성, 평균·불일치 판단
- `app/judgment/service.py`: LLM 판정이 보류가 아닐 때만 scoring 호출. 활성 응답이면 `versions.model`을 `"{name}@{version}"`으로 바꾸고 `modelScores` 포함. 교차 확인을 켜면 `HELD(MODEL_DISAGREEMENT)`·`HELD(LOW_CONFIDENCE)`
- `app/judgment/models.py`: 요청 선택 필드(`question`·`keywords`·`essayType`·`answerKey`·`solution`), `HeldReason` 6종, 응답 `modelScores`
- `app/config.py`: `JUDGE_DEADLINE`·`SCORING_TIMEOUT`·`M2_CROSS_CHECK_ENABLED`·경계 4개·`M1_CHECK_ENABLED`·`M1_MIN_CONFIDENCE`
- `app/bootstrap.py`·`router.py`: lifespan에서 scoring 클라이언트 생성, 판정 서비스에 주입

### learning-service
- `V9__rubric_m2_inputs.sql`: `rubric_version.keywords jsonb`, `essay_type varchar` + 값 CHECK. 기존 migration은 수정하지 않음
- 판정용 기준표(`Rubric`)가 미션 질문·핵심어·글 종류를 읽어 ai 판정 요청에 전달
- ai 응답 `modelScores`(객체 또는 null)를 `judgment.model_scores`에 저장. 객체가 아니면 `AI_BAD_RESPONSE`
- 관리자 기준표 `PUT /internal/admin/missions/{id}/rubric`에 `keywords`(100개·각 200자, 빈 값 거부)·`essayType`(5종) 추가, 응답 `AdminRubric`에도 포함. 게시 필수 항목은 바꾸지 않음
- GitOps local migration revision `v8` → `v9`

### 계약·문서
- `contracts/openapi/ai-service.yaml`: 판정 요청·응답, `SCORING_UNAVAILABLE`
- `contracts/openapi/learning-service.yaml`: `AdminRubric`·`AdminRubricRequest`
- api-spec 3.2·4.1 관리자 기준표·4.2·4.2.2, erd `rubric_version`·`model_scores`, class-diagram, sequence-diagram 3.2, audit D10

## 검증 (로컬, 2026-11-03)

| 대상 | 결과 |
|---|---|
| ai `ruff check`·`ruff format --check`·`pytest` | 통과, 336개. 새 테스트: 교차 확인 분기 19개(`tests/judgment/test_cross_check.py`), scoring 클라이언트 9개(`tests/clients/test_scoring_client.py`) |
| learning `./gradlew test` (JDK 21, Testcontainers PostgreSQL) | 통과, 290개. 질문·핵심어 전달과 `model_scores` 저장, NULL 저장, 객체가 아닌 `modelScores`, 관리자 기준표 저장·조회·판정용 조회, 입력 검증 400 추가 |
| 계약 테스트 `scripts/tests` | 통과, 100개 |
| `check_db_migrations.py` (임시 PostgreSQL 17) | 통과. learning_db 19개 테이블·162개 컬럼 ERD 일치, 재실행·왕복 확인 |

ai 테스트의 scoring은 대역이다. 실제 scoring·M2 모델과 연결한 판정과 learning→ai→scoring 전체 35초 실측은 하지 않았다.

## 한계·후속

- 불일치 경계값은 임시값이다. M2 담당자가 실제 점수 분포로 확인한 뒤 `M2_CROSS_CHECK_ENABLED=true`를 켠다.
- 관리자 웹 기준표 화면에는 `keywords`·`essayType` 입력 칸이 아직 없다(웹 담당 범위). 지금은 learning 관리자 API로만 입력할 수 있으므로, 입력하기 전까지 서술·논술 M2는 호출되지 않는다.
- 데모 미션 시드에는 핵심어·글 종류를 넣지 않았다.
- M1: scoring 활성 응답 형식(`confidence`·모델 식별)은 ai의 기대 형식일 뿐이다. M1 활성화 때 scoring과 확정하고, learning이 `answerKey`·`solution`을 보내도록 연결해야 한다.
- learning은 ai의 `SCORING_UNAVAILABLE`도 기존처럼 `AI_UNAVAILABLE` 실패 코드로 기록한다(`retryable` 값은 유지).
