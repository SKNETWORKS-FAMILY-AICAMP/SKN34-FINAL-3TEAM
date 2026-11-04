# 점검·검증 기록

develop 종합 검증 회차별 결함 원장과 최신 회차 결과. 회차별 실행 결과 표와 과거 재판정 표는 git 이력(이 파일의 이전 버전) 참고.

| 회차 | 기준 | 범위 | 번호 |
|---|---|---|---|
| 1 | develop `c608f52` | 코드 통합·코드↔문서·테스트·CI | B1~B17, C1~C15, D1~D14 |
| 2 | develop `40a2501` (PR #92) | 설계 문서 정합성 | D1~D11(결정 항목), #93~#97 |
| 3 | develop `640e0a2` | PR 16개 병합 후 + 아키텍처 원칙 | B18~B21, C16~C21, D15~D16, A1~A7 |
| 4 | develop `2db122c` | PR 73커밋 병합 후 | B22~B27, C22~C34, D17~D21, A8~A15 |
| 5 | develop `92d522b` | PR 28개 병합 후 | B28~B35, C35~C44, D22~D25, A16~A19 |
| 6 | develop `b97cc67` | PR 22개 병합 후 | B36~B43, C45~C59, D26~D29, A20~A21, T1 (3장) |

## 1. 결함 원장 (1~5회차)

6회차 항목은 3.3. "유지"는 b97cc67 기준 미해결.

### 1.1 코드 결함·설정 (B)

| # | 내용 | 처리 |
|---|---|---|
| B1·B2 | 역할·내부 토큰 판정을 디코딩하지 않은 `requestURI` 접두사로 해 `;매개변수`·`%xx` 경로가 우회 | 해결(1회차, `MatchedPath` 정규화) |
| B3 | learning `student.deleted` 소비자 없음 → 삭제 COMPLETED 불가 | 해결(#128) |
| B4 | `ReportEntitlementService` 항상 503, 스케줄러가 자녀별 실패 미격리 | 해결(자녀별 격리 1회차, 공급자 #48·#129) |
| B5 | report-worker 기본 생성기 미연결 | 해결(#56·#64) |
| B6·B7 | 리포트 목록 `status=QUEUED` 전달, `ReportClient`가 409·503 구분 없이 503 | 해결(1회차) |
| B8 | report Outbox 영구 실패 이벤트가 뒤 이벤트를 막음 | 해결(#131) |
| B9 | 종료 이벤트 없이 core 작업이 QUEUED/RUNNING에 남는 경로 | 해결(#132) |
| B10 | 기기 등록 rate limit 키가 `remoteAddr`(프록시 뒤 한 버킷) | 해결(#133) |
| B11·B13 | 웹이 `/children`의 `plan`·재생성 코드·목록 봉투를 잘못 가정 | 해결(#134) |
| B12 | 웹 관리자 모델 요청 모양·`/auth/login` 잔존 호출 | 해결(#93·#97) |
| B14 | `saveDraft`가 잠금 없이 저장해 닫힌 시도에 초안 저장 가능 | 해결(1회차, `lockOwned`) |
| B15 | readiness가 쓰지 않는 RabbitMQ에 의존 | 해결(1회차) |
| B16 | 처리한 삭제 이벤트 재전달 시 DLQ | 해결(1회차) |
| B17 | 미사용 설정 주입·요청별 클라이언트 생성 | 해결(#135, `scoring_url`은 #69에서 사용) |
| B18·B19 | core가 learning 404·403을 503으로 변환 | 해결(#163) |
| B20·B21 | 정책 마이그레이션 검사 버전 고정, `verify_feedback_learning.py`의 `CORE_URL` 누락 | 해결(3회차, #164) |
| B22 | 웹 `answerInquiry`가 core에 없는 경로 호출 | 해결(4회차, 도달 불가 화면·API 제거) |
| B23 | `AdminOperations.tsx:204` oxlint immutability 경고 | 유지(동작 문제 없음, 이슈 #306에 기재) |
| B24 | compose core에 RabbitMQ 관리 API 환경 변수 없음 | 해결(4회차) |
| B25·B26 | `ConversationRetryWorker` stale 예외, ai 소비자 ACK 범위 | 결함 아님(조치 없음) |
| B27 | core 통합 테스트 `too many clients` | 재현 안 됨(#218 이후) |
| B28 | 웹 support·help·notices 경로가 실제 API 미사용 | 해결(5회차) |
| B29·B30 | GitOps local migration revision·RabbitMQ 관리 API 값 낡음 | 해결(5회차, `test_core_migration_versions.py` 추가) |
| B31 | `ReportTemplateService.forStudent` 오류 코드 | 해결(5회차, `STUDENT_UNAVAILABLE`) |
| B32 | #275 다중 보호자 전제가 P02와 불일치 | 해결(#289) |
| B33 | 리포트 설정 제안의 사용량 차감 | 결함 아님(api-spec #209 절에 명시) |
| B34·B35 | learning이 core 409를 모두 `REFUND_IN_PROGRESS`로 변환, 공지 목록 입력 검사가 권한 검사보다 먼저 | 해결(#276·#277) |

### 1.2 코드↔문서 (C)

| # | 내용 | 처리 |
|---|---|---|
| C1~C15 | report OpenAPI 오류 응답·422, ai OpenAPI 누락 필드, 재생성·알림 오류 코드, ERD 수치·결번, `SPEECH` CHECK, 미구현 표기, 목록 봉투 예외, 문서·compose 환경 변수 | 해결(1회차) |
| C16~C21 | class-diagram 구현 이름·상태, ai 분석 에이전트 파일 대응, #132·#47 구현 상태, report 연결 상태 | 해결(3회차) |
| C22~C34 | ai OpenAPI `title`, 관리자 재처리 응답 선언, 리포트 오류 코드, `AI_UNAVAILABLE` 503/502, 누락 경로, 재처리 구현 상태, SSE 수명, `OutboxRelay` 서술, 단절 실패 코드, ERD 수치, 결제 화면, architecture 트리, 보고서 상태 서술 | 해결(4회차) |
| C35~C44 | api-spec 1.3 누락 오류 코드·400/422 구분·누락 경로, 3.13 옛 목업, ERD 수치, architecture 트리, class-diagram 파일 위치, user-flow 누락 흐름, ai 보고서 문구, ai OpenAPI Problem 스키마 | 해결(5회차) |

### 1.3 문서 간 (D)

| # | 내용 | 처리 |
|---|---|---|
| D1~D14 | (1회차) 미구현 잔존 문장, 알림 상태·채널·재연결, SSE 연결 시간, 재인증 흐름, 실제 클래스 이름 | 해결 |
| D1~D11 | (2회차 결정) Google 계정 복구 위임, 삭제 1단계 + `X-Reauth-Token`, `pinLocked` 통일, 용도별 SSE 시간, Problem `traceId` 필수, 내부 API OpenAPI 추가, 이벤트 스키마 선행, 목표 구조 "(예정)" 표시, `heldReason` 조건 표기 | 반영 |
| D15·D17·D22 | `docs/README.md` 보고서 색인 누락 | 해결(문서 정리로 색인 재작성) |
| D16 | 이슈별 절이 번호 체계 밖 | 해결(#165·#245) |
| D18·D21 | 종료된 임시 통합 규칙, 루트 병합 메모 | 삭제(4회차) |
| D19·D20 | 알림 `RUNNING`·`conversation_job_retry.status` 상태 표 누락 | 해결(4회차) |
| D23·D24·D25 | ml/m2 앵커, 4회차 낡은 상태, Redis 사용처 표 기준 | 해결(5회차) |

### 1.4 아키텍처 (A)

| # | 내용 | 처리 |
|---|---|---|
| A1 | `OutboxRelay.relay`가 트랜잭션 안에서 AMQP 발행 | 해결(#166) |
| A2 | 서킷 브레이커가 core→learning에만 | 해결(#167·#192) |
| A3·A4·A8 | domain의 `HttpStatus`·Jackson·`BusinessException(ErrorKind)` 의존, 레이어 역참조 | 해결(#168·#169·#249) |
| A5·A14 | 웹 컴포넌트의 API 직접 호출 | 해결(#170·#255) |
| A6 | ai→scoring 교차 확인 호출자 없음 | 해결(#69) |
| A7 | 앱 배포 chart·NetworkPolicy·관측 미구현 | 해결(local, #171·#204) |
| A9 | `NotificationRedisPublisher`가 Application 호출 | 해결(#250) |
| A10 | 기능 간 controller·config 참조 | 해결(#251) |
| A11 | report 기능 간 DB 직접 접근 | 해결(#252) |
| A12 | ai 분석 에이전트 router가 계층 건너뜀 | 해결(#253) |
| A13 | ai·scoring 소비자에 revision 조정 로직 | 일부 해결(ai #254). scoring 소비자의 `ModelStartup` 생성·revision 조정 유지 |
| A15 | 설계와 다른 위치(learning 삭제 소비) | 해결(#256) |
| A16 | `ReportTemplate.kt`의 `HttpStatus` | 해결(#249) |
| A17~A19 | #208 이벤트 기록 위치, 기능 간 client·repository 직접 참조, ai 리포트 설정 제안 프롬프트 등록 | 해결(#278·#279·#280) |

### 1.5 이슈 상태 (2회차 발행)

| 이슈 | 내용 | 상태 |
|---|---|---|
| #93·#97 | 웹 관리자 모델 레지스트리 요청 모양, `/auth/login` 등 잔존 호출 | 해결 |
| #94 | 토큰 미기록 비용을 0으로 계산 | 해결(토큰 하나라도 null이면 `cost_usd` null) |
| #95 | `SPEECH` 호출 종류 잔존 | 해결(V14) |
| #96 | P12 "확정 전 임시값" 주석 | 해결 |

## 2. 아키텍처 원칙 점검 기준

[아키텍처](../design/architecture.md) 1.1~1.6(서비스 경계·통신·메시징)·2.1~2.4(백엔드 레이어)·3장(프론트엔드)·4장(인프라) 원칙을 HEAD 코드와 대조. core·learning은 패키지 import를 레이어(`controller`·`consumer`·`scheduler` / `service`·`facade` / `domain` / `repository`·`client`·`messaging`)로 분류해 전수 검사하고, 나머지는 클라이언트·트랜잭션·설정을 grep으로 확인.

지켜지는 원칙:

| 원칙 | 확인 결과 |
|---|---|
| 서비스 DB 직접 접근 금지(1.1) | 각 서비스 DB URL은 자기 DB만. 다른 서비스 데이터는 내부 API·이벤트로만 조회 |
| core만 공개 API·JWT 검증(1.1·2.3) | 웹 `apiClient`는 core `/api/v1`만 호출. JWT 검증은 core만, 내부 호출은 내부 토큰 + 컨텍스트 헤더 |
| 컨텍스트 전파(2.3) | ai `clients/base.py`가 받은 `X-User-*`·`X-Student-Scope`를 learning 호출에 부착. report 소비자는 `SYSTEM` + 이벤트 학생 범위 |
| 레이어 단방향·기능 간 service 경유(2.2) | core·learning에서 controller→repository 0건, 다른 기능 repository 참조 0건, Presentation의 `@Transactional` 0건. support의 learning client 재사용은 #46 결정 |
| 트랜잭션 안 외부 호출 금지(2.2) | 리포트 복구 `NOT_SUPPORTED`, 알림 Redis 발행 `AFTER_COMMIT`, learning 피드백은 `FeedbackFacade` 트랜잭션 밖 AI 호출, report Outbox는 advisory lock·짧은 트랜잭션. 예외 A1 |
| 재시도 계층(1.3) | 재시도는 ai LLM 호출(1회, 1초)과 되묻기 유출 재생성(1회)만. core·learning·report 서비스 간 호출은 재시도 없음 |
| Outbox·멱등 소비(1.6) | Outbox는 core·report만, learning은 발행 없음, ai·scoring은 best-effort 발행. core·learning 리스너는 수동 ACK·`RetryingConsumer` |
| readiness(4.4) | core·learning `readinessState,db,rabbit`, ai RabbitMQ, scoring RabbitMQ·모델, report DB. 하위 서비스 호출 없음 |
| 스케줄 중복 방지(1.5) | 정기·복구 스케줄러 4개(주간 리포트·리포트 복구·결제 갱신·결제 복구) 모두 ShedLock |
| 프론트엔드(3장) | access token 메모리 보관, 서버 상태는 TanStack Query만, 전역 상태 라이브러리 없음, `domain`이 `data`·`presentation`을 참조하지 않음 |

회차마다 위 원칙을 HEAD 코드와 다시 대조하고, 다른 구현은 A 번호로 원장에 기록.

## 3. 최신 회차: develop 종합 검증 (b97cc67)

5회차 이후 PR 22개(#272~#304 범위, 84커밋·307파일) 병합 직후 develop `b97cc67`의 테스트·코드↔코드·코드↔문서·문서 간·아키텍처 정합성 점검. 이번 점검은 코드·설계 문서를 수정하지 않고 발견 항목을 모두 이슈로 발행함(이 문서의 낡은 상태 표기만 정정, D29). 번호는 5회차에 이어 결함 B36~, 코드↔문서 C45~, 문서 간 D26~, 아키텍처 A20~, 테스트 공백 T1~.

### 3.1 실행 결과

Windows 11 로컬 실행. CI와 같은 명령, core·learning은 5회차와 같이 `gradle:8.14.6-jdk21` 컨테이너(저장소 마운트, Docker 소켓, `TESTCONTAINERS_HOST_OVERRIDE=host.docker.internal`, 서비스별 Gradle 캐시 볼륨. 두 서비스가 캐시 볼륨 하나를 함께 쓰면 Gradle 잠금 충돌로 learning 빌드가 시작 전 실패), helm은 `alpine/helm:4.3.1` 컨테이너. develop CI도 `b97cc67`·`8636a4d` 기준 전 워크플로 통과.

| 대상 | 명령 | 결과 |
|---|---|---|
| ai-service | `uv sync --frozen` → `ruff check` → `ruff format --check` → `pytest` | 통과. 343건(295초) |
| scoring-service | 동일 | 통과. 199건(74초) |
| report-service | 동일 + `playwright install chromium` | 통과. 337건(226초), 경고 1건(`starlette.testclient`의 httpx 사용 폐기 예정) |
| core-service | `./gradlew test bootJar` | 통과. 476건(23분) |
| learning-service | 동일 | 통과. 290건(10분) |
| web | `npm ci` → `npm run lint` → `npm test` → `npm run test:types` → `npm run build` → `npm run test:browser` | 통과. lint 경고 1건(B23), 단위 209건, 타입 검사·빌드 통과(500 kB 경고 없음), 브라우저 24건 |
| web 운영 산출물 | `node tests/production-mocks.mjs` | 통과 |
| web 수동 브라우저 | `VITE_API_MOCK=true` 개발 서버 + `node tests/requirements-browser.mjs` | 실패(B43, 5회차 계정 단계와 같은 지점). #318 이후 통과(9단계) |
| 루트 계약 테스트 | PyYAML 6.0.3·jsonschema 4.26.0, `python -O -m unittest discover -s scripts/tests` | 통과. 100건(69초) |
| DB 마이그레이션 | 임시 `postgres:17.11-alpine`에서 `check_db_migrations.py`·`check_policy_migrations.py` | 통과. core 48/441, learning 19/162, report 8/63(테이블/컬럼), 위반 입력 71건, CHECK 값 79종, 인덱스 37개, 재실행·Alembic 왕복(41초). 정책 마이그레이션 통과(133초) |
| GitOps | `ci-gitops.yml`과 같은 local 환경별 `helm lint --strict`·`helm template`(Kubernetes 1.35.8) | 통과(8개 release). kubeconform은 원격 스키마 카탈로그가 필요해 미실행(develop CI 통과) |
| ml | `ci-ml-m1.yml`·`ci-ml-m2.yml`과 같은 `ruff check`·`ruff format --check`·`pytest` | 통과. m1 3건(1건 건너뜀), m2 9건(3건 건너뜀) |

정적 대조:

| 대상 | 결과 |
|---|---|
| core·learning 컨트롤러 경로 ↔ OpenAPI | core 149/149, learning 36/36 일치(#289 이관 7개 경로 포함) |
| ai·report·scoring 라우트 ↔ OpenAPI | ai 6/6, report 7/7, scoring 3/3. ai `/versions` 프롬프트 키 5종(`reportTemplate` 포함). ai `JudgmentSummary.heldReason` enum 1건(C51) |
| 요청·응답 DTO | #289 이관·`/auth/parent-unlock`·보호자 비밀번호 DTO가 컨트롤러·OpenAPI·웹 타입 일치. 이관 상태·재인증 purpose 7종이 V26 CHECK·Kotlin·OpenAPI·웹 일치 |
| api-spec ↔ OpenAPI·코드 | #289 오류 코드·경로 표·재인증 purpose 누락(C45~C47), V24 refresh 쿠키 서술(C50) |
| 웹 API 호출 ↔ core OpenAPI | 경로는 시연 전용(`/auth/login`·`/auth/signup`·`/auth/student/demo-device`·`/__payment-test`) 외 일치. #304 돌아보기·분석 요청 정렬 확인. 관리자 기준표 요청 필드 누락(B37), MSW 차이(C48·C50) |
| 서비스 간 HTTP 클라이언트 ↔ 호출 대상 | core→learning·ai·report, learning→ai·core, ai→learning·scoring(#69 `M2Request`·점수 키·`{active:false}`), report→core·learning·ai 경로·DTO 일치. scoring 오류 전파 1건(A20·B36) |
| 이벤트·큐 | `definitions.json` exchange 3·큐 30 ↔ 발행자·소비자 일치. 5회차 이후 이벤트 스키마 변경 없음. #250 이후 Redis 알림 채널 발행·구독 일치 |
| 공유 상수 | 내부 헤더(`X-Internal-Token`·`X-User-*`·`X-Student-Scope`·`traceparent`) ai→scoring 포함 일치. P12 시간 제한과 #69 시간 예산(ai `judge_deadline` 33초 < learning→ai 35초, scoring 시간은 남은 시간으로 제한) 일치. `essay_type` 값 V9 CHECK·learning·ai·scoring 일치 |
| 환경 변수 | compose·`.env.example`·`application.yml`·Python `Settings`·GitOps 대조. GitOps `secretKeyRef` 키는 `create-app-secrets.ps1`이 모두 생성. 전달 누락 1건(B41) |
| 마이그레이션 revision | GitOps local `v26`·`v9`·`20261102-05` = 최신 마이그레이션(`test_core_migration_versions.py` 검사) |
| 상태 값 | ERD CHECK ↔ 코드 enum 일치. state-diagram에 이관·세션 잠금 없음(C49) |
| FN/NFR/UC ID | 참조 ID 모두 정의됨(FN 120·NFR 39·UC 28), 중복 정의 없음 |
| 문서 링크 | 상대 링크·앵커 343개 중 깨짐 0건 |

실행하지 않은 것: JDK 21 JAR 전제 `verify_*`, 모델 archive 전제 `verify_scoring_*`, `requirements-browser.mjs` 외 `tests/*-browser.mjs`, compose 전체 스택 E2E(`e2e.yml`, main 미병합 C43), kubeconform.

### 3.2 5회차 미해결 항목 재판정

| # | 현재 상태 | 근거 |
|---|---|---|
| A6 | 해결 | #69(#303). ai 판정이 scoring M2·M1 교차 확인 호출(기본 꺼짐), `clients/scoring_client.py`·`judgment/cross_check.py`. B17의 `scoring_url`도 #69에서 사용 |
| A13 | 유지 | scoring `messaging/consumer.py`가 `ModelStartup` 생성·revision 조정을 계속 담당 |
| B23 | 해결(#306) | `AdminOperations.tsx` 작업 재처리 멱등 키를 `useAdminMutation` 인자 클로저에서 읽지 않고 mutation 변수로 넘김(실패 후 재시도는 같은 키, 성공·원래 작업 복귀 때만 폐기 동작 유지). oxlint 경고 0 |
| B32·B34·B35·A17·A18·A19 | 해결 | #275·#276·#277·#278·#279·#280 모두 종료 |
| 5회차 OpenAPI | 유지 | `STUDENT_RECORDS_PRIVATE`가 core OpenAPI에 0건(C59) |
| 5회차 요구사항 차이 | 유지 | FN-AGT-12 수학 점검 예시 질문 차이, api-spec 2.4에 현재 동작 기재 |
| 5회차 테스트 공백 | 유지 | core HTTP 테스트 없음: `/attempts/{id}/comparison` 프록시, sharing-preferences(T1) |
| 5회차 CI | 유지 | main(`91664fd`)에 `e2e.yml` 없음. `tests/*-browser.mjs`·JDK 21 `verify_*`는 수동 |
| 5회차 수동 브라우저 스크립트 | 원인 확인 | 계정 단계 실패 재현. 목업 자녀 별명이 이미 `서윤`이고 #134 이후 화면은 바뀐 필드만 보내므로 "바뀐 내용이 없습니다." 표시. 스크립트 입력값 문제(B43) |
| 4회차 인프라·설계 차이 | 유지 | #211(Karpenter)·#212(S3 Gateway) 열림 |

### 3.3 발견 항목과 처리

| # | 종류 | 내용 | 처리 |
|---|---|---|---|
| A20·B36 | 아키텍처·결함(중간) | scoring 장애·시간 초과·5xx와 scoring 400(learning이 허용하는 keywords 100개×200자가 M2 토큰 한도 초과)을 ai가 모두 503 `SCORING_UNAVAILABLE`로 변환. learning `AiClient`는 판정·되묻기 공용 `ai` 서킷에서 5xx를 실패로 집계해 LLM 단독 판정·되묻기까지 30초 차단. `M2_CROSS_CHECK_ENABLED=false`여도 keywords·essayType이 있으면 scoring 호출(플래그는 HELD 여부만 결정). architecture 1.3 구간 독립·1.1 scoring 분리 취지와 다름. ai `judgment/service.py:63-71,111-153`, `clients/scoring_client.py:79-84`, learning `judgment/client/AiClient.kt:40,49,68`, `mission/controller/AdminMissionController.kt:239,255-256`, scoring `m2/service.py:39-40` | 이슈 #305 |
| B37 | 결함(중간) | 웹 관리자 기준표 저장이 `keywords`·`essayType`을 보내지 않아 새 rubric_version에서 빈 값으로 저장, 해당 미션 M2 교차 확인이 조용히 중단. 웹 `Rubric` 타입·편집 UI에 두 필드 없음. 웹 `data/admin/api.ts:60-61`, `domain/admin/operations.ts:96-108`, learning `AdminMissionController.kt:77-79,238-244`, `learning-service.yaml` `AdminRubric` | #306 해결(편집 UI 없이 기존 값 보존으로 결정): 웹 `Rubric`에 `keywords`·`essayType`(선택) 추가, `rubricWritePayload`가 불러온 값을 그대로 보내고 없으면 `[]`·`null` 명시. 기준표 화면에 "핵심어 n개·글 종류" 보존 안내. MSW는 learning `AdminRubricRequest`와 같은 검사(핵심어 ≤100개·1~200자, 글 종류 5종)·빈 값 기본값, 시연 기준표에 핵심어 추가. 계약 변경 없음. 테스트: `adminMockLifecycle`(불러와 저장해도 두 필드 유지, 빈 기준표 `[]`·`null`, 잘못된 글 종류 400) |
| B38 | 결함(낮음) | `/guardian-transfers*`가 `PublicAuthFilter` 동의 요구 대상이라, 서비스가 동의 없이 허용한 취소(`{id}/cancel`·`cancel-outgoing`)가 403 `CONSENT_REQUIRED`. 필수 동의가 빠진 학부모는 탈퇴 409 `TRANSFER_PENDING`과 취소 403 사이에서 막힘. core `account/controller/PublicAuthFilter.kt:49,58-67`, `guardianship/service/GuardianTransferService.kt:101-116`, `AccountWithdrawalService.kt:28` | 이슈 #307 |
| B39 | 결함(낮음) | `GuardianTransferController`는 `app.guardian-transfer.enabled`일 때만 등록되지만 `GuardianTransferAccessService` 대기 검사는 항상 동작. 플래그를 끄면 남은 PENDING 행이 탈퇴·연결 해제·삭제를 409로 막고 취소 API는 404. `ChildManagementService.kt:47,55` | 이슈 #307 |
| B40 | 결함(낮음) | `PUT /me/guardian-password`가 비밀번호 규칙 검사(422)를 역할 확인(403)보다 먼저 수행(#277과 같은 유형). core `GuardianPasswordService.kt:28-30` | #310 해결: `set`이 `accounts.lock`(학부모·활성 세션 확인)을 규칙 검사보다 먼저 수행하고, 규칙 검사는 여전히 재인증 grant 소비 전. MSW는 이미 `parentGuard`가 먼저. api-spec 3절 표·core OpenAPI 설명에 순서 기재. 테스트: `AccountManagementTest`(학생 세션 + 잘못된·올바른 값 → 403 `FORBIDDEN`, 저장 없음) |
| B41 | 설정(낮음) | ai #69 설정(`M2_CROSS_CHECK_ENABLED`·`M1_CHECK_ENABLED`·M2 임계값·`M1_MIN_CONFIDENCE`·`JUDGE_DEADLINE`·`SCORING_TIMEOUT`·`SCORING_RESERVE`)이 compose·`.env.example`·GitOps 어디에도 없어 `.env`로 켤 수 없음. GitOps local core `APP_GUARDIAN_TRANSFER_ENABLED`·scoring `M2_CONTENT3_RULE_ENABLED` 없음(compose·`.env.example`에는 있음, 기본 false). `compose.transfer-local.yaml`은 scoring을 끄지만 ai `SCORING_URL`은 유지. ai `config.py:47-58` | 이슈 #312 |
| B42 | 결함(낮음) | #199 평가 러너 `evaluatedScopes`가 M2 모델 scope(`judgment/grade-N/{type}`, api-spec 4.3.1)인데 평가 대상은 LLM 판정 프롬프트(scope `ai/judgment`, api-spec 4.2). 산출 `evaluation`으로 PROMPT 등록 후 `ai/judgment` 활성화 시 core `evidence.covers` 실패 400. `evaluation/runners/judgment_eval.py:60-62,267`, core `ModelVersionService.kt:46` | 이슈 #313 |
| B43 | 테스트(낮음) | `tests/requirements-browser.mjs`가 목업 자녀 별명과 같은 `서윤`을 입력해 저장 성공 문구를 기다림. 화면은 "바뀐 내용이 없습니다." 표시 후 15초 시간 초과(`requirements-browser.mjs:44-46`, `AccountForms.tsx:285-293`) | #318 해결: 새 별명 `서윤이`로 저장 성공 경로를 확인하고 삭제 확인 별명도 같은 값 사용. 끝까지 실행하며 드러난 후속 실패도 정리: 관리자 메뉴 링크의 기간 쿼리(`/admin/support?from=…`)를 링크 선택에 허용, 관리자 화면에 `/review` 링크가 없어 링크가 없으면 새로고침 없이 앱 안에서 이동(목업 상태 유지), 시연 로그인 후 화면 이동을 기다려 다음 이동이 덮어써지지 않게 함, 문의 답변 단계를 현재 화면 문구(`문의 답변과 공지 관리`·`문의 선택`·`답변 저장`)에 맞춤. `VITE_API_MOCK=true` 개발 서버에서 9단계 모두 통과 |
| C45 | 코드↔문서 | #289 오류 코드 6종(`TRANSFER_PENDING`·`TRANSFER_ALREADY_RESOLVED`·`TRANSFER_CHILD_UNAVAILABLE`·`TRANSFER_RECIPIENT_NOT_FOUND`·`TRANSFER_ACTIVITY_IN_PROGRESS`·`TRANSFER_PAYMENT_BLOCKED`)이 api-spec 1.3·OpenAPI 응답 설명에 없음. 탈퇴·연결 해제·삭제 요청 행에 `TRANSFER_PENDING` 409 미기재 | #308 반영: api-spec 오류 6종·기존 3개 작업의 대기 차단 및 OpenAPI 경로별 404/409 설명. 계약 검사 통과 |
| C46 | 코드↔문서 | 이관 7개 경로가 api-spec 2.1 표에 없음(본문 서술만). OpenAPI는 "격리된 로컬 이관 실험", api-spec은 구현 계약으로 기술. api-spec 1.5 상태 값에 이관 상태 없음 | #308 반영: 2.1 이관 7개 작업·1.5 상태 4종. #309·PR #325 기준 정식 흐름·기본 false 노출 제어로 표현 통일 |
| C47 | 코드↔문서 | api-spec 재인증 purpose 목록(1041행)에 `CHILD_TRANSFER`·`TRANSFER_ACCEPT` 없음(코드·OpenAPI·ERD는 7종) | #308 반영: 5.6 재인증 목적 7종·자녀/계정 범위 명시. MSW 두 목적의 Google 재인증 테스트 통과 |
| C48 | 코드↔코드 | MSW에 `/guardian-transfers*` 핸들러 없음, MSW `/me/reauth`가 `CHILD_TRANSFER`·`TRANSFER_ACCEPT`를 비밀번호 분기로 보내 401. 목업 모드에서 이관 화면 동작 안 함 | #308 반영: 이관 7개 MSW 작업·재인증·연결 갱신·대기 차단. 웹 219개 및 이관 Chrome 화면 2개 통과(실서버 E2E 아님) |
| C49 | 코드↔문서 | #289·V24가 state-diagram(이관 상태 머신, 2.3 TRANSFER·`transferred_at`·V26 부분 UK, 탈퇴 조건, `auth_session` 잠금)·class-diagram(이관 클래스·`GuardianPasswordService`)·sequence(이관 흐름)·usecase(UC-03·05)·user-flow(`/parent/transfers`·`ParentUnlock`·보호자 비밀번호 설정)에 없음. "다른 보호자 연결 없음" 문장(class 507·state 97·sequence 104행)에 이관 예외 없음 | #309 해결(이관은 정식 흐름으로 표기, 기능 플래그는 노출 제어로만 기재): state-diagram 2.4 `guardian_transfer.status`·2.5 `auth_session` 잠금 신설, 2.1 탈퇴·2.2 삭제의 `TRANSFER_PENDING` 차단, 2.3 TRANSFER 연결·`transferred_at`·V26 부분 UK. class-diagram 3.1에 이관·`ConversationTransferService`·`GuardianPasswordService` 클래스·관계·구현 상태. sequence-diagram 2.4 보호자 비밀번호 설정, 2.5 이관 시퀀스. usecase UC-02·03·05, user-flow 전체 지도·학부모(`/parent/transfers`·보호자 비밀번호)·예외(학부모 복귀). 세 문장에 이관 예외 추가. Mermaid 76개 파싱·상대 링크·앵커 신규 깨짐 0 |
| C50 | 코드↔문서 | core OpenAPI 4곳이 "학생 전환은 refresh 쿠키를 만료"(V24 이후 `keepRefresh=true`로 유지), `/auth/refresh` 401에 `PARENT_SESSION_LOCKED` 미기재. MSW `parent-unlock`은 잠기지 않은 세션에 401(core는 200) | #310 해결: OpenAPI 4곳을 "로그아웃은 만료, 학생 전환은 잠긴 부모 refresh 쿠키 유지(V24)"로 정정, `/auth/refresh` 401에 `PARENT_SESSION_LOCKED` 기재. MSW `parent-unlock`은 잠기지 않은 세션을 refresh와 같은 처리(`refreshUnlocked`)로 200. 기준 지문 테스트(`test_admin_operations_contract`)에 승인 변경 정규화 추가. 테스트: `guardianPassword.test.ts`(비잠금 세션 + 틀린 비밀번호 → 200) |
| C51 | 코드↔코드 | ai-service.yaml `JudgmentSummary.heldReason` enum 4종, 코드 `HeldReason`은 6종(`MODEL_DISAGREEMENT`·`LOW_CONFIDENCE`) | 이슈 #311 |
| C52 | 코드↔문서 | class-diagram `ScoringClient` 시그니처(1566-1569행)가 코드 `m2_scores(body, timeout)`·`m1_check(body, timeout)`와 다름. `ai.md:288` 논술 text 조합 "미정"(api-spec 4.2.2에서 `answerText`로 결정) | 이슈 #311 |
| C53 | 코드↔문서 | ERD 1213행 "learning Flyway V1~V8, 75개 테이블·664개 컬럼, learning 19/160" → 실제 V9·19/162·666 | 이슈 #311 |
| C54 | 코드↔문서 | architecture 2.6 트리: `scoring_client.py` "(예정)" 잔존, `judgment/cross_check.py`·scoring `m2/metadata.py`·`content3_rule.py`·notification `messaging/`·#289 클래스 없음 | 이슈 #315 |
| C55 | 코드↔문서 | architecture 4.3 "learning·report-worker → core는 삭제 완료 보고만"(625행). 실제로 learning `/internal/payment-usage/*`, report-worker `/internal/students/{id}/profile`·`/report-template` 호출(NetworkPolicy는 허용) | 이슈 #315 |
| C56 | 코드↔문서 | architecture 5장 트리에 삭제된 `kind/*-issue-171*` 잔존, 실제 kind 파일(`README.md`·`calico-installation.yaml`·`create-*-secret*.ps1`·`ingress-nginx-values.yaml`)·`compose.transfer-local.yaml`·`scripts/`·`playwright.transfer-local.config.ts` 누락. 768행 "`ci-<service>`는 해당 서비스 계약 파일" → ai·core는 `contracts/**` 전체, ai는 `evaluation/**`도 감시 | 이슈 #315 |
| C57 | 문서 간 | class-diagram 1706행 "`AnalysisService` 없이 `router.py`가 그래프를 실행" — #253 이후 `analysis_agent/service.py` `AnalysisService`(같은 문서 1618·1686행, architecture 397행과 모순) | 이슈 #315 |
| C58 | 코드↔문서 | README 53행 "동의 문서 미게시는 503"(V25 시드로 1.0 게시), 54행 "앱 Deployment는 저장소에 없음"(app-service chart 존재), 환경 변수 표에 `APP_GUARDIAN_TRANSFER_ENABLED`·`VITE_GUARDIAN_TRANSFER_ENABLED` 없음 | 이슈 #316 |
| C59 | 코드↔문서 | `STUDENT_RECORDS_PRIVATE`(403)가 api-spec·코드에만 있고 core OpenAPI 응답 설명에 없음(5회차 이월) | #317 해결: `requireShared`를 거치는 학부모 경로 13개 연산(자녀 답변 목록·상세, 분석 대화 생성·목록·상세·메시지·재시도·근거, `/agent/example-questions`, 리포트 템플릿 3종, 리포트 근거·다운로드)의 403 설명에 기재. 403이 없던 대화 경로는 403 응답을 추가. 기준 지문 테스트에 승인 변경 정규화, 루트 계약 테스트 `StudentRecordsPrivateContract` 추가 |
| T1 | 테스트 공백 | core HTTP 테스트 없음: `/attempts/{id}/comparison` 프록시, `/students/me/sharing-preferences`(서비스·DB 테스트만, 5회차 이월) | #317 해결: `LearningProxyIntegrationTest`(비교 프록시가 검증된 학생 문맥으로 `/internal/attempts/{id}/comparison` 전달·no-store·learning 409 `REVEAL_CONDITION_UNMET` 보존, 학부모는 공개·비공개 모두 403 `FORBIDDEN`이며 learning 미호출), `StudentSharingHttpTest`(학생 조회·변경·누락/null 400, 학부모의 학생 경로 403·연결 자녀만 조회, 학생의 학부모 경로 403, 위조 토큰 401). 남은 차이: api-spec 3절 표(276행)는 비교를 "학생·학부모(공개 설정을 따름)"로 적지만 core 코드·OpenAPI는 학생 전용. 학부모 비교 제공 여부 결정 필요 |
| D26 | 문서 간 | api-spec 929행 번호 없는 `### #289` 절(#245 번호 체계 정리 회귀) | #308 반영: 번호 없는 #289 절을 5.17로 이동, 기존 5.1~5.16 번호 유지 |
| D27 | 문서 간 | FN-ACC-11 "다른 연결 계정 권한 영향 확인"이 P02(학생당 보호자 1명)·V26 부분 UK와 모순 | #309 해결: FN-ACC-11 예외 처리를 "해제·삭제 후 그 자녀를 볼 다른 학부모 없음 안내, 넘기려면 이관, 이관 대기 중 해제·삭제 불가"로 정정. FN-ACC-12에 탈퇴 전 이관·대기 중 탈퇴 차단 추가 |
| D28 | 문서 간 | `docs/README.md` 색인에 `issue-228-m2-model-compat.md` 없음, issue-168 항목에 #251 절 미언급 | 이슈 #316 (README 색인 부분은 문서 정리로 해소) |
| D29 | 문서 간 | 이 문서의 낡은 상태 표기(#93·#97·A6·B17·5회차 발행 이슈) | 원장에 최종 상태로 반영 |
| A21 | 아키텍처(낮음) | core `_common/web/IdempotencyService.kt:62-66` `IdempotencyCleanup`의 `@Scheduled`가 scheduler 패키지 밖(2.1). #278 예외는 `_common/messaging`만. 만료 행 DELETE라 레플리카 중복 실행은 안전 | 이슈 #314 |

발행 이슈와 담당자(관련 기존 이슈 담당자):

| 이슈 | 항목 | 담당자 | 근거 이슈 |
|---|---|---|---|
| #305 | A20·B36 | 20220348-kim | #69 |
| #306 | B37·B23 | kim-4480, 20220348-kim | #242(관리자 화면), #69 |
| #307 | B38·B39 | inyoung9629 | #289 |
| #308 | C45~C48·D26 | inyoung9629 | #289 |
| #309 | C49·D27 | inyoung9629, kim-4480 | #289, PR #290(관련 이슈 없음) |
| #310 | B40·C50 | kim-4480 | PR #290(관련 이슈 없음) |
| #311 | C51~C53 | 20220348-kim | #69 |
| #312 | B41 | 20220348-kim, inyoung9629 | #236, #289·#298 |
| #313 | B42 | subinss838 | #199 |
| #314 | A21 | 20220348-kim | #278 |
| #315 | C54~C57 | 20220348-kim, kty2001 | #245·#273, #253 |
| #316 | C58·D28 | 20220348-kim, inyoung9629 | #235·#171, #228·#289 |
| #317 | C59·T1 | kim-4480, 20220348-kim | #206·#207 |
| #318 | B43 | kim-4480 | #134 |

### 3.4 아키텍처 원칙 정합성

core·learning은 import를 레이어로 분류해 전수 검사, Python·웹은 grep으로 확인.

지켜지는 원칙: 2장 기준 유지. 5회차 이후 코드 추가 확인:
- 레이어: #289 이관·V24 보호자 비밀번호·#286 재처리 코드 포함 presentation→repository/client 0건, domain의 Spring·Jackson·`HttpStatus` import 0건, infrastructure→service 0건, 다른 기능은 service로만 참조. 예외는 기존 결정(`_common/messaging` #278, support의 learning client #46)뿐
- 트랜잭션 안 외부 호출 없음: #289 `request`·`accept`·`cancel`은 DB만, `ReportTemplateService`는 잠금 블록 사이 AI 호출, #286 `claim`은 트랜잭션·`runBackground`는 트랜잭션 밖
- 클라이언트: core·learning·ai 모든 클라이언트에 타임아웃, #280 `ai-report-template` 별도 서킷, 재시도는 ai LLM 호출만
- 주기 작업: ShedLock 또는 레플리카 안전 조건부 UPDATE·DELETE. #286 선점 만료는 DB 시계
- DB 경계: 서비스별 자기 DB만, #289 SQL은 자기 기능 테이블만. report #252 경계 유지
- Python: ai #253·#254 구조 유지, #69 교차 확인은 Application(`judgment/service.py`·`cross_check.py`)·클라이언트는 `clients/`
- 웹: domain이 data·presentation 미참조, presentation의 `apiFetch`·mocks 참조 0건(이관·보호자 비밀번호·지원 화면 포함), access token 메모리 보관
- readiness는 하위 서비스 호출 없음(ai readiness가 scoring 미확인), Outbox는 core·report만, `@RabbitListener` 4개 모두 `RetryingConsumer`·수동 ACK
- GitOps: ai→`scoring-service:8001` egress와 scoring의 ai ingress 선언

원칙과 다른 구현:

| # | 내용 | 원칙 | 근거 |
|---|---|---|---|
| A20 | scoring 장애가 learning→ai 단일 서킷으로 번져 scoring과 무관한 판정·되묻기까지 차단 | 1.3 구간 독립, 1.1 scoring 분리 | 6.3 A20·B36, 이슈 #305 |
| A21 | `IdempotencyCleanup` `@Scheduled`가 `_common/web`에 위치 | 2.1 scheduler 진입점 | 6.3 A21, 이슈 #314 |

### 3.5 남은 공백

| 대상 | 내용 |
|---|---|
| CI | `e2e.yml` 야간 실행은 main 병합 전까지 동작하지 않음. `tests/*-browser.mjs`·JDK 21 `verify_*`는 수동 |
| 요구사항 차이 | FN-AGT-12(5회차와 같음) |
| 인프라·설계 차이 | #211·#212 열림, architecture 4.2~4.4는 Cluster Autoscaler·NAT 기술 |
| 기존 아키텍처 항목 | A13(scoring 소비자의 `ModelStartup` 생성·revision 조정) |

