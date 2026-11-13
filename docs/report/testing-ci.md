# 테스트·CI·점검 원장

## 1. 계약 검사 CI (#143·#237)

DB 파일을 바꾸지 않은 API·이벤트 계약 변경도 CI에서 검사하도록 계약 검사를 `ci-contracts.yml`로 분리. 기존 테스트·검증 스크립트를 재사용하고 제품 API·DB 스키마는 변경하지 않음.

| 구성 | 동작 |
|---|---|
| `_web.yml` | npm ci → lint → **npm test** → build |
| `ci-contracts.yml` | PR·develop/main push·수동 실행. 계약·backend·web·scripts·설계 문서·Compose·RabbitMQ 정의 변경을 검사 |
| 계약 CI의 저장소 검사 | Python 3.12, PyYAML 6.0.3, jsonschema 4.26.0으로 `python -O -m unittest discover -s scripts/tests -v` |
| 계약 CI의 실제 응답 검사 | JDK21에서 core 통합 테스트 8개 클래스로 산출물을 생성하고 validator 7개 실행 |
| `ci-db-schema.yml` | DB 검증기 회귀와 실제 마이그레이션·ERD 대조 유지. API 계약용 jsonschema 별도 설치와 전체 계약 테스트 중복 실행 제거 |
| `ci-report-service.yml` | PR·push 모두 `contracts/openapi/report-service.yaml` 변경도 report CI 실행 |

- 계약 테스트가 컨트롤러 외 서비스·DTO·웹 어댑터도 읽으므로 `backend/**`, `frontend/web/**` 전체를 경로 필터에 포함. 보고서(`docs/report/**`)만 수정하면 CI 미실행. 경로 필터는 PR 전체 diff 기준
- `_spring.yml`의 서비스 전체 테스트·빌드·이미지 빌드는 유지. 계약 CI의 선택 테스트는 산출물 생성에 필요한 범위이며 core 전체 회귀를 대체하지 않음
- `clean test`로 이전 빌드 JSON 재사용 방지, 산출물 누락·스키마 불일치는 실패. continue-on-error·Docker 미존재 시 skip 없음. `test_contract_artifact_presence.py`가 산출물이 없는 임시 디렉터리에서 일곱 검증기 모두 실패하는지 검사

| 검사 | 실제 응답 생성 테스트 | 산출물 (core-service/build 기준) |
|---|---|---|
| 리포트 | ReportMessagingTest, ReportHttpTest | contracts/report-*.json |
| 알림 | NotificationIntegrationTest | generated-contracts/notification-*.json |
| 문의 | SupportIntegrationTest | generated-contracts/support-*.json |
| 결제 | PaymentIntegrationTest | generated-contracts/payment-*.json |
| 관리자 리포트 재처리 | AdminReportRetryIntegrationTest | admin-retry-contracts/report-retry-*.json |
| 분석 대화 | ConversationIntegrationTest | generated-contracts/analysis.json |
| 관리자 운영 | AdminOperationsIntegrationTest | generated-contracts/admin-operations.json |

- 분석 대화는 다섯 결과 유형(LLM, VERIFICATION_FAILED, AI_UNAVAILABLE, NO_RECORD, UNSUPPORTED) 테스트에서 core가 반환한 최종 SSE result를 내보냄(AI 대역 응답을 복사하지 않음). 관리자 운영은 인증된 MockMvc 요청으로 overview·jobs·job·queues·audit-logs 응답 생성, 큐 조회는 Testcontainers RabbitMQ 관리 API. 파일에 인증 헤더·토큰 미저장
- PostgreSQL·Redis·RabbitMQ와 core 코드는 실제, AI·learning·외부 결제는 테스트 대역. 운영 외부 연동 E2E로 해석하지 않음

### 로컬 재현

- Docker 실행 필수(core·learning·report 통합 테스트는 Testcontainers 사용, 합성 데이터·테스트 자격 증명)
- 웹: Node 22로 `npm ci`, `npm run lint`, `npm test`, `npm run build`
- 계약: `.github/workflows/ci-contracts.yml`의 테스트 8개 클래스와 검증 단계 7개를 그대로 실행. 분석·관리자 운영 검증기는 위 표의 JSON 경로를 인자로 받음
- Windows는 Python `.venv-contracts/Scripts/python.exe`, `gradlew.bat`, JAVA_HOME JDK21. Docker 컨테이너에서 Gradle을 실행하면 Docker 소켓 접근 설정 필요

## 2. 실서버 브라우저 E2E와 외부 스텁 (#246)

- 기존 브라우저 테스트(`playwright.config.ts`)는 전부 MSW 목업 대상이라 실제 서비스 연동 미검증(NFR-QA-01) → 외부 의존(Google OAuth·LLM·토스페이먼츠)을 `infrastructure/stubs/` 대역으로 바꾼 compose 스택에서 핵심 흐름 E2E
- 담당자 결정(2026-11-02)
  - 로그인 대체: Google 스텁(token·JWKS) + Playwright의 authorize 리다이렉트 재작성. 테스트 전용 로그인 API 미추가
  - CI 실행: 수동·E2E 구성 파일 변경 PR. 매일 03:00 KST schedule(GitHub는 기본 브랜치 main의 워크플로만 예약 실행, `e2e.yml`은 main에 반영됨)
  - 토스: core에 PG 주소 설정 추가, toss-stub, 결제 승인 E2E 1건
- 실제 Google·토스·LLM 키와 GitHub secrets 미사용. 모든 값은 `infrastructure/stubs/e2e.env`의 합성 값

### 설정 변경 (공개 API 계약 변경 없음)

| 대상 | 변경 | 기본값·영향 |
|---|---|---|
| core `app.payment.toss-base-url` (`TOSS_API_BASE_URL`) | `TossClient` 요청 주소를 설정값으로 | 기본 `https://api.tosspayments.com`. `test_sk_`·`test_gsk_` 키 검사 유지 |
| core `app.auth.google-token-url`·`google-jwk-url` | 코드 변경 없음. 완화 바인딩 환경 변수 `APP_AUTH_GOOGLETOKENURL`·`APP_AUTH_GOOGLEJWKURL`를 E2E 오버레이에서만 지정 | 기본 Google 주소 |
| ai-service | 코드 변경 없음. 기존 `OPENAI_BASE_URL`로 llm-stub 지정 | E2E 오버레이에서 실제 키 변수를 빈 값으로 고정 |

### 스텁 (`infrastructure/stubs/<target>-stub/`)

Node 22 alpine 표준 라이브러리만 사용(RS256 서명 필요). 각 이미지에 `GET /health`.

| 스텁 | 구현 경로 | 동작 |
|---|---|---|
| google-stub | `GET /jwks`, `POST /token` | 기동 시 RSA 키 생성. `code`는 base64url JSON `{sub,email,name,nonce,challenge,redirectUri}`라 상태 없음. client_id·secret·redirect_uri·PKCE(S256) 검증 후 `iss=https://accounts.google.com`, `aud=GOOGLE_CLIENT_ID`, `email_verified=true` id_token 발급 |
| llm-stub | `POST /v1/chat/completions` | `response_format.json_schema.name`으로 응답 선택. `Extraction`은 프롬프트의 모든 `elementId`를 답변 원문 인용·FOUND로 반환(정답 판정), `GeneratedQuestion`·`GeneratedNarrative`(숫자 없음)·`Classification`·`TemplateProposal` 고정 응답, `stream:true`는 SSE 조각·사용량·`[DONE]`. 그 외 이름은 400 |
| toss-stub | confirm, `orders/{orderId}` 조회, billing 발급·청구, cancel, transactions | 메모리 저장. Basic 키는 `test_` 접두사만 허용, 정기결제 키면 `TOSS_TEST_BILLING_MID`, 아니면 `TOSS_TEST_MID`. 조회 실패는 404 `NOT_FOUND_PAYMENT` |

### 스택·시드

- `compose.e2e.yaml`: `compose.yaml`·`compose.minio.yaml`과 함께 지정하는 오버레이. 스텁 3종, core·ai 환경 변수 재정의, report-api·worker는 버킷 생성 후 기동. scoring-service는 E2E 흐름에서 호출하지 않아 제외
- `e2e-seed`: 마이그레이션 직후 `frontend/web/tests/e2e/seed/core.sql`(core_db)과 `backend/learning-service/db/seed/demo_missions.sql`(learning_db) 실행
- `core.sql`(재실행 결과 동일): 필수 동의 문서 3종, 무료(`PAYMENT_FREE_PRODUCT_ID`)·유료(`E2E 프리미엄`, 14,900원) 상품, ADMIN 계정(Google sub `e2e-admin`)과 관리자 권한 4종
- 주간 리포트: cron이 월요일 00:00·지난주 기간이라 테스트가 `report_job`(QUEUED)과 `report.generate` outbox 이벤트를 이번 주 기간으로 직접 삽입(`tests/e2e/support/db.ts`). 이후 OutboxRelay → RabbitMQ → report-worker → 완료 이벤트는 실제 경로

### 테스트 (`frontend/web/tests/e2e/`, `npm run test:e2e`)

`playwright.e2e.config.ts` 별도 파일(webServer가 설정 파일 단위라 MSW 설정과 분리). 웹은 `http://127.0.0.1:5272` Vite dev(`VITE_API_MOCK=false`)로 `/api`를 core에 프록시.

| 스펙 | 흐름 |
|---|---|
| `admin-home.spec.ts` | 관리자 Google 로그인 → `/admin/home` 운영 현황·실제 집계 기간·학습 시도·처리 현황 |
| `learning-journey.spec.ts` 1 | 학부모 로그인·동의·자녀 등록 → 학습 시작 → 미션 작성·제출 → 정답 판정·되묻기 → 돌아보기 저장 → 공책 완료 → 답 공개 설정 |
| `learning-journey.spec.ts` 2 | 같은 학부모 재로그인 → 대시보드 학습 기록·원문 보기 → 이번 주 리포트 생성 → 상세 기간·수치 |
| `payment.spec.ts` | 유료 이용권 선택 → 주문 생성 → `/payment/success` → core confirm이 toss-stub 호출 → 결제 완료 |

- 학생 토큰은 메모리에만 있어 학생 단계는 화면 내 이동만 사용. 학생 모드 진입 시 학부모 refresh 쿠키가 지워져 학부모 단계는 새 컨텍스트에서 재로그인
- 토스 결제 위젯 JS·Google 폰트 차단, 외부 네트워크 호출 없음
- 가입 도우미는 동의 문서 제목을 고정하지 않고 화면이 조회한 `/api/v1/consent-documents` 응답의 TERMS·PRIVACY·GUARDIAN 3종 제목으로 체크박스 선택(V25 실제 문서가 합성 시드보다 최신이라 선택되는 문서가 바뀜, PR #300)

### 실행

```sh
COMPOSE="docker compose -p sagomungchi-e2e --env-file infrastructure/stubs/e2e.env -f compose.yaml -f compose.minio.yaml -f compose.e2e.yaml"
$COMPOSE up -d --build --wait core-service learning-service ai-service report-api report-worker
cd frontend/web && npm ci && npx playwright install chromium && npm run test:e2e
$COMPOSE down -v
```

- `--env-file` 지정으로 개발자 `.env` 미사용
- 인프라 포트(5432·5672·6379·8080 등) 고정이라 기본 compose 스택과 동시 실행 불가
- postgres 컨테이너 이름이 다르면 `E2E_POSTGRES_CONTAINER` 지정

검증(로컬, 2026-11-02·11-03): 4개 시나리오 통과, 실행 후 DB에서 `llm_usage` 모델 `e2e-stub`·되묻기 출처 `LLM`, `payment` `APPROVED`·구독 `ACTIVE`, `report_job` COMPLETED·report_id 연결 확인.

### 미검증 범위

- 학생 기기 등록·PIN 로그인, Google 재인증 팝업
- 토스 결제 위젯 JS, 정기결제 등록·갱신·실패·해지·환불 경로(toss-stub 경로만 구현)
- 분석 대화 스트리밍·리포트 템플릿 제안(llm-stub 응답만 구현)
- 지난주 기간 cron 스케줄링 자체
- kind `<target>-stub` Service·NetworkPolicy egress

## 3. core 계정 HTTP 경로 테스트 (#136)

[점검 원장](#5-develop-종합-점검-원장-16회차)의 "통합 테스트 없음" 공백 중 core 계정·기기·Google 시작 경로 7묶음에 `account/AccountHttpTest.kt`(MockMvc로 실제 `PublicAuthFilter`·컨트롤러·서비스·DB 경유) 추가.

- 기반은 `PostgresRepositoryTest` 상속(메시징 없는 테스트, [db-dev-guide](db-dev-guide.md) 5장). 처음 `IntegrationTestSupport`로 만들었을 때 그 DB 연결이 100/100에 닿아 다른 통합 테스트가 `too many clients`로 실패
- 학생 403은 `PublicAuthFilter`(역할별 경로)와 서비스 `AccountManagementService.lock` 두 겹이고 둘 다 403 `FORBIDDEN`이라, 응답만으로는 필터 규칙 누락을 알 수 없음 → MockMvc `handler` 없음(컨트롤러 미도달)까지 확인
- 재인증 실패는 `X-Reauth-Token`을 쓰는 연결 해제 경로에만 해당. PIN 설정은 2026-11-10 재인증 제거([auth-account 15절](auth-account.md#15-학생-pin-추가-재인증-제거-2026-11-10)) 뒤 규칙 위반 422만 검사

| 경로 | 확인한 성공·실패 |
|---|---|
| `GET /me/withdrawal/precheck` | 200·`no-store`, 5칸(`pendingPayments` 포함), 구독·미처리 환불·확인 중 결제가 있으면 `canWithdraw=false`(409 아님). 401, 학생 403 |
| `GET /children/{id}/deletion-impact` | 200·`no-store`, UNLINK·PROFILE·RECORDS. 다른 보호자 403 `CHILD_NOT_LINKED` |
| `DELETE /children/{id}/link` | 204, 감사 `CHILD_UNLINKED`. 재인증 누락·다른 목적 토큰 403 `REAUTH_REQUIRED` |
| `POST /student-devices/pairings` | 8자리 코드로 실제 기기 등록 201. 빈 목록·중복·4명 400 |
| `GET`·`DELETE /student-devices` | 해제 기기 제외·토큰 해시 없음, 재해제 204·감사 1건. 다른 보호자 404 |
| `PUT /children/{id}/pin` | 204, 감사 `STUDENT_PIN_CHANGED`. `1234` 422 (재인증 없음, 2026-11-10) |
| `GET /auth/google/authorize` | 302, `Referrer-Policy: no-referrer`, 상태 쿠키 `sagomungchi_oauth`(HttpOnly·SameSite=Lax·600초), 쿠키·URL state 일치. 설정 없음 503 `OAUTH_UNAVAILABLE` |

남은 위험: `IntegrationTestSupport`는 연결 풀 상한이 없어 설정이 다른 클래스마다 캐시된 Spring 컨텍스트가 연결 10개(Hikari 기본값)를 계속 점유. develop 원본만으로 최대 99/100이라 이 기반을 쓰는 클래스가 하나 더 생기면 `too many clients` 위험(공통 기반 조정은 core 담당 판단).

## 4. GitOps chart CI (#238)

`.github/workflows/ci-gitops.yml`. `infrastructure/gitops/**`, migration 이미지가 복사하는 core·learning `db/migration/**`, 워크플로 파일 변경 PR과 `develop`·`main` push에서 실행.

| job | 검사 | 실패 조건 |
|---|---|---|
| charts | Helm v4.3.1·kubeconform v0.8.0을 공식 배포본에서 받아 SHA256 대조 | 체크섬 불일치 |
| charts | `environments/<env>/*.yaml`마다 `helm lint --strict`와 `helm template` | 렌더 실패, `values.schema.json` 위반, lint 경고 |
| charts | `environments/prod/*.json`(#509): 저장소 chart values는 local과 같은 규칙으로 lint·template, `migrations/<release>.json`이 있으면 덮어써 migration Job까지 렌더. `kind`가 있는 manifest(NodePool·NetworkPolicy·ExternalSecret)는 그대로 kubeconform 대상 | 렌더 실패, 스키마 위반 |
| charts | 렌더 결과와 `argocd/`·`policies/` 원본 manifest의 kubeconform `-strict` | 스키마 위반, 정의되지 않은 필드 |
| migrations | `migrations/*.Dockerfile`을 저장소 루트 context로 `docker build`(push 없음) | 빌드 실패 |

- 렌더 조합은 Argo CD 정의를 따름. 환경 파일 이름과 같은 chart가 있으면(`observability`·`platform-data`) 그 chart, 나머지는 파일 이름을 릴리스 이름으로 `app-service` chart에. namespace는 app-service `app`, observability `observability`, platform-data `platform`. 새 chart 추가 시 워크플로의 namespace 대응도 추가(빠지면 CI 오류). 의존 chart가 있으면 `helm dependency build` 선행(현재 없음)
- prod의 외부 chart values(`external-secrets`·`aws-load-balancer-controller`·`karpenter`)는 chart를 받아야 해서 검사하지 않음. 새 외부 chart values를 추가하면 워크플로 건너뛰기 목록에도 추가(빠지면 app-service로 렌더돼 CI 오류)
- `app-service` 기본 values는 `image.repository`가 빈 문자열이라 단독 lint 시 스키마 `minLength` 실패. 환경별 이미지를 강제하는 설계이므로 실제 배포 조합으로만 lint

### CRD 처리

kubeconform은 기본 Kubernetes 스키마 → 공개 CRD 카탈로그 순으로 찾고, 둘 다 없는 종류만 `-ignore-missing-schemas`로 건너뜀(건너뛴 `Kind/이름 (파일)` 목록·경고 annotation 출력). CRD 스키마를 저장소에 복사하는 방식은 업그레이드마다 갱신이 필요해 제외.

| 항목 | 고정 값 | 근거 |
|---|---|---|
| Kubernetes 스키마 | [yannh/kubernetes-json-schema](https://github.com/yannh/kubernetes-json-schema) `e0c72a1`의 `v1.35.8-standalone-strict` | kind 노드 이미지 v1.35.8과 같은 버전 |
| CRD 스키마 | [datreeio/CRDs-catalog](https://github.com/datreeio/CRDs-catalog) `27233a5` | KEDA 2.21.0 CRD 갱신(2026-11-01) 포함, Argo CD `Application`·`ApplicationSet` 포함 |

KEDA chart 버전을 올리면 카탈로그 커밋도 같은 버전 이후로 갱신. 카탈로그의 Argo CD 스키마와 v3.5.5 일치 여부는 미확인.

### 로컬 실행

Linux 셸(WSL 또는 컨테이너)에서 같은 버전의 두 도구 설치 후 저장소 루트에서 실행(워크플로 run 블록과 같은 명령).

```bash
cd infrastructure/gitops
out=/tmp/gitops-rendered; mkdir -p "$out/local"
for values in environments/local/*.yaml; do
  release="$(basename "$values" .yaml)"
  if [ -d "charts/$release" ]; then chart="$release"; else chart=app-service; fi
  case "$chart" in app-service) ns=app ;; observability) ns=observability ;; platform-data) ns=platform ;; esac
  helm lint --strict "charts/$chart" --namespace "$ns" -f "$values"
  helm template "$release" "charts/$chart" --namespace "$ns" --kube-version 1.35.8 -f "$values" > "$out/local/$release.yaml"
done
kubeconform -strict -summary -kubernetes-version 1.35.8 \
  -schema-location 'https://raw.githubusercontent.com/yannh/kubernetes-json-schema/e0c72a1bc5f409d1685c0e1323460c8a98cd7459/{{.NormalizedKubernetesVersion}}-standalone{{.StrictSuffix}}/{{.ResourceKind}}{{.KindSuffix}}.json' \
  -schema-location 'https://raw.githubusercontent.com/datreeio/CRDs-catalog/27233a506de0085e71c7f9702597806a7f95eb24/{{.Group}}/{{.ResourceKind}}_{{.ResourceAPIVersion}}.json' \
  -ignore-missing-schemas "$out" argocd policies
```

migration 이미지는 `docker build -f infrastructure/gitops/migrations/core.Dockerfile .`처럼 확인.

### 검사하지 않는 항목

- Argo CD가 받는 외부 chart(KEDA 2.21.0, metrics-server 3.14.0) 렌더링
- 실제 클러스터 적용, Argo sync, admission webhook·NetworkPolicy 동작(스키마 검사는 필드 형식만)
- migration 이미지 실행·게시(#186)
- values 오타는 렌더되는 경로에서만 드러남. 스키마가 있는 `app-service`만 values 단계에서 차단

검증(2026-11-02): local 환경 파일 8개 lint·template 통과, 15개 파일 76개 리소스 Valid 76·Skipped 0. 타입 오류(`replicaCount: "one"`)는 helm lint, 스키마 없는 chart 필드 오타는 kubeconform이 실패 처리, 카탈로그에 없는 CRD는 건너뜀 목록으로 출력됨을 확인.

## 5. develop 종합 점검 원장 (1~6회차)

develop 종합 검증 회차별 결함 원장. 회차별 실행 결과 표와 재판정 표는 git 이력(삭제된 `docs/report/audit.md`) 참고. 번호는 결함 B, 코드↔문서 C, 문서 간 D, 아키텍처 A, 테스트 공백 T.

| 회차 | 기준 | 범위 | 번호 |
|---|---|---|---|
| 1 | develop `c608f52` | 코드 통합·코드↔문서·테스트·CI | B1~B17, C1~C15, D1~D14 |
| 2 | develop `40a2501` (PR #92) | 설계 문서 정합성 | D1~D11(결정 항목), #93~#97 |
| 3 | develop `640e0a2` | PR 16개 병합 후 + 아키텍처 원칙 | B18~B21, C16~C21, D15~D16, A1~A7 |
| 4 | develop `2db122c` | PR 73커밋 병합 후 | B22~B27, C22~C34, D17~D21, A8~A15 |
| 5 | develop `92d522b` | PR 28개 병합 후 | B28~B35, C35~C44, D22~D25, A16~A19 |
| 6 | develop `b97cc67` | PR 22개 병합 후 | B36~B43, C45~C59, D26~D29, A20~A21, T1 |

### 5.1 코드 결함·설정 (B)

| # | 내용 | 처리 |
|---|---|---|
| B1·B2 | 역할·내부 토큰 판정을 디코딩하지 않은 `requestURI` 접두사로 해 `;매개변수`·`%xx` 경로가 우회 | 해결(1회차, `MatchedPath` 정규화) |
| B3 | learning `student.deleted` 소비자 없음 → 삭제 COMPLETED 불가 | 해결(#128) |
| B4 | `ReportEntitlementService` 항상 503, 스케줄러가 자녀별 실패 미격리 | 해결(#48·#129) |
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
| B17 | 미사용 설정 주입·요청별 클라이언트 생성 | 해결(#135) |
| B18·B19 | core가 learning 404·403을 503으로 변환 | 해결(#163) |
| B20·B21 | 정책 마이그레이션 검사 버전 고정, `verify_feedback_learning.py`의 `CORE_URL` 누락 | 해결(#164) |
| B22 | 웹 `answerInquiry`가 core에 없는 경로 호출 | 해결(4회차, 도달 불가 화면 제거) |
| B23 | `AdminOperations.tsx` oxlint immutability 경고 | 해결(#306) |
| B24 | compose core에 RabbitMQ 관리 API 환경 변수 없음 | 해결(4회차) |
| B25·B26 | `ConversationRetryWorker` stale 예외, ai 소비자 ACK 범위 | 결함 아님 |
| B27 | core 통합 테스트 `too many clients` | 재현 안 됨(#218 이후) |
| B28 | 웹 support·help·notices 경로가 실제 API 미사용 | 해결(5회차) |
| B29·B30 | GitOps local migration revision·RabbitMQ 관리 API 값 낡음 | 해결(5회차, `test_core_migration_versions.py`) |
| B31 | `ReportTemplateService.forStudent` 오류 코드 | 해결(5회차, `STUDENT_UNAVAILABLE`) |
| B32 | #275 다중 보호자 전제가 P02와 불일치 | 해결(#289) |
| B33 | 리포트 설정 제안의 사용량 차감 | 결함 아님(api-spec에 명시) |
| B34·B35 | learning이 core 409를 모두 `REFUND_IN_PROGRESS`로 변환, 공지 목록 입력 검사가 권한 검사보다 먼저 | 해결(#276·#277) |
| B36 (A20) | scoring 장애·400을 ai가 모두 503으로 바꿔 learning의 `ai` 서킷이 LLM 단독 판정·되묻기까지 차단. 플래그가 꺼져도 scoring 호출 | 해결(#305): 플래그가 꺼지면 M2 미호출, scoring 실패는 LLM 판정만 200 + `modelScores.skipped`([ai 4.3.1](ai.md#431-scoring-실패-격리-305-2026-11-04)) |
| B37 | 웹 관리자 기준표 저장이 `keywords`·`essayType`을 보내지 않아 M2 교차 확인이 조용히 중단 | 해결(#306): 편집 UI 없이 불러온 값을 그대로 보존해 전송 |
| B38 | 동의가 빠진 학부모가 이관 취소(403 `CONSENT_REQUIRED`)와 탈퇴(409 `TRANSFER_PENDING`) 사이에서 막힘 | 해결(#307): 본인 목록·거절·취소만 동의 회복 경로로 허용 |
| B39 | 이관 플래그를 끄면 남은 PENDING이 탈퇴·삭제를 막고 취소 API는 404 | 해결(#307): 관리 경로는 항상 등록, 신규 요청·수락만 플래그로 제한 |
| B40 | `PUT /me/guardian-password`가 규칙 검사(422)를 역할 확인(403)보다 먼저 | 해결(#310) |
| B41 | #69 교차 확인 설정·이관·content_3 플래그가 compose·GitOps에 전달되지 않음 | 해결(#312, [infra 3.3](infra.md#33-교차-확인이관content_3-설정-전달-312)) |
| B42 | 평가 러너 `evaluatedScopes`가 M2 모델 scope라 PROMPT 활성화 시 `evidence.covers` 실패 | 해결(#313): `["ai/judgment"]` |
| B43 | `requirements-browser.mjs`가 목업과 같은 별명을 입력해 저장 성공 문구를 못 받음 | 해결(#318) |

### 5.2 코드↔문서 (C)

| # | 내용 | 처리 |
|---|---|---|
| C1~C15 | report·ai OpenAPI 누락, 오류 코드, ERD 수치·결번, `SPEECH` CHECK, 미구현 표기, 환경 변수 | 해결(1회차) |
| C16~C21 | class-diagram 구현 이름·상태, #132·#47 구현 상태 | 해결(3회차) |
| C22~C34 | ai OpenAPI, 재처리 응답 선언, 오류 코드, 누락 경로, SSE 수명, ERD 수치, architecture 트리 | 해결(4회차) |
| C35~C44 | api-spec 1.3 누락 오류 코드·경로, 옛 목업, ERD 수치, class-diagram 파일 위치, user-flow 누락 흐름 | 해결(5회차) |
| C45~C48 | #289 이관 오류 코드 6종·경로 7개·재인증 purpose 2종이 api-spec에 없음, MSW 이관 핸들러 없음 | 해결(#308) |
| C49 | #289·V24가 state·class·sequence·usecase·user-flow에 없음 | 해결(#309) |
| C50 | OpenAPI "학생 전환은 refresh 쿠키 만료"(V24 이후 유지), `PARENT_SESSION_LOCKED` 미기재 | 해결(#310) |
| C51~C53 | ai OpenAPI `heldReason` enum 4종(코드 6종), class-diagram `ScoringClient` 시그니처, ERD 수치 | 해결(#311) |
| C54~C57 | architecture 2.6·4.3·5장 트리와 내부 호출 서술, class-diagram `AnalysisService` 모순 | 해결(#315) |
| C58 | README 동의 문서 503·Deployment 서술, 환경 변수 표 | 해결(#316) |
| C59 | `STUDENT_RECORDS_PRIVATE`(403)가 core OpenAPI에 없음 | 해결(#317): 학부모 경로 13개 연산에 기재 |

### 5.3 문서 간 (D)

| # | 내용 | 처리 |
|---|---|---|
| D1~D14 | (1회차) 미구현 잔존 문장, 알림 상태·채널, SSE 연결 시간, 재인증 흐름, 클래스 이름 | 해결 |
| D1~D11 | (2회차 결정) Google 계정 복구 위임, 삭제 1단계 + `X-Reauth-Token`, `pinLocked` 통일, 용도별 SSE 시간, Problem `traceId` 필수, 내부 API OpenAPI 추가, 이벤트 스키마 선행 | 반영 |
| D15·D17·D22·D28 | `docs/README.md` 보고서 색인 누락 | 해결(문서 정리로 색인 재작성) |
| D16·D26 | 이슈별 절이 번호 체계 밖 | 해결(#165·#245·#308) |
| D18·D21 | 종료된 임시 통합 규칙, 루트 병합 메모 | 삭제(4회차) |
| D19·D20 | 알림 `RUNNING`·`conversation_job_retry.status` 상태 표 누락 | 해결(4회차) |
| D23~D25 | ml/m2 앵커, 낡은 상태, Redis 사용처 표 기준 | 해결(5회차) |
| D27 | FN-ACC-11 "다른 연결 계정 권한 영향"이 P02(보호자 1명)와 모순 | 해결(#309) |

### 5.4 아키텍처 (A)·테스트 공백 (T)

| # | 내용 | 처리 |
|---|---|---|
| A1 | `OutboxRelay.relay`가 트랜잭션 안에서 AMQP 발행 | 해결(#166) |
| A2 | 서킷 브레이커가 core→learning에만 | 해결(#167·#192) |
| A3·A4·A8·A16 | domain의 `HttpStatus`·Jackson·`BusinessException(ErrorKind)` 의존, 레이어 역참조 | 해결(#168·#169·#249) |
| A5·A14 | 웹 컴포넌트의 API 직접 호출 | 해결(#170·#255) |
| A6 | ai→scoring 교차 확인 호출자 없음 | 해결(#69) |
| A7 | 앱 배포 chart·NetworkPolicy·관측 미구현 | 해결(#171·#204) |
| A9~A12·A15 | 알림 Redis 발행자의 Application 호출, 기능 간 controller·config 참조, report 기능 간 DB 접근, ai router 계층 건너뜀, learning 삭제 소비 위치 | 해결(#250~#253·#256) |
| A13 | ai·scoring 소비자에 revision 조정 로직 | 해결(ai #254, scoring #632: 세션별 `ModelStartup` 생성·대상 필터를 `ModelSync`로 이동, [scoring](scoring.md) 2절) |
| A17~A19 | 이벤트 기록 위치, 기능 간 client·repository 직접 참조, ai 리포트 설정 제안 프롬프트 등록 | 해결(#278~#280) |
| A21 | `IdempotencyCleanup`의 `@Scheduled`가 scheduler 패키지 밖 | 해결(#314) |
| T1 | core HTTP 테스트 없음: 비교 프록시, sharing-preferences | 해결(#317). 대상 차이는 학생 전용 유지로 결정(#632, 2026-11-13): api-spec 2.3은 11/09에 정정됐고 1절 오류 표의 `STUDENT_RECORDS_PRIVATE` 설명에서 비교를 뺌 |

### 5.5 남은 공백

- CI: `tests/*-browser.mjs`·JDK 21 `verify_*`는 수동. `e2e.yml` 야간 실행 결과 미확인
- 요구사항 차이: FN-AGT-12 수학 점검 예시 질문은 요구사항을 실제 동작(고정 5문항, 기록 유무로 일괄 판단)에 맞추고 M1 활성 후 추가로 정리(#632, 2026-11-13 결정)
- 로컬 실행 주의: core·learning이 Gradle 캐시 볼륨 하나를 함께 쓰면 잠금 충돌로 빌드가 시작 전 실패

## 6. 아키텍처 원칙 점검 기준

[아키텍처](../design/architecture.md) 1.1~1.6·2.1~2.4·3장·4장 원칙을 HEAD 코드와 대조한다. core·learning은 패키지 import를 레이어(`controller`·`consumer`·`scheduler` / `service`·`facade` / `domain` / `repository`·`client`·`messaging`)로 분류해 전수 검사하고, 나머지는 클라이언트·트랜잭션·설정을 grep으로 확인한다. 다른 구현은 A 번호로 원장에 기록한다.

| 원칙 | 확인 방법·현재 결과 |
|---|---|
| 서비스 DB 직접 접근 금지(1.1) | 각 서비스 DB URL은 자기 DB만. 다른 서비스 데이터는 내부 API·이벤트로만 |
| core만 공개 API·JWT 검증(1.1·2.3) | 웹 `apiClient`는 core `/api/v1`만. 내부 호출은 내부 토큰 + 컨텍스트 헤더 |
| 컨텍스트 전파(2.3) | ai `clients/base.py`가 `X-User-*`·`X-Student-Scope`를 learning 호출에 부착. report 소비자는 `SYSTEM` + 이벤트 학생 범위 |
| 레이어 단방향·기능 간 service 경유(2.2) | controller→repository 0건, 다른 기능 repository 참조 0건, Presentation의 `@Transactional` 0건. 예외는 기존 결정(`_common/messaging` #278, support의 learning client #46) |
| 트랜잭션 안 외부 호출 금지(2.2) | 리포트 복구 `NOT_SUPPORTED`, 알림 Redis 발행 `AFTER_COMMIT`, learning 피드백은 `FeedbackFacade` 트랜잭션 밖 AI 호출, report Outbox는 advisory lock·짧은 트랜잭션 |
| 재시도 계층(1.3) | 재시도는 ai LLM 호출(1회, 1초)과 되묻기 유출 재생성(1회)만. 서비스 간 호출은 재시도 없음. 모든 클라이언트에 타임아웃 |
| Outbox·멱등 소비(1.6) | Outbox는 core·report만, learning은 발행 없음, ai·scoring은 best-effort. 리스너는 수동 ACK·`RetryingConsumer` |
| readiness(4.4) | core·learning `readinessState,db,rabbit`, ai RabbitMQ, scoring RabbitMQ·모델, report DB. 하위 서비스 호출 없음 |
| 스케줄 중복 방지(1.5) | 정기·복구 스케줄러는 ShedLock 또는 레플리카 안전 조건부 UPDATE·DELETE |
| 프론트엔드(3장) | access token 메모리 보관, 서버 상태는 TanStack Query만, `domain`이 `data`·`presentation`을 참조하지 않음, presentation의 `apiFetch`·mocks 참조 0건 |


## 7. report PDF 실행 환경 설치 재시도 (#539)

report CI의 `Prepare report PDF runtime`에서 Ubuntu 패키지 미러 DNS 일시 장애가 나면 테스트 실행 전 설치가 실패했다. report 전용 `backend/report-service/scripts/install_pdf_runtime.sh`를 CI와 Docker 이미지 빌드에서 함께 사용한다. 다른 Python 서비스의 단계와 제품 API는 변경하지 않는다.

- OS 의존성(`playwright install-deps chromium`) → 한글 글꼴(`fonts-noto-cjk`) → Chromium(`playwright install chromium`) 순서로 분리한다. 실패한 단계만 최대 3회 실행하고 사이에 5초·10초 대기한다. 마지막 종료 코드를 그대로 반환해 지속 장애를 성공으로 숨기지 않는다.
- Playwright가 내부에서 실행하는 apt에도 적용되도록 `/etc/apt/apt.conf.d/80report-pdf-runtime`에 파일 다운로드 재시도 3회, HTTP·HTTPS 대기 30초, update 일부 실패도 오류로 처리하는 설정을 둔다. 단계 재시도와 APT 자체 파일 재시도는 서로 다른 계층이다.
- Chromium 다운로드 연결 대기는 45초, CI 설치 단계 전체 상한은 5분이다. 상한 초과나 최종 실패면 해당 테스트 작업은 실패한다. develop의 CI 병렬화에 따라 이미지 빌드는 별도 작업으로 실행되며, 이미지 안에서도 같은 설치 스크립트가 실패하면 빌드가 실패한다.
- CI의 일반 사용자에서는 필요한 apt 작업만 sudo, Docker 빌드에서는 root로 실행한다. Chromium 경로와 최종 이미지 사용자(uid 10001)는 유지한다.
- 같은 설치 실패가 이미지 빌드에서도 발생할 수 있으므로 Dockerfile도 적용했다. 새 액션·Python 패키지·외부 미러·기본 이미지 교체는 없다.

근거: [Playwright 브라우저·의존성 분리 설치](https://playwright.dev/python/docs/browsers), [APT 재시도 설정](https://manpages.debian.org/trixie/apt/apt.conf.5.en.html).

검증: `scripts/tests/test_report_pdf_runtime.py`는 실제 POSIX 스크립트에 격리된 명령을 연결해 정상 설치, 각 단계 일시·지속 실패, 후속 단계 차단, 종료 코드, sudo 경로를 확인한다. 테스트에서는 호스트 패키지를 설치하지 않는다. report 원격 CI 통과는 PR 생성 후 해당 커밋의 실행 결과로 별도 확인한다.

2026-11-12 로컬 검증(develop `0565ef3e` 기준):

- report 전체 pytest 426개 통과, Ruff check·format 통과. 기존 Starlette/httpx 사용 중단 예정 경고 1개가 있다.
- 설치 장애 회귀 테스트 8개: Windows Git Bash와 Linux POSIX 셸에서 통과.
- 실제 Docker 이미지 빌드 및 uid 10001·네트워크 차단 상태에서 합성 리포트 PDF·HTML·Markdown 생성 통과. Noto Sans CJK KR 글꼴 검색 확인. 별도 `fc-match` 실행에서는 쓰기 가능한 글꼴 캐시 디렉터리가 없다는 경고가 있었으나 글꼴 조회와 PDF 생성은 성공했다.
- 재사용 워크플로에서 report 전용 설치 단계를 제외한 구성이 기존과 동일함을 비교 확인.
- GitHub report CI는 PR 생성 후 검증할 항목이며, 위 로컬 결과로 원격 통과를 대신하지 않는다.

develop `7ef72985` 병합 시 PR #544의 테스트·이미지 빌드 병렬화, 이미지 캐시, 작업별 15분 제한과 report 설치 단계 5분 제한을 유지했다. report 설치 명령만 재시도 스크립트 호출로 대체한다.
병합 후 Linux 설치 장애 테스트 8개와 report 렌더링 테스트 11개가 통과했다. YAML 구조 비교로 최신 develop 대비 report 설치 명령 외 변경이 없음을 확인했다.
