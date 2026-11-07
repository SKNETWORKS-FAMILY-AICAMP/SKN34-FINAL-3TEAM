# 테스트·CI (#143·#237·#246·#136·#238)

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
- 주간 리포트: cron이 월요일 07:00·지난주 기간이라 테스트가 `report_job`(QUEUED)과 `report.generate` outbox 이벤트를 이번 주 기간으로 직접 삽입(`tests/e2e/support/db.ts`). 이후 OutboxRelay → RabbitMQ → report-worker → 완료 이벤트는 실제 경로

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

[점검 기록](audit.md)의 "통합 테스트 없음" 공백 중 core 계정·기기·Google 시작 경로 7묶음에 `account/AccountHttpTest.kt`(MockMvc로 실제 `PublicAuthFilter`·컨트롤러·서비스·DB 경유) 추가.

- 기반은 `PostgresRepositoryTest` 상속(메시징 없는 테스트, [db-dev-guide](db-dev-guide.md) 5장). 처음 `IntegrationTestSupport`로 만들었을 때 그 DB 연결이 100/100에 닿아 다른 통합 테스트가 `too many clients`로 실패
- 학생 403은 `PublicAuthFilter`(역할별 경로)와 서비스 `AccountManagementService.lock` 두 겹이고 둘 다 403 `FORBIDDEN`이라, 응답만으로는 필터 규칙 누락을 알 수 없음 → MockMvc `handler` 없음(컨트롤러 미도달)까지 확인
- 재인증 실패는 `X-Reauth-Token`을 쓰는 연결 해제·PIN 설정 두 경로에만 해당. PIN 규칙 위반 422는 재인증보다 먼저 검사

| 경로 | 확인한 성공·실패 |
|---|---|
| `GET /me/withdrawal/precheck` | 200·`no-store`, 5칸(`pendingPayments` 포함), 구독·미처리 환불·확인 중 결제가 있으면 `canWithdraw=false`(409 아님). 401, 학생 403 |
| `GET /children/{id}/deletion-impact` | 200·`no-store`, UNLINK·PROFILE·RECORDS. 다른 보호자 403 `CHILD_NOT_LINKED` |
| `DELETE /children/{id}/link` | 204, 감사 `CHILD_UNLINKED`. 재인증 누락·다른 목적 토큰 403 `REAUTH_REQUIRED` |
| `POST /student-devices/pairings` | 8자리 코드로 실제 기기 등록 201. 빈 목록·중복·4명 400 |
| `GET`·`DELETE /student-devices` | 해제 기기 제외·토큰 해시 없음, 재해제 204·감사 1건. 다른 보호자 404 |
| `PUT /children/{id}/pin` | 204, 감사 `STUDENT_PIN_CHANGED`. `1234` 422, 재인증 403 |
| `GET /auth/google/authorize` | 302, `Referrer-Policy: no-referrer`, 상태 쿠키 `sagomungchi_oauth`(HttpOnly·SameSite=Lax·600초), 쿠키·URL state 일치. 설정 없음 503 `OAUTH_UNAVAILABLE` |

남은 위험: `IntegrationTestSupport`는 연결 풀 상한이 없어 설정이 다른 클래스마다 캐시된 Spring 컨텍스트가 연결 10개(Hikari 기본값)를 계속 점유. develop 원본만으로 최대 99/100이라 이 기반을 쓰는 클래스가 하나 더 생기면 `too many clients` 위험(공통 기반 조정은 core 담당 판단).

## 4. GitOps chart CI (#238)

`.github/workflows/ci-gitops.yml`. `infrastructure/gitops/**`, migration 이미지가 복사하는 core·learning `db/migration/**`, 워크플로 파일 변경 PR과 `develop`·`main` push에서 실행.

| job | 검사 | 실패 조건 |
|---|---|---|
| charts | Helm v4.3.1·kubeconform v0.8.0을 공식 배포본에서 받아 SHA256 대조 | 체크섬 불일치 |
| charts | `environments/<env>/*.yaml`마다 `helm lint --strict`와 `helm template` | 렌더 실패, `values.schema.json` 위반, lint 경고 |
| charts | 렌더 결과와 `argocd/`·`policies/` 원본 manifest의 kubeconform `-strict` | 스키마 위반, 정의되지 않은 필드 |
| migrations | `migrations/*.Dockerfile`을 저장소 루트 context로 `docker build`(push 없음) | 빌드 실패 |

- 렌더 조합은 Argo CD 정의를 따름. 환경 파일 이름과 같은 chart가 있으면(`observability`·`platform-data`) 그 chart, 나머지는 파일 이름을 릴리스 이름으로 `app-service` chart에. namespace는 app-service `app`, observability `observability`, platform-data `platform`. 새 chart 추가 시 워크플로의 namespace 대응도 추가(빠지면 CI 오류). 의존 chart가 있으면 `helm dependency build` 선행(현재 없음)
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
