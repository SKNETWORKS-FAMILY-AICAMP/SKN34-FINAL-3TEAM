# 설계 문서 정합성 점검

develop `40a2501` 기준으로 설계 문서를 코드와 대조하고, 문서끼리도 대조한 결과다. 코드나 최신 보고서가 기준인 항목은 설계 문서를 고쳤다(1장). 결정이 필요한 항목은 선택 결과를 반영했다(2장). 코드 결함은 3장에 이슈 초안으로 남겼다. 애플리케이션 코드·이벤트 스키마는 수정하지 않았고, OpenAPI·계약 테스트는 2장 결정에 따라 수정했다.

## 범위·방법

- 문서: `docs/design/*.md`, `docs/README.md`, 루트 `README.md`, `contracts/openapi/*.yaml`, `contracts/events/*.json`
- 코드: core·learning controller·service·repository·domain, ai·report·scoring `app/`, core·learning Flyway, report Alembic, `compose*.yaml`, `.env.example`, `application.yml`, `config.py`, `definitions.json`, `.github/workflows`, `frontend/web/src/data`
- 대조 항목
  - API: 경로·본문·응답·오류 코드·헤더·SSE 이벤트
  - 스키마: 테이블·컬럼·CHECK·인덱스
  - 구조: 클래스·메서드·의존 방향, 상태 전이
  - 메시징: 이벤트 봉투·스키마
  - 설정: 타임아웃·포트·버전
- 아직 구현하지 않은 기능(결제·리포트·대화·알림 등)의 설계는 불일치로 보지 않았다. 문서가 이미 구현된 것처럼 읽히는 경우만 포함했다.

### 기존 자동 검증 범위

| 검증 | 확인 대상 | 확인하지 않는 대상 |
|---|---|---|
| `scripts/verify_db_schema.py` (`ci-db-schema.yml`) | ERD 컬럼 이름·타입·NULL 여부·기본값 없음·PK·FK 컬럼·단일 컬럼 UK, 단일 컬럼 CHECK 값, §6 인덱스 존재, 위반 입력 47건 | FK 대상 테이블·ON DELETE, 복합·부분 UK 대부분, §6 밖의 추가 인덱스, 시드 |
| `scripts/tests/test_*_openapi.py` | core controller 매핑과 yaml의 메서드+경로 집합, 일부 헤더·스키마. 2장 D6 이후 learning 컨트롤러·ai 라우터 경로 집합도 대조 | 요청·응답 필드와 실제 직렬화 결과, 프론트 호출 |

## 1. 수정한 문서

| 문서 | 수정 | 근거 |
|---|---|---|
| `erd.md` §9 | 59/506 뒤에 V8 반영 현재 수치 60개 테이블·518개 컬럼(core 35/318) 추가. 과거 보고서(`db-schema-ci.md` 등)의 59/506은 당시 검증 기록이라 유지 | `verify_db_schema.erd_contract()` 집계, V8 `auth_session` |
| `erd.md` §6 | `ix_auth_session_user`, `ix_refresh_token_session` 추가 | V8:25,29 |
| `erd.md` 2장 | `auth_session`의 `version > 0`, `ck_auth_session_student` 명시 | V8:17,21-23 |
| `erd.md` `answer.content` | `finalAnswer`·`steps`·`assignments` 추가 | `AnswerContent.kt` |
| `erd.md` 5장 | 삭제 완료 통보를 "이벤트"에서 core 내부 API `POST /internal/deletion-requests/{id}/completions`로 정정 | architecture 1.4·api-spec 4.5·state·sequence와 일치, 같은 절 "learning은 이벤트 미발행" |
| `class-diagram.md` 2장 | `IdempotencyService`·`SseEmitters`를 "신규"에서 구현됨으로 변경. 이벤트 봉투에 `specversion`·`time`(Python은 `source`·`dataschema`·`traceparent` 포함) 추가 | `_common/web`, `EventEnvelope.kt`, `envelope.py` |
| `class-diagram.md` 3.1 | `ConsentController`·`ConsentService`(documents·history·save·withdraw), `ChildrenController`, `GuardianshipService.register/children`과 의존(`AccountAccessService`·`ConsentAccessService`·`LearningRecordService`), `ConsentAccessRepository`·`StudentAccessRepository` 반영. 코드에 없는 `Consent` entity 제거, 구현 상태 갱신 | `consent/`·`guardianship/`, [이슈 #37 보고서](issue-37-consent-children.md) |
| `class-diagram.md` 3.2 | `LearningController → LearningProxyService → LearningClient.exchange`, `FeedbackController → FeedbackService`, `LearningRecordService → LearningRecordClient`. "service 없이 controller → client" 문구와 `UserContextHolder.runWith` 추가 필요 문구를 현재 구조(`SseEmitters.open`이 컨텍스트 설정·해제)로 교체 | `core/learning/`, [#38](issue-38-core-learning-proxy.md)·[#39](issue-39-core-feedback-sse.md) 보고서 |
| `class-diagram.md` 4.1·4.3 | `AttemptService.start → AttemptStart`, `openHint → HintOpened`, `AttemptDraft.update(content, now)`, `updateIfVersion(next, ifMatch): Boolean`·`clearAnswer`, `MissionRepository.findRubric`(값 객체 `Rubric`), `RecordExists*` 구현 상태 추가. #26·삭제 미구현 표기 | `attempt/`·`mission/`·`record/` |
| `class-diagram.md` 4.3·8장 | learning 하위 기록 CASCADE "가정"을 미결 항목으로 변경(현재 FK 모두 NO ACTION) | learning `V2__learning_records.sql`, ERD 1장·7장 |
| `class-diagram.md` 5.1 | 라우터 함수 `judge`·`create_followup`, 추출·대조·유출 검사는 모듈 함수, `BackgroundUsageRecorder` 경유 사용량 발행, `ActiveVersions`·`stream`·M2/M1 교차 확인 미구현 표기 | `app/judgment`·`app/followup`·`app/llm/base.py`·`app/versions.py` |
| `state-diagram.md` 1장 | 조건부 UPDATE 규칙의 예외(`model_version` advisory lock, 동의 철회 행 잠금) 명시 | `ModelVersionMapper.xml`, `ConsentAccessMapper.xml` |
| `state-diagram.md` 2.3 | 동의는 선택마다 새 행(AGREED·WITHDRAWN)을 저장하고 최신 행으로 판정. 담당 `ConsentService.save/withdraw`, `GuardianshipService.register` | `ConsentService.kt:28-60` |
| `state-diagram.md` 3.3 | 고착 `RUNNING` 1분 주기 탐지는 미구현이며 현재는 요청 때 재획득한다고 명시 | [이슈 #25 보고서](learning-feedback.md) 후속 |
| `api-spec.md` 1.3 | 오류 코드 추가: `SESSION_CHANGED`, `REFRESH_REUSED`, `OAUTH_*`, `ACCOUNT_EXISTS`, `AUTH_UNAVAILABLE`, `CONSENT_*`, `IDEMPOTENCY_*`, `LEARNING_*`, `MODEL_*`, `INTERNAL_ERROR`. 피드백 SSE `error`의 형식(`about:blank`, `instance`·`traceId` 없음) 명시 | core `BusinessException` 전수, `FeedbackController.kt`·`SseEmitters.kt` |
| `api-spec.md` 2.1·3.11 | `GET /children`의 `pinSet`·`pinLocked`를 #58·#59 후속(현재 미반환)으로 정리. 5.3·OpenAPI·코드와 일치시킴 | `ChildRecords.kt`, `test_auth_openapi.py` |
| `api-spec.md` 3.7·3.8 | 실제 미션 상세 필드(`hint`·`inputTemplate`·`sceneUri`)와 `scene`·`categories` 미제공 명시 | `MissionResponses.kt`, [이슈 #22 보고서](learning-mission.md) |
| `api-spec.md` 3.10 | model-version·ai-usage는 5.2·4.6 확정 계약이 우선한다고 명시 | 5.2·4.6, OpenAPI |
| `api-spec.md` 4.1 | 판정 전 타임라인 `feedback`의 실제 모양 `{status, judgment:null, followup:null, nextActions:[], versions:null}` | `FeedbackResult.inProgress` |
| `api-spec.md` 5.1 | 부모·관리자 `/me`와 refresh 응답의 `child:null` 명시 | `AuthController.kt`, OpenAPI `ParentMeResponse` |
| `api-spec.md` 1.6·3.2 | 예시 모델 ID `claude-sonnet-5-5` → `gpt-6.1-terra` | architecture 6장 기본 LLM |
| `architecture.md` | 구성도의 `2222222222222222222` 제거. core `learning/` 트리에 `service/`·`config/`·`LearningRecordClient` 추가. 봉투 필드에 `specversion` 추가 | 1.2·2.6, 코드 패키지 |
| `architecture.md` | CloudFront 전달 헤더에 `Origin`·`X-Requested-With` 추가. 쿠키 API 검사에 필요 | api-spec 5.1, `PublicAuthFilter` |
| `architecture.md` | 타임아웃 상한 문구에 SSE heartbeat 전제를 추가. 로컬 stub 미구성(실제 LLM 호출, 키 없으면 `AI_UNAVAILABLE`)을 명시. 트리에 `ci-db-schema.yml` 추가 | `compose.yaml`, `UnconfiguredLlm` |
| `sequence-diagram.md` | 절 순서를 2.3·2.4로 교정. `GuardianshipService.register`로 수정. 무료 한도 문구를 "신규 `201`만 집계, 이어하기 `200` 허용"으로 정리 | api-spec 2.2, architecture 2장 |
| 루트 `README.md` | MinIO 실행에 `AUTH_JWT_SECRET`도 필요함을 추가 | `compose.yaml:129` `:?` |
| `docs/README.md` | 보고서 색인 누락 6건과 이 보고서 추가 | `docs/report/` |

## 2. 결정 항목과 반영 결과

점검 직후 결정이 필요했던 11건. 항목마다 문제·원인·선택지를 정리했고, 사용자가 모두 권장안을 선택해 반영했다.

| # | 문제 | 원인 | 결정 | 반영 |
|---|---|---|---|---|
| D1 계정 복구 | FN-ACC-08·10, UC-04, ERD Redis "계정 복구 확인 코드"가 남음. api-spec 5.1은 제외 | #36에서 Google 단일 로그인 확정 시 요구사항 문서 미갱신 | Google 기준 정리 | `functional-spec.md` FN-ACC-08(Google 계정 복구 위임·재로그인 안내)·FN-ACC-10(로그인 수단 변경 삭제, 재확인은 Google 재인증), `usecase.md` UC-04 "정보 수정·접근 복구 안내", `erd.md` Redis 항목 삭제 |
| D2 삭제 재확인 | state·sequence는 2단계(`REQUESTED → CONFIRMED`에 `X-Reauth-Token`), api-spec은 헤더·확인 API 없음 | 상태 설계와 API 표를 따로 작성 | 1단계 + 헤더 (연결 해제·탈퇴와 같은 방식) | api-spec 2.1, state 2.2, sequence 10.1, class 3.1(`confirmDeletion` 제거) |
| D3 PIN 잠금 필드명 | `/auth/student/profiles`는 `locked`, `/children`은 `pinLocked` | #59 목업에서 따로 정의 | `pinLocked` 통일 | api-spec 2.1, sequence 2.4. 프론트 `studentDevice.ts`의 `locked`는 #58·#59에서 변경 |
| D4 SSE 연결 시간 | `SseEmitters` 90초 고정이 범용으로 기술됨, 분석 대화는 120초(P12) | #39가 피드백 전용 값으로 구현 | 용도별 설정 명시 | architecture 1.3, class 2.1. 코드 확장은 #41 |
| D5 Problem `traceId` | core yaml 선택·nullable, learning yaml 필수. 코드는 항상 포함 | #36·#37이 각자 스키마 정의 | 필수로 통일 | core yaml `Problem.required`에 `traceId` 추가 |
| D6 내부 API OpenAPI | 구현된 learning 내부 API 8개·ai 3개가 yaml에 없음, 테스트가 learning yaml을 경로 1개로 고정 | #37이 최소 범위만 계약화, 이후 이슈는 api-spec만 갱신 | 지금 yaml 추가 | `learning-service.yaml` 9개 경로(DTO 기준 스키마), `ai-service.yaml` 신규 3개 경로(FastAPI 생성 스키마). 테스트: learning 컨트롤러·ai 라우터 경로 집합 대조, ai `heldReason` 대조. api-spec 4.1·4.2에 링크 |
| D7 이벤트 스키마 | `report.*`·`student.deleted` 스키마, asyncapi·`ci-contracts.yml` 없음 | 해당 기능 미착수 | 기능 이슈에서 선행 | #45·#42·#50 체크리스트에 이미 스키마 항목 있음. 새 정보만 코멘트: [#45](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/45#issuecomment-6459420129)(D1·D2 결정, `student.deleted` 선행), [#42](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/42#issuecomment-6459420524)·[#50](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/50#issuecomment-6459420848)(같은 스키마 중복 추가 방지, `narrativeEnabled`). #55는 #45 스키마 사용이라 생략 |
| D8 목표 구조 | stub·eks·aws·argocd·app chart·adr·환경별 yml·E2E·Redis·ShedLock·이미지 푸시가 저장소에 없음 | 최종 목표 구조로 작성 | "(예정)" 표시 | architecture 2.6·4.5·5·6장 |
| D9 core yaml 경미 | 공개 `GET /consent-documents`에 불필요한 오류 응답, `Admin`·`ModelRegistry` 태그 미선언 | 응답 블록 복사 | D5·D6과 함께 수정 | 400·401·403·409 제거(503 유지), 최상위 `tags` 추가 |
| D10 `heldReason` | ai 4종, api-spec 6종 | M1·M2 교차 확인(#69) 미구현 | 명세에 조건 표기 | api-spec 3.2. ai 추가는 #69 |
| D11 보고서 기록 | `learning-answer.md`의 판정 전 피드백 모양이 코드와 다름 | 당시 기록 | 조치 없음 | 과거 기록 유지 |

## 3. 코드 결함 이슈 초안 (코드 미수정)

### 3.1 프론트 관리자 모델 레지스트리 API 계약 불일치
- 현상
  - `frontend/web/src/data/admin/api.ts:64-75`
    - 등록 본문 `{kind,name,version,evalResult:string,approvedBy}`
    - 활성화·복귀 본문 `{reason, reanalyze:false}`
  - `domain/admin/operations.ts:102`의 `evalResult`가 문자열이고 `refId`가 없음
  - `ModelManager.tsx:47`이 `evalResult`를 그대로 렌더링함
- 기대
  - 등록 본문: `{kind,name,version,refId?,artifactUri?,evaluation:{…}}`
  - 활성화 본문: `{approved:true,scopes,reason,reanalysisPlanned}`
  - 복귀 본문: `{scopes,reason,reanalysisPlanned}`
  - `evalResult`는 객체 (api-spec 5.2, `core-service.yaml:919-977,1048`)
- 영향: 실제 API 모드에서 등록·활성화가 400으로 실패한다. 평가 기록이 있는 버전을 렌더링하면 React 오류가 난다. ai-usage 화면에는 `unpricedCalls`가 없고, callType 선택지가 7종 중 4종뿐이다.
- 참고: #43 보고서상 프론트 실연동은 후속이다.

### 3.2 LLM 사용량 비용: 토큰 미기록을 0으로 계산
- 현상: `LlmUsageService.kt:57-61`이 `inputTokens`·`outputTokens`가 null이면 0으로 곱한다.
- 영향: 단가가 등록된 모델에서 토큰이 미기록인 호출의 `cost_usd`가 null이 아니라 과소값으로 저장된다. api-spec 4.6은 토큰 미기록 합계를 null로 두고 null 비용을 `unpricedCalls`로 공개한다.
- 현재: `llm-pricing: {}`라서 잠재 결함이다.
- 제안: 토큰 중 하나라도 null이면 비용 null

### 3.3 `SPEECH` 호출 종류 잔존
- 현상: 음성 시범은 미구현으로 결정됐다(P03, `answer.speech_transcribed` 제거). 하지만 `SPEECH`가 다음 위치에 남아 있다.
  - `llm.usage.recorded.v1.schema.json:10`
  - `publisher.py:23`
  - `erd.md` `llm_usage.call_type` CHECK
  - api-spec 4.6 "7개 호출 종류"
  - 빈 `ai-service/app/speech/` 패키지
- 제안: 제거 여부를 결정한다. 제거하면 이벤트 스키마·ERD CHECK 마이그레이션·OpenAPI `CallType`·ai·core·프론트를 함께 변경한다.

### 3.4 P12 "확정 전 임시값" 주석
- 현상: P12는 확정됐다(`functional-spec.md` 1.4). 그런데 `[P12] 확정 전 임시값` 주석이 남아 있다.
  - core `application.yml:66`
  - ai·report·scoring `config.py`
- 제안: 확정값 근거로 주석만 정리한다.

### 3.5 프론트 잔존 호출
- 현상
  - `/auth/login`: `apiGateway.ts:127`, `apiClient.ts:110`
  - `/auth/signup`: `parent/api.ts:41`
  - `/me/reauth {password}`: `parent/api.ts:48`
- 기대: 이메일 로그인·가입은 제거됐다(api-spec 3.7). 재확인은 Google 재인증(#45)이다.
- 영향: 실제 UI는 목업 모드에서만 이 경로에 도달한다.

### 참고 (이슈 생략)
- core가 `finish`·`self-assessment`·`reflection`을 프록시하지만 learning 핸들러가 없어 404가 전달된다. #26에서 처리 중이다.
