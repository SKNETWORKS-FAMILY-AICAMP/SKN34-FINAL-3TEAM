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
| 시간 예산 | 판정 전체 마감 33초. M2·M1 입력이 있으면 LLM은 scoring 몫 3초를 뺀 30초까지만 쓰고, scoring 한도는 10초와 남은 시간 중 작은 값. 남은 시간이 1초 미만이면 호출하지 않고 503 ([시간 배분](#시간-배분-p12)) |

`keywords`와 `essayType`을 `mission`이 아닌 `rubric_version`에 두었다. 두 값은 채점 입력이라 기준표와 함께 바뀌고 검토·게시되는 쪽이 맞고, 미션 버전(V7) 구조를 건드리지 않는다.

## 변경

### ai-service
- `app/clients/scoring_client.py`: `ScoringClient`. `{active:false}`만 비활성(None), 나머지 오류는 `ScoringUnavailable(retryable)`. M2 응답의 점수 키가 입력 방식(서술 9항목·논술 3영역)과 다르면 계약 밖 응답으로 처리
- `app/judgment/cross_check.py`: M2·M1 요청 본문 구성, 평균·불일치 판단
- `app/judgment/service.py`: LLM 판정이 보류가 아닐 때만 scoring 호출. M2·M1 입력이 있으면 LLM 추출 마감을 `SCORING_RESERVE`만큼 앞당김(되묻기와 같은 `deadline` 방식, 새 재시도 로직 없음). 활성 응답이면 `versions.model`을 `"{name}@{version}"`으로 바꾸고 `modelScores` 포함. 교차 확인을 켜면 `HELD(MODEL_DISAGREEMENT)`·`HELD(LOW_CONFIDENCE)`
- `app/judgment/models.py`: 요청 선택 필드(`question`·`keywords`·`essayType`·`answerKey`·`solution`), `HeldReason` 6종, 응답 `modelScores`
- `app/judgment/extractor.py`: LLM 호출에 `deadline` 전달
- `app/config.py`: `JUDGE_DEADLINE`·`SCORING_TIMEOUT`·`SCORING_RESERVE`·`M2_CROSS_CHECK_ENABLED`·경계 4개·`M1_CHECK_ENABLED`·`M1_MIN_CONFIDENCE`
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
| ai `ruff check`·`ruff format --check`·`pytest` | 통과, 339개. 새 테스트: 교차 확인 분기·시간 배분 22개(`tests/judgment/test_cross_check.py`), scoring 클라이언트 9개(`tests/clients/test_scoring_client.py`) |
| learning `./gradlew test` (JDK 21, Testcontainers PostgreSQL) | 통과, 290개. 질문·핵심어 전달과 `model_scores` 저장, NULL 저장, 객체가 아닌 `modelScores`, 관리자 기준표 저장·조회·판정용 조회, 입력 검증 400 추가 |
| 계약 테스트 `scripts/tests` | 통과, 100개 |
| `check_db_migrations.py` (임시 PostgreSQL 17) | 통과. learning_db 19개 테이블·162개 컬럼 ERD 일치, 재실행·왕복 확인 |

ai 테스트의 scoring은 대역이다. 실제 scoring·M2 모델과 연결한 판정과 learning→ai→scoring 전체 35초 실측은 하지 않았다.

## 시간 배분 (P12)

learning→ai 판정 읽기 제한 35초 안에서 ai가 쓰는 시간이다. M2·M1 입력이 있는 판정 기준.

| 구간 | 설정 | 최악 시간 |
|---|---|---:|
| LLM 1회 | `LLM_TIMEOUT=15` | 15초 |
| 재시도 전 대기 | `LLM_RETRY_BACKOFF=1` | 1초 |
| LLM 재시도 | LLM 마감(33 - 3 = 30초)까지 남은 시간으로 줄어듦 | 14초 |
| LLM 소계 | `JUDGE_DEADLINE - SCORING_RESERVE` | 30초 |
| scoring 몫 | `SCORING_RESERVE=3`, 한도 `min(SCORING_TIMEOUT=10, 남은 시간)` | 3초 이상 |
| 판정 마감 | `JUDGE_DEADLINE=33` | 33초 |
| learning 35초 대비 여유 | 네트워크·직렬화 | 2초 |

- 근거: #87 실측([issue-87-scoring-m2.md](issue-87-scoring-m2.md))에서 M2 예열 후 HTTP 포함 p95 최대 0.83초, 최대 1.68초다. 3초 몫은 이 최대값의 약 1.8배다.
- 첫 요청(예열 전) 8.4초는 LLM이 빠르면(보통 경로) 10초 한도 안에 들어가지만, LLM이 최악 경로를 가면 3초 몫을 넘어 `503 SCORING_UNAVAILABLE`(`retryable:true`)이 된다. scoring 기동 시 예열이 필요하다(scoring 담당 확인).
- 예약 전(LLM이 33초 전체 사용)에는 LLM 최악 31초 뒤 scoring 몫이 약 2초였다. 교차 확인 입력이 없는 판정은 지금도 LLM이 33초 전체를 쓴다.
- 이 PC에는 M2 모델 파일이 없어 실제 learning→ai→scoring 전체 측정은 하지 못했다. **실제 모델 전체 측정은 배포 환경 후속**이다.

### 실제 경과 시간 검증 (대역, 2026-11-03)

가짜 LLM(시간 초과 단계는 요청 timeout을 다 기다림)과 가짜 scoring(정한 시간만큼 기다림)으로 실제 판정 서비스를 실행해 경과 시간을 쟀다. 설정은 실제 값 그대로(1배)와 1/10 축소 두 가지이며, 1/10 결과는 10배로 환산했다. 1/10 축소는 `tests/judgment/test_cross_check.py`의 `test_llm_retry_worst_path_still_leaves_scoring_reserve`로 CI에서 반복한다.

| 경우 | 결과 | LLM 요청 timeout | scoring timeout | 전체 (1배 / 1/10 환산) |
|---|---|---|---:|---:|
| A. LLM 시간 초과 + 재시도가 마감 직전 응답, scoring 2.9초 | 정상 판정 | 15초 → 13.98초 | 3.08초 | 32.84초 / 32.97초 |
| B. LLM 2초, scoring 첫 요청 8.4초 | 정상 판정 | 15초 | 10초 | 10.41초 / 10.62초 |
| C. LLM 두 번 모두 시간 초과 | `503 AI_UNAVAILABLE` | 15초 → 13.99초 | 호출 안 함 | 30.00초 / 30.00초 |
| D. (비교) 예약 없음, A와 같은 LLM 최악 + scoring 2.9초 | `503 SCORING_UNAVAILABLE` | 15초 → 15초 | 2.08초 | 33.02초 / 33.12초 |

모든 경우가 33초 안팎에서 끝나 learning 35초 제한 안이다. A는 LLM이 최악 경로를 가도 scoring이 3초 몫을 받는 것을, D는 예약이 없으면 같은 상황에서 scoring 몫이 약 2초뿐이라 실패하는 것을 보여 준다.

## 한계·후속

- 실제 scoring·M2 모델을 포함한 learning→ai→scoring 전체 35초 측정은 배포 환경에서 한다. scoring 첫 요청(예열 전)이 3초 몫을 넘으면 LLM 최악 경로와 겹칠 때 503이 된다.
- 불일치 경계값은 임시값이다. M2 담당자가 실제 점수 분포로 확인한 뒤 `M2_CROSS_CHECK_ENABLED=true`를 켠다.
- 관리자 웹 기준표 화면에는 `keywords`·`essayType` 입력 칸이 아직 없다(웹 담당 범위). 지금은 learning 관리자 API로만 입력할 수 있으므로, 입력하기 전까지 서술·논술 M2는 호출되지 않는다.
- 데모 미션 시드에는 핵심어·글 종류를 넣지 않았다.
- M1: scoring 활성 응답 형식(`confidence`·모델 식별)은 ai의 기대 형식일 뿐이다. M1 활성화 때 scoring과 확정하고, learning이 `answerKey`·`solution`을 보내도록 연결해야 한다.
- learning은 ai의 `SCORING_UNAVAILABLE`도 기존처럼 `AI_UNAVAILABLE` 실패 코드로 기록한다(`retryable` 값은 유지).
