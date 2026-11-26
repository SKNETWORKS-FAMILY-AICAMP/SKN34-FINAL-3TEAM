# 인프라·배포·운영

로컬 kind 플랫폼, AWS 데모 배포, CD, 운영 경보·trace, 부하 시험의 결정과 근거. 실행 절차는 각 디렉터리 문서가 소유한다: [kind](../../infrastructure/kind/README.md), [platform-data](../../infrastructure/gitops/charts/platform-data/README.md), [prod 환경](../../infrastructure/gitops/environments/prod/README.md), [EKS](../../infrastructure/eks/README.md), [AWS](../../infrastructure/aws/README.md), [CD](../../infrastructure/cd/README.md), [부하 시험](../../evaluation/load/README.md). 경보 규칙·경계는 [아키텍처 4.7](../design/architecture.md#47-운영-경보-구성-경계-187).

## 1. 로컬 플랫폼 (#17)

[아키텍처 4.1](../design/architecture.md#41-환경-구분)의 로컬 Kubernetes 환경. 설정값은 [local values](../../infrastructure/gitops/environments/local/platform-data.yaml).

### 1.1 환경 경계

- 로컬은 kind 단일 노드에 PostgreSQL·RabbitMQ·Redis·MinIO, 운영은 RDS·S3와 RabbitMQ·Redis StatefulSet
- 저장소 구성은 `platform-data` chart 하나. PostgreSQL·MinIO는 로컬 values에서만 활성화
- 로컬 API·HTTP·HTTPS는 loopback에만 노출
- 기준 PC: Windows 11, i5-1135G7 4코어·8스레드, 16GB, Docker Desktop WSL 2

### 1.2 Kubernetes·CNI·Ingress 조합

| 설정 | 근거 |
|---|---|
| kind v0.33.0 / Kubernetes v1.35.8 | ingress-nginx v1.15.1의 E2E 범위가 1.35까지. 공식 노드 이미지 digest 고정 |
| Calico v3.33.0 / IPv4·iptables | Calico의 1.35 테스트 범위. 기본 CNI 비활성 |
| `MutatingAdmissionPolicy` feature gate·beta API | Calico native v3 CRD 기본값 처리에 필요, 1.35에서 기본 비활성 |
| Pod `10.244.0.0/16`, Service `10.96.0.0/12` | 기준 PC의 Wi-Fi·WSL·Docker 대역과 비중복. 다른 네트워크에서는 재확인 |
| ingress-nginx controller v1.15.1 / chart 4.15.1 | 이슈 지정 유지(사용자 결정). 유지보수 종료 프로젝트라 버전 고정이 보안 패치를 뜻하지 않음. 운영 ALB 설계는 불변 |

### 1.3 MinIO

- 커뮤니티판의 소스 전용 배포 전환으로 Chainguard 공개 이미지 사용. linux/amd64 digest를 [공통 values](../../infrastructure/gitops/charts/platform-data/values.yaml) `minio.image`에 고정
- 서버 이미지에 shell·curl이 있다고 가정하지 않음. 버킷 초기화는 `curlimages/curl:8.17.0`의 S3 SigV4 요청, 인증은 curl 설정 stdin
- 버킷 3개(`sagomungchi-local-missions`·`-reports`·`-models`)가 단일 Pod·2Gi PVC 공유. 버킷 분리가 앱의 사용자별 권한 검사를 대체하지 않음

### 1.4 초기화와 자격 증명

- Compose MinIO는 [compose.minio.yaml](../../compose.minio.yaml)로 분리. Compose는 병합 전에 각 파일의 변수를 해석해 profile만으로 `${VAR:?}` 검사를 피할 수 없기 때문
- Secret 준비 스크립트는 PowerShell 7 이상. MinIO 사용자명 3자·비밀번호 8자 이상
- RabbitMQ는 계정 기동 후 Job이 관리 API로 `definitions.json` 반영(계정을 JSON에 넣지 않으려고 순서 분리). `default_queue_type`을 전역 quorum으로 강제하지 않음(Pod별 exclusive 큐와 충돌)
- `init.sql`·`definitions.json`은 원래 위치에 두고 Helm `.Files`와 Compose 마운트가 같은 파일을 읽음
- `.env`의 계정 6개만 `platform/platform-data-credentials` Secret으로 준비. 기존 Secret과 값이 다르면 덮어쓰지 않음(환경 변수 변경만으로 계정이 회전되지 않음)
- 활성 저장소의 requests·limits·필수 설정이 없으면 렌더링 중단

### 1.5 자원 예산

requests는 스케줄링 기준, limits는 상한이며 실측값이 아님.

| 대상 | CPU request / limit | 메모리 request / limit | PVC |
|---|---|---|---|
| PostgreSQL | 100m / 500m | 256Mi / 512Mi | 2Gi |
| RabbitMQ | 250m / 1000m | 512Mi / 2Gi | 2Gi |
| Redis | 50m / 250m | 64Mi / 256Mi | 512Mi |
| MinIO | 100m / 500m | 256Mi / 1Gi | 2Gi |
| ingress-nginx controller | 100m / 500m | 128Mi / 512Mi | - |
| **상시 합계** | **600m / 2750m** | **1216Mi / 4.25Gi** | **6.5Gi** |

- 초기화 Job(RabbitMQ·MinIO)은 각 50m/250m, 64Mi/128Mi
- 플랫폼 전체 약 6GiB 예산(control plane 등 1.5GiB 포함). 앱·모델 추론·관측·이미지 빌드는 제외. Docker 상한 약 7.62GiB라 Compose 전체와 kind는 동시에 실행하지 않음
- 시작값: PostgreSQL `shared_buffers=64MB`·`max_connections=40`·`work_mem=2MB`, RabbitMQ `vm_memory_high_watermark.absolute=1GiB`(quorum WAL 512MiB의 3배 고려해 limit 2Gi), Redis `maxmemory=128mb`·`noeviction`. 운영 튜닝 값 아님
- StatefulSet 삭제·축소 시 PVC 보존(kind 노드 삭제로부터는 보호하지 않음). 로컬 provisioner는 PVC 요청을 quota로 강제하지 않을 수 있어 호스트 여유 30GiB 이상 권장

## 2. 로컬 앱 배포·네트워크·관측 (#171)

EKS 사용 확정(#171 PM 결정).

| 릴리스 | Service / readiness | migration |
|---|---|---|
| core-service | 8080 / `/actuator/health/readiness` | 전용 Flyway 이미지 `migrate` |
| learning-service | 8081 / `/actuator/health/readiness` | 전용 Flyway 이미지 `migrate` |
| ai-service | 8000 / `/health/ready` | 없음 |
| scoring-service | 8001 / `/health/ready` | 없음 |
| report-api | 8002 / `/health/ready` | report 이미지의 `alembic upgrade head` |
| report-worker | HTTP Service 없음 (`python -m app.worker`) | report-api의 migration 선행 |

### 2.1 배포

- core·learning Flyway는 앱 기동에서 비활성. 기존 SQL을 전용 이미지에 복사해 `FLYWAY_*`만 주입. migration 허용 NetworkPolicy는 PreSync wave -2, Job은 wave -1. `migration.revision`은 SQL/Alembic 변경 시 명시적으로 갱신. 실패 시 앱 sync 중단
- local values의 `:local` 태그는 kind에 직접 로드할 빌드 입력
- Secret: `app/app-service-credentials`, `observability/observability-credentials`. chart는 이름·키만 참조. URL 비밀번호는 URL 인코딩
- **report Alembic URL**: `migrations/env.py`가 URL을 `ConfigParser`에 넘겨 `%`가 보간 오류를 일으킴. Alembic Job에만 `%`→`%%` 이스케이프한 `REPORT_ALEMBIC_DATABASE_URL`을 별도 키로 제공
- core·learning Java agent는 chart의 선택적 initContainer(OTel Java agent 2.33.1 digest 고정)
- local report presigned URL은 `S3_PUBLIC_ENDPOINT_URL=http://127.0.0.1:19000`. 호스트 다운로드 확인 시 MinIO 9000을 19000으로 port-forward

### 2.2 네트워크·확장

- `app`·`platform`·`observability` 기본 거부 + 필요한 포트만 허용. app ingress는 ingress-nginx → core 8080과 설계 4.3의 내부 호출만. RabbitMQ 관리 15672는 core와 초기화 Job, metrics 15692는 Prometheus만
- startup·liveness는 `/health/live`·`/actuator/health/liveness`, readiness만 ready 경로. core snapshot·scoring 모델 준비가 오래 실패해도 startup probe가 백그라운드 재시도를 끊지 않도록 분리
- local 단일 레플리카에서는 HPA/PDB 비활성. report-worker는 두 큐 기준 KEDA 0–1, `CONSUMER_PREFETCH=1`
- core 15초 preStop·180초 grace·Spring graceful 30초는 SSE executor 85초·timer 5초를 고려한 시작값(롤링 종료 실측 전)
- NetworkPolicy 렌더만으로 Calico/VPC CNI 동작이 증명되지 않음

### 2.3 관측

- local `observability` chart: OTel Collector v0.164.0, Prometheus v3.15.1, Grafana v13.3.0, KEDA 2.21.0. 외부 Ingress 없음, 저장은 `emptyDir`
- Grafana: 저메모리 첫 기동이 60초를 넘어 startup probe 300초, Pod 두 개가 겹치지 않게 `Recreate`, CPU 한도 250m에서 throttling으로 startup 실패해 요청 100m·한도 1
- AI·scoring·report-api에는 exporter가 없어 core·learning Java agent 지표만 수집
- Langfuse: EKS 자체 호스팅 예정(#379, 미배포). 공식 최소 자원이 로컬 한도 초과. Collector에 EKS용 OTLP traces → Langfuse 전달 설정만 있음(local 비활성)
- AI Langfuse v4 계측: `LANGFUSE_ENABLED` 기본 false. true이면 public/secret key와 Collector endpoint가 모두 필요(빠지면 기동 오류). call type·프롬프트 버전·모델·토큰·오류 코드만 기록, 원문·학생 ID 미전달

### 2.4 검증에서 얻은 교훈

- 다중 플랫폼 캐시 이미지는 `kind load docker-image`에서 digest 누락 오류 → `docker image save --platform linux/amd64` archive로 로드
- kind 노드 `/tmp`는 별도 tmpfs라 archive가 containerd에서 보이지 않음 → 노드 `/root`에 복사
- KEDA `scaledjobs.keda.sh` CRD가 client-side apply annotation 한도(262144 bytes) 초과 → chart `crds.additionalAnnotations`에 `argocd.argoproj.io/sync-options: Replace=true`(local 전용)
- ingress-nginx controller가 0개면 admission webhook 연결 거부로 Helm 설치 실패 → controller 먼저 복구
- Helm으로 직접 설치할 때는 Argo PreSync 훅이 없으므로 core·learning·report-api를 먼저 설치하고 migration Job 완료 후 나머지 설치
- 미검증: 실제 모델 가중치 추론, SSE 진행 중 종료, Langfuse 저장·조회

## 3. kind 통합과 환경값 (#273·#236·#312)

### 3.1 kind 클러스터 통합 (#273)

로컬 kind를 `sagomungchi-local` 하나로 통합(Docker 메모리 약 7.6GiB에서 두 클러스터 동시 운영 곤란).

- 앱 Secret `create-app-secrets.ps1`과 platform Secret `create-platform-secret.ps1`이 같은 루트 `.env`를 읽어 계정 원본 단일화. 대상 context·노드를 고정 검사, 기존 Secret 값과 불일치 시 중단
- 관측 Secret은 `.env`에 `GRAFANA_ADMIN_USER`·`GRAFANA_ADMIN_PASSWORD`가 둘 다 있을 때만 생성
- 옛 `sagomungchi-issue171` 클러스터·`kind-issue171` 네트워크가 남아 있으면 `kind delete cluster --name sagomungchi-issue171`, `docker network rm kind-issue171`

### 3.2 kind 환경값·외부 egress (#236)

kind values가 `compose.yaml`보다 적어 Google 로그인·토스 결제·LLM 판정이 동작하지 않던 문제 보완.

- 외부 키(Google·토스·결제 암호화 키·`ANTHROPIC_API_KEY`)는 루트 `.env`를 원본으로 `create-app-secrets.ps1`이 값이 있을 때만 앱 Secret에 복사. values는 `optional: true` 참조. 토스 `live_` 키 거부
- 인증 TTL·Redis 포트·LLM 공급자·모델 등 비밀이 아닌 값은 values에 compose 기본값
- 추가하지 않은 값: `REDIS_PASSWORD`(양쪽 모두 비밀번호 없음), `OPENAI_BASE_URL`(sLLM 사용 시에만), report-api의 `RABBITMQ_URL`(소비는 worker만)
- egress: core·ai에만 사설·CGNAT·link-local·loopback을 뺀 TCP 443 허용. Calico 오픈소스판에 FQDN 규칙이 없고 공급자 IP 목록은 유지 곤란
- 웹은 호스트 Vite에서 `CORE_PROXY_TARGET`·`CORE_PROXY_HOST`로 `/api`를 kind Ingress(`api.sagomungchi.local`)에 전달
- 토스 웹훅은 외부에서 로컬 kind로 들어올 수 없어 확인 범위 밖
- 토스 결제위젯 키(`test_gck_`·`test_gsk_`)는 전자결제 신청 이후에만 보임. 신청 전에는 문서 테스트 키(`test_gck_docs_`·`test_gsk_docs_`)와 `TOSS_TEST_MID=tgen_docs` 사용(다르면 `PAYMENT_PG_MISMATCH`). 문서 테스트 키는 주문번호 조회가 `NOT_FOUND_MERCHANT`라 상태 재확인·복구·관리자 대조 경로 검증 불가
- 실제 확인(2026-11-03): Ingress `/api` 200·외부 `/internal` 404, core→Google·토스와 ai→OpenAI 허용, learning 외부 443 차단, Google 로그인·LLM 판정·토스 테스트 결제 승인

### 3.3 교차 확인·이관·content_3 설정 전달 (#312)

- [AI 4.3](ai.md#43-판정-모델-교차-확인-69)의 교차 확인 설정 10개(판정 마감·scoring timeout·reserve, M2·M1 플래그와 경계)를 Compose·`.env.example`·GitOps local AI values에 전달. 값과 기본 false는 그대로
- GitOps local core `APP_GUARDIAN_TRANSFER_ENABLED=false`, scoring `M2_CONTENT3_RULE_ENABLED=false` 추가
- transfer-local은 scoring을 함께 실행하고 호스트 포트는 닫음. #305 이후 교차 확인이 꺼져 있으면 scoring을 부르지 않아 AI→scoring `service_healthy` 의존성은 제거(#502)
- 회귀 검사: `scripts/tests/test_runtime_config.py`가 앱 기본값과 예제·values를 대조하고 합성 환경 파일로 Compose 렌더링 확인

### 3.4 추억 검색 문서 임베딩 켜기 (#591)

- learning `MEMORY_EMBEDDING_ENABLED`는 앱 기본 false(#563)인데 GitOps 값 어디에도 없어 배포에서 문서가 `PENDING`에 머물고 검색이 늘 `NO_RESULTS`였음(#562 kind 확인 D에서 발견)
- GitOps local·prod learning 값에 `true` 추가. 주기 1분·선점 64행·8글 묶음은 앱 설정 그대로이고 `AI_URL`·`CORE_URL`·`INTERNAL_TOKEN`·learning→ai/core 네트워크 정책은 이미 있어 더 넣을 값 없음. 선점은 `FOR UPDATE SKIP LOCKED`라 prod HPA 최대 3대에서도 중복 임베딩 없음
- 앱 기본값은 false 유지(테스트·Compose에서 실제 OpenAI 호출을 막음). Compose는 `${MEMORY_EMBEDDING_ENABLED:-false}`로 넘겨받음. 키 없이 켜면 문서가 5회 실패 뒤 `FAILED`가 되고 자동으로 되살아나지 않음
- 비용: 문서는 8건씩 묶어 `text-embedding-3-small` 1회 호출, 검색 질문은 1회씩. kind 실측 문서 19건(평균 301자) 적재 약 6,000토큰, 1원 미만
- kind 확인(2026-11-12): `READY` 2건을 `PENDING`으로 되돌린 뒤 helm upgrade(learning 17). 새 Pod 기동 약 1분 뒤 첫 주기에서 2건 `READY`(`text-embedding-3-small`), `MEMORY_EMBEDDING` 1회·724토큰 기록. 다른 서비스 변경 없음

## 4. AWS 데모 구성 (#185)

계정 347161580747 / ap-northeast-2. 수집한 values는 배포 상태를 보존한 것이며 새 계정을 처음부터 만드는 완성된 IaC는 아니다. 비밀 값·Secret data·CloudFront origin header 원문은 기록하지 않는다.

| 항목 | 결정 |
|---|---|
| IaC | eksctl(`infrastructure/eks/cluster.json`) + AWS CLI 스크립트(`demo_stack.py` plan·apply·pause·resume). IAM 원문은 `infrastructure/aws/iam/` |
| 진입 | 기본 cloudfront.net 도메인, CloudFront→ALB HTTP(ALB SG는 CloudFront prefix list만 허용, origin 헤더 규칙) |
| 노드그룹 | 모두 On-Demand t3.medium: `application` 2대(최대 3), `platform-observability` 2대(`workload=platform:NoSchedule`). 상태 저장 서비스(replica 1, AZ 고정 EBS)에 Spot이 맞지 않아 설계의 Spot을 변경(PM 승인). scoring 메모리 예약 2Gi → 1Gi |
| Pod 권한 | 설계의 IRSA 대신 EKS Pod Identity |
| RDS | db.t4g.small Single-AZ. 서비스별 계정은 [db-dev-guide 8절](db-dev-guide.md#8-서비스별-db-계정-230) |
| 데모 외 기간 | 노드 0대 + RDS 정지(`demo_stack.py pause`/`resume`, Karpenter 정지 포함). control plane·NAT·저장소 비용은 남음 |
| 배포 기준 | develop → main 릴리스 PR 병합 후 그 SHA만 배포(ECR 태그 `main-<sha>`) |
| 시연 계정 | `AUTH_NEW_ACCOUNT_DEMO=true`로 새 Google 부모를 `is_demo=true` 저장 |
| 결제 | 공용 문서 테스트 키를 `sagomungchi/demo/app/payment` Secret으로 ESO 연결. 일반 결제 승인만 시연 가능 |
| 비밀 스캔 | Gitleaks 8.30.1, 루트 `.gitleaks.toml`. 재실행 도구 `infrastructure/aws/scan-repository-secrets.py`. CI `ci-secrets.yml`이 모든 PR·develop/main push를 검사(#810, [4.3](#43-비밀-정보-스캔-ci-810)). develop `8b23de1f` 전체 스캔(11/19, 이력 1006 커밋·현재 파일 2350개): 합성 값 3건 검토 후 예외 추가([4.3](#43-비밀-정보-스캔-ci-810)), 이후 발견 0 |

### 4.1 설계와 남은 차이

| 항목 | 현재 | 남은 일 |
|---|---|---|
| RDS | 비공개·암호화·자동 백업 7일, Single-AZ, 삭제 보호 off. PITR 복원 1회 성공(#629, 9.12): 요청→available 약 19분(RTO 4시간 안), 요청 시각과 최신 복원 가능 시점 간격 5분 23초 | RPO 5분은 로그 업로드 주기(5분) 경계라 넘을 수 있음(9.12.4). 근거 연결·결제 행이 없어 실데이터 정합성 미확인, 앱 전환 시간 미측정 |
| 플랫폼 | RabbitMQ·Redis·관측 단일 replica, AZ 고정 PVC(RabbitMQ·Prometheus·Grafana 2a, Redis 2b) | EBS/PVC 삭제·AZ 장애 복구 미검증 |
| 진입 | CloudFront→ALB HTTP origin | custom domain·ALB TLS 미구성 |
| Secret | ESO·Secrets Manager 원격 key 참조 | 키 회전·장애 복구 미검증 |
| NetworkPolicy | 서비스별 정책 있음, 일부 외부 연결은 넓은 CIDR. 저장소 값은 app 기본 거부를 켬(#657, 9.8), 배포 중이던 환경은 `namespaceDefaultDeny=false` | 설계 호출 표 전체 미검증, 기본 거부는 재가동 때 적용·확인 |
| S3·IAM 재생성 | 인벤토리·정책 원문 보존. 테마 자산 ai·learning 역할 2개는 저장소에만 정의(#652, 9.8) | 새 계정 실제 생성 미실행 |
| NAT | 2a 한 곳 | 다중 AZ는 담당자 결정 사항(5절) |

### 4.2 실제 서비스 검증 (11-03~04)

- CloudFront URL에서 학부모 Google 로그인·답변 제출·AI 피드백·돌아보기, 주간 리포트 생성과 PDF·Markdown 다운로드
- 클라이언트 IP 판정([검증 스크립트](../../infrastructure/aws/verify-viewer-ip.ps1)): viewer IP 제한 카운터 증가, 위조 XFF 무시
- 미실행: 신규 Google 가입 실계정, 공용 테스트 키 결제 승인, 새 클러스터 복원

### 4.3 비밀 정보 스캔 CI (#810)

NFR-SEC-04 검증(저장소 비밀 정보 스캔)을 손 도구에서 PR 단계로 옮긴다. 워크플로 구성은 [testing-ci 8절](testing-ci.md#8-비밀-정보-스캔-ci-810).

| 결정 | 내용 |
|---|---|
| 실행 방식 | 공식 릴리스 `gitleaks_8.30.1_linux_x64.tar.gz`를 SHA256 대조 후 실행. `gitleaks-action`은 조직 저장소에 유료 라이선스가 필요해 쓰지 않음 |
| 검사 범위 | PR은 PR 커밋(`base..head`), push는 push된 커밋(`before..after`, 이전 커밋이 없으면 머리 커밋까지 전체), 수동 실행은 선택한 ref 전체 이력. 작업 트리 미커밋 파일·Git 무시 파일은 범위 밖(손 도구 `scan-repository-secrets.py`가 담당) |
| 출력 | `--redact=100`. 로그에는 파일·줄·커밋·규칙 이름만, 값은 `REDACTED` |
| 경로 필터 | 없음. 문서만 바꾼 PR도 검사 |

도입 전 전체 스캔(2026-11-19, `scan-repository-secrets.py`, 로컬 모든 ref): `generic-api-key` 3건. 담당자 승인 후 값을 확인했고 모두 합성 값이라 `.gitleaks.toml`에 파일·값 단위 예외를 추가했다. 재실행 결과 이력·현재 파일 모두 발견 0.

| 위치 | 판단 |
|---|---|
| `scripts/tests/test_admin_account_sql.py:56` | 출력에 비밀번호가 안 나오는지 확인하는 시험용 비밀번호 |
| `backend/core-service/.../admin/ModelVersionBrowserIntegrationTest.kt:23` | 다른 테스트에서 이미 예외로 둔 합성 JWT 비밀(`test-auth-secret-...` base64) |
| `scripts/tests/test_sagemaker_model_check.py:115` | 잘못된 manifest 시험의 S3 객체 key. develop에는 없고 미병합 `feature/sagemaker-model-lock`(#777)에만 있어, 그 PR이 막히지 않도록 미리 예외 |
| `scripts/tests/test_admin_operations_contract.py:300` | 계약 지문 시험에서 `'key'` 다음에 적은 OpenAPI 필드 이름 `p50LatencyMs`(#1051). 비밀 값 아님 |

걸렸을 때 대응:

1. 로그나 보고서에서 값을 열어 보거나 PR 댓글·이슈·메신저에 붙여 넣지 않는다. 위치(파일·줄·커밋·규칙 이름)만 공유한다.
2. 실제 비밀이면 먼저 발급처에서 회수·교체한다(커밋을 지워도 push된 값은 노출된 것으로 본다). 그다음 해당 커밋을 PR에서 빼고 값은 환경 변수·GitHub Secrets·AWS Secrets Manager로 옮긴다. 이미 develop·main에 들어간 이력 재작성은 #810 범위 밖이며 팀장과 따로 정한다.
3. 합성 값(시험 fixture, 문서용 예시, 계약 해시 등)이면 `.gitleaks.toml`에 기존 형식대로 예외를 추가한다: `targetRules`는 걸린 규칙 하나, `condition = "AND"`, `paths`는 그 파일 하나, `regexes`는 그 값 전체(`^…$`), `description`에 합성 근거. 규칙 전체·폴더 단위·값 일부 패턴 예외는 두지 않는다. 예외 추가 PR은 리뷰어가 값이 합성인지 직접 확인한다.
4. 오탐이 규칙 자체 문제로 반복되면 규칙 끄기 대신 이슈로 올려 정한다.

## 5. S3 Gateway 엔드포인트와 NAT 점검 (#212)

10/29 멘토링의 "S3 엔드포인트 연결, core·NAT 구간 병목" 지적을 읽기 전용으로 점검(2026-11-04). AWS 자원 변경 없음.

- S3 Gateway 엔드포인트(`sagomungchi-demo-vpce-s3`)가 이미 있고 private 라우팅 테이블 2개 모두 S3 prefix list → vpce 경로 active
- **엔드포인트 정책은 기본 전체 허용 유지**: 노드의 ECR 이미지 layer도 AWS 소유 S3 버킷을 이 엔드포인트로 받아, 우리 버킷으로 좁히면 이미지 pull이 깨짐. 버킷 접근 제한은 Pod Identity 역할 정책이 맡음
- S3가 NAT를 거치지 않는 근거: scoring Pod가 모델 약 844MiB를 받는 동안 NAT 수신 0.04MiB, Pod 안 DNS 해석 IP가 모두 S3 prefix list 대역
- NAT를 거치는 것은 외부 호출뿐: ai→LLM API, core→토스·Google OAuth, ESO·Pod Identity→Secrets Manager·STS, kubelet→ECR API·공개 레지스트리, Grafana→Discord
- **NAT 병목 없음**: 51시간 지표에서 활성 연결 최대 126(한도 55,000), 포트 할당 오류 0, 처리량 약 4.8GiB
- 남은 위험은 가용성: NAT가 2a 한 곳이라 2a 장애 시 2b Pod도 외부 호출 불가

| 완화안 | 월 추가 비용 | 판단 |
|---|---|---|
| A. 현재 유지(zonal NAT 1개) | $0 | **데모 기간 채택**. 2a 장애 때는 RabbitMQ·관측 EBS도 2a라 서비스가 이미 함께 멈춤 |
| B. AZ별 zonal NAT | 약 +$46.7 | 운영 전환 결정 시 재검토(가장 단순) |
| C. Regional NAT GW | 약 +$43~47 | 기존 NAT 교체, 도구 지원 확인 필요 |
| D. Interface 엔드포인트 4종 | 약 +$76 | LLM·토스·OAuth는 그대로 NAT. 현재 양 대비 비쌈 |

한계: VPC Flow Logs 없음(패킷 단위 경로 기록 없음), 350초 넘는 유휴 연결의 stale 오류는 미확인.

## 6. Karpenter와 앱 HPA (#211·#372)

Karpenter는 트래픽을 보지 않고 Pending Pod가 생길 때만 노드를 추가한다. 흐름은 트래픽 증가 → HPA가 Pod 증가 → 기존 노드 자리 부족 → Pending → Karpenter 노드 추가 → 부하 종료 후 HPA 축소 → 빈 노드 정리.

| 항목 | 결정 | 근거 |
|---|---|---|
| 설치 | Karpenter 1.15.1 Helm(OCI), 수동 Helm. values `environments/prod/karpenter.json` | 1.35는 1.9 이상 지원. prod는 Argo CD 미구성 |
| 노드 | t3.medium·t3.large On-Demand, 2a·2b. Spot·중단 알림 큐 미사용 | 앱이 replica 1·PDB 없음이라 Spot 회수가 곧 중단 |
| 상한 | NodePool `limits` CPU 4·메모리 16Gi(최대 약 2대, 최악 약 $156/월) | 평소 0대 |
| 정리 | `WhenEmptyOrUnderutilized`, `consolidateAfter 5m`, 한 번에 1노드, `expireAfter 720h` | 부하 종료 후 비용이 남지 않게 |
| 기존 노드그룹 | 둘 다 유지. 컨트롤러는 `application` 노드에 replica 1 | 컨트롤러가 자기가 만든 노드에 있으면 안 됨 |
| AZ·EBS | NodePool에 `workload=platform` taint 없음 → 상태 저장 Pod는 Karpenter 노드에 가지 않음 | PV의 AZ 제약 유지 |
| HPA | core·learning·ai, 최소 1·최대 3·CPU 70%. scoring·report-api는 고정 | 평소 비용 불변. scoring은 모델 로딩·메모리 1Gi |
| 축소 끊김 | 최소 1 유지 + `application` 노드그룹 preferred nodeAffinity + ReplicaSet 기본 삭제 순서(최근 Pod부터) | 아래 |

- replica 1에서 노드를 정리하면 eviction이 Pod를 먼저 지워 새 Pod가 Ready가 될 때까지 끊긴다. 기본 Pod를 관리형 노드에 두고 늘어난 Pod만 Karpenter 노드에 올려, 축소 때 최근 Pod부터 지워지게 했다. 부하 중 재배포로 Pod 나이 순서가 바뀌면 한 번 끊길 수 있다. 최소 2 + PDB 안은 상시 노드 1대(약 $38/월)가 뜰 수 있어 보류
- 적용(2026-11-05): metrics-server add-on, IAM 역할·Pod Identity, Karpenter, NodePool `application-burst`, 세 앱 HPA. 이미지 digest는 바꾸지 않음
- t3.medium은 노드당 Pod 17개 제한이라 CPU·메모리보다 Pod 수로 먼저 Pending이 날 수 있음
- 실측(#384, 2026-11-18 → 9.14): 노드 확장 Pending→Ready 41초, 상한(CPU 4)에서 세 번째 노드 거부, 축소는 부하 종료 10분 46초~11분 20초 뒤 노드 0대. ai도 CPU 기준으로 확장됨. **D안 삭제 순서는 보장되지 않음**(2회 중 1회 기본 Pod가 함께 지워짐, 9.14.5)
- 후속: scoring HPA, report-worker KEDA, Spot 혼합(replica 2·PDB 이후)

## 7. CD 배포 승인·이력·롤백 (#186)

`cd-release.yml`: main 수동 실행 → GitHub Environment `prod` 승인 → 작업자 PC runner에서 (배포만) DB migration Job 완료 → Helm 적용 → 경로 확인 → 이력.

### 7.1 확정 정책 (담당자 답변)

- 이전 승인 앱이 현재 DB 스키마·데이터와 호환될 때만 새 승인을 받아 이미지 버전을 복귀. 비호환·미확인은 모두 복귀 차단. DB 버전 번호만으로 호환성을 판정하지 않음
- API·이벤트 계약, 진행 중 학습·결제 작업 영향과 검증 근거를 함께 기록
- DB 자동 downgrade·백업 자동 복원은 구현하지 않음
- 운영 승인자는 `20220348-kim`·`kty2001` 2명(2026-11-03). 둘 중 한 명의 승인 없이는 실행하지 않음

### 7.2 구현 결정

| 결정 | 내용 | 근거 |
|---|---|---|
| 적용 위치 | 작업자 PC의 self-hosted runner(`cd-prod`) | EKS API 공개 접근이 작업자 공인 IP로 제한 |
| 승인 | Environment `prod` Required reviewers(2명 중 1명 승인으로 시작), main만 허용 | 승인자는 GitHub 승인 기록 API로 읽어 이력에 남김. 계획 파일의 승인 표시는 읽지 않음 |
| 이미지 | publish job이 main SHA를 `main-<12자리>`로 ECR 게시, 있으면 재사용. core·learning migration 이미지(`*-migrate`)도 같은 태그로 게시, report는 앱 이미지가 Alembic을 포함 | ECR 태그 IMMUTABLE. GitHub OIDC 역할은 ECR 쓰기만 |
| migration (2026-11-17) | 배포만. 승인 후 migration·앱 server dry-run을 모두 마친 뒤 core → learning → report 순서로 Job 적용·`Complete` 확인, 그다음 앱 적용. 실패·시간 초과면 앱 미적용, DB는 되돌리지 않음. 같은 SHA 재실행은 완료된 Job을 건너뜀. 롤백은 migration 없음 | 11/6 이후 core V29~V51·learning V11~V21·report 3개가 수동 절차에 묶여 있었음. 승인 한 번으로 스키마와 앱을 같은 SHA로 맞추고, 실패 시 앱이 새 스키마 없이 뜨는 것을 막음 |
| 계획 입력 | 실행 입력 JSON(커밋하지 않음), 원문은 artifact | 계획의 SHA가 그 계획을 담은 커밋을 가리키는 순환 회피 |
| 실행 게이트 | `scripts/cd_release.py`가 오류·차단 사유가 없을 때만 `executable=true` | 근거·승인자 미비 상태에서 게시·적용 차단 |
| 적용 | release별 server dry-run 전체 → 순서대로 `redeploy-app.ps1 -ImageDigest -Apply`. 빈 클러스터 첫 배포는 계획 `currentRelease: "none"`일 때만 release 없는 앱을 install(2026-11-18, 9.16) | 실패하면 다음 release 미적용, 자동 롤백 없음 |
| 경로 확인 | 학생 PIN 로그인 → 시도 시작 → 답변 → 부모 refresh → 리포트 목록 | 판정(LLM)·결제 미호출. 부모 refresh 쿠키는 회전하므로 새 값을 fixture에 즉시 저장 |
| 이력 | `history.json` artifact(90일)와 실행 요약 | workflow에 `contents: write`를 주지 않음 |
| 롤백 | 이전 승인 digest를 같은 workflow·승인으로 적용 | DB downgrade 없음, migration 실행 없음 |

- OIDC trust: AWS IAM은 GitHub 토큰의 `job_workflow_ref`를 조건 키로 비교하지 못함. 저장소 OIDC subject에 `job_workflow_ref`를 포함시키고 trust를 `sub` 하나(`StringLike`)로 main의 `cd-release.yml`만 허용
- deploy job `env`에서 `${{ runner.temp }}`를 쓰면 workflow 파일 오류가 됨 → 첫 step에서 `GITHUB_ENV`로 설정
- 웹(S3/CloudFront) 배포는 범위 밖. migration은 2026-11-17부터 workflow 안에서 실행(이전에는 배포 전 prod README 절차로 수동 적용). Job 로그는 공개 Actions 로그에 옮기지 않고 작업자 PC에서 확인
- migration 게시에는 publish 역할의 ECR 대상에 `core-migrate`·`learning-migrate`가 필요하다. 저장소 정책 파일만 고쳤고 AWS 반영은 재가동 때(그 전에는 publish가 실패해 배포로 넘어가지 않음). AWS 실행 검증은 아직 없음
- main·develop 브랜치 보호 규칙 없음(2026-11-04). main 직접 push로 workflow를 바꾸면 승인 전 publish job이 ECR 게시 역할을 쓸 수 있음. main 보호는 팀 결정 사항

### 7.3 DB 호환성 검토 시 포함할 제약

- #131 `20261030_04`: 기존 report-worker 중지 → migration → 새 worker 순서. 혼합 실행 미지원. downgrade 시 실패·격리·수동 재처리 메타데이터 소실
- report 삭제 guard 제거는 삭제된 학생의 재생성 차단을 잃을 수 있어 무조건 롤백 금지
- core·learning 앱 자동 migration은 꺼져 있음. 운영 DB 초기화·Flyway 이력 수정으로 버전을 맞추지 않음
- migration은 앱보다 먼저 적용되고 롤백해도 남으므로, 현재 앱과 롤백 대상 앱이 새 스키마에서 동작해야 함(추가만, 삭제·이름 변경은 앱이 먼저 안 쓰게 된 뒤 다음 릴리스로). 이 근거를 `compatibility.schema`에 적음

### 7.4 운영 실행에서 얻은 주의점

- 11-04 첫 배포(main `a47a596`)·scoring 롤백 리허설·복귀, 11-05 두 번째 배포(main `322e797`) 완료. run 이력은 Actions artifact
- 경로 확인 fixture 미션의 `inputType`이 답변 형식과 같아야 함(처음에 `CHOICE` 미션으로 400)
- 이전 확인이 남긴 진행 중 시도를 돌려받으면 첫 답변 재제출이 422 → 저장된 답변 조회 경로로 처리(#376·#377)
- runner가 쓰는 AWS 프로필은 `sagomungchi-provided`. 세션 만료 시 `aws login --profile sagomungchi-provided`
- 배포 후 prod values의 앱 digest·migration 값을 실제 적용값으로 맞춤

## 8. 운영 경보와 trace (#185·#187)

| 항목 | 결정 |
|---|---|
| 경보 경로 | Grafana Alerting → 팀 디스코드 `aws-alerts`(webhook은 Secret `discord-alert-webhook`). SNS→Lambda 중계안은 채택하지 않음 |
| chart 구조 | #185의 observability chart 구조(values `rules`, 조직 notification policy, datasource UID `prometheus`)가 기준. #187 독립 생성기는 제거 |
| DLQ 수집 | opt-in `rabbitmq-dlq` job(`<큐>.dlq`만). DLQ 규칙이 있는데 수집이 꺼져 있으면 렌더 실패 |
| 월 LLM 비용 | 예산 300 USD, 80%(240 USD) 경보, KST 달력 월. core `LlmCostMetrics` gauge(단가 있는 비용·미산정 호출 수 분리). 미산정 경보는 최근 1시간에 새로 생긴 미산정만(#764) |
| 담당 | 동섭 1명, `aws-alerts` 한 채널 |
| trace 저장소 | Tempo(observability chart 선택 구성, 24h, #784로 72h에서 줄임, `observability.json`). Langfuse는 LLM 계측용으로 별도 |

### 8.1 구현에서 정한 것

- target 규칙은 `min(up{job=~...})`라 job 자체가 사라지면 발생이 아니라 NoData로 보고(NoData 알림은 전송)
- Prometheus·Collector·Grafana는 ConfigMap 변경을 다시 읽지 않아 재생성 annotation 사용
- app-service chart가 env의 `JAVA_TOOL_OPTIONS`를 agent 옵션 뒤에 합침. 이전에는 prod의 `-XX:MaxRAMPercentage`가 agent 플래그를 덮어써 agent가 빠져 있었음
- `app-metrics-missing`은 `absent() or absent()`로 쓰면 정상일 때 NoData가 됨 → `max(... or vector(0))`
- 기존 `summarize`는 미산정 호출이 섞인 call type의 비용을 null로 내므로 예산용 `monthToDate`를 따로 둠
- `llm-unpriced-calls`(#764): 처음엔 월 누적 `max(...unpriced_calls) > 0`이라 11/17 재가동 뒤 단가 등록(#651) 전 11/03~05 기록 6,748건 때문에 계속 켜져 4시간마다 Discord 알림이 반복됨. `max(delta(...[1h])) > 0`으로 바꿔 새 누락만 보고, 새 누락이 1시간 없으면 해제, 월초 0 초기화는 음수라 울리지 않음. 설계상 비용이 없는 M2는 단가 0, Veo·RunPod Gemma는 별도 청구로 미산정에서 뺌([core-gateway 33장](core-gateway.md#33-llm-미산정-경보-정리-764-2026-11-18)). model 라벨은 붙이지 않음(새 모델의 첫 시계열은 delta가 0이라 오히려 놓침)
- trace: core `OutboxWriter`가 봉투 `traceparent`를 넣고 `OutboxRelay`가 그 context에서 발행. report-worker는 `app/tracing.py`(OTel SDK)로 소비 span을 봉투 값에 연결
- span 상태는 재시도 처리기·업무 실패가 예외를 밖으로 내지 않아 ERROR가 아니라 재시도 발행·DLQ 이동으로 드러남

### 8.2 검증 상태

- 경보: kind에서 실제 DLQ 적재 → 규칙 발생 → `aws-alerts` Firing·Resolved 수신(11-04). prod는 임시 규칙으로 수신 경로 확인(11-03)
- trace: kind에서 명령 소비 → 동기 HTTP → 결과 이벤트 → 재시도·DLQ가 한 trace(span 67개). 로그인 사용자 요청 시작점은 미실행
- 검증 도구: `infrastructure/gitops/charts/observability`의 `verify_chart.py`(격리 Docker에서 규칙 발생·회복)
- 확인 필요: prod의 규칙 16개·Tempo 실제 적용 시각, core OTLP span 전송 404 경고 해소 여부
- 남은 것: report(Python) 자체 HTTP 지표(ai는 [9.28](#928-ai-service-tracehttp-지표-1029-2026-11-25)), 임계값 실측 조정, 서비스별 담당 라우팅

## 9. AWS 데모 부하 시험 1차 (#361)

2026-11-05, k6로 CloudFront → ALB → core에 단계별 부하. Karpenter·HPA 적용 전. 2차(#384)는 [9.14](#914-aws-데모-부하-시험-2차-hpakarpenter-확장축소-384-2026-11-18).

조건: core replica 1(CPU limit 1, Hikari 풀 10), RDS db.t4g.small, LLM은 클러스터 안 스텁(지연 2.5~4초), 시험 계정 1개(자녀 3명). 시나리오 `evaluation/load/core-load.js`(browse 55%·learn 20%·notify 15%·analyze 10%).

| 항목 | 50명 | 100명 | 200명 | 300명 |
|---|---|---|---|---|
| API 오류 | 0/5,705 | 0/12,338 | 0/26,968 | 0/40,312 |
| API p95 (ms) | 150 | 159 | 204 | 374 |
| core 처리량 (req/s) | 26.9 | 59.3 | 133.1 | 197.4 |
| core CPU 최대 (코어) | 0.13 | 0.23 | 0.48 | 0.69 |
| core DB 풀 사용 / 대기 최대 | 1 / 0 | 1 / 0 | 2 / 0 | 9 / 8 |
| RDS CPU 최대 (%) | 16 | 24 | 46 | 68 |

**결론**

1. 먼저 한계에 닿은 것은 DB 계층. RDS CPU가 VU에 비례해 약 350명에서 80%에 닿을 추세, 300명에서 core Hikari 풀 포화 직전
2. core CPU는 그다음(약 400명에서 한도 추정)
3. NAT는 훨씬 나중(계산 판단). 실제 LLM을 가정한 300명 트래픽도 약 6건/초·동시 연결 50개로 한도의 1% 미만
4. 가상 스레드 pinning 기록 0건, Pod 재시작 0, RabbitMQ 적체 0

**해석상 주의**

- 시도는 자녀×미션마다 하나라 학습 칸이 3 × 5 = 15개로 고정. 판정 처리량 상한 약 1.4건/초이고 75명을 넘으면 LLM 쪽 부하가 늘지 않음
- 칸을 얻지 못한 VU는 경합 호출을 반복해 300명 API의 약 35%가 경합. "DB가 먼저" 결론은 계정을 늘린 2차에서 재확인
- 판정 경로까지 보려면 계정 수 × 15 ≥ 0.2 × VU(300명은 계정 4개). #415 이후 `evaluation/load/prepare_accounts.py`로 ID·비밀번호 시험 계정 생성 가능

**개선 제안**

| 우선 | 제안 |
|---|---|
| 1 | RDS Performance Insights로 상위 쿼리 확인. `student_attempts`(p95 818ms)·`student_home` 쿼리 계획·인덱스 점검 |
| 2 | HPA 최대 Pod 수와 Hikari 풀 크기를 함께 정함(Pod 수 × 풀 ≤ RDS 최대 연결) |
| 3 | RDS 사양·읽기 복제본·자주 읽는 조회 캐시 검토(t4g는 CPU 크레딧 방식) |
| 4 | core HPA 기준은 CPU 0.5코어 근처로 시작 |
| 5 | NAT 실측은 실제 LLM 또는 클러스터 밖 스텁으로 따로 |

**남은 것**

- 토스 공용 위젯 키가 500(code 5000)을 돌려줘 결제 불가였음. 팀 전용 테스트 키 전환 검토
- 시험 데이터(시도 약 2,800건, 대화 106건 등)는 2차 시험 뒤 보호자 화면의 자녀 삭제 절차로 정리. SQL로 직접 지우지 않음. 시험용 기기 해제·k6 비밀 파일 삭제도 그때
- ECR `sagomungchi/llm-stub` 이미지는 2차 시험용으로 보존. 그 외 변경(스텁 배포, ai `OPENAI_BASE_URL`, core `JAVA_TOOL_OPTIONS`, PREMIUM 상품, 시험 구독)은 원복 완료

## 9.5 정지 중 고정비 축소 (#573, 2026-11-12)

데모는 2026-11-06부터 정지 상태(노드그룹 0대, RDS stopped)인데도 하루 약 7천 원이 나가 지원 예산을 넘을 우려가 있었다(#573). 계정 SCP가 Cost Explorer(`ce:GetCostAndUsage`)를 막아 서비스별 청구는 조회하지 못했고, 아래 금액은 서울 리전 공시 단가로 계산한 추정이다.

| 항목 | 하루 추정 | 결정 |
|---|---|---|
| EKS 컨트롤 플레인 + 노드그룹 정의 | 약 3,300원 | **삭제(2차).** 처음엔 재생성 절차 미검증으로 유지했으나, RDS·S3·ECR·Secrets Manager는 남아 DB 초기화·seed가 필요 없고 클러스터에만 있던 Secret을 백업한 뒤 지움. 12/8 시연 1주 전 재생성 |
| NAT 게이트웨이 + EIP | 약 2,100원 | **삭제.** 노드 0대라 외부 호출이 없음. 재개 때 다시 만듦 |
| ALB + 공인 IP 2개 | 약 1,000원 | **삭제.** 재개 때 LB Controller가 Ingress로 다시 만듦 |
| EBS(PVC 4개)·스냅숏·RDS 저장소·S3·ECR·Secrets Manager·로그 | 약 500~800원 | 유지(데이터 보존) |
| RDS 인스턴스 | 정지 중 0 | 정지 최대 7일 뒤 자동 재시작(첫 재시작 2026-11-13 10:19 KST 무렵) → 그때마다 다시 정지 |

실행(동섭 승인, 2026-11-12)
- ALB `sagomungchi-demo-core`와 대상 그룹을 지웠다. ALB 공인 IP 2개가 함께 해제됐다. LB Controller가 만든 보안 그룹 2개는 비용이 없어 남겼다
- NAT `sagomungchi-demo-nat-2a`를 지우고 EIP를 반납했다. 계정에 남은 EIP는 0개다. private route table 두 개의 `0.0.0.0/0`은 blackhole로 남는다(노드 0대라 영향 없음)
- 지우기 전 ALB 리스너·규칙·대상 그룹, NAT·EIP·route table 설정을 작업자 PC(저장소 밖)에 JSON으로 보관했다. ALB 규칙에는 CloudFront origin 헤더 값이 있어 저장소에 넣지 않는다

2차 실행: EKS 삭제(동섭 승인, 2026-11-12)
- 삭제 전 백업: ESO 동기화 대상이 아닌 Secret은 관측 2개뿐이라 Secrets Manager `sagomungchi/demo/observability/grafana-admin`·`…/discord-webhook`에 복사하고 원본과 해시로 일치를 확인했다(값 미출력). 클러스터·노드그룹·add-on·access entry·Pod Identity 8개·Helm release 11개 values·Karpenter·Ingress·PVC·replica 수는 작업자 PC(저장소 밖)에 JSON으로 보관했다
- 노드그룹 `application`·`platform-observability`(모두 0대)를 지운 뒤 클러스터 `sagomungchi-demo-eks`를 지웠다. Pod Identity 연결은 함께 사라졌고, 클러스터 SG는 RDS SG 규칙이 참조해 남았다(비용 없음, 재생성 뒤 정리)
- 남긴 것: RDS·S3·ECR·Secrets Manager·IAM 역할·VPC·스냅숏, PVC였던 EBS 4개(합계 10GiB, 월 약 1천 원, 재연결 선택지로 보존)

결과: 하루 약 7천 원 → NAT·ALB 삭제 후 약 4천 원 → EKS 삭제 후 약 700원(모두 추정). 실제 금액은 결제 콘솔에서 며칠 치 청구로 확인한다.

재개는 이제 재생성이다(→ [EKS 재생성 순서](../../infrastructure/eks/README.md#재생성-순서-2026-11-12-eks-삭제-이후)). 처음 실행하는 절차라 12/8 시연 1주 이상 전에 시작한다.

## 9.6 ai 영상 이어 붙이기 메모리 (#586, 2026-11-12)

#546 kind 확인에서 주간 테마 초안 첫 생성이 영상 컷 이어 붙이기 단계에서 ai 메모리 상한 512Mi를 넘어 OOMKilled됐다. 같은 입력을 1Gi로 다시 생성했을 때는 `READY`였다.

측정 방법
- Veo·OpenAI는 부르지 않았다. #546 때 MinIO `theme-drafts/`에 남은 INTRO·OUTRO 결과 영상(1280x720·24fps·22.5초)을 4·6·8·6초 컷으로 잘라 Veo 컷 대신 쓰고, 장면 그림(1536x864 PNG)으로 움직이는 그림 컷을 만들었다.
- kind와 같은 이미지(`sagomungchi/ai-service:local`) 컨테이너에서 `app.main`을 불러 둔 채 `app/llm/media.py`·`theme_draft/nodes/video.py` 함수를 실제 흐름 순서대로 불렀다. CPU 상한은 500m, 메모리는 2Gi로 열어 두고 cgroup `memory.current`를 10ms 간격으로 읽어 단계별 최대값을 쟀다.
- ffmpeg(libx264)는 CPU 상한이 아니라 보이는 코어 수만큼 스레드를 만든다. 그래서 kind 노드(16코어)와 운영 노드(t3.medium·t3.large, 2 vCPU)를 `--cpuset-cpus`로 나눠 쟀다.

컨테이너 메모리 최대값(MiB, 대기 상태 약 145)

| 단계 | 2코어(운영) | 4코어 | 16코어(kind) |
|---|---|---|---|
| 컷 8개 동시 검토(멈춤 감지·장면 뽑기) | 377 | 443 | 749 |
| 움직이는 그림 컷 1개(8초) | 380 | 422 | 593 |
| 컷 4개 다시 인코딩(앞뒤 멈춤 자르기) | 390 | 427 | 631 |
| **이어 붙이기(Veo 컷 4개)** | **509** | **566** | **846** |
| **이어 붙이기(Veo 1 + 그림 컷 3)** | **528** | **566** | **850** |

- 메모리 대부분은 Python이 아니라 ffmpeg 하위 프로세스다. ffmpeg 최대 RSS는 2코어 391MiB, 16코어 709MiB였다. Python 쪽 컷 바이트는 수 MB라 영향이 작다.
- 실제 서버는 측정 컨테이너보다 대기 메모리가 약 30MiB 많다(kind ai 약 175MiB).
- 운영(2 vCPU)도 이어 붙이기가 512Mi를 넘는다. 영상을 켜면 운영도 같은 실패가 난다.

결정

| 항목 | 값 | 근거 |
|---|---|---|
| 메모리 상한 | 512Mi → **1Gi**(kind·운영) | kind 최대 약 880MiB(대기 차이 포함)에 여유 약 140MiB. 운영은 약 560MiB라 여유가 크다 |
| 메모리 요청 | **256Mi 유지** | 평소 약 180MiB. 영상 작업은 주 1회 관리자 초안 생성 때만 몇 분이다 |
| 적용 범위 | **영상을 켜든 끄든 항상 1Gi** | 요청을 그대로 두면 스케줄링·노드 용량이 바뀌지 않는다. 영상 스위치와 메모리 값을 따로 맞춰야 하는 실수를 없앤다 |

영향 확인
- 스케줄링은 요청만 보므로 앱 노드그룹(t3.medium)과 NodePool `application-burst`(CPU 4·메모리 16Gi 상한) 계산은 바뀌지 않는다.
- HPA는 CPU 70%만 본다. 메모리 값은 확장 조건에 들어가지 않는다. 다만 ffmpeg가 CPU 상한 500m까지 쓰면 요청 100m 대비 70%를 넘어 영상 생성 몇 분 동안 ai가 최대 3개까지 늘 수 있다. 늘어난 Pod는 영상 작업을 나눠 받지 않고, 부하가 끝나면 줄어든다.
- 상한 합은 늘지만(최대 3 replica × 1Gi), 요청을 넘는 메모리는 노드에 여유가 있을 때만 쓴다. 노드 메모리가 부족하면 요청을 넘게 쓰는 ai가 먼저 축출될 수 있다. 영상 작업 중 축출되면 초안은 실패로 끝나고 learning이 재시도한다.
- 운영 `prod/ai-service.json`에는 아직 `THEME_VIDEO_ENABLED`·`ASSET_S3_BUCKET` 같은 테마 그림·영상 env가 없다. 운영에서 영상을 켜려면 이 env와 Google 자격 증명 배포(#538)가 따로 필요하다.

검토한 대안(적용하지 않음)
- 컷을 파일로 이어 붙이기: ffmpeg는 이미 임시 파일로 입력을 받는다. 줄일 수 있는 것은 Python이 쥔 수 MB뿐이라 효과가 거의 없다.
- ffmpeg 스레드 제한: 16코어에서 출력 쪽만 `-threads 2`로 묶으면 이어 붙이기가 850 → 650MiB로 줄었다. 하지만 컷 8개 동시 검토(디코딩)가 710MiB로 남아, 입력 디코딩 스레드와 동시 처리 수까지 손봐야 한다. 상한 1Gi로 충분해 코드는 바꾸지 않았다. 코어가 많은 노드에서 영상을 켤 때 다시 검토한다.

검증
- local·prod `helm lint --strict`·`helm template`에서 limits 1Gi, requests 256Mi를 확인했다.
- kind ai에 적용해 Running(cgroup `memory.max` 1Gi)을 확인했다. 영상은 꺼 둔 상태(`THEME_VIDEO_ENABLED=false`)다.
  - #546 때 `kubectl set resources`로 바꾼 필드 소유권이 남아 있어 Helm 적용이 충돌했다. `helm upgrade --force-conflicts`로 그 필드를 Helm이 다시 가져왔다.
- 완료 조건(영상을 켠 kind 초안 1건 `READY`)은 #546 재시도(상한 1Gi·영상 켬·`READY`·OOM 없음)와 위 실측으로 확인했다. Veo는 다시 부르지 않았다.
- 실제 Veo 컷의 앞뒤 정지 구간 자르기(다시 인코딩)가 여러 컷에서 동시에 일어나는 경우는 재지 못했다.

## 9.7 시연 계정 데이터 준비 (#624, 2026-11-13)

추억 앨범·추억 검색(FN-RET-10~12)은 진행 주 이전에 5문제를 모두 끝낸 회차가 있어야 내용이 나오고, 주간 리포트 설명(FN-RPT-09)은 그 주 M2 점수가 있는 답변이 있어야 생긴다. 새 시연 계정은 빈 화면이라 12/7(월) 시연 전에 지난 회차 기록을 만드는 절차를 정했다. 실행 순서는 [infrastructure/aws/README.md](../../infrastructure/aws/README.md#시연-계정-데이터-준비-624)에 있다.

### 9.7.1 결정 (담당자 확인 2026-11-13)

| 항목 | 결정 | 근거 |
|---|---|---|
| 기록 생성 방식 | 혼합 API: 지난 주(11/30 주)는 재가동 뒤 실제 시각으로, 앞선 2회차는 core·learning 시계를 그 주 토요일로 옮겨 같은 API 스크립트로 만든다. SQL INSERT 없음 | 시드 SQL은 learning·scoring·core·report 4개 DB의 시도·답변·판정·점수·포인트·문서·리포트 정합성을 손으로 맞춰야 하고 이슈의 "가능하면 API 흐름" 원칙과 어긋난다. 12/7이 월요일이라 지난 주는 실제로 지나가므로 시계를 옮길 필요가 없다. 실시간만으로 2회차 이상을 만들려면 EKS를 2주 켜 둬야 한다(비용) |
| 회차·학생 | 초3 무료 1명·초5 프리미엄 1명, 학생별 3회차(11/16·11/23·11/30 주) | 검색 문서가 학생당 15개라 상위 3개 카드가 의미 있게 갈린다. 설명 카드는 명세상 프리미엄·M2 승인 범위(서술 초5·6)만이라 초5에서만 확인한다 |
| 답변 내용 | 스크립트에 자체 작성한 가상 소재 15개(고양이·우산·텃밭 등)를 주·요일마다 다르게 넣는다 | 같은 미션이 반복돼도 답변 표현으로 회차가 구분돼 추억 검색을 보여 줄 수 있다(NFR-SEC-07) |
| 풀이 시점 | 토요일 | 무료도 금·토에는 다섯 요일이 모두 열리고(#483) 토요일 정답 고르기로 바로 엔딩까지 간다. 일요일은 무료가 닫힌다 |

### 9.7.2 kind 확인 (실제 17:20~17:45)

- 대상: develop 배포 그대로(core 6e4eb6c9 이미지, learning 2026-11-13 이미지). 새 시연 학부모(ID·비밀번호)와 자녀 시연3학년(G3)·시연5학년(G5, `LOCAL-PLUS` 시험 구독)
- 테마: G3 11/23은 있던 테마, 나머지 5개(G3 11/16·11/30, G5 11/16·11/23·11/30)는 기존 게시 테마를 복사해 관리자 API로 작성·게시했다(kind 게시 미션만 사용)
- 시계: 11/21(토)·11/28(토)·12/5(토) 14:00 KST에 `solve`, 12/5 23:56 → 일일 리포트, 12/6 23:56 → 월요일 00:00 주간 리포트. 12/7 00시대에 `decorate`·`verify`
- 결과(API와 웹 화면)

| 항목 | 결과 |
|---|---|
| 회차 완료 | 두 학생 모두 3회차 5문제 완료·완주(finished), 초3은 정답 고르기로 엔딩(G5 바탕 테마는 정답 후보가 없어 엔딩 전) |
| 추억 앨범 | 액자 3개, 최근 회차 "새 액자" 표시(웹 앨범 안내 "새 액자가 생겼어요!"), 회차 상세 5문제, 초3 엔딩 보임 |
| 추억 검색 | 검색 문서 30개 모두 `READY`(실제 OpenAI 임베딩). "비 오는 날 우산을 같이 쓴 이야기" → 초3 11/16 회차, "자전거 타기 연습했던 거" → 초5 11/30 회차가 결과로 나옴. 웹 검색 화면은 #567 구현 전이라 API로만 확인 |
| 추억의 벽·가구 | 벽 슬롯 3개(웹 내 방에 액자 3개·"새 액자 1"), DESK·WALL 가구 해금·착용 |
| 주간 리포트 | 11/30~12/6 두 학생 `OK`. 초5는 설명 카드 3개 `INCLUDED`(웹 "대표 답변 설명"·"AI 관찰" 카드 3개, 문구는 대역) |
| 일일 리포트 | 12/5 `OK`, 12/6(일, 기록 없음) `NO_RECORD` |
| 점검 SQL | `audit-demo-data.sql` 세 DB 모두 통과(기준 월요일을 12/7로 바꾼 복사본) |

임시로 바꾼 것(모두 되돌림): core·learning 시험 시계 이미지·환경 변수, ai `OPENAI_BASE_URL`=sllm-server(llm-stub 대역, 판정 LLM 비용 0), ai `M2_CROSS_CHECK_ENABLED=true`, sllm-server 임시 설치(KEDA 끔·1대). 되돌린 뒤 core·learning·ai ReplicaSet이 helm 상태와 같은 해시로 돌아가고 Pod 시각이 실제 시각인지 확인했다. 실제 OpenAI는 추억 검색 임베딩(문서 30건·질문 몇 건)만 불렀다.

kind에 남긴 것: 시연 학부모·자녀 2명과 미래 날짜(11/16~12/7) 기록·리포트, 위 테마 5개(게시), G5 서술 미션 3개의 기준표 v2(M2 핵심어), MinIO `models/m2-klue-narrative/3.0/`, 모델 등록 `m2-klue-narrative` 3.0·`report-explanation` kind-stub-624(활성), 시험 시계 이미지 `sagomungchi/{core,learning}-service:demo-clock`. 활성 모델을 끄는 관리자 API가 없어(rollback은 이전 승인 버전으로만) 모델 활성 상태는 정리 방법을 정할 때까지 그대로 둔다.

### 9.7.3 발견

1. **설명 카드는 지금 운영 값으로는 나오지 않는다.** ai `M2_CROSS_CHECK_ENABLED` 기본 false(#305)라 M2를 부르지 않고, 저장소 시드 미션 기준표에 M2 핵심어(`keywords`)·논술 글 종류(`essayType`)가 없어 켜더라도 M2 입력이 없다. kind에서는 둘 다 임시로 채워야 설명 카드 3개가 생겼다. 시연에서 설명 카드를 보이려면 플래그를 켤지(판정 보류 `HELD` 발생 가능)와 초5 테마 미션 기준표 보완을 정해야 한다 → 9.7.5(#668)에서 정함
2. 활성 모델을 끄는 경로가 없다. 첫 버전을 시험으로 활성화하면 DB를 직접 고치지 않고는 되돌릴 수 없다
3. 새 학부모는 자녀 등록 전에 계정 동의(TERMS·PRIVACY)가 필요하다(`children` 명령이 처리)

### 9.7.4 한계

- AWS에서는 실행하지 않았다. 운영 적용은 #601 재가동 때이고, AWS 테마·가구 아이템·M2·sLLM 상태에 따라 사전 조건이 달라진다
- 시험 시계 동안 가짜 시각으로 서명한 S3(MinIO) 그림 URL은 "not valid yet"으로 깨진다. kind 화면 확인의 그림 자리는 기본 그림이었다. AWS 지난 주 회차는 실제 시각이라 영향이 없다
- 앞선 2회차의 주간·일일 리포트는 만들지 않았다(시연에 필요한 것은 지난 주 리포트)
- 웹 추억 검색 화면(#567)은 구현 전이라 검색은 API로만 확인했다

### 9.7.5 설명 카드용 기준표 M2 입력과 교차 확인 켜기 (#668, 2026-11-16)

#661에서 설명 카드(FN-RPT-09)가 나오는 조건을 ① ai `M2_CROSS_CHECK_ENABLED=true` ② 미션 기준표 M2 입력(서술 `keywords`, 논술 `essayType`) ③ M2 활성 모델로 정리했다. ③은 #601 재가동 절차에 있고, 이번에 ①·②를 정했다.

| 항목 | 결정 | 근거 |
|---|---|---|
| 교차 확인 켜기 | 켠다. 앱 기본값(false, #305)은 두고 prod 값 `gitops/environments/prod/ai-service.json`에 `true` | prod 값이 곧 AWS 데모 환경이고 `redeploy-app.ps1`·cd-release가 매번 이 파일로 helm upgrade를 한다. 시연 절차에서 `kubectl set env`로만 켜면 그 뒤 ai 재배포 때 꺼진다. M2는 기준표에 M2 입력이 있는 미션에서만 불리므로(api-spec 4.2.2) 영향은 시연 스크립트로 보강한 초5 테마 미션뿐이고, A 계정 시험도 시연과 같은 조건이 된다 |
| 판정 보류 | 허용하고 확인 항목으로 둔다 | 켜면 LLM `CORRECT`·M2 평균 낮음(서술 2.0 이하) 또는 `RETHINK`·높음(4.0 이상)일 때 `HELD(MODEL_DISAGREEMENT)`가 생긴다(글자 수 하한 미만 제외). `audit-demo-data.sql`에 `demo668_recent_judgments`(최근 3주 판정 결과·보류 사유별 건수)를 더해 `solve` 뒤 확인한다 |
| 기준표 M2 입력 위치 | 운영 시드 migration이 아니라 #624 시연 스크립트 `demo_account_data.py m2-rubric`에서만 | 운영 시드를 바꾸면 모든 환경 판정에 M2가 붙는다. 스크립트는 공개 기준표를 복사해 M2 입력만 더한 새 기준표 버전 → 검토 승인 → 재게시(api-spec 2.8 관리자 미션, P07 불변 버전)로 넣고, 이미 있으면 그대로 둔다 |
| 입력 값 | 시드 G5 미션 4개는 스크립트 상수(`M2_INPUTS`): DEMO-11·13·15 서술 핵심어 3묶음(`핵심어(비슷한 말)`), DEMO-12 논술 `주장`. 관리자 화면·초안으로 만든 테마 미션은 `--m2-input` JSON | DEMO-11·15는 9.7.2 kind 확인 때 쓴 값 그대로. 설명은 생각 유형이 겹치지 않는 M2 점수 답변 최대 3개이고 초5 M2 활성 범위가 서술이라, 주마다 생각 유형이 다른 서술 미션 3개에 핵심어가 있어야 카드 3개가 나온다. 스크립트가 주별 "M2 입력 서술 N유형"을 출력한다 |

kind 확인(실제 2026-11-16 09:57~10:07 KST, 공유 `kind-sagomungchi-local`)

- 대상: develop 배포 그대로(helm ai rev 21·learning rev 18·core rev 13). 9.7.2의 시연 학부모·시연5학년(프리미엄 시험 구독)과 게시된 G5 테마 11/16·11/23·11/30
- ai `kubectl set env M2_CROSS_CHECK_ENABLED=true` 적용
- `m2-rubric --dry-run` → 실제 실행 → 재실행

| 항목 | 결과 |
|---|---|
| 기준표 보강 | DEMO-12(논술) v1→v2 `essayType`, DEMO-13(서술) v1→v2 핵심어, kind 초안 M-E1708259 v8→v9 핵심어(`--m2-input`) 저장·검토 승인·재게시. DEMO-11·15·M-D0651927은 9.7.2 때 넣은 v2라 그대로. 세 주 모두 "M2 입력 서술 3유형(ANALYZE·CREATE·REFLECT)" |
| 다시 실행 | 모든 미션 "있음"으로 아무것도 바꾸지 않음 |
| 입력 없음 | 보강 전 `--m2-input` 없이 `--dry-run`하면 M-E1708259를 이름으로 알려 주고 실패 |
| 새 답변 M2 점수 | learning만 시험 시계(12/5 토 14:00 KST)로 옮겨 시연5학년이 보강한 DEMO-13·M-E1708259를 추가 문제(`EXTRA`)로 풂(실제 LLM 판정 2건). 두 판정 모두 보강한 기준표 버전(v2·v9)으로 `model_scores.m2` 있음, `versions.model` `m2-klue-narrative@3.0`, 결과 `RETHINK`(보류 아님) |
| 주간 설명 카드 | sLLM 서버 대역(llm-stub) 임시 설치 뒤 시연5학년 11/30~12/6 주간 리포트를 학부모 재생성 → `OK`, 설명 `INCLUDED` 카드 3개(ANALYZE·CREATE·REFLECT, 검사 통과). 카드는 같은 주 9.7.2 테마 답변(DEMO-11·M-D0651927·DEMO-15)이 뽑혔다. 새 답변 2개도 후보였지만 가짜 시각이 같은 12/5 05:00 UTC에서 시작해 9.7.2 답변이 약 20초 늦게 제출돼 "같은 생각 유형은 최근 답변 우선" 규칙으로 밀렸다 |
| 점검 SQL | `demo668_recent_judgments`에 `MODEL_DISAGREEMENT` 0건, `demo668_published_m2_rubrics` 서술 G5 5개·논술 G5 1개 |

임시로 바꾼 것(되돌림): learning 시험 시계 이미지·환경 변수(되돌린 뒤 helm 상태와 같은 ReplicaSet·실제 시각 확인), sLLM 서버 대역 설치(helm uninstall). 실제 OpenAI는 답변 2건의 판정·되묻기와 재생성 리포트 서술 1건만 불렀다.

kind에 남긴 것: **ai `M2_CROSS_CHECK_ENABLED=true`**(kind ai는 helm rev 21 값과 다르다. 이어지는 #630 실측을 시연과 같은 조건으로 재기 위해 켜 둠, `helm upgrade`나 local 값 재적용 때 false로 돌아감), 위 기준표 새 버전 3개(게시), 시연5학년 12/5 추가 문제 시도 2건, 11/30 주 재생성 리포트(학부모 재생성 기회 사용).

AWS에서 남은 확인(#601 재가동 뒤 B 계정)

- prod 값 반영 뒤 ai Pod 환경 변수 `M2_CROSS_CHECK_ENABLED=true`
- 시드·관리자 테마 기준으로 `m2-rubric`이 세 주 모두 "서술 3유형"을 내는지(초안 미션이면 `--m2-input` 준비)
- 12/4~12/5 실제 시각 `solve` 뒤 `demo668_recent_judgments`의 보류 건수, 12/7 주간 리포트 설명 카드 3개(`verify`). 새 답변으로만 뽑히는 확인은 여기서 된다(지난 주 답변이 모두 보강 뒤에 생기므로)
- 실제 리포트 Gemma(SageMaker, 9.13.9)·`report-explanation` 활성 상태에서의 설명 문구(kind는 대역 문구)

### 9.7.6 전체 서비스 시연용 더미 데이터 생성 계획 (#854, 2026-11-22)

9.7(#624)은 시연 학생 2명만 만든다. 이대로면 12/7에 학생 커뮤니티(친구 생각·반응·친구 방)와 관리자 화면(운영 현황·작업 상태·AI 사용량·결제·신고·문의·공지)이 거의 비어 보인다. 가상 가족 30개에 4주치 기록을 공개 API 흐름으로 쌓는 계획을 정했다. **아직 실행하지 않은 계획**이다. 구현·실행은 #808(U1~U5)이 맡고 결과를 이 절 아래에 남긴다. 결정은 2026-11-20 담당자 확인(9.7.6.5)이다.

#### 9.7.6.1 데이터 구조 확인 (develop `4382b45a`)

- 최신 마이그레이션: core `V53__llm_usage_billed_externally.sql`, learning `V24__expression_review.sql`, report `20261110_08_report_explanations.py`
- 테이블 수: core 63·learning 40·report 8. [ERD](../design/erd.md) 3~5장과 이름 차이 없음. scoring은 DB 없음. report `weekly_report`는 이름 그대로 일일 리포트도 담음(`period_type`)

| 영역 | 테이블 | 보이는 화면 | 생기는 경로 | 이 계획에서 |
|---|---|---|---|---|
| 계정·가족 | `user_account`·`parent_credential`·`student`·`guardianship`·`consent`·`student_device(_child)` | 학부모 설정·기기, 관리자 | 공개 API(가입·동의·자녀·기기·PIN) | 1단계 |
| 상품·구독 | `product`·`subscription` | 학부모 결제, 관리자 결제 | `product`는 SQL만, `subscription`은 결제 승인 API 또는 SQL | 시험 구독 SQL(2단계, 결정 4) |
| 결제 | `payment_order`·`payment`·`refund_request`·`payment_charge_attempt`·`pg_webhook_event` | 학부모 결제 내역, 관리자 결제·대조·환불 | 토스 위젯 결제 승인, 갱신 스케줄(매일 09:00) | 위젯이 동작할 때만 손으로(결정 4) |
| 테마·미션 | `weekly_theme(_version, _day)`·`mission(_version)`·`rubric_version` | 학생 홈·테마, 관리자 | 관리자 API, 시드 | 0단계 게시 확인 |
| 학습 기록 | `attempt`·`answer`·`judgment(_element)`·`followup`·`reflection`·`self_assessment`·`hint_usage` | 학생 기록·활동, 학부모 기록, 관리자 운영 현황 | 공개 API(판정·되묻기는 ai 동기 호출) | 5~9단계 풀이 |
| 테마 진행·액자 | `theme_story_view`·`theme_answer_pick`·`theme_review_view`·`theme_frame` | 학생 테마·앨범·내 방 | 공개 API와 그 부수 효과(5문제 완료 시 액자) | 풀이 |
| 추억 검색 | learning `memory_search_doc`, core `memory_daily_usage` | 학생 추억 검색 | 스케줄(`MemoryEmbeddingScheduler` 1분)이 완료 시도로 만들고 ai가 임베딩 | 풀이 뒤 자동 |
| 커뮤니티 | `community_post`·`community_reaction`·`community_visibility` | 학생 커뮤니티·친구 방, 학부모 참여 | 돌아보기 저장 때 자동 공유(core `CommunityService.shareCompleted`), 반응 API | 3단계 공개 켬 → 풀이·반응 |
| 포인트·꾸미기·방 | `reward_point_ledger`·`reward_point_balance`·`look_item`·`student_look_unlock`·`student_look_equipment`·`student_room_decor`·`room_decor_spot`·`room_frame_slot` | 학생 포인트·꾸미기·내 방, 친구 방 | 완료·공유·반응 적립(부수 효과), 해금·구매·배치 API. `look_item`은 관리자 API | 9단계 꾸미기 |
| 리포트 | core `report_job`·`job_execution`, report `weekly_report`·`report_item(_evidence)`·`report_file` | 학부모 리포트, 관리자 작업 상태 | 스케줄(`WeeklyReportScheduler`: 일일 매일 00:00·주간 월 00:00) → report 소비 | 시계 경계 통과·실제 시각 |
| 분석 대화 | `conversation`·`conversation_message`·`message_evidence` | 학부모 분석 대화, 관리자 작업 상태 | 공개 API(프리미엄만, ai 동기 호출) | 9단계 |
| 알림 | `notification` | 학부모 알림(학생 알림 유형 없음) | 리포트 완료·문의 답변·신고 처리·결제/구독 변경의 부수 효과 | 자동(시험 구독 SQL은 알림 없음) |
| 신고·정정 | `error_report`·`correction`, learning `judgment_correction` | 학생·학부모 처리 결과, 관리자 신고 | 공개 API, 처리는 관리자 API | 9단계 |
| 문의·공지 | `inquiry`·`notice` | 학생·학부모 도움, 관리자 문의·공지 | 공개 API, 관리자 API | 9단계 |
| 표현 검토 | learning `expression_review` | 관리자 표현 검토(#728) | 경계 구간 답변(`GRAY_ZONE`), 공유물 신고 숨김(`COMMUNITY_REPORT`)의 부수 효과(#727 머지됨) | 9단계 커뮤니티 신고로 생김 |
| LLM 사용량 | `llm_usage` | 관리자 AI 사용량 | ai·scoring 사용량 이벤트 소비 | 실제 호출의 부수 효과(kind 대역은 stub) |
| 작업·메시지 | `outbox_event`·`processed_event`·`event_log`·`audit_log` | 관리자 큐·감사 | 부수 효과 | 자동 |
| 만들지 않음 | `knowledge_*`·`mission_draft`·`theme_draft`·`model_version`·`model_loading_report`·삭제·탈퇴·학년 올림 | — | — | 시연 범위 밖이거나 기존 데이터 사용 |

- SQL로 넣는 것은 시험 구독(`subscription`) 하나. 결제 승인 API는 토스 위젯 결제가 있어야 해서 12명을 손으로 결제할 수 없음(결정 4). 상품은 기존 `add-demo-premium-product.sql` 그대로. 그 밖은 SQL INSERT 없음
- 리텐션 지표는 별도 테이블 없이 `scripts/retention_metrics/{core,learning}.sql`이 위 테이블을 읽음. 기본은 시연 학생을 빼므로 `-v include_demo=1`로 실행

#### 9.7.6.2 화면별 필요 데이터와 최소 건수

가족 구성
- 학부모 30, 자녀 36(G3~G6 각 9). 학부모 6명은 다른 학년 자녀 2명
- 학년마다 꾸준 3·보통 3·들쭉 2·늦게 시작 1명. 프리미엄은 학년마다 꾸준 2·보통 1(합 12)
- COMMUNITY 동의는 36명 모두. 공개 켬은 G3·G5 각 7명(꾸준 3·보통 3·들쭉 1), G4·G6 각 3명(꾸준). #624 시연 학생 2명도 공개 켬(반응을 받으려면)

무리별 주별 문제 수(W1~W3는 시험 시계, W4는 실제 시각)

| 무리 | 인원 | W1 11/9 | W2 11/16 | W3 11/23 | W4 11/30 | 합계 |
|---|---|---|---|---|---|---|
| 꾸준 | 12 | 5 | 5 | 5 | 5 | 240 |
| 보통 | 12 | 5 | 4 | 3 | 4 | 192 |
| 들쭉 | 8 | 5 | 0 | 4 | 2 | 88 |
| 늦게 시작 | 4 | 0 | 0 | 5 | 5 | 40 |
| 합 | 36 | 160 | 108 | 148 | 144 | **560** |

- 문제는 월요일부터 열린 요일 순서로 품. 5문제 주는 수 19:00에 월~수, 토 14:00에 목·금과 정답 고르기·종료 이야기. 5문제 미만 주는 토 14:00에 한 번에
- 5문제 주만 정답 고르기·기념 액자가 생김. 12/7 기준 액자는 꾸준 4·보통 1·들쭉 1·늦게 시작 2개
- 주간 리포트 서술은 프리미엄이고 그 주 기록 5건 이상일 때만. 꾸준 프리미엄 8명은 4주 모두, 보통 프리미엄 4명은 W1만
- #624 시연 학생은 9.7.1대로 W2·W3·W4에 5문제씩(W2·W3는 같은 시계 정지점에서 함께)

화면별 최소 건수(단계 번호는 9.7.6.3)

| 화면 | 12/7에 보여야 할 것 | 만드는 흐름 | 단계 |
|---|---|---|---|
| 학생 친구 생각 | 시연 학생이 끝낸 W2~W4 미션마다 다른 학생 공개 글 3개 이상(금요일 미션 포함) | G3·G5 공개 더미가 같은 주 같은 요일을 풀고 돌아보기 저장. 금요일 미션은 꾸준 3명이 채움 | 3, 5~9 |
| 학생 반응 | 시연 학생 공유물 3개 이상에 반응 1개 이상, 더미 공유물 반응 합 30개 이상 | 같은 미션을 끝낸 더미가 반응(멱등). 정지점마다 풀이가 다 끝난 뒤 | 5~9 |
| 학생 친구 방 | G3·G5 공개 더미 각 3명 이상: 가구 1개·소품 배치 2개·추억의 벽 액자 2개 이상 | 해금·소품 구매·배치·벽 슬롯 API | 9 |
| 학생 추억 앨범·검색·벽·가구 | 9.7.1과 같음 | #624 `solve`·`decorate` | 6, 7, 9, 10 |
| 학부모 주간 리포트 | 시연 자녀 4개(W1 기록 없음, W2~W4 내용 있음), 더미 꾸준 프리미엄 자녀 4개 모두 서술 포함 | 시계 일 23:56 → 월 00:00 정기 실행, W4는 12/7 00:00 | 5~7, 10 |
| 학부모 일일 리포트 | W1~W3 토·일 것, W4 매일 | 토 23:56·일 23:56 경계 통과, W4 실제 시각 | 5~10 |
| 학부모 분석 대화 | 더미 프리미엄 학부모 6명이 대화 1개씩(질문 2~3개) | 대화 생성·메시지 API | 9 |
| 학부모 알림 | 학부모마다 리포트 완료 알림, 문의 답변·신고 처리 알림 각 2개 이상 | 부수 효과 | 자동, 9 |
| 관리자 운영 현황 | 기본 최근 7일(12/1~12/7)에 W4 풀이 약 140건, 기간을 11/9~12/6으로 넓히면 560건+시연 | 풀이 | 5~9 |
| 관리자 작업 상태 | 리포트 작업(주간 38명×4주, 일일 경계분·W4 매일), 분석 대화 작업 6개 이상 | 자동 | 5~10 |
| 관리자 AI 사용량 | B에서 판정·되묻기·분석·주간 서술·임베딩 호출 종류가 모두 보임 | 실제 호출 | 5~9 |
| 관리자 결제 | 구독 12(+시연 1). 결제 내역은 토스 테스트 결제가 되면 시연 학부모 1·더미 2 | 시험 구독 SQL, 손 결제 | 2, 9 |
| 관리자 신고 | 6건: 학부모 정정 요청(`WRONG_JUDGMENT`, 대상 `JUDGMENT`) 4·학생 커뮤니티 신고(`COMMUNITY_POST`) 2. 정정 요청 2건 처리 | 신고 API, 관리자 처리 | 9 |
| 관리자 문의 | 8건(학부모 6·학생 2), 4건 답변 | 문의 API, 관리자 답변 | 9 |
| 관리자 공지 | 3건(학생·학부모·관리자 대상 각 1) | 관리자 API | 9 |
| 관리자 표현 검토 큐 | 2건(`COMMUNITY_REPORT`, 위 커뮤니티 신고에서 자동) | 관리자 표현 검토 화면(#728) | 9 |
| 리텐션 지표 | 주별 회차 완료·액자 걸기·포인트 사용·추억 검색 | `-v from=2026-11-09 -v to=2026-12-07 -v include_demo=1` | 10 |

- 커뮤니티 신고는 처리 전까지 그 공유물을 바로 숨긴다. 시연 학생 화면에서 글이 빠지지 않게 G4·G6 공유물만 신고함
- 학부모 화면에 여러 주 추이 그래프는 없음. "주간 추이"는 주간 리포트 목록 4개로 보이고, 관리자 "기간 비교"는 기간 필터를 바꿔 보는 것임
- 실패 작업은 일부러 만들지 않음. 주간 서술은 리포트 Gemma로만 만들어 SageMaker 0대면 그 리포트가 실패하므로, W1~W3 시계 동안 SageMaker를 1대로 켜 둠(2026-11-23 결정, 9.7.6.7 발견 1)

#### 9.7.6.3 생성 방법·실행 순서·다시 실행 규칙

이름 규칙(#624 시연 학생과 분리)

| 대상 | #624 시연 | 더미 |
|---|---|---|
| 학부모 로그인 ID | 시연 학부모 1개(B에서 정함) | `dm854p01`~`dm854p30` |
| 학부모 이름 | 시연 보호자 | `가상가족01`~`30` |
| 자녀 별명 | `시연3학년`·`시연5학년` | 미리 정한 자연스러운 별명 36개(`시연`으로 시작하지 않음) |
| 시험 구독 표시 | `product_snapshot.demoAccount = '624'` | `'854'` |
| 비밀번호·PIN | 저장소 밖 | 저장소 밖 별도 파일 |

- 답변 문구는 자체 작성(NFR-SEC-07). 학생·주·요일마다 달라야 친구 생각과 추억 검색이 구분됨. 실행 전에 문구를 미리 검수함(결정 2)
- 더미 계정은 `AUTH_NEW_ACCOUNT_DEMO=true`라 모두 `is_demo`. core 관리자 집계·커뮤니티는 `is_demo`로 거르지 않아 그대로 보임
- 도구·명령·시계 정지점·다시 실행 규칙은 [AWS README 런북](../../infrastructure/aws/README.md#전체-서비스-더미-데이터-808). B 기준이고 kind 리허설은 가족 6개·llm-stub로 같은 순서
  - 단계: 0 테마(#890 담당자 게시, 없으면 멈춤)·판매 아이템 확인 → 1 가족 가입(실제 시각) → 2 시험 구독 SQL → 3 공개 켬(공유물은 돌아보기 저장 때만 생겨 첫 풀이 전) → 4 시계 켬(B는 Argo CD 자동 동기화 끔, 초안 생성 끔) → 5~7 W1~W3 정지점 → 8 시계 끔 → 9 W4 실제 시각 풀이·관리자 처리 → 10 12/7 확인
  - 멱등이 아닌 생성(신고·문의·공지·분석 대화·소품 구매)은 기존 목록 확인 뒤 건너뜀. 주를 넘긴 뒤 빠진 데이터는 채우지 않음("이번 주"가 서버 시계 기준)
- 시계로 생기는 차이: 정지점 사이 자정을 지나지 않아 수·목·금 일일 리포트는 W1~W3에 없음, W1~W3 주간 리포트는 시계 동안 SageMaker를 1대로 켜 둬 서술·설명이 실제 Gemma로 만들어짐(시연 자녀 W2·W3 포함, 9.7.6.7 발견 1), kind 리허설(11/26)은 실제 날짜보다 미래 기록이 남음(9.7.2와 같음)

#### 9.7.6.4 LLM 호출 수·비용 추정

단가는 [ai 보고서 19.2](ai.md#192-호출-종류별-평균-토큰비용-이번-측정) 실측값이다.

| 호출 | 건수 추정 | 1회 비용(USD) | 합계(USD) |
|---|---|---|---|
| 판정 | 590(더미 560+시연 30) | 0.000209 | 약 0.12 |
| 되묻기 | 최대 1,180(문제당 최대 2회) | 0.000235 | 최대 약 0.28 |
| 주간 서술 | 약 40(더미 36+시연) | 0.000571 | 약 0.02(B 리포트가 Gemma면 토큰 비용 없음) |
| 분석 대화 | 질문 약 18 | 0.000296(질문당) | 약 0.01 |
| 추억 검색 임베딩 | 완료 시도 약 590 | 약 0.0000062 | 약 0.004 |
| 추억 검색·설명 | 몇 건 | 약 0.000356 | 0.01 미만 |
| **합** | | | **약 0.45 이하**(상한 $5) |

- 가장 큰 위험은 테마 초안 자동 생성(1개 $4~5). 0단계 12/7 주 테마 미리 게시와 4단계 초안 끄기로 0건이어야 함
- SageMaker는 기존 12/7 창(일 23:30~월 02:00, 실제 시각, 약 $0.5)에 더해 B W1~W3 시계 동안 1대(약 3시간·$10, 2026-11-23 결정)를 씀. 넘으면 멈추고 원인 확인
- kind 리허설은 llm-stub라 판정·되묻기·서술 비용 0. 임베딩은 실제 OpenAI(9.7.2와 같음)
- 단계마다 `llm_usage_window.sql -v from=<시작> -v to=<끝>`(실제 시각)으로 누적 비용을 보고, $5를 넘을 것 같으면 멈춤

#### 9.7.6.5 결정 (담당자 확인 2026-11-20)

| 항목 | 결정 |
|---|---|
| #808과의 관계 | #854는 계획 문서로 닫고 #808이 계획 전체(더미 가족·학생·학부모·관리자) 구현 |
| 커뮤니티 노출 | 시연 학생에게 더미 글이 보이게 함. G3·G5 더미 6명 이상 공개 켬, 더미 답변 문구 미리 검수 |
| LLM 비용 상한 | OpenAI $5, SageMaker는 기존 12/7 창만(약 $0.5). 넘으면 멈추고 원인 확인. 11/23 kind 리허설 뒤 B W1~W3 시계 동안 1대 추가(약 $10, 9.7.6.7 발견 1) |
| 결제 내역 | 시험 구독 SQL로 프리미엄. 토스 테스트 결제는 위젯이 동작할 때만 시연 학부모 1건·더미 2건을 손으로. 실패하면 결제 화면은 시연 대본에서 뺌 |
| 표현 검토 큐 | 공유물 신고 숨김으로 데이터 생성. 관리자 화면(#728)이 12/7 전에 머지되면 시연에 씀(2026-11-22 머지됨) |

#### 9.7.6.6 구현 단위 (#808)

| 단위 | 구현(#808) | 상태 |
|---|---|---|
| U1 가족 목록·계정 | `infrastructure/aws/dummy854-families.json`(로그인 접두어·이름·별명·학년·무리·주별 문제 수·공개 여부), `evaluation/load/prepare_accounts.py --families` | 구현 |
| U2 여러 학생 풀이 | `infrastructure/aws/dummy854_data.py`(`demo_account_data.py` 풀이 흐름 재사용, 열린 요일 N개·학생별 답변·공개 켬·반응·꾸미기·분석 대화·신고·문의·공지) | 구현 |
| U3 구독 SQL·점검 | `add-dummy854-subscriptions.sql`, `audit-demo-data.sql` `dummy854_*` | 구현 |
| U4 시계 실행 런북 | [AWS README](../../infrastructure/aws/README.md#전체-서비스-더미-데이터-808) | 구현 |
| U5 실행 | 11/23 kind 리허설(가족 6개, 9.7.6.7) → B W1~W3 → 12/1~12/6 W4·관리자 처리 → 12/7 확인, 결과를 이 절 아래 기록 | 12/7까지 |

구현 때 확인한 차이: 자녀 등록은 GUARDIAN 동의 1개만 받아 COMMUNITY 동의는 등록 뒤 별도 호출(`POST /me/consents`), 커뮤니티 공유물·반응 테이블은 learning DB, `payment`에는 샌드박스 표시 칸이 없어 테스트 거래 여부는 시연 표시별 결제 집계와 결제 키 설정으로 판단(#811 QA-03).

#### 9.7.6.7 U5 kind 리허설 결과 (2026-11-23)

B 전에 실제 API와의 차이를 찾으려고 11/26 예정이던 kind 리허설을 앞당겼다. 실제 실행한 것만 적는다. AWS는 조회도 변경도 하지 않았다.

- 대상: 공유 `kind-sagomungchi-local`, develop `9311b3ce`로 앱 5종·migration 2종·llm-stub 이미지를 다시 빌드해 local 값으로 helm upgrade(core V55·learning V27·report `20261110_08`). ai는 kind에 켜 둔 `M2_CROSS_CHECK_ENABLED=true`를 그대로 뒀다(9.7.5)
- 대역: ai `OPENAI_BASE_URL`=llm-stub(판정·되묻기·분석 대화), `REPORT_LLM_ENDPOINT_URL`=llm-stub의 없는 경로(404, B의 SageMaker 0대 흉내). 실제 OpenAI는 추억 검색 임베딩만
- 계정: 앞 6가족(`--count 6`), 리허설용 관리자 1개(`scripts/admin_account_sql.py`, ALL 권한)와 #624 시연 학부모 1개(시연3학년·시연5학년)를 새로 만들었다. 비밀번호·PIN은 저장소 밖 파일
- 테마(`themes`, 만들지 않음): G3·G5는 11/9~11/30 4주 게시, G4 없음, G6은 11/9만, 12/7 주는 전 학년 없음 → `--grades G3,G5`(학생 4명+시연 2명). G4·G6 학생 4명은 가입·동의·구독까지만
- 판매 아이템: 가구 DESK `KIND485_DESK_OAK`(20포인트)는 있고 소품(DECOR)은 없어 `room`은 `--furniture`만
- 실행 시각 실제 01:20~03:10 KST. 시계는 kind라 W4(12/2·12/5·12/6)도 시계로 돌렸다

| 단계 | 결과 | 걸린 시간(실제) |
|---|---|---|
| 1 가족 | `6/6 families ready`. 다시 실행하면 학부모 6·자녀 8·동의 28·기기 6 그대로, 비밀 파일도 같음 | 605초(가입 제한으로 6번째 가족 10분 대기), 재실행 1초 |
| 2 구독 SQL | `LOCAL-PLUS` 4명, 학년별 `premium_854` 1씩. 두 번 실행해도 같음 | 1초 |
| 2 시연 구독 | `prepare-demo-account-students.sql`은 생략. kind에 9.7.2의 같은 별명 학생이 있어 가드(별명당 1명)가 막는다. B에는 해당 없음 | — |
| 3 공개 켬 | 4명 켬 + `--demo-child` 2명(COMMUNITY 동의 추가 후 켬). 재실행 같음 | 2초 |
| 정지점 수 19:00 | 5문제 무리만 월~수 3개. 무료 학생도 수요일에 월~수가 열려 있었다 | 약 43초(전환 39초+풀이 4초) |
| 정지점 토 14:00 | 나머지 풀이·정답 고르기(G5 바탕 테마는 정답 후보 없음)·#624 `solve`(W2~W4)·`react` | 약 53~61초 |
| 정지점 토·일 23:56 | 가짜 00:00+5분까지 기다린 뒤 작업 확인 | 약 543초 |
| W4 토 | `room`(액자 도토리 3·나머지 1, DESK 착용)·`converse`(dm854p01 대화 1개·질문 2개, 대역 SSE)·`support`(정정 요청 3·문의 5). 모두 재실행 변경 없음 | 약 61초 |
| W4 토 밤 | `admin-ops` 공지 3·문의 답변 3·정정 처리 2(정해 둔 2건만 처리하고 나머지는 관리자 화면에 접수 상태로 남김, `CORRECTIONS_TO_RESOLVE`). 재실행 같음 | 1초 |

주 완료 문제 수(learning, 리허설 학생만)는 `plan --count 6 --grades G3,G5` 무리 표와 같다: 꾸준 도토리 5·5·5·5, 보통 봄비·구름빵 5·4·3·4, 들쭉 아기별 5·0·4·2, 시연 2명 0·5·5·5. 액자는 5문제 주에만 생겼다. 추억 검색 문서 93개 모두 `READY`. 반응은 정지점마다 새로 12~26개, 같은 명령 재실행은 0개.

리포트(core `report_job`, 리허설 학생 10명)

| 기간 | 결과 |
|---|---|
| 일일 토·일(11/14·15·21·22·28·29, 12/5·6) | 경계마다 10건 모두 `COMPLETED` |
| 주간 W1~W4 | 경계마다 8건 `COMPLETED`, **2건 `FAILED(GENERATION_FAILED)`**: 프리미엄 도토리(G3)·봄비(G5) |
| 테마 초안 | 시계 동안 `theme_draft` 새 행 0건 |
| 같은 기간 재생성 | 11/29 23:56에서 core를 다시 띄워 월 00:00 경계를 한 번 더 지나게 함 → 두 스케줄이 다시 돌았지만(ShedLock 갱신) 11/23 주간·11/29 일일 작업은 각 10건 그대로 |
| 복구 | 대역을 원래 llm-stub로 되돌린 뒤 관리자 재시도(`POST /admin/jobs/{id}/retry`)로 도토리 W4 주간 → `COMPLETED`, 서술 있음, 설명 `NOT_INCLUDED` |

LLM: 판정 87·되묻기 93·분석 4건은 모두 대역(토큰 1). 실제 호출은 임베딩 13건(배치) 약 $0.0006, M2 24건(로컬 모델). `llm_usage_window.sql` 기준 실사용은 임베딩뿐이다.

점검 SQL: 세 DB `audit-demo-data.sql`을 app 계정으로 실행해 오류 없이 끝났다. learning·report 집계에는 kind에 있던 다른 학생 기록이 섞인다.

발견(B 전에 볼 것)

1. **주간 서술 실패 = 리포트 실패 → B는 시계 동안 SageMaker 1대 유지(2026-11-23 결정).** 서술은 리포트 Gemma(SageMaker)로만 부르고(`create_report_llm`), 실패하면 대체 문구 없이 작업이 `FAILED`다. B W1~W3 경계는 SageMaker 0대라 그 주 기록이 있는 프리미엄 학생 주간 리포트가 모두 실패하고 학부모 목록에 실패로 보인다. 기록 4건인 봄비도 실패했으므로 "5건 이상일 때만 서술"(9.7.6.2)도 맞지 않는다. 런북의 "설명 없이 발행(정상)"은 고쳤다. 선택지는 경계마다 SageMaker를 켬, 실패분을 12/6~7 SageMaker 창에 관리자 재시도로 다시 만듦(이번에 확인), W1~W3 주간 리포트 포기였다. **B 시계 동안 1대로 켜 두는 쪽으로 정했다**: 시연 전날 밤 재시도(약 30건, 창 2.5시간) 부담이 없고, 실제 Gemma 서술·설명 경로와 #777 잠금을 시연 1주일 전(11/29)에 B에서 먼저 확인할 수 있다. 추가 비용은 약 3시간·$10이고, 11/29 23:30 실제 창(#886 PRF-03) 전에 `copies 0`으로 내린다. 재시도는 켜 두기가 실패했을 때의 대체 수단으로 남긴다
2. 롤아웃이 끝나도 이전 Pod가 `Terminating`으로 약 1분 요청을 받아, 그 사이 로그인한 토큰을 새 Pod가 `TOKEN_EXPIRED`로 거절했다(W1 토 14:00 첫 시도 4명 실패, 다시 실행해 통과). 런북에 "Terminating이 없어진 뒤 실행"을 넣었다
3. `kubectl exec ... date -u`는 늘 `FAKETIME` 시작 값을 보여 줘 앱 시각 확인이 안 된다. 런북을 로그 시각·컨테이너 시작 시각 기준으로 고쳤다
4. Git Bash에서 `kubectl set env LD_PRELOAD=/usr/...`가 Windows 경로로 바뀌어 첫 시계가 켜지지 않았고, 그 사이 도토리가 실제 시각(11/23 주) 월요일 1문제를 풀었다. W3 목표 5에 포함돼 수는 맞다. 런북에 `MSYS_NO_PATHCONV=1`을 넣었다
5. 같은 `FAKETIME`을 다시 넣으면 Pod가 다시 뜨지 않는다(같은 시각 재시작은 `rollout restart`)
6. 커뮤니티 신고는 G4·G6 공유물만이라 kind(G4·G6 테마 없음)에서는 0건이었다. B는 G4·G6 테마가 있어야 신고 2건·표현 검토 큐 2건이 생긴다
7. `admin-ops` 문의 답변은 `INQUIRY_ANSWERS` 제목만 대상이라 가족 6개에서는 3건이었다(30가족이면 4건)

되돌림·남긴 것

- 되돌림: core·learning 이미지·환경 변수(`set image`·`set env ...-`), ai `OPENAI_BASE_URL` 제거·`REPORT_LLM_ENDPOINT_URL` 원래 값. 세 Deployment 모두 `helm get manifest | kubectl diff` 차이 없음, Pod 시각 실제
- kind에 남김: develop `9311b3ce` 이미지(이전 이미지는 `:pre-808` 태그), 시험 시계 이미지 `sagomungchi/{core,learning}-service:demo-clock808`, dm854p01~06 가족·시연 학부모·리허설 관리자, 시험 구독 4건, 11/9~12/6 미래 날짜 기록·리포트·공지 3건·문의·정정 요청
- kind는 learning 주간 초안 자동 생성(수 03:00)이 기본으로 켜져 있고 11/30 주 G4·G6 테마가 없어, 실제 11/25(수) 03:00에 실제 OpenAI로 초안이 만들어질 수 있었다. 리허설 뒤 kind learning에 `APP_THEMEDRAFT_ENABLED=false`를 직접 넣어 껐다(2026-11-23). helm upgrade를 하면 다시 켜진다

## 9.8 prod 테마 자산 버킷과 네임스페이스 기본 거부 준비 (#652·#657, 2026-11-16)

AWS가 내려가 있어(EKS 삭제, RDS 정지) 저장소 값과 문서만 고쳤다. AWS 호출은 읽기도 하지 않았고, 적용·확인은 A 계정 재가동(#601) 때 한다. 2026-11-17 재가동 때 실제로 적용·확인한 결과는 9.8.3에 있다.

### 9.8.1 테마 자산 버킷 (#652)

- 문제: prod ai·learning 값에 `ASSET_S3_BUCKET`이 없어 ai는 그림·영상 단계를 건너뛰고(`app/theme_draft/storage.py` `create_storage`, `app/llm/media.py` `create_media_clients`), learning은 자산 URL을 null로 준다(`app.assets.bucket`). 오류가 나지 않아 눈에 띄지 않았다.
- 값: 두 서비스에 `ASSET_S3_BUCKET=sagomungchi-demo-<A 계정>-missions`, `S3_REGION`·`AWS_REGION=ap-northeast-2`. local과 달리 `S3_ENDPOINT_URL`(ai)·`S3_PUBLIC_ENDPOINT_URL`(learning)은 넣지 않는다. 비어 있어야 AWS S3 주소로 올리고 서명한다(local 값은 MinIO 주소).
- 권한: `infrastructure/aws/iam`에 ai·learning용 역할이 없었다(report·scoring만 있음). 역할 2개(ai `PutObject`, learning `GetObject`, 둘 다 `theme-drafts/*`만)와 trust를 정의하고 `demo-stack.json`(IAM 역할 12개)·`eks/cluster.json`(Pod Identity 10개)에 넣었다. 재가동 절차는 [AWS README 테마 자산 버킷 권한](../../infrastructure/aws/README.md#테마-자산-버킷-권한-652-2026-11-16-정의-2026-11-17-적용).
- #537(2026-11-17): ai 역할 정책에 `s3:GetObject`를 더함(`theme-drafts/*` 그대로). 테마 초안 부분 다시 생성이 S3에 둔 재료 그림(테마 옷 뭉치·컷 첫 그림)을 다시 읽기 때문. 정책 이름 `sagomungchi-demo-ai-asset-s3-write`는 `demo-stack.json`·AWS 역할과 이어져 있어 바꾸지 않음. 역할은 아직 AWS에 없어 #652로 만들 때 같이 들어가고, 그 뒤에 들어오면 정책만 다시 적용(#652 담당 확인)
- 네트워크: 두 앱은 이미 자기 NetworkPolicy로 egress가 격리돼 있어, 역할만 연결하면 Pod Identity agent(`169.254.170.23:80`)에 못 닿아 자격 증명을 못 받는다. 두 앱 egress에 agent를 더했다(report·scoring·sLLM과 같은 규칙).
- 한계: presigned URL은 Pod Identity 임시 자격 증명으로 서명하므로, 자격 증명 만료가 1시간(`url-ttl`)보다 가까우면 URL이 더 일찍 만료될 수 있다(`AssetUrls` 주석). 화면에서 그림이 중간에 안 보이면 이것부터 본다.
- B 계정 이전 때 바꿀 항목: 버킷 이름·IAM 원문·`cluster.json`의 계정 번호(AWS README 같은 절). 전체 목록과 교체 절차는 [AWS README B 계정 전환 런북](../../infrastructure/aws/README.md#b-계정-전환-런북-809)(#809).

### 9.8.2 app 네임스페이스 기본 거부 (#657)

결정(권장안): prod 값에 켜고 필요한 허용을 더하며, 실제 확인은 A 계정 재가동 때 한다.

판단 근거(읽기 위주): 공유 local kind는 이날 Docker가 꺼져 있어 조회하지 못했고, 켜 보는 시험도 하지 않았다. 대신 다음으로 판단했다.

- local은 이미 core 값에서 `namespaceDefaultDeny: true`로 app 기본 거부를 켜 둔 상태로 kind 확인 A~D(#436)·#546·#624를 통과했다. 기본 거부 아래에서 앱 7개·migration Job(Argo PreSync 정책 포함)이 동작한 근거다.
- prod 앱 values 7개와 migration 덮어쓰기 3개를 helm 4.3.1로 렌더링해 모든 Pod 라벨이 어떤 정책에 선택되는지 대조했다. 앱 Deployment 7개는 이미 자기 정책(ingress·egress)으로 격리돼 있어 기본 거부를 더해도 허용 범위가 같다. NetworkPolicy는 합집합이므로 기본 거부는 "자기 정책이 없는 Pod"에만 영향을 준다.

기본 거부를 켜면 막히는 것과 처리:

| 대상 | 현재 prod | 처리 |
|---|---|---|
| migration Job(core·learning·report) | `--show-only migration-job.yaml`로 Job만 적용 → 정책 없음 | `migrations/*.json`에 `networkPolicy.migrationEgress`(RDS 5432) 추가, prod README 절차와 ci-gitops 렌더링에 `migration-networkpolicy.yaml`을 같이 넣음 |
| `rds-bootstrap` Job(`demo_stack.py`), `demo-db-oneoff` Pod | 정책 없음 | `prod/app-oneoff-db-network.json`(DNS·RDS 5432) |
| 배포 확인 Pod(`deployment-check` 라벨) | core·learning·scoring ingress만 허용, Pod 자체 egress 정책 없음 | `prod/app-check-pods-network.json`(DNS·core·learning·scoring) |
| `kubectl run` 등 그 밖의 임시 Pod | 정책 없음 | 막히는 것이 의도. 필요하면 위 라벨을 쓰거나 정책을 먼저 만든다 |
| KEDA(#476 sLLM cron) | prod 미설치 | cron 스케일러는 app Pod와 통신하지 않음. RabbitMQ 스케일러를 쓰면 platform 정책(`platform-network.json`) 문제이고 app 기본 거부와 무관 |
| 관측(Collector·Prometheus·Langfuse) | 앱별 `egressToCollector`·`ingressFromPrometheus`·`egressToLangfuse` | 앱 Pod가 이미 격리돼 있어 변화 없음. 관측 Pod는 `observability` namespace라 대상 아님 |
| ALB → core, kubelet probe, `kubectl exec`·`logs` | `core-alb-network.json`, 기존 격리 상태에서 동작 | 변화 없음 |

- `app-default-deny`는 core release만 만든다. 두 release에 켜면 같은 이름 객체로 Helm 소유권 충돌이 난다.
- 재가동 때 확인할 것: core 재배포 뒤 `kubectl -n app get networkpolicy app-default-deny`, 앱 7개 readiness, migration Job 1회 성공, `demo-db-oneoff`로 `select 1`, 정책 없는 `kubectl run` Pod의 DNS 조회가 실패하는지. 되돌리기는 prod README NetworkPolicy 절.

### 9.8.3 A 계정 재가동 확인 결과 (2026-11-17)

운영 기준 main `e3cb5084`로 재가동하며 실제로 실행한 결과다. 순서는 9.11.5를 따랐다.

#### 테마 자산 버킷 (#652)

실행:

- `demo_stack.py apply`로 역할 `sagomungchi-demo-ai-asset-s3-role`·`sagomungchi-demo-learning-asset-s3-role` 생성(15:45 KST). 원문은 `e3cb5084` 기준이라 ai 정책에 #537 `s3:GetObject`가 이미 들어 있다
- 새 클러스터 `eksctl create cluster`로 Pod Identity 연결 `app/ai-service`·`app/learning-service` 생성(16:18)
- ai·learning을 main prod values(`ASSET_S3_BUCKET` 포함)로 설치
- 관리자 화면에서 테마 초안 1건 요청(초5, 2026-11-16 주, 18:03)

결과:

| 확인 | 결과 |
|---|---|
| 초안 생성 | READY(18:17, 1회 시도) |
| 그림 저장 | 그림 16장이 missions 버킷 `theme-drafts/<초안 ID>/`에 저장됨(18:10:53, PNG 1.1~1.7MiB). 초안 출력 `images`에 S3 키가 연결됨 |
| 사용량 | `THEME_IMAGE` 15건(18:08~18:10) |
| 학생 자산 URL | 채택·미션 5개·테마 게시 뒤 학생 `GET /students/me/weekly-theme`에서 `introImageUrl`·`introVideoUrl`이 서명 URL(유효 3600초)로 내려옴 |
| 서명 URL 열기 | 두 URL에 실제 GET → 206(`image/png`, `video/mp4`) |

- `outroImageUrl`·`outroVideoUrl`은 null이었다. 주 마감 전이라 정상인지는 확인하지 않았다
- 영상(Veo) 저장은 #600에서 따로 확인했다(mp4 2개)

#### app 네임스페이스 기본 거부 (#657)

실행:

- core를 prod values(`namespaceDefaultDeny: true`)로 설치 → `app-default-deny`(podSelector 전체, Ingress·Egress) 생성
- 기본 거부 아래에서 필요한 정책을 함께 적용: migration 정책 3개(chart 렌더링), `app-oneoff-db`, `app-deployment-checks`, `core-demo-alb-ingress`

결과:

| 확인 | 결과 |
|---|---|
| 앱 | 6개 서비스 정상 기동, ALB → core 경로 정상 |
| migration Job | core·learning·report 3개 모두 성공. learning은 첫 실행이 pgvector 권한(DB 권한, 네트워크 아님)으로 실패해 `rds-bootstrap` 뒤 다시 실행 |
| 일회성 DB Pod | `rds-bootstrap`·`demo-db-oneoff` 정상 동작 |
| 정책 없는 Pod | app namespace에 busybox 시험 Pod: 기동 직후 DNS 조회 성공, 약 20초 뒤 같은 조회 실패 → 기본 거부 적용 확인 |

- 기동 직후 허용 구간: VPC CNI 기본(표준) 모드의 NetworkPolicy는 새 Pod에 정책이 적용되기 전까지 짧게 통신을 허용한다. 이번 확인에서 약 20초였다. 정책 없는 임시 Pod도 이 구간에는 통신할 수 있으므로, 기본 거부를 "기동 순간부터 차단"으로 설명하지 않는다
- KEDA는 prod에 설치돼 있지 않아 영향 확인 대상이 아니다. observability·platform은 별도 namespace라 대상이 아니다

## 9.9 서비스별 내부 토큰·브로커 계정 분리 (2026-11-16)

전 서비스가 내부 토큰 1개(`INTERNAL_TOKEN`)와 RabbitMQ 기본 관리자 계정 1개를 공유해 한 Pod 토큰이 새면 모든 서비스의 `/internal/**`를 부르고 모든 큐를 읽기·삭제·발행할 수 있었다(예: report-worker 토큰으로 core 결제 사용 예약). 설계 문서에 분리 요구가 없어 DB 계정 분리(#230)와 같은 기준으로 나눴다. 규칙은 [아키텍처 2.2](../design/architecture.md#22-의존-규칙)·[4.5 Secret](../design/architecture.md#45-cicd), 허용 경로 표는 [API 명세서 4장](../design/api-spec.md#4-내부-api-internal).

### 9.9.1 결정

| 항목 | 결정 | 근거 |
|---|---|---|
| 토큰 단위 | 호출 주체 7개(core·learning·ai·scoring·report-api·report-worker·ops)마다 1개. 보내는 쪽 `INTERNAL_TOKEN`은 그대로 자기 토큰 | 클라이언트(`InternalRestClientFactory`·`internal_client`) 코드 변경 없음. 호출 쌍마다 토큰(14개)은 관리 부담 대비 이득이 작음 |
| 받는 쪽 검사 | 토큰으로 호출자 식별 후 호출자별 경로 허용 목록. 불일치 401, 허용 밖 403 | report-worker는 원래 core 별명 조회를 부르므로 호출자만 확인하면 예시 위험이 남음(사용자 결정: 호출자+경로) |
| 허용 목록 위치 | 받는 쪽 코드 상수(Spring `InternalCallerPolicy`, Python `CALLER_PATHS`) | 권한은 코드 리뷰 대상. 토큰 값만 환경 변수 |
| 같은 토큰 여러 호출자 | 허용 범위 합집합 | 테스트·일회용 검증 스택이 토큰 하나로 동작. 운영 값 중복·16자 미만은 `create-app-secrets.ps1`이 거부 |
| 브로커 계정 | 서비스별 5개(이름 고정), 최소 권한 + `events.topic` 토픽 권한. 관리자는 앱에 미주입 | 큐 삭제·남의 큐 소비·남의 이벤트 키 발행 차단 |
| 재시도 경로 | 기본 exchange → `core.retry`·`learning.retry`·`report.retry` | 기본 exchange 쓰기 권한은 큐 이름만으로 남의 큐에 넣을 수 있어 제거(사용자 결정) |
| core 큐 현황 | core 계정에 `monitoring` 태그 | 관리 API 큐 목록 조회용. 메시지 내용 접근 없음 |

### 9.9.2 남는 위험

- 받는 쪽 Pod가 새면 그 Pod가 받는 호출자 토큰도 노출된다(예: learning Pod에는 core 토큰 포함). 해시 저장은 ESO·compose 값 생성이 복잡해져 이번 범위에서 제외
- kind는 Secret 객체 1개(`app-service-credentials`)에 모든 키가 있고 Pod별로 필요한 키만 `secretKeyRef`로 받는다. Secret 읽기 RBAC가 있으면 전체가 보이는 점은 #230과 같다
- learning은 core에게 `/internal/**` 전체를 연다(관리자·학습 프록시 대부분). core 토큰 유출은 여전히 learning 내부 API 전체 위험

### 9.9.3 적용 절차

- 로컬 `.env`: `.env.example`의 `INTERNAL_TOKEN_*` 6개(+선택 ops)와 `RABBITMQ_<SVC>_PASSWORD` 5개를 채우고 기존 `INTERNAL_TOKEN`은 지운다. compose는 `rabbitmq-init`이 실행될 때마다 계정·비밀번호·권한을 다시 반영한다
- kind: 기존 `platform/platform-data-credentials`·`app/app-service-credentials`는 키가 달라 스크립트가 중단한다. 두 Secret을 지우고 `create-platform-secret.ps1`·`create-app-secrets.ps1`을 다시 실행한 뒤 platform-data(새 init Job)와 앱을 동기화한다
- AWS 데모: Secrets Manager `sagomungchi/demo/app/internal`에 `INTERNAL_TOKEN_<호출자>` 6개, `sagomungchi/demo/platform/rabbitmq`에 `core_password`·`learning_password`·`ai_password`·`scoring_password`·`report_password`를 추가한다(기존 secret 이름이라 ESO IAM 변경 없음). 그 뒤 platform-data → 앱 순서로 재배포한다. 저장소에는 정의만 반영했고 실제 값 생성·재배포는 하지 않았다
- 운영 스크립트(`scripts/knowledge`, `evaluation/runners/judgment_eval.py`)는 `INTERNAL_TOKEN` 환경 변수에 ops 토큰을 넣어 실행한다. kind에서 쓰려면 `.env`에 `INTERNAL_TOKEN_OPS`를 넣고 app Secret을 다시 만든다

## 9.10 실제 LLM 조건 로컬 응답 시간 실측 (#630, 2026-11-16)

1차 부하 시험(9절)은 LLM 스텁 기준이라 실제 LLM 지연이 빠져 있었다. 실제 OpenAI로 화면과 같은 core 경로의 응답 시간을 처음 쟀다. 결과 수치·호출 종류별 토큰·원가 산식은 [ai 19절](ai.md#19-실제-llm-조건-응답-시간원가-산식-630-2026-11-16).

### 9.10.1 환경

| 항목 | 값 |
|---|---|
| 클러스터 | local kind `kind-sagomungchi-local`, develop 배포(006c2476 기준) 그대로 |
| 진입 | `http://127.0.0.1` + Host `api.sagomungchi.local`(ingress-nginx → core), 측정 PC = 클러스터 호스트 |
| ai | 실제 OpenAI(`OPENAI_MODEL=gpt-6-luna`, 테마 검토 `gpt-6.1-terra`), `M2_CROSS_CHECK_ENABLED=true`(시연 조건, #668이 적용), `THEME_VIDEO_ENABLED=false` |
| 동시 사용자 | 1명(요청을 한 건씩 차례로) |
| 시각 | 2026-11-16 10:09~11:28 KST. 판정·분석·리포트 10:09~10:16, 테마 10:18~11:28 |
| 재시작 | 측정 구간 동안 앱 Pod 재시작·교체 없음(15~20초마다 확인). 테마 초안만 ai에 `IMAGE_PROVIDER=fake`를 넣어 재시작한 뒤 재고 측정 뒤 원래 ReplicaSet으로 되돌림 |

### 9.10.2 절차와 표본

`evaluation/load/llm_latency.py`가 요청 시작부터 SSE `done`(리포트는 관리자 작업 `COMPLETED`, 테마는 초안이 `GENERATING`을 벗어날 때)까지를 잰다. 같은 시간대 `llm_usage`는 `llm_usage_window.sql`로 묶는다.

| 흐름 | 경로 | 표본 |
|---|---|---|
| 판정·되묻기 | 학생 `POST /missions/{id}/attempts` → `POST /attempts/{id}/answers` → `POST /answers/{id}/feedback`(SSE). 되묻기가 오면 `followupId`로 답해 다시 판정 | 판정 SSE 30건(그중 LLM 되묻기 20건), 초5 서술 미션 10개 |
| 분석 대화 | 학부모 `POST /conversations` → `POST /conversations/{id}/messages`(SSE) | 20건 |
| 주간 리포트 서술 | 관리자 `POST /reports/{id}/regenerate` → `GET /admin/jobs/{jobId}` | 같은 리포트(시험 계정 `kindqa1` 자녀, 11/09 주) 5회 |
| 테마 초안 글 | 관리자 `POST /admin/theme-drafts`(`G3`·`G4`·`G5`, 2027-01-04 주) → `GET /admin/theme-drafts/{id}` | 3건, 끝난 뒤 버림 처리 |

- 시작 직후 learning이 다른 작업(#668)으로 교체돼 판정 4건(10:02~10:03)을 버리고 처음부터 다시 쟀다
- 테마 G4는 관리자 access 토큰(15분) 만료로 폴링이 끊겨 learning `theme_draft.created_at → updated_at`(36분 27초)으로 보정했다. 스크립트는 401이면 다시 로그인하도록 고쳤다
- 비용: 이번 측정 전체 $0.665(테마 글 $0.644)

### 9.10.3 결과 요약

| 흐름 | 건수 | p50 | p95 | 최대 |
|---|---|---|---|---|
| 판정 SSE(되묻기 없음) | 10 | 5.2초 | 8.9초 | 9.4초 |
| 판정 + 되묻기 SSE | 20 | 7.2초 | 12.5초 | 14.0초 |
| 분석 대화 SSE | 20 | 3.6초 | 8.9초 | 11.8초 |
| 주간 리포트 재생성 | 5 | 13.2초 | 35.3초 | 40.6초 |
| 테마 초안 글 | 3 | 4.8분 | — | 36.4분(`CHECK_FAILED`) |

- 1차 부하 시험 판정 SSE p95(스텁 2.5~4초)와 바로 비교하지 않는다. 동시 사용자 수·환경이 달라 개선율·악화율을 내지 않는다
- 실패 0건(HTTP·SSE `error` 없음). 분석 대화 LLM 호출 33회 중 1회 실패가 있었지만 응답은 정상 종료됐다

### 9.10.4 만든 시험 데이터 (kind에 남김)

| 대상 | 내용 |
|---|---|
| 학부모 `perf6301`(ID·비밀번호, `is_demo=false`) | 자녀 초5 `부하1`·`부하2`·`부하3`, 학생 기기 1대·PIN, 보호자 공유 켬. `prepare_accounts.py`로 만듦 |
| 구독 3건 | 위 자녀 3명 `LOCAL-PLUS` ACTIVE(11/16~12/16, 자동 갱신 없음). 결제 없이 core_db에 직접 넣음(무료 학생은 일반 미션 시작 불가) |
| 관리자 `perf630-admin` | CONTENT·SERVICE_OPS. `scripts/admin_account_sql.py`로 만듦 |
| 학습 기록 | 서술 미션 시도 12개(버린 표본 포함)와 답변·판정·되묻기, 분석 대화 1개(질문 20개) |
| 리포트 | `kindqa1` 자녀 11/09 주 주간 리포트 revision 2~6 |
| 테마 초안 | 2027-01-04 주 G3·G4·G5 초안 3건(`DISCARDED`). 대역 그림은 MinIO `theme-drafts/` 아래 |
| `llm_usage` | 10:02~11:28 KST 실제 호출 약 380건(같은 시간대 다른 세션의 kind 확인 호출이 일부 섞임, 측정분은 시간 구간으로 구분) |

비밀번호·PIN·기기 쿠키는 저장소 밖 파일에만 있다. 정리(관리자 비활성화 `admin_account_sql.py --disable`, 구독 해지, 계정 탈퇴)는 #601 AWS 실측 뒤 함께 정한다.

### 9.10.5 한계와 남은 것

- 로컬 kind·동시 1명이라 NAT·ALB·실제 네트워크 지연과 동시 부하에서의 OpenAI 지연·429는 반영되지 않았다
- AWS 실측은 #601 A 계정 재가동 때 같은 도구(`LOAD_API_BASE`·`LOAD_API_HOST`만 바꿈)로 한다. 동시 사용자를 늘린 실제 LLM 부하는 #384 범위
- 테마 초안은 그림 대역이라 그림 생성 시간(1장 p50 약 34초, 11/12 기록)이 빠졌다

### 9.10.6 AWS 운영 데모 실측 (2026-11-18)

9.11.4 절차대로 A 계정 운영 데모에서 같은 도구로 다시 쟀다. 결과 수치·kind 비교·원가는 [ai 19.5](ai.md#195-aws-운영-데모-실측과-kind-비교-2026-11-18).

| 항목 | 값 |
|---|---|
| 환경 | AWS A 계정 운영 데모, main `e3cb5084`. 측정 PC → CloudFront → ALB → core(외부 인터넷 경유) |
| ai | 실제 OpenAI(`LLM_PROVIDER=openai`, `OPENAI_MODEL=gpt-6-luna`, `OPENAI_BASE_URL` 없음), `M2_CROSS_CHECK_ENABLED=true`, `THEME_VIDEO_ENABLED=true`. 측정 전 ReplicaSet이 helm 것(`ai-service-d4888b47`)이고 #384 스텁이 원복된 것을 확인 |
| 시각 | 2026-11-18 13:54:46~14:01:29 KST(판정 13:54~13:58, 분석 13:59~14:00, 추억 검색 14:01). #384 부하 시험이 끝난 뒤, 다른 부하 없음 |
| 동시 사용자 | 1명 |
| 재시작 | 측정 동안 ai·learning·scoring·report Pod 재시작·교체 없음. core는 측정 시작 때 2개(HPA)였다가 끝난 뒤 1개로 줄어 있었다(실패 0) |
| 표본 | 판정 SSE 30건(되묻기 20, 초5 서술 미션 10개 시도), 분석 대화 20건, 추억 검색 9건. 테마 초안은 11/18 03:00 스케줄러 실행분 4건(`llm_usage`·관리자 초안 목록 조회) |
| 측정하지 않은 것 | 주간 리포트(서술이 있는 주간 리포트가 운영에 없고, 다음 주간 생성이 11/23), 추억 설명(시험 자녀에게 보유 액자 없음). 이유는 ai 19.5 |

도구 변경
- `llm_latency.py`: 학생·학부모 access(15분, refresh 없음)가 만료되면 같은 자격 증명으로 다시 로그인한다(관리자는 9.10.2에서 이미 그렇게 고침). 추억 검색 → 설명 `memory` 명령을 더했다
- `llm_usage_window.sql`은 그대로 쓰고, 파일 앞에 `\set from`·`\set to`를 붙인 사본을 일회성 DB Pod로 실행했다

만든 시험 데이터와 정리

| 대상 | 만든 것 | 정리 | 정리 뒤 확인 |
|---|---|---|---|
| 학부모 1개(ID·비밀번호, `is_demo=true`) | `prepare_accounts.py --count 1 --children 3 --grade 5`, 자녀 3명·학생 기기 1대·PIN | 비밀번호 재확인 → `POST /me/withdrawal`(202) | core 로그인 ID 0건, 자녀 3명 `DELETED`, learning 시도 0건 |
| 시험 구독 3건(결제 없음, PREMIUM 상품 행의 `limits` 그대로, 7일) | 일회성 DB Pod로 `subscription` INSERT | `CANCELED` → 이용 기간을 당일로 끝냄(#384 정리 때와 같이 기간이 남으면 탈퇴가 `WITHDRAWAL_BLOCKED`) | 활성 0 |
| 관리자 | 새로 만들지 않음(재가동 때 만든 공용 관리자 계정으로 목록 조회만) | — | — |
| 일회성 DB Pod·ConfigMap | `demo-db-oneoff.k8s.yaml` 사본(이름만 바꿈, 같은 라벨·정책), core·report·learning DB | 실행마다 delete | app 네임스페이스에 남은 것 없음 |
| 비밀 파일(작업자 PC, 저장소 밖) | 비밀번호·PIN·기기 쿠키 | 삭제 | — |

- 남긴 것: 측정 구간 `llm_usage` 78행(판정 26·되묻기 20·분석 32, $0.0153). 클러스터 설정(HPA·스텁·ai env)은 바꾸지 않았고 앱 재시작·배포도 하지 않았다
- 한계: 동시 1명. 실제 LLM에서 동시 사용자를 늘린 지연·429는 재지 않았다. 판정·분석 표본 수는 kind와 같지만 10~20건이라 p95는 거친 값이다

## 9.11 A 계정 재가동 당일 체크리스트 (#601, 2026-11-17 준비)

재가동 전 AWS 읽기 전용 조회로 확인한 결과와 당일 절차다. 실제 실행 결과는 9.8.3(재가동), 9.10.6(#630), 9.12(#629), 9.14(#384), [scoring 7.8](scoring.md#78-운영-적용-613-2026-11-17)(#613)·[6.5](scoring.md#65-실행-결과-2026-11-10-pod-경로-확인-2026-11-17)(#493). B 계정 전환 절차는 [AWS README](../../infrastructure/aws/README.md)의 B 계정 런북.

### 9.11.1 0단계 점검 결과 (2026-11-17 읽기 전용)

- `demo_stack.py plan`: OK 40 · DIFF 2(지운 NAT를 가리키는 private route `blackhole` 2개, `apply`가 바꾸지 않아 `replace-route` 필요) · MISSING 4(NAT, #652 자산 IAM 역할 2개, EKS)
- RDS(정지): PostgreSQL 17.11, db.t4g.small·gp3 20 GiB·Single-AZ·백업 7일, 7일 자동 시작 규칙 있음. `max_connections`는 2 GiB 기준 약 225 미만
- 옛 values로 복구하면 막히는 곳: 서비스별 내부 토큰·브로커 계정 키(9.9)로 바뀐 ESO 매니페스트, cd-release가 migration 이미지를 만들지 않음, #657 기본 거부, 자산 IAM 역할을 `eksctl create` 전에 만들어야 함
- 결정(2026-11-17): DB가 11/6 이후 바뀌지 않아 앱은 옛 values 단계를 건너뛰고 플랫폼(values 차이 0)만 보관 values로 올린 뒤 새 main SHA로 배포

### 9.11.2 #384 준비

연결 수(HPA 최대 기준 core·learning 각 30, report-api 15, ai 0)와 부하 단계를 준비했다. 실행 결과는 9.14.

### 9.11.3 #629 PITR 복구 시험 준비

복원 시점 T 전후 표지 A·B를 남기고 `LatestRestorableTime`·요청 시각을 기록하는 절차를 준비했다. 실행 결과는 9.12.

### 9.11.4 #630·#613·#493 당일 절차

**#630 AWS 실측**: 9.10과 같은 도구·표본(판정 30·되묻기 20·분석 20·리포트 5·테마 3)으로, 진입 주소만 바꾼다. #384 부하가 없는 시간대에 실제 OpenAI로 하고 #384 결과를 본 뒤 표본을 조정한다.

```powershell
$env:LOAD_API_BASE = 'https://d3jf0rnm6vhd9v.cloudfront.net/api/v1'
$env:LOAD_API_HOST = 'd3jf0rnm6vhd9v.cloudfront.net'
$env:LOAD_ORIGIN   = 'https://d3jf0rnm6vhd9v.cloudfront.net'
python evaluation/load/llm_latency.py judge --secrets <밖>/secrets-630.json --out <밖>/aws-630.jsonl --judgments 20 --followups 20
```

`llm_usage_window.sql`은 core_db에서 돌린다. AWS에는 psql 접속 경로가 demo-db-oneoff Pod뿐이므로, 파일 앞에 `\set from '''<시작 UTC>'''`·`\set to '''<끝 UTC>'''`를 붙인 사본을 ConfigMap으로 넣어 실행한다. 관리자 계정(리포트·테마)과 프리미엄 구독 자녀는 #384와 같은 승인 절차로 만든다.

**#613 모델 새 버전 등록 (운영 관리자 화면, SERVICE_OPS)**
1. 선행: scoring·ai가 새 main 이미지인지(#588 이후) 확인
2. `GET /admin/model-versions?kind=MODEL`로 현재 행·`artifactUri`·revision 기록(복귀 기준)
3. 사전 검사 `POST /admin/models/preflight`: `artifactUri`는 `models/m2-klue-essay/3.1-1112b/`·`models/m2-klue-narrative/3.0-1112b/`, 파일 6개 해시는 `metadata/1112b` manifest 값 → `PASS` 확인
4. 등록: `(kind,name,version)`이 UNIQUE이고 이미 활성화된 버전은 다시 활성화할 수 없으므로(409) **새 버전 문자열** `3.1-1112b`·`3.0-1112b`로 등록
5. 승인·활성화: 논술 scope는 초5·초6(11/17 결정), 서술은 기존 scope 그대로
6. scoring `/internal/versions`에서 새 revision 로딩, 서술·논술 요청 1건씩 새 경계 확인. 복귀는 `rollback`으로 이전 버전

**#493 확인**: 위 3번 사전 검사가 실제 scoring Pod 자격 증명(Pod Identity)으로 활성 경로 `3.1/`·`3.0/`과 새 경로 둘 다 `PASS`이면 남은 AWS 항목이 끝난다. `CHECKSUM_UNAVAILABLE`이 나오면 해당 객체를 `put-object --checksum-sha256` 단일 PUT으로 다시 올린다.

### 9.11.5 당일 순서

예상 시간은 처음 실행하는 절차의 추정이다. 실제 시간을 옆에 적는다. ★는 실행 전 동섭 님 승인 지점이다.

| # | 단계 | 명령·방법 | 확인 | 예상 |
|---|---|---|---|---|
| 0 | 선행(전날까지) | #537 병합 → develop→main 병합 SHA 확정. migration 이미지: cd-release에 migration 단계가 들어가면 그것으로, 아니면 새 main으로 core-migrate·learning-migrate 이미지 수동 빌드·ECR 푸시 후 `migrations/*.json` digest·revision PR. 팀 공지 | main SHA·digest 3개 기록 | — |
| 1 | 읽기 점검 | `demo_stack.py plan` | 9.11.1과 같은지(MISSING 4, DIFF 2) | 2분 |
| 2★ | NAT·IAM 생성 | `demo_stack.py apply --confirm-account <계정>` → `aws ec2 replace-route --route-table-id <private 2개> --destination-cidr-block 0.0.0.0/0 --nat-gateway-id <새 NAT>` | `plan`에서 nat·route·IAM 2개 OK(EKS만 MISSING) | 10분 |
| 3★ | RDS 시작 | `aws rds start-db-instance` → `wait db-instance-available` | endpoint·`rds.force_ssl`·백업 7일. 11/20 자동 시작 뒤라면 이미 available | 10분 |
| 4★ | 클러스터 | `render-eksctl --operator-cidr <IP>/32 --out <밖>` → `eksctl create cluster -f <파일>` | 노드그룹 2개(2a·2b 1대씩 platform), add-on 7개, Pod Identity 10개, access entry가 백업(`access-entries.json`)과 같은 권한 | 30~40분 |
| 5★ | RDS SG | `apply --after-eksctl` → 옛 SG `sg-086c7c83b3638da59` 규칙·SG 정리 | 새 SG에서 5432 허용 | 5분 |
| 6 | 플랫폼 | gp3·namespace·ESO 2.14.0·LB Controller 1.14.1·`rds-ca`·ExternalSecret(현재 파일)·platform-data·Karpenter 1.15.1 + NodePool·EC2NodeClass(`karpenter.json` 대조) | ESO Ready, Secret 키가 서비스별 키, `ai-provider-credentials`에 `OPENAI_API_KEY`(값 미출력. #747 뒤 RunPod 키 2개는 빠짐), RabbitMQ 서비스별 계정 5개, NodePool limits CPU 4·16Gi | 30분 |
| 7 | DB 상태 | demo-db-oneoff(core 앱 계정)로 `SHOW max_connections`, `model_version` 행·활성 상태 조회. 앱 계정은 migration 이력 테이블 권한이 없으므로 적용 번호는 8단계 Job 로그로 본다 | 9.11.2 연결 판단, #613 등록 전 기준 | 10분 |
| 8★ | migration | 기본 거부용 정책 2개 → core·learning·report migration Job(9.11.1 2·3번). cd-release에 migration 단계가 들어갔으면 그 단계로 실행. **11/17 실행에서 빠짐: 그 전에 `demo_stack.py rds-bootstrap --execute`(learning V14 `vector` 확장), 뒤에 한 번 더(9.16)** | Job complete, 로그의 시작·끝 schema 버전(Flyway)·revision(Alembic) | 15분 |
| 9★ | 앱 배포 | cd-release(plan JSON, 승인 2명), 6개 서비스 | 앱 readiness, `app-default-deny` 1개, 정책 없는 Pod DNS 실패 | 30~40분 |
| 10 | 관측 | Secrets Manager 백업으로 관측 Secret 2개 생성(값 미출력) → observability | Grafana 로그인·datasource·경보 평가 | 15분 |
| 11★ | 진입 | `core-alb-network.json` + Ingress(origin 헤더 Git 밖 주입) → 새 ALB DNS로 CloudFront `/api/*` origin 변경 | prefix list 제한, CloudFront 배포 완료 | 20분 |
| 12 | 흐름 확인 | 로그인 → 학습 제출 → 리포트 조회, 테마 초안 1건(자산 버킷·Veo, #652·#600), 설명 단계 상태, 리포트 AI 요약(#747부터 SageMaker IC. 창 밖이면 사본 0이라 503이 정상, 창 안 503이면 IC 상태·ai `REPORT_LLM_*` env 확인) | 걸린 시간·실패 항목을 #601에 기록 | 20분 |
| 13 | #613·#493 | 9.11.4 | 사전 검사 PASS, 새 revision | 30분 |
| 14★ | #384 | 공지 → 계정 4개 → 스텁 → 단계별 k6 → 축소 관찰 → 원복 | Karpenter 노드 0대로 끝남 | 2~3시간 |
| 15 | #630 | 9.11.4(실제 LLM, 부하 없는 시간) | 표본·비용 기록 | 1.5시간 |
| 16★ | #629 | 9.11.3(재가동 1시간 뒤부터 가능) | A 있음·B 없음, RPO·RTO | 1시간 |
| 17★ | 내리기 | 시험 데이터 정리 범위 확인 → `demo_stack.py pause --execute` 또는 클러스터·NAT 삭제(9.5 방식) | RDS stopped, 실행 중 EC2 0대, 정지 시각과 7일 뒤 자동 시작 기록 | 1시간 |

0~12는 한 번에 약 4시간이다. 13~16은 하루 안에 모두 끝내지 않아도 되지만, 켜 둔 동안 고정비(EKS·NAT·노드 4대·RDS)가 쌓이므로 이틀을 넘기지 않는다.

## 9.12 RDS PITR 복구 시험 (#629, 2026-11-18)

NFR-DAT-05(RPO 5분·RTO 4시간, 복구 시험 기록)를 A 계정 운영 RDS에서 처음 실행했다. 원본 `sagomungchi-demo-db`는 수정·재시작하지 않았고, 새 인스턴스로 복원해 확인한 뒤 바로 삭제했다. 절차는 9.11.3을 따랐다.

### 9.12.1 조건

| 항목 | 값 |
|---|---|
| 복원 시점 T | 2026-11-18 09:30:00 KST(00:30:00 UTC). 재가동(11/17 15:43) 뒤 17시간이 지난 시점이고, #384 부하 시험 시작(첫 시험 계정 가입 09:37:26) 전이다 |
| 표지 A(T 이전) | learning `answer` 1건(11/17 18:29:49 KST 제출, ID 앞 8자리 `429717b2`) |
| 표지 B(T 이후) | core `user_account`의 #384 시험 계정 10개(`load2` 접두사, 09:37:26~09:48:03 KST 가입) |
| 복원본 | `sagomungchi-demo-db-pitr629`, db.t4g.micro(가장 작은 사양), 원본과 같은 서브넷 그룹·RDS SG, 비공개, Single-AZ(2b), 태그 `purpose=pitr-test-629` |
| 확인 방법 | 클러스터 안 임시 Pod(`demo-db-oneoff` 정책 라벨, 앱 계정 Secret·RDS CA 사용)로 원본과 복원본에 같은 SQL을 실행. 건수·md5·짧은 ID만 출력하고 학생 원문·개인정보는 출력하지 않음. Pod·ConfigMap은 실행 직후 삭제 |

### 9.12.2 시간 기록 (KST)

| 시각 | 단계 |
|---|---|
| 09:46:14 | 요청 직전 원본 `LatestRestorableTime` |
| 09:51:37 | `restore-db-instance-to-point-in-time` 요청 |
| 09:54:20 | 인스턴스 생성 시각(`InstanceCreateTime`) |
| 09:58:31 | RDS 이벤트 "Restored from DB instance sagomungchi-demo-db to 2026-11-18 00:30:00.0" |
| 09:59:07 | 재시작 |
| 10:01:00~10:09:43 | 복원본 첫 자동 백업(보존 기간 7일을 원본에서 이어받음) |
| 10:10:45 | `available`(30초 간격 조회라 ±30초) |
| 10:11:08 | 표지·행 수·스키마 대조 끝 |
| 10:11:15 | 삭제 요청(`--skip-final-snapshot --delete-automated-backups`) |
| 10:12:50 | 삭제 완료(`wait db-instance-deleted`, 이후 `DBInstanceNotFound`) |
| 10:15:12 | 복원본 자동 스냅샷 `rds:sagomungchi-demo-db-pitr629-…`이 사라짐(삭제 뒤 약 2분 남아 있었음). 남은 자동 백업은 원본 것 1개, `purpose=pitr-test-629` 태그 자원 0개, RDS SG 규칙 변경 없음, 임시 Pod·ConfigMap 0개 |

- **RTO**: 요청→`available` **19분 8초**, 요청→확인 끝 19분 31초. 목표 4시간 안이다. 이 중 약 9분은 복원본 첫 자동 백업이라, 데이터 복원 자체는 요청 뒤 약 7분(09:58:31 이벤트)에 끝났다
- **RPO**: 요청 시각 − `LatestRestorableTime` = **5분 23초**. 같은 날 09:49:51에 본 값은 3분 37초였다. RDS는 트랜잭션 로그를 약 5분마다 올리므로 이 간격은 0~5분대에서 오르내리고, 이번 측정은 목표 5분을 23초 넘었다(9.12.4)

### 9.12.3 대조 결과

| 대상 | 원본(T 이전으로 거름) | 복원본 | 판정 |
|---|---|---|---|
| 표지 A 답변 | 1 | 1 | 있음 |
| 표지 B 시험 계정 | 10(전체) | 0 | 없음 |
| 계정(T 이전 / 전체) | 6 / 16 | 6 / 6 | 같음 |
| 학생 | 36 | 6 | T 이후 생긴 30명 없음 |
| 답변(T 이전) 건수·md5(`id:version`) | 2,814 · 같음 | 2,814 · 같음 | 같음 |
| 판정 상태(T 이전 답변) | DONE 2,812·PENDING 2 | 같음 | 같음 |
| 시도·판정·미션·테마 초안 | 2,812 · 2,814 · 25 · 8 | 같음 | 같음 |
| 분석 대화 메시지·`llm_usage`(T 이전) | 562 · 7,410 | 같음 | 같음 |
| 구독(T 이전 상태별) | ACTIVE 1·CANCELED 1 | 같음 | 같음 |
| 주간 리포트·항목 | 5 · 25 | 같음 | 같음 |
| 근거 연결(core `message_evidence`, report `report_item_evidence`)·결제 `payment` | 0 · 0 · 0 | 0 · 0 · 0 | 행 없음(9.12.4) |
| 근거가 가리키는 답변 중 learning에 없는 수 | 0/0 | 0/0 | 행 없음 |
| 스키마 | core V51 있음·V52 없음, learning V21 있음, report `20261110_08` 제약 있음 | 같음 | 같음 |
| 열 지문(`information_schema.columns` md5) | core 535·learning 352·report 66열 | 세 DB 모두 같음 | 같음 |

- T 직전 가장 가까운 쓰기는 테마 초안(09:01:52), T 직후 가장 가까운 쓰기는 시험 계정 가입(09:37:26)이다. 경계 정밀도는 이 36분 안에서만 확인했다
- 앱 계정은 `flyway_schema_history`·`alembic_version` 읽기 권한이 없어(permission denied) Flyway·Alembic 버전 번호는 직접 읽지 못했다. 마지막으로 적용된 migration이 만든 열·제약과 열 지문으로 대신했다

### 9.12.4 한계와 남은 것

- **RPO 5분 경계**: 측정 1회에서 5분 23초였다. PITR만으로는 "최대 약 5분 + 업로드 지연"이 실제 값이라, NFR-DAT-05의 RPO 5분을 지키려면 목표를 "약 5분(로그 업로드 주기)"으로 적거나 별도 수단(읽기 복제본 등)이 필요하다. 설계 문구 변경은 담당자 결정 사항이라 이번에 바꾸지 않았다
- **근거 연결·결제 정합성**: AWS 데모 DB에 `message_evidence`·`report_item_evidence`·`payment` 행이 0건이라 대조 쿼리는 실행됐지만 실데이터로 확인한 것은 아니다. PG 상태 별도 대조도 결제가 없어 하지 않았다
- **RTO 범위**: 데이터가 작다(답변 2,814건, gp3 20 GiB). 앱 Secret의 DB 주소를 복원본으로 바꾸고 재배포하는 전환 시간은 재지 않았다
- 복원본은 가장 작은 사양(t4g.micro)이라 원본(t4g.small)과 사양이 다르다.

## 9.13 리포트 Gemma CPU·GPU 서빙 비교와 S3 반입 (#743·#745, 2026-11-18)

에픽 #742에서 리포트 Gemma(26B-A4B QAT + LoRA r16)를 RunPod에서 클러스터 안 `sllm-server`로 옮기기로 했다. 그 전에 CPU와 GPU를 AWS A 계정의 임시 EC2에서 같은 입력으로 쟀다. 수치 원본은 [`ml/sllm/results/serving-compare-20261118.json`](../../ml/sllm/results/serving-compare-20261118.json)에 있고, 측정 스크립트는 [`ml/sllm/scripts/serving/`](../../ml/sllm/scripts/serving/)에 있다.

### 9.13.1 결정 (2026-11-18 팀 방향)

**SageMaker 실시간 엔드포인트(GPU) + 0대 축소**로 간다. 아래 측정에서는 CPU가 변경량이 가장 적었다. 그래도 GPU 생성 속도(상세 1건 약 16초)를 쓰면서, 노드·드라이버·이미지를 EKS 안에서 직접 관리하지 않는 쪽을 골랐다. 실제로 되는지는 새 이슈에서 검증한다.

| 항목 | 내용 |
|---|---|
| 위치 | 같은 AWS 계정의 SageMaker 엔드포인트(VPC 안). 학생 글이 AWS 밖으로 나가지 않는 원칙(#473)을 유지한다. 클러스터 밖이라 architecture 7장 "클러스터 안 GPU 두지 않음"(#725)은 바꾸지 않아도 된다. 대신 4.4의 `sllm-server`(클러스터 안 llama.cpp) 구조는 바뀐다(#744) |
| 모델 | S3 `base-awq/` + `adapter/`(9.13.6) 그대로. vLLM 계열 컨테이너(SageMaker LMI)에 LoRA를 붙인다 |
| 할당량 (2026-11-18 조회) | 서울 `ml.g6.xlarge for endpoint usage` 2, `ml.g5.xlarge` 4, `ml.g6e.xlarge` 2. 증설 요청은 필요 없다 |
| 요금 (서울, 시간당) | `ml.g6.xlarge` $1.385(같은 EC2 $0.990보다 약 40% 비쌈), `ml.g5.xlarge` $1.732, `ml.g6e.xlarge` $3.200. 창(130분) 기준 월 약 $13(`ml.g6.xlarge`) |
| 콜드 스타트 | 0대에서 깨어나면 인스턴스 준비 + 모델 17GB 적재(EC2 실측 기동 224초 + 이미지)로 몇 분 걸린다. RunPod의 191~315초 문제가 그대로 남으므로, 창 시작 전 예약 확장으로 1대를 미리 켜는 방식을 검증한다 |
| 확인할 것 | Gemma 4를 지원하는 LMI·vLLM 버전, `ml.g6.xlarge`(L4, 호스트 16GiB)에서 9.13.5의 메모리 옵션이 그대로 통하는지(안 되면 `ml.g6e.xlarge`), 실제 콜드 시간, GPU 재고 부족 때의 동작, ai 호출 방식(`InvokeEndpoint`·SigV4) |
| 하위 이슈 영향 | #744 문서(4.4·7장 결정 줄), #745 레지스트리 등록과 쓰지 않을 `base-gguf/`·`adapter-gguf/` 정리, #746 범위를 EKS NodePool에서 SageMaker 엔드포인트·예약 확장·IAM으로 변경, #747 ai 클라이언트를 RunPod에서 SageMaker로 변경 |
| 검증 결과 (#746) | 9.13.9. 컨테이너는 vLLM SageMaker DLC, 인스턴스는 `ml.g6e.xlarge`로 바뀌었다 |

### 9.13.2 측정 기준 검토안 (채택하지 않음)

측정만 놓고 본 검토안은 클러스터 안 CPU(`c7i.4xlarge`, llama.cpp `llama-server` + 공식 QAT Q4_0 GGUF·LoRA GGUF, `--jinja --reasoning off`, 30명 배치 약 70~75분, 창 기준 월 약 $7.6)였다. 기존 `sllm-server` 구조를 그대로 쓸 수 있었지만 9.13.1 결정(SageMaker GPU)으로 채택하지 않았다. 측정값은 9.13.4.

### 9.13.3 측정 조건

| 항목 | 값 |
|---|---|
| 입력 | ai-service 실제 프롬프트(`report@2` 서술, `report-explanation@3` 상세)에 가상 데이터만 넣음(`gen_prompts.py`). 서술 1,137토큰·최대 2,048, 상세 1,360토큰·최대 4,096, `json_schema` strict, temperature 0 |
| 자원 | 임시 VPC(기존 EKS VPC 밖)의 퍼블릭 서브넷, EC2 2대(SSH는 측정 PC IP만 허용), S3 `explanation/*`만 쓸 수 있는 임시 IAM 역할 |
| 시각 | 2026-11-18 09:52~11:10 KST |
| GPU | g6.xlarge(L4), DLAMI Ubuntu 24.04, vLLM 0.34.0. LoRA는 `explain` 이름으로 붙임 |
| CPU | c7i.4xlarge(Xeon 8488C, AVX-512·AMX), llama.cpp 52975342 직접 빌드 |
| 기동 시간 | 페이지 캐시를 비운 뒤 서버 시작부터 `/health` 200까지 |

### 9.13.4 결과

| 항목 | CPU c7i.4xlarge | GPU g6.xlarge |
|---|---|---|
| 시간당 요금 | $0.806 | $0.990 |
| 서버 기동(모델 적재 포함) | 53초 | 224초(가중치 54초 + torch.compile 48초 + CUDA graph 등). 컴파일 캐시가 있으면 148초(업로드와 겹쳐 잰 값) |
| 그 밖의 콜드 요소 | 모델 14.4GB 받기(HF에서 35초) | vLLM 이미지 36.3GB pull 133초, 모델 17.2GB 받기(HF에서 72초) |
| 메모리 | RSS 28GiB(mmap 포함), 사용 15GiB | VRAM 20.3GiB / 22.0GiB, 호스트 8GiB |
| 생성 속도(1건, LoRA) | 18.4 tok/s | 49 tok/s(LoRA 없이 54) |
| 리포트 서술 1건 | 23.6초(캐시 없음) | 6.2초(30명 배치 p50) |
| 상세 설명 1건 | 50.2초(캐시 없음) | 16.4초(30명 배치 p50, p95 21.2초) |
| 30명 배치(120요청) | 약 70~75분(동시 2, 추정) | 10~15분(동시 4·8, 실측 3회) |
| 최대 토큰까지 반복 생성 | 38건 중 2건(상세) | 120건 중 9·19·19건(모두 상세) |
| `checks.py` | 상세 3/3 통과, 서술 JSON 3/3 | 상세 3/3 통과, 서술 3건 중 2건이 73자에서 끊김 |

- CPU `llama-bench`(LoRA 없음)의 생성 속도는 4·8·16스레드에서 11.2·20.0·24.1 tok/s다. 8스레드인 `m7i.2xlarge`(32GiB, $0.50)도 후보이지만 서버로는 재지 않았다
- CPU 동시 2는 처리량이 19.8 tok/s로 동시 1(18.4)과 거의 같고, 슬롯당 속도는 11 tok/s로 떨어진다
- CPU 30명 배치는 #384 부하 시험에 계정을 넘기려고 22요청에서 멈췄다. 70~75분은 4명 배치(583초)와 22요청 기록으로 추정한 값이다

### 9.13.5 발견

- **반복 생성**: 상세 설명이 `max_tokens` 4096까지 반복하는 경우가 GPU에서 8~21%, CPU에서 약 5% 나왔다. 서비스에서는 `finish_reason=length`가 `LLM_INVALID_OUTPUT`이 되어 설명 없이 발행된다. CPU에서는 이런 1건이 약 400초를 점유해, 지금 상세 마감(305초)을 넘는다. #747에서 상세 `max_tokens`(정상 출력은 520~710토큰)와 마감을 함께 조정해야 한다
- **L4 메모리 한계**: 17.2GB 단일 safetensors는 16GiB 호스트에서 mmap 실패(ENOMEM)로 vLLM이 기동하지 않았다. 4조각으로 나누자 기동했다. VRAM은 bf16 KV로는 8192 길이 1건분도 남지 않아, `--kv-cache-dtype fp8 --max-num-seqs 8 --max-num-batched-tokens 2560 --gpu-memory-utilization 0.97`와 멀티모달 0개 설정이 필요했다. 그래도 KV는 12,653토큰(8192 기준 1.54건)뿐이다
- **생각 모드**: llama.cpp `--jinja`의 기본값에서는 Gemma 4가 생각(reasoning)부터 출력해, 서술 1건이 2,048토큰을 모두 쓰고 본문이 비었다. `--reasoning off`로 해결했다. vLLM은 기본값으로도 생각 출력이 없었다
- **운영 호출 모델 이름**: ai-service `REPORT_GEMMA_MODEL` 기본값과 prod 설정은 기반 이름 `gemma-4-26b-a4b-it-qat-awq-int4`다. vLLM에서 이 이름으로 부르면 LoRA가 붙지 않는다(LoRA는 `explain`). 같은 입력에서 두 이름의 출력이 달랐다. 지금 RunPod 호출에 LoRA가 적용되는지 확인이 필요하다(#747). llama.cpp `--lora`는 모델 이름과 상관없이 모든 요청에 붙는다

### 9.13.6 S3 반입 (#745)

경로는 `s3://sagomungchi-demo-<계정>-models/explanation/gemma4-26b-a4b-lora-20261118/` 아래 18개 객체(31.7GB)다. 파일별 크기·sha256은 결과 JSON의 `s3`에 있다.

| 하위 경로 | 내용 |
|---|---|
| `adapter/` | PEFT 원본 `adapter_model.safetensors`·`adapter_config.json`(로컬 사본, `ml/sllm/README.md` 해시와 같음) |
| `adapter-gguf/` | `explain-lora-f16.gguf`(CPU용 변환본, 230 텐서) |
| `base-awq/` | AWQ 기반 모델 설정·토크나이저와 `model-0000{1..4}-of-00004.safetensors` + index(GPU용) |
| `base-gguf/` | 공식 QAT Q4_0 GGUF를 `llama-gguf-split`으로 나눈 4개 파일(CPU용, 1번 파일로 기동) |

- 모든 객체를 `PutObject` 1회 + `ChecksumSHA256`으로 올렸고, HEAD에서 `ChecksumType=FULL_OBJECT`와 값이 일치함을 확인했다(`upload.py`). 덮어쓰기는 `If-None-Match: *`로 막았다
- **5GB 초과 파일**: S3는 multipart 업로드에 SHA-256 `FULL_OBJECT`를 허용하지 않는다(2026-11-18 실제 요청이 `InvalidRequest`). multipart SHA-256은 COMPOSITE뿐이라 #368·#493 원칙(전체 SHA-256만 인정)에 맞지 않는다. 그래서 형식이 지원하는 방법으로 파일을 나눴다. safetensors는 텐서 바이트를 그대로 옮겨 4조각으로 나누고, 원본과 35,743개 텐서의 dtype·shape·sha256이 같음을 대조했다(`reshard.py`·`verify_shards.py`). GGUF는 `llama-gguf-split`으로 나눴다. 원본 단일 파일의 sha256은 HF LFS 값과 같고(AWQ `c0b6bbe9…`, GGUF `3eca3b8f…`), 이 값도 결과 JSON에 남겼다
- 대안으로 원본을 바이트 단위로 잘라 올리고 받을 때 이어 붙이는 방법, multipart CRC64 FULL_OBJECT + 메타데이터 sha256 방법도 있었다. 앞의 것은 서버가 그대로 읽지 못하고, 뒤의 것은 #368 원칙(CRC·메타데이터 불인정)에 맞지 않아 쓰지 않았다
- `sllm-server` initContainer는 지금 `MODEL_KEY` 파일 1개와 `MODEL_SHA256` 1개만 받는다. 여러 파일과 LoRA를 받도록 바꾸는 일은 #746 범위다
- 결정하지 않은 형식 쪽(CPU를 고르면 `base-awq/`, GPU를 고르면 `base-gguf/`·`adapter-gguf/`)은 결정 뒤 지울지 정한다. 보관 비용은 31.7GB에 월 약 $0.8다
- core 모델 레지스트리 `report-explanation` 등록은 반입 때 하지 않았다. 형식 결정(GPU)과 #746 구성 뒤인 2026-11-18에 A 계정에서 `gemma4-26b-a4b-lora-20261118-r2`로 등록·활성화했다. `artifactFiles`는 `manifest.json`의 13개 파일이고, 범위는 `explanation/grade-{5,6}/narrative`·`grade-{4,5,6}/essay`다. 자세한 내용은 [`ml/sllm/README.md`](../../ml/sllm/README.md#승인-목록과-레지스트리-등록-2026-11-18)에 있다

### 9.13.7 임시 자원과 정리

| 자원 | 이름·종류 | 상태 |
|---|---|---|
| VPC·서브넷·IGW·라우트 테이블 | `sagomungchi-tmp-gemma-bench`, 10.99.0.0/24, 2a | 삭제 |
| 보안 그룹 | 같은 이름, 22/tcp를 측정 PC IP만 허용 | 삭제 |
| 키 페어 | 같은 이름, ed25519 | 삭제(로컬 개인 키도 지움) |
| IAM 역할·인스턴스 프로필 | 같은 이름, S3 `explanation/*` Put·Get만 허용 | 삭제 |
| EC2 | g6.xlarge·c7i.4xlarge 각 1대(gp3 200·120GB, 종료 시 삭제) | 종료, 볼륨 없음 확인 |

2026-11-18 11:12 KST에 태그 `Purpose=issue-743-745-temp` 기준 인스턴스·볼륨·VPC·IGW와 이름 기준 보안 그룹·키 페어·IAM이 모두 0개이고, `explanation/` 아래 남은 multipart 업로드가 0건임을 확인했다. EKS·RDS 자원은 건드리지 않았다. 측정 비용은 약 $2.5(EC2 2대 약 1.3시간과 EBS)다.

### 9.13.8 한계와 남은 것

- 입력이 고정 가상 글 1편과 서술 1건이라 같은 프롬프트가 반복된다. 그래서 2회째부터는 접두 캐시로 입력 처리 시간이 줄었다. 표의 1건 값은 첫 실행(캐시 없음)이나 배치 p50으로 적었다. 글 길이가 다른 여러 입력과 RunPod 출력 비교(`explanation_eval.py`)는 하지 않았다
- 품질은 `checks.py` 통과와 JSON 형식만 봤다. CPU(GGUF)와 GPU(AWQ) 출력의 의미 차이는 사람 검토가 필요하다
- EKS 안 기동 시간(노드 준비, S3 initContainer 내려받기)은 재지 않았다
- 학습 기준 모델 확인: 어댑터의 `base_model_name_or_path`는 `/workspace/models/gemma-4-26b-qat`(로컬 경로)라 정확한 원본 저장소·revision을 알 수 없다. 구조(30층, hidden 2816, 전역 주의 층의 K=V 공유로 `v_proj` 25개)는 두 기반 모델과 모두 맞는다. kim-4480에게 확인을 요청했다
- 다음 순서: SageMaker 검증 이슈(LMI 버전, LoRA, 콜드 스타트, 예약 확장, 재고 부족 동작) → #744 문서 → #746 SageMaker 엔드포인트·IAM → 레지스트리 등록 → #747 호출 전환(SageMaker 클라이언트, 모델 이름, `max_tokens`·마감)

### 9.13.9 SageMaker 검증과 엔드포인트 구성 (#746, 2026-11-18)

9.13.1 결정의 "확인할 것"을 AWS A 계정에서 실제로 실행해 확인했다. 입력은 9.13.3과 같은 가상 글·가상 서술 데이터만 썼다(`gen_prompts.py`). 생성 원문은 저장소에 넣지 않았다. 구성은 [`infrastructure/aws/sagemaker_explanation.py`](../../infrastructure/aws/sagemaker_explanation.py)와 [`sagemaker/explanation-endpoint.json`](../../infrastructure/aws/sagemaker/explanation-endpoint.json)으로 다시 만들 수 있다(B 계정 재현용). 측정 스크립트는 [`ml/sllm/scripts/serving/sagemaker_bench.py`](../../ml/sllm/scripts/serving/sagemaker_bench.py)다.

#### 결정과 바뀐 점

| 항목 | 9.13.1 계획 | 실행 결과·결정 |
|---|---|---|
| 컨테이너 | SageMaker LMI(DJL) | AWS vLLM SageMaker DLC `vllm:server-sagemaker-cuda-v2.8.2`(vLLM 0.33.0+amzn2023, `Gemma4ForConditionalGeneration` 인식). LMI 최신(`0.38.0-lmi30`)은 쓰지 않았다. `SM_VLLM_*` 환경 변수가 vLLM 인자가 된다(#746 D4 승인) |
| 인스턴스 | `ml.g6.xlarge`(L4), 안 되면 `ml.g6e.xlarge` | **`ml.g6e.xlarge`**(L40S 48GB, 호스트 32GiB). g6.xlarge에서는 인퍼런스 컴포넌트(IC) 배치가 실패했다(아래). 시간당 $3.2, 창 기준 월 약 $30(#746 D5 승인) |
| 메모리 옵션 | 9.13.5의 fp8 KV 등 | g6.xlarge에서는 컨테이너가 뜨기 전에 실패해 확인하지 못했다. g6e에서는 fp8 KV 없이(bf16) 기동한다. `--max-num-batched-tokens 2560`도 필요 없다 |
| 모델 데이터 | `base-awq/` + `adapter/` | `ModelDataSource`(S3 경로, 압축 없음)로 `base-awq/`를 `/opt/ml/model`에 받는다. LoRA는 어댑터 IC(`BaseInferenceComponentName`)로 붙인다 |
| 호출 이름 | 미정 | 기반: IC `sagomungchi-demo-explanation-ic`. LoRA: 어댑터 IC `sagomungchi-demo-explanation-explain`. **요청 본문의 `model` 값으로는 LoRA가 붙지 않는다**(아래) |
| 해시 확인 | #745 방안 | 배포 전 대조만 함(#746 D1). 경로 잠금·적재 때 검사는 #777(9.17, A 계정 검증 완료·B 적용 예정) |

#### 인퍼런스 컴포넌트 배치 (메모리 예약)

IC의 `ComputeResourceRequirements.MinMemoryRequiredInMb`에 따라 결과가 갈렸다(가속기 1개 공통).

| 인스턴스 | 예약 | 결과 |
|---|---|---|
| ml.g6.xlarge (16GiB) | 10240·8192MB | 32초 만에 Failed: "not enough hardware resources" |
| ml.g6.xlarge | 2048MB | 47초 만에 Failed: "not enough memory available". 컨테이너 로그가 생기지 않았다(뜨기 전 실패) |
| ml.g6e.xlarge (32GiB) | 16384·8192MB | "not enough hardware resources" |
| ml.g6e.xlarge | **4096MB** | 배치 성공, InService |

- 호스트 메모리에서 SageMaker가 남기는 몫이 커서 예약 가능한 값이 작다. g6e에서 vLLM이 본 가용 RAM은 23.25GiB, 체크포인트는 16.01GiB였다. g6.xlarge에서 2048MB도 실패한 것은 체크포인트(16GiB)가 호스트에 들어가지 않기 때문으로 보인다. 원인을 AWS 문서로 확인하지는 못했다
- IC가 붙을 엔드포인트는 인스턴스 종류를 `UpdateEndpoint`로 바꿀 수 없다(ValidationException "Cannot update endpoint with a different instance type…"). 엔드포인트를 지우고 다시 만들어야 하며, 스크립트가 그렇게 처리한다
- 생성 중(Creating)인 IC는 지울 수 없다. 서버 인자 오류로 재시작을 반복한 IC가 Failed가 되기까지 36분 걸렸다(기동 제한 1800초 설정). 그래서 제한을 1200초로 줄였다

#### LoRA 부착

- 정적 `--lora-modules explain=…`로 올린 LoRA는 요청 본문에 `"model": "explain"`을 넣어도 쓰이지 않았다. 응답 `model`은 기반 이름이었고 출력도 기반과 같았다. SageMaker 경로에서는 본문의 모델 이름이 아니라 어댑터 IC 이름으로 고른다
- 어댑터 IC를 만들면 SageMaker가 컨테이너의 `POST /adapters?name=…&src=…`를 부른다. 이 경로는 `VLLM_ALLOW_RUNTIME_LORA_UPDATING=true`일 때만 열린다. 없으면 404이고 호출이 실패한다. 설정 뒤에는 어댑터 IC가 몇 초 만에 InService가 되고, 응답 `model`이 어댑터 IC 이름으로 바뀌었다
- 빈 값 환경 변수(`SM_VLLM_ENABLE_LORA=""`)는 `__MAEVE_EMPTY_STRING_PLACEHOLDER__`로 바뀌어 위치 인자로 들어간다. `--enable-lora`는 켜지고 동작에는 지장이 없었다

#### 출력 문제: JSON 문자열 안 인용 부호

- `json_schema` 응답에서 모델이 글을 인용할 때 `\"` 대신 `"`를 쓰면 문자열이 거기서 닫힌다. 그 뒤 문법이 허용하는 공백(탭)을 `max_tokens`까지 반복한다(`finish_reason=length`). 같은 입력을 다시 보내 접두 캐시가 맞으면, 대신 각 칸이 "처음에는 "처럼 짧게 끊긴 채 끝났다(125토큰). 9.13.4의 반복 생성과 서술이 73자에서 끊긴 현상도 같은 원인으로 보인다
- vLLM `--structured-outputs-config '{"backend":"xgrammar","disable_any_whitespace":true}'`로 공백을 막아 보았다. 그러자 상세 설명이 20토큰 안팎의 빈 값이 되고 값 앞에 `": "`가 붙어 더 나빠졌다. 그래서 쓰지 않는다(`backend`를 빼면 서버가 기동하지 않는다)
- 해결은 프롬프트나 출력 형식 쪽이다(예: 인용은 「」로 쓰게 함). 이 부분은 #747 범위다

#### 기반 단독과 LoRA 비교 (#746 D2)

g6e, 모델 4판(최종 설정), 요청마다 system 앞에 무작위 표식을 붙여 접두 캐시를 피했다. 상세 `max_tokens` 1536, 서술 1024, 각 15회 순차 호출이다. 통과는 ai-service `checks.py` 규칙과 본문 200자 이상이다.

| 항목 | 기반 단독 | LoRA (`explain`) |
|---|---|---|
| 상세 `finish_reason=length` | **7/15** | 1/15 |
| 상세 JSON·규칙 통과 | 8/15 | 14/15 |
| 상세 지연 p50(정상 종료분) | 5.14초(597토큰) | 5.69초(568토큰) |
| 서술 통과 | 15/15 | 15/15 |
| 서술 지연 p50 | 2.23초 | 2.85초 |

- D2 기준 세 가지 중 JSON 통과율과 `length`는 LoRA가 낫다. 지연은 상세 약 11%, 서술 약 28% 늘어 "지연이 늘지 않음"을 만족하지 못한다
- **결정(2026-11-18, 동섭): LoRA(`explain`)를 쓴다.** 팀장이 #746 D2에 정한 기준(세 가지를 모두 만족할 때만 LoRA, 기본값은 기반 단독)과 다르게 정했다. 이유는 다음과 같다
  - 당시 단일 호출 계측에서 기반 단독은 상세 설명 15건 중 7건이 `max_tokens`까지 반복 생성되어 잘렸다. LoRA는 14/15건이 규칙을 통과했다. 현재 서비스는 같은 75초 안에서 최대 한 번 재생성하고, 유효한 상세 설명을 얻지 못하면 설명을 빼고 발행한다([ai 25](ai.md#25-리포트-상세-설명-재생성-850910-2026-11-23))
  - 늘어난 지연은 상세 p50 기준 약 0.5초(5.14초 → 5.69초)다. 리포트는 배치 작업이라 사용자가 기다리지 않는다. 최악 경우(동시 8건, 1536토큰)도 23.4초로 60초 제한 안이다
  - 따라서 호출 대상은 어댑터 IC `sagomungchi-demo-explanation-explain`이다(#747). 승인 목록과 레지스트리에는 `adapter/`를 포함한다(#745)
- 표본이 같은 가상 글 1편이고 15회뿐이다. 의미 품질은 보지 않았다
- 학습 담당(kim-4480) 확인(2026-11-18)
  - LoRA는 AWQ가 아니라 16비트 QAT 원본 `google/gemma-4-26B-A4B-it-qat-q4_0-unquantized`로 학습했다(`train_lora.py`, `load_in_4bit=False`). 위 비교는 AWQ 위에 얹은 결과라 학습 때와 기반이 다르다. 16비트 원본(약 52GB)은 g6e(48GB)에도 들어가지 않는다
  - LoRA는 "항목별 이유 한두 문장" 형식으로 학습됐고, 당시 비교에서는 3칸 JSON 장문(`report-explanation@3`)을 요청했다
  - RunPod 워커는 `LORA_MODULES`로 `explain`을 올렸지만, 요청 `model`이 `explain`일 때만 붙는다. 운영은 기반 이름으로 불러 지금까지 리포트에는 LoRA가 쓰이지 않았다. 바꾸려면 `REPORT_GEMMA_MODEL`(SageMaker에서는 호출 IC 이름)을 바꾼다(#747)
  - LoRA 정상 출력 토큰은 위 측정에서 p50 568토큰(기반 597토큰)이라 상세 `max_tokens` 1536(정상 최대 대비 약 2.2배)은 LoRA에도 맞다. 서술은 1024로 줄여도 된다(15/15 정상 종료)
- #599 낱말 챗봇은 sLLM이 아니라 외부 API로 구현할 예정이라 이 엔드포인트 범위에 들어가지 않는다

#### 60초 응답 제한 (#746 D3)

최악의 경우를 흉내 내려고 `response_format` 없이 `ignore_eos`로 1536토큰을 끝까지 생성하게 했다.

| 동시 요청 | 기반 최대 | LoRA 최대 |
|---|---|---|
| 1 | 12.3초 | 14.4초 |
| 4 | 17.8초 | — |
| 8(`--max-num-seqs` 상한) | 21.9초 | 23.4초 |

상세 `max_tokens` 1536은 동시 8건에서도 60초 안에 들어온다. 정상 상세 1건은 약 5초다(L4 EC2의 16.4초보다 빠름).

#### 콜드 시간과 예약 확장

시각을 당긴 시험 일정(Application Auto Scaling 예약 작업 `at(...)`, UTC)으로 축소와 확장을 한 번씩 확인했다(2026-11-18 KST).

| 단계 | 시각 | 경과 |
|---|---|---|
| 축소 예약(최소·최대 0) | 15:47 | — |
| IC 사본 0, 호출 즉시 실패 | 15:50 | +3분 |
| 관리형 인스턴스 축소로 인스턴스 0대 | 16:01 | +14분 |
| 확장 예약(최소·최대 1) | 16:10 | — |
| Auto Scaling 반영(사본 목표 1, 인스턴스 목표 1) | 16:11 | +1분 |
| 인스턴스 InService | 16:19:54 | +10분 |
| 컨테이너 시작(이미지 10.6GB·모델 17GB 받기 뒤) | 16:26:06 | +16분 |
| vLLM 준비(가중치 45초, torch.compile 44초, 엔진 초기화 102초) | 16:29:46 | +20분 |
| 기반 IC InService, 어댑터 적재(`POST /adapters` 200) | 16:30:23~31 | **+20.5분** |

- 깨어난 직후 기반·어댑터 IC 호출이 모두 성공했다. 어댑터 IC는 기반이 다시 뜨면 SageMaker가 자동으로 다시 적재한다
- 인스턴스가 이미 있을 때 IC만 새로 만드는 데는 약 9분(534~535초) 걸렸다
- 배치는 월 00:00에 시작한다(architecture 4.4). 23:50에 켜면 00:10에야 준비되므로 **확장을 일 23:30으로 당겼다**. 축소는 g6e에서 30명 배치를 재기 전까지 기존 창 끝(월 02:00)을 유지한다. 과금 구간은 약 23:31~02:14(축소 뒤 인스턴스 정리까지)로 주 약 2.7시간, 월 약 $35다. 30명 배치 실측 뒤 창 끝을 당기면 줄어든다
- GPU 재고 부족: 이번 시험에서는 `ml.g6e.xlarge` 확보가 바로 됐다(재고 부족 없음). 재고가 없을 때의 동작(확장이 계속 대기하는지, 오류가 나는지)은 확인하지 못했다. 창 시작 뒤 IC가 InService가 아니면 알리는 경보가 필요하다(#747과 함께)

#### 구성

| 자원 | 내용 |
|---|---|
| SageMaker 모델 | `sagomungchi-demo-explanation-<모델 버전>-r4`. 이미지는 위 DLC, `ModelDataSource` `base-awq/`, `VpcConfig` private 서브넷 2개 + 전용 SG. 환경 변수는 설정 JSON의 `environment`(LoRA를 쓰면 `adapterEnvironment` 추가) |
| 엔드포인트 설정 | `ml.g6e.xlarge`, `InitialInstanceCount` 1, `ManagedInstanceScaling` 0~1, `LEAST_OUTSTANDING_REQUESTS`, 실행 역할, `VpcConfig` |
| 엔드포인트 | `sagomungchi-demo-explanation` |
| IC | 기반 `sagomungchi-demo-explanation-ic`(GPU 1, 메모리 4096MB, 사본 1), 어댑터 `sagomungchi-demo-explanation-explain` |
| Auto Scaling | 대상 `inference-component/sagomungchi-demo-explanation-ic`, `DesiredCopyCount` 0~1. 예약: 일 23:30 KST 최소·최대 1, 월 02:00 최소·최대 0(`Asia/Seoul`). 시험 뒤 A 계정에 주간 일정으로 걸고, 비용을 줄이려고 사본을 0으로 내렸다 |
| IAM | 실행 역할 `sagomungchi-demo-sagemaker-explanation-role`: S3 `models/explanation/*` 읽기, `763104351884` `vllm` 이미지 받기, 로그·지표, VPC ENI. ai Pod Identity 역할(`sagomungchi-demo-ai-asset-s3-role`)에 inline `sagemaker:InvokeEndpoint`를 더했다(`demo-stack.json`·`iam/`) |
| 네트워크 | 엔드포인트 SG `sagomungchi-demo-sagemaker-explanation-sg`: ingress 없음, egress 443만. 모델은 S3 Gateway endpoint로 받는다. ai egress는 기존 공인 443 허용으로 `runtime.sagemaker` 공인 엔드포인트(NAT)에 나간다. NetworkPolicy는 바꾸지 않았다. 인터페이스 VPC 엔드포인트를 쓰면 사설 IP라 지금 ai 정책의 `except 10.0.0.0/8`에 막히므로 정책도 함께 고쳐야 한다 |

- **IC 단위 권한**: IC를 지정한 `InvokeEndpoint`는 엔드포인트 ARN이 아니라 `inference-component/<이름>` ARN으로 권한을 검사한다. 엔드포인트 ARN만 허용했을 때 ai Pod 호출이 AccessDenied였고, IC ARN 2개를 더하자 성공했다
- **ai Pod에서 호출**: 2026-11-18 15:43 KST, 실행 중인 ai Pod에서 `kubectl exec`로 boto3 `invoke_endpoint`를 불렀다. 기반·어댑터 IC 모두 200이었고, 호출 주체는 Pod Identity 역할이었다. Pod 재시작은 없었다(inline 정책 추가는 재시작 없이 반영). boto3 기본 리전이 잡히지 않아 `region_name`을 명시해야 했다(#747 클라이언트에서 설정으로 둘 것)
- **0대일 때 요청**: 사본이 0이면 `InvokeEndpoint`가 0.6초 만에 `ValidationError`("Inference Component has no capacity to process this request…")로 실패한다. 창 밖 요청을 어떻게 처리할지(설명 없이 발행, 또는 `NoCapacityInvocationFailures` 경보 + 단계 확장으로 깨운 뒤 재시도)는 #747과 함께 정한다. 이번에는 경보·단계 확장 정책을 만들지 않았다

#### 해시 대조 (#746 D1)

- `sagemaker_explanation.py manifest`가 결과 JSON의 `s3`에서 SageMaker가 읽는 경로(`base-awq/`, LoRA를 쓰면 `adapter/`)의 key·bytes·sha256을 `manifest.json`으로 만든다. `--upload`를 주면 `explanation/<버전>/manifest.json`에 `If-None-Match: *`와 SHA-256으로 한 번만 올린다
- `verify`(그리고 `apply` 직전)는 S3의 `manifest.json` 자체 FULL_OBJECT SHA-256을 확인한다. 그다음 경로 아래 객체 목록이 manifest와 정확히 같은지, 객체마다 FULL_OBJECT SHA-256·크기가 같은지 본다. 하나라도 다르면 모델을 만들지 않는다
- D2(LoRA 사용)에 따라 `manifest.json`(`base-awq/` 11개 + `adapter/` 2개, sha256 `adb264cb…`)을 `explanation/gemma4-26b-a4b-lora-20261118/manifest.json`에 올렸다(2026-11-18). HEAD의 FULL_OBJECT SHA-256이 본문 값과 같고, `verify`에서 13개 모두 일치했다. 같은 키에 다시 올리면 `PreconditionFailed`로 거부되는 것도 확인했다. 그 전 구성은 같은 내용의 로컬 manifest로 대조했다

#### 정리와 남은 것

- 기존 `sllm-server` 파일 정리안(팀 확인): `prod/sllm-server.json`·`prod/karpenter-nodepool-explanation.json`·`local/sllm-server.yaml`은 지운다. 함께 정리할 참조는 `prod/ai-service.json`·`local/ai-service.yaml`의 `EXPLANATION_BASE_URL`과 `sllm-server` egress, `argocd/local/apps/applicationset.yaml`, `policies/local/platform.yaml`, `charts/platform-data/values.yaml` 주석, prod·kind·app-service README다. ai 설정 쪽은 #747 호출 전환과 같은 PR에서 바꾸는 편이 안전하다. A 계정 클러스터에는 `sllm-server`가 배포되어 있지 않다. → #835(2026-11-20)에서 위 파일과 참조를 지웠다. local은 SageMaker 대역 `llm-stub` release로 바꿨다
- A 계정 SageMaker 자원(엔드포인트·설정·모델·IC·Auto Scaling 대상과 예약)은 11/19 A 종료 때 지운다(동섭 결정). S3 `explanation/` 가중치는 남긴다. 이번에는 ECR 이미지를 만들지 않았다(AWS DLC를 그대로 씀). B 계정은 `demo-stack.json`·`iam/`의 계정 번호를 바꾸고 `demo_stack.py apply`(IAM)·SG 생성 → `sagemaker_explanation.py manifest --upload`·`apply`·`schedule` 순서로 만든다. 가중치를 A 버킷에서 복사하면 `manifest.json`도 같이 복사되므로 `manifest --upload` 대신 `verify`로 확인한다([B 계정 전환 런북](../../infrastructure/aws/README.md#b-계정-전환-런북-809) 2·13단계)
- 남은 결정: 창 밖 요청 처리(#747 구현 뒤 [ai 24.5](ai.md#245-창-밖-요청-남은-결정)에 후보 정리), 창 끝 시각(g6e 30명 배치 실측 뒤), 인용 부호 문제(#747 프롬프트), GPU 재고 부족 동작(이번에는 재고 부족이 나지 않아 확인하지 못함)

## 9.14 AWS 데모 부하 시험 2차: HPA·Karpenter 확장·축소 (#384, 2026-11-18)

1차(9장)와 같은 도구(`evaluation/load/`)로 CloudFront → ALB → core에 단계별 부하를 주고, #211·#372로 켠 HPA·Karpenter가 실제로 늘고 주는지 쟀다. 운영 쓰기(계정·구독·LLM 스텁·pause Pod·정리)는 시작 전에 묶어서 담당자 승인을 받았다.

### 9.14.1 조건

| 항목 | 1차(11-05) | 2차(11-18) |
|---|---|---|
| 앱 | core replica 1, HPA·Karpenter 없음 | main `e3cb5084`. HPA core·learning·ai 최소 1·최대 3·CPU 70%(요청 대비), NodePool `application-burst`(t3.medium·t3.large, CPU 4·메모리 16Gi 상한, `consolidateAfter 5m`) |
| 노드 | — | 관리형 `application` t3.medium 2대 + `platform-observability` 2대(taint) |
| LLM | 클러스터 안 스텁(2.5~4초) | 같은 스텁 이미지. ai `OPENAI_BASE_URL`만 스텁으로 바꿈(임베딩은 이 값을 따르지 않아 실제 OpenAI 호출, 비용 무시할 수준) |
| 시험 계정 | 1개(자녀 3명, 학습 칸 15) | `prepare_accounts.py`로 14개(초5 자녀 3명씩 42명, 학습 칸 420). 자녀마다 결제 없는 시험 구독·보호자 공유 켬 |
| RDS | db.t4g.small | 같음. `max_connections` 181 → 앱이 쓸 수 있는 수 176(예약 5 제외) |
| 단계 | 50·100·200·300명 | 50~300명은 1차와 같은 중단 기준(API 오류 1%·p95 1초). 400~1000명은 한계 찾기로 기준을 p95 10초(1000명은 60초)·오류 5%로 올림(`P95_API_MS`·`MAX_API_ERROR_RATE`) |
| 범위 밖 | — | KEDA(AWS 미설치), NAT 실측(스텁이라 외부 호출이 거의 없음) |

연결 수(시작 전 계산): core 3×10 + learning 3×10 + report-api·worker 15+15 = 90, rolling update 여유 +20 → 110 ≤ 176. 풀 크기는 바꾸지 않았다. 시험 중 RDS 연결은 최대 68개였다.

### 9.14.2 단계별 결과

| 항목 | 50 | 100 | 200 | 300 | 400 | 600 | 800 | 1000 |
|---|---|---|---|---|---|---|---|---|
| API 오류 | 0/5,619 | 0/11,201 | 2/22,173 | 15/28,574 | 28/38,015 | 68/38,128 | 9/6,526 | 648/11,998 (5.4%) |
| API p95 (ms) | 109 | 136 | 238 | 1,042 | 1,984 | 4,935 | 10,674 | 15,123 |
| 판정 SSE p95 (초) | 7.8 | 7.6 | 7.7 | 9.6 | 13.2 | 22.7 | 33.8 | 50.7 |
| 학습 성공 | 297/297 | 596/596 | 1,196/1,197 | 1,513/1,513 | 1,980/1,981 | 1,519/1,521 | 203/203 | 274/428 |
| core 처리량 (req/s) | 28.7 | 55.3 | 107.9 | 160.0 | 151.7 | — | — | — |
| RDS CPU 최대 (%) | 13 | 24 | 58 | 72 | 98 | 98 | 90 | 97 |
| learning DB 풀 대기 최대 | 0 | 0 | 0 | 18 | 36 | — | — | 178(로그) |
| Pod 최대 core/learning/ai | 3/1/1 | 3/3/1 | 3/3/2 | 3/3/3 | 3/3/3 | 3/3/3 | 3/3/3 | 3/3/3 |
| Karpenter 노드 | 0 | 1 | 1 | 1 | 1 | 1 | 1 | 1 |
| 결과 | | | | p95 1초 넘어 끝 무렵 중단 | | | 1분 54초에 p95 10초 넘어 중단 | 2분 46초에 오류 5% 넘어 중단 |

- 요청 수는 400명(약 3.8만)과 600명(약 3.8만)이 같다. 400명부터 처리량이 늘지 않고 지연만 늘었다.
- 1000명 오류 대부분은 learning Hikari 풀 대기 30초 초과다(`Connection is not available, request timed out after 30000ms (total=10, active=10, waiting=178)`). 그래서 API p99가 30초 근처에 몰렸다. CloudFront 원본 읽기 제한(60초)·k6 제한(60초)에는 닿지 않았다.
- 400명 11:47 이후 JVM·DB 풀 지표는 수집되지 않았다(9.14.6). 표의 "—"는 그 때문이다. Pod 수·HPA CPU는 metrics-server 기준이라 끝까지 있다.
- Pod 재시작은 전 단계 0회, RabbitMQ 적체(ready)는 0, ALB ELB 5xx는 0이었다.

### 9.14.3 HPA 확장

| 시각(KST) | 사건 |
|---|---|
| 09:37 | 부하 전, 시험 계정 가입 중 core 1→3. 가입 비밀번호 해시 CPU에 새로 뜬 JVM의 기동 CPU(Pod당 0.6~1코어)가 평균에 더해져 바로 최대까지 감 |
| 11:13:03 | 50명 시작 27초 만에 core 1→3(181%). k6 `setup()`의 보호자 14·학생 42명 로그인(비밀번호·PIN 해시)이 몰린 순간이다. 정상 부하는 core 3개 합계 0.36~0.85코어였다 |
| 11:23:14 | 100명, learning 1→2(81%) |
| 11:24:59 | learning 2→3(136%) |
| 11:29:26 | 200명, ai 1→2(121%), 300명에서 3 |

- 먼저 바빠진 것은 core가 아니라 learning이었다. 1차는 core만 봤고 learning은 1개 고정이었다.
- ai는 LLM을 기다리는 서비스지만 스텁 지연 동안에도 요청 처리 CPU로 70%를 넘어 늘었다. CPU 기준 확장이 ai에도 걸린다는 것은 확인했지만, 늘어난 ai가 병목을 풀지는 않았다(병목은 DB).
- HPA 확장 중 오류는 늘지 않았다(100명 0건, 200명 2건).

### 9.14.4 Karpenter 확장·상한

자연 부하(100명, learning 2→3):

| 시각 | 사건 | 경과 |
|---|---|---|
| 11:24:59 | learning Pod Pending(`1 Too many pods, 2 Insufficient memory`) | 0 |
| 11:25:00 | NodeClaim `application-burst-…` 배정 | 1초 |
| 11:25:03 | 인스턴스 Launched(t3.medium, 2a) | 4초 |
| 11:25:21 | 노드 Registered | 22초 |
| 11:25:36 | Pod 배치 | 37초 |
| 11:25:40 | 노드 Ready | **41초** |
| 약 11:26:55 | learning Pod Ready(JVM 기동 포함) | **약 1분 55초** |

- 새 노드의 learning Pod는 400~1000명 동안 RDS·RabbitMQ로 정상 처리했다(학습 성공률 유지, 그 Pod 재시작 0). CloudFront → ALB → core → learning(새 노드) 경로가 그대로 동작했다.
- 관리형 노드 2대의 여유는 CPU보다 Pod 수(t3.medium 17개)와 메모리가 먼저 찼다. 6.의 예상과 같다.
- 600·800·1000명에서도 Karpenter 노드는 1대였다. HPA 최대 3에 막혀 더 늘 Pod가 없었기 때문이다.

상한(12:15, pause Pod 900m×5개를 Karpenter 노드에만 띄움):

- NodeClaim 2개를 동시에 만들고 39초 뒤 둘 다 Ready. DaemonSet 요청 때문에 t3.medium 한 대에 900m Pod가 1개씩만 들어갔다.
- 남은 3개는 Pending으로 남고 Karpenter는 `all available instance types exceed limits for nodepool`을 기록했다. 세 번째 노드는 만들지 않았다. 상한에서 멈추고 Pod가 기다리는 동작을 확인했다.
- pause Pod 삭제 뒤 두 노드도 빈 노드 정리로 사라졌다(9.14.5).

### 9.14.5 축소와 D안 삭제 순서

두 번 관찰했다. 두 번 모두 부하를 끝낸 뒤 10명 저부하(알림 SSE 유지)를 걸어 둔 채 Pod·노드가 줄어드는 것을 봤다.

| | 1회(1000명 중단 12:02:17 뒤) | 2회(200명 종료 12:29:47 뒤) |
|---|---|---|
| HPA 축소 | ai 12:07:04(3→2, Karpenter 노드 Pod)·12:07:49(→1), learning 12:07:49(3→1), core 12:08:50(3→1) | ai 12:31:52(3→2, Karpenter 노드 Pod)·12:34:22(→1), core 12:34:22(3→2)·12:34:37(→1), learning 12:34:22(3→2)·12:34:52(→1) |
| 지워진 learning Pod | Karpenter 노드 Pod + **가장 오래된 기본 Pod(관리형 노드, 18시간)** | Karpenter 노드 Pod → 관리형 노드 Pod(같은 노드에 core 2개와 함께 있던 것) |
| Karpenter 노드 빈 시각 → 정리 시작 → 삭제 | 12:07:50 → 12:13:10 → 12:13:37 | 12:34:22 → 12:39:54 → 12:40:33 |
| 부하 종료 → 노드 0대 | **11분 20초** | **10분 46초** |

- HPA 축소는 부하 종료 뒤 약 5분(기본 축소 안정화 5분)에 시작했다. 노드는 빈 뒤 `consolidateAfter 5m` + 약 20~30초에 정리가 시작돼 30초 안팎에 사라졌다.
- **D안 삭제 순서는 보장되지 않는다.** 2회는 의도대로 Karpenter 노드 Pod가 먼저 지워졌지만, 1회는 learning 3→1에서 가장 오래된 기본 Pod도 함께 지워지고 39분 된 Pod가 남았다. core는 세 번(09:37 확장 뒤 포함) 모두 같은 노드에 몰린 두 Pod가 지워졌다. ReplicaSet 축소는 생성 순서보다 "같은 노드에 같은 ReplicaSet Pod가 몇 개 있는지"를 먼저 보기 때문이다.
- 노드 정리 때 실행 중인 Pod를 내보내는 일은 없었다. HPA가 Pod를 먼저 줄여 Karpenter 노드가 빈 다음에 지웠다(`Disrupting Node: Empty`).
- **축소 중 끊김(2회, DEBUG 기록)**: 축소 구간 12:34~12:37에 API 오류는 0건이었다. 알림 SSE 1건이 core Pod 삭제(12:34:37) 33초 뒤인 12:35:10에 `stream error: INTERNAL_ERROR; received from peer`로 끊겼다. 지워진 Pod에 붙어 있던 SSE가 종료 유예가 끝날 때 끊긴 것이다(웹 EventSource는 다시 연결한다). 판정 2건은 learning Pod 삭제 즈음 `PENDING` 상태로 다시 받아 끝났다(k6 경합 처리). 12:37:09 이후 401 `TOKEN_EXPIRED`는 k6가 시작 때 받은 학생 토큰(15분)이 25분 실행 중 만료된 것이라 축소와 무관하다.
- 1회 관찰의 오류(API 1.11%)는 1000명 단계에서 밀린 요청이 남은 첫 1분(ALB 대상 5xx 636건, learning 풀 시간 초과 로그가 모두 12:02)에 몰려 있어 축소 영향과 가를 수 없었다. 그래서 2회를 다시 쟀다.

### 9.14.6 발견

1. **한계는 RDS CPU이고, 원인은 learning 쿼리 두 개다.** 400~1000명 구간 Performance Insights(평균 활성 세션)는 `learning_app` 5.30, `core_app` 0.63이었다. 상위 두 쿼리가 전체의 약 82%다.
   - 학생 학습 기록 목록(`learning-service` `RecordMapper.xml`, 3.49): 시도마다 `hint_usage`·`followup`·`answer.followup_id`를 상관 서브쿼리로 찾는다
   - 최근 되묻기 조회(`JudgmentMapper.xml`, 1.56): `followup`을 `attempt_id`로 찾는다
   - learning migration에는 `answer(attempt_id, submitted_at)` 인덱스만 있다. **`followup(attempt_id)`·`hint_usage(attempt_id)`·`answer(followup_id)` 인덱스가 없어** 시도 하나마다 테이블 전체를 읽는다. 시험으로 시도가 쌓일수록 느려졌다
   - 쌓인 데이터의 영향: 11:20 100명 학습 기록 p95 287ms·RDS CPU 24% → 12:20 10명(시험 데이터가 쌓인 뒤) 학습 기록 p95 1,014ms·RDS CPU 13~15%. 같은 200명도 11:27에는 API p95 238ms, 12:20에는 1분 만에 1초를 넘었다(바로 앞 축소 관찰 중이라 시작이 느렸고, 12:22 재시도는 423ms)
2. **앱 확장은 DB 앞에서 멈췄다.** core CPU는 3개 합계 0.75~0.85코어로 여유가 있었고 DB 연결은 68/176이었다. 병목이 DB인 동안에는 HPA 최대 수·노드를 늘려도 처리량이 늘지 않는다.
3. **HPA가 로그인 순간에 최대까지 간다.** 비밀번호·PIN 해시(로그인·가입)가 몰리면 core가 수십 초 안에 1→3이 된다. 새 JVM 기동 CPU가 평균을 더 올린다.
4. **D안 삭제 순서는 보장되지 않는다**(9.14.5).
5. **관측 경로가 부하에 같이 무너졌다.** Tempo가 CrashLoopBackOff(재시작 57회)인 상태에서 trace가 늘자 OTel Collector가 재시도 대기로 메모리 상한(soft limit)에 닿았고, 받는 데이터를 거부하면서 JVM·DB 풀 지표까지 버렸다(400명 11:47부터, 시험 뒤에도 앱 쪽 `HTTP 503`). trace 경로 장애가 지표 수집까지 막는다.

1차와 비교(300명): API p95 374 → 1,042ms, RDS CPU 68 → 72%. 1차는 학습 칸이 15개라 300명 API의 약 35%가 가벼운 경합 호출이었고, 2차는 칸 420개로 학습·판정이 실제로 돌았다. 그래서 같은 300명이라도 2차가 DB에 더 무겁다. "DB가 먼저 한계"라는 1차 결론은 계정을 늘린 2차에서도 맞았고, 그 DB 부하의 대부분이 learning이라는 것이 새로 드러났다.

해석 주의: k6 사용자 하나는 1~3초마다 요청을 보낸다. 실제 아이는 답을 쓰고 읽느라 훨씬 드물게 보내므로 k6 300명은 실제 동시 사용자 300명보다 무겁다. 또 시험 자녀 한 명이 한 시간에 수십~수백 번 시도해 학습 기록 쿼리(기간 안 시도 수에 비례) 비용이 실제보다 크다.

### 9.14.7 개선안

| 우선 | 제안 | 근거 |
|---|---|---|
| 1 | learning 인덱스 3개 추가: `followup(attempt_id, created_at)`, `hint_usage(attempt_id)`, `answer(followup_id)` | DB 부하 약 82%가 이 인덱스가 없는 두 쿼리. #775 learning V22로 추가(`hint_usage`는 `(attempt_id, opened_at)`, `answer`는 `followup_id IS NOT NULL` 부분 인덱스). kind 시험 데이터(시도 2만, 학생 1명 1,275개)에서 학습 기록 목록 3,300 → 13ms([learning 41절](learning.md#41-학습-기록되묻기-조회-인덱스-775-2026-11-18)). 같은 부하 단계 재측정은 AWS 재가동 때 |
| 2 | HPA 기준: CPU 70% 유지, `behavior.scaleUp` 안정화 30~60초 또는 JVM 기동 구간 제외 | 로그인 순간·JVM 기동 CPU로 바로 최대까지 감(9.14.3). 비용이 크지 않아 지금 값도 위험하지 않지만 확장이 실제 부하를 따라가지 않는다 |
| 3 | 최대 Pod 수: 1이 해결될 때까지 3 유지. 그 뒤 learning 최대를 먼저 올림 | 지금은 DB가 병목이라 늘려도 처리량이 같다. learning이 core보다 먼저 바빠짐 |
| 4 | Hikari 풀: 지금 10 유지. 1 뒤 learning 풀 대기가 남으면 15까지 | 연결 상한 계산: core 3×10 + learning 3×15 + report 30 = 105(+rolling 25) ≤ 176 |
| 5 | RDS 사양: 1을 먼저. 그래도 부족하면 t4g.medium 이상 또는 읽기 복제본 | 지금 효율 그대로 단순 비례하면 k6 1000명에 vCPU 약 7개가 필요(300명에서 2 vCPU의 72%). 1로 이 숫자가 크게 줄 것으로 본다 |
| 6 | 축소 끊김: D안 대신 최소 2 + PDB, 또는 `controller.kubernetes.io/pod-deletion-cost`로 Karpenter 노드 Pod 우선 삭제 | 9.14.5 |
| 7 | 관측: Tempo 장애 해결, Collector에서 trace와 지표 파이프라인의 메모리 제한 분리 | 9.14.6-5. #784로 chart에 반영하고 kind에서 확인(9.15). AWS 적용은 B 계정 |

### 9.14.8 운영 변경과 원복

| 변경 | 원복·정리 | 확인 |
|---|---|---|
| LLM 스텁 Deployment·Service·NetworkPolicy 2개(`llm-stub.k8s.yaml`) | 같은 파일로 delete(12:50) | app 네임스페이스에 `llm-stub` 자원 0 |
| ai `OPENAI_BASE_URL`=스텁(`kubectl set env`, 09:36) | `OPENAI_BASE_URL-`(12:49) | 시험 전 ReplicaSet `ai-service-d4888b47`로 복귀, helm 매니페스트와 `kubectl diff` 차이 없음 |
| 시험 계정 `load21`~`load214`(자녀 42명, 기기 14대) | 비밀번호 재확인 → `POST /me/withdrawal` 14건(202) | core `load2` 계정 0·연결 자녀 0, learning 11/18 시도·답변·되묻기 0, 분석 대화 0 |
| 시험 구독 42건(결제 없음, 1차 SQL과 같은 형식) | 해지 → 이용 기간을 당일로 끝냄 | 활성 0. 탈퇴 사전 확인은 해지만 해도 이용 기간이 남은 구독을 "진행 중"으로 세서 기간을 끝내야 탈퇴됐다 |
| pause Deployment `karpenter-limit-probe` | delete(12:15:59) | 노드 2대 빈 노드 정리 |
| 일회용 DB Pod·ConfigMap(`-384`) | 실행마다 delete | 0 |
| 비밀 파일(작업자 PC, 저장소 밖) | 삭제 | — |

- 시험 뒤 상태(12:55): 노드 4대(관리형 2 + 관측 2), NodeClaim 0, EC2 4대. HPA 설정은 시험 전과 같다(최소 1·최대 3·70%). 탈퇴 처리의 로그인·재확인 해시로 core가 잠시 3개가 됐다가(12:50:53) 12:57:54에 1개로 돌아왔다. core·learning·ai 모두 1개.
- 바꾸지 않은 것: HPA·Hikari·NodePool 값, 모델 레지스트리, scoring. core HPA 임시 상한 6은 필요 없어 쓰지 않았다(9.14.9).
- 남긴 것: 스텁 호출 `llm_usage` 21,629행(판정 9,289·되묻기 9,282·분석 3,058, 합계 $0.013). 스텁인데 모델명이 `gpt-6-luna`로 기록돼 호출 수 집계에서 실제 호출과 구분되지 않는다. 금액이 작아 지우지 않았다
- 1차(11-05) 시험 데이터(Google 시험 계정 자녀, 시도 약 2,800건)는 Google 재인증이 필요해 이번에 지우지 못했다. 보호자 화면의 자녀 삭제로 담당자가 정리한다
- app 네임스페이스에 11/17 재가동 때 만든 `demo-db-oneoff-sql` ConfigMap이 남아 있다(이 시험과 무관, 손대지 않음)

### 9.14.9 한계

- KEDA·report-worker 큐 확장은 AWS에 없어 재지 않았다.
- NAT는 스텁이라 외부 호출이 거의 없어 재지 않았다(최대 활성 연결 30, 포트 할당 오류 0은 임베딩·OAuth 등 기본 호출).
- core HPA 최대를 6으로 올려 Karpenter를 띄우려던 계획은 learning 확장으로 자연스럽게 노드가 떠서 하지 않았다. 그래서 HPA 최대가 3보다 클 때의 동작은 재지 않았다.
- 400명 11:47 이후 JVM·DB 풀 지표가 없다(관측 경로 장애). 1000명 풀 대기는 learning 로그 값이다.
- 실제 LLM 지연·429는 반영되지 않았다(#630은 동시 1명).

## 9.15 Tempo 장애와 지표 수집 격리 (#784, 2026-11-18)

9.14.6-5의 후속이다. Tempo가 죽어 있으면 Collector가 앱 지표까지 거부하는 문제를 chart에서 고치고 kind에서 수정 전후를 비교했다. AWS(A 계정)에는 적용하지 않았다. B 계정 배포 때 prod values로 들어간다.

### 9.15.1 원인 (chart 코드)

- Collector의 `memory_limiter`(`limit_mib: 192`)는 프로세스 전체 heap을 기준으로 한다. metrics·traces pipeline이 이 limiter 하나를 함께 썼다.
- `otlp/tempo` exporter의 대기열은 배치 500개, 재시도는 기본값(최대 5분)이었다. batch 처리기 배치 하나가 수 MB라서 Tempo가 응답하지 않으면 대기열이 heap을 soft limit(약 154MiB)까지 채운다.
- soft limit을 넘으면 limiter가 수신을 거부한다. 같은 limiter를 쓰는 metrics pipeline도 거부되고, 앱 OTLP 전송이 실패한다(A 계정의 `HTTP 503`).
- Tempo는 limits 512Mi에 ingester 기본값(블록 최대 500MB·30분)을 썼다. A 계정에서는 `completing block` 직후 OOMKilled가 반복됐다.

### 9.15.2 변경

| 대상 | 전 | 후 |
|---|---|---|
| traces pipeline limiter | `memory_limiter`(192MiB, metrics와 공유) | 자기 limiter `memory_limiter/traces` 144MiB·spike 32MiB(112MiB부터 trace만 거부). metrics는 기존 192MiB 그대로 |
| `otlp/tempo`·`otlp_http/langfuse` 대기열 | 배치 500개 | `sizer: bytes` 16MiB, 넘치면 버림 |
| 재시도 | 최대 5분(기본) | `max_elapsed_time: 30s`, `otlp/tempo` timeout 5s |
| Collector 재생성 | Tempo 켤 때만 annotation | trace 제한 값 checksum annotation 추가 |
| Tempo 자원 | requests 128Mi·limits 512Mi | requests 256Mi·limits 1Gi, `GOMEMLIMIT` 800MiB |
| Tempo ingester | 기본(500MB·30분) | `max_block_bytes` 64MiB, `max_block_duration` 5m, `trace_idle_period` 5s |
| Tempo 수집 상한 | 기본(15MB/s·burst 20MB, trace당 5MB) | 8MiB/s·burst 12MiB, 살아 있는 trace 5,000개, trace당 2MiB |
| 보존 | 72h(chart·prod) | 24h. 실패 요청 확인은 당일 조회로 충분하고 2Gi PVC와 compactor 부담을 줄인다 |
| Tempo 재생성 | 보존 값만 checksum | 설정 전체 checksum |

- 값은 `collector.traceLimits`, `tempo.ingester`·`tempo.limits`·`tempo.goMemLimit`로 바꿀 수 있다. trace를 켜지 않는 기본·local 렌더는 이전과 같다(`verify_chart.py` 기준 비교 통과).
- 고르지 않은 방법: 별도 trace Collector는 앱의 신호별 endpoint(`OTEL_EXPORTER_OTLP_TRACES_ENDPOINT`)·NetworkPolicy 변경과 관측 노드 Pod 추가가 필요하다. 앱 trace 표본 추출은 실패 요청 trace를 잃는다. 디스크 대기열(`file_storage`)은 Collector에 볼륨이 필요하다. 이번 문제는 메모리 대기열 상한만으로 막혀서 넣지 않았다.

### 9.15.3 kind 검증 방법

- `kind-sagomungchi-local`. observability chart에 local values + Tempo 켬 + 경보 3개(`demo-metrics-target-down`, `app-metrics-missing`, `http-auth-errors`, 지속 1m·평가 30s, 시험용 웹훅 Secret)를 올렸다.
- 앱 지표는 실제 core·learning Java agent(OTLP HTTP, 60초 주기)다. trace 부하는 app 네임스페이스에 `telemetrygen` v0.140.0 Pod(초당 400 trace × 10 span, 4 worker, Collector 4317만 허용하는 시험 NetworkPolicy)로 만들었다.
- 순서: 부하 시작(Tempo 켬, 2분) → `tempo` replicas 0(9분) → Tempo 1·부하 0(1.5분). 15초마다 Collector 자체 지표(heap, trace 대기열, 받은·거부한 지표 수), Prometheus의 core HTTP 지표 시계열 수와 2분 안에 값이 바뀐 JVM 지표 수, Grafana 규칙 상태·마지막 평가 시각을 기록했다.
- 수정 전은 이 PR 직전 chart, 수정 후는 이 PR chart로 같은 values를 썼다.

### 9.15.4 결과

| 항목 (Tempo 0 구간) | 수정 전 | 수정 후 |
|---|---|---|
| Collector heap | 2분 만에 145Mi, 이후 153~159Mi(soft limit) | 최대 약 90Mi |
| trace 대기열 | 배치 389~393개에서 멈춤 | 16MiB(상한)에서 넘치는 span 버림(대기열 진입 실패 570,880 span) |
| 거부한 앱 지표 | 0 → 3,100점(17:18부터), 17:20~17:26 받은 지표 증가 없음 | **0점**, 받은 지표 계속 증가(1,174점) |
| 받은 trace 거부 | 23,128 span | 0 span(대기열에서 버림) |
| Prometheus core HTTP 시계열 | 7분 30초 뒤 0(Collector exporter 5분 만료) | 3~4개 유지 |
| 값이 바뀌는 JVM 지표 | 4분 뒤 0 | 4~11개 유지 |
| `app-metrics-missing` | pending(7분 30초) → **firing**(8분 30초) | inactive 유지 |
| 규칙 평가 | 30초마다 계속(health ok). 평가는 됐지만 데이터가 없어 지표 부재 경보가 남 | 30초마다 계속, 세 규칙 모두 inactive/ok |
| Collector 로그 | soft limit `Refusing data` 5회, GC 강제 21회 | 시나리오 15분 로그 `sending queue is full` 1,000건, `Rejecting data`(trace 재시도 포기) 500건, `Dropping data` 252건, trace limiter GC 강제 13회, soft limit 수신 거부 0회 |
| 회복(Tempo 1·부하 0) | heap 150Mi대가 이어지다 약 1분 뒤 지표 수신 재개, 시계열 복구 뒤에도 경보는 firing 유지(관찰 종료 시점) | 지표·경보 변화 없음(시계열 4개, 규칙 inactive/ok), Tempo 재시작 0회 |

- 수정 전 kind 재현은 A 계정 현상(9.14.6-5)과 같다. trace 대기열이 heap을 채우고 limiter가 지표를 거부하며, 5분 뒤 시계열이 사라져 지표 부재 경보가 난다.
- 수정 후 trace는 버려지지만(최선 노력), 지표와 경보는 Tempo 상태와 상관없이 이어졌다.
- Tempo 새 설정은 `/status/config`에서 `max_block_bytes: 67108864`, `max_block_duration: 5m0s`, `rate_limit_bytes: 8388608`, `max_bytes_per_trace: 2097152`, `block_retention: 24h0m0s`로 적용된 것을 확인했다. 부하 2분과 회복 구간에서 Tempo 재시작은 0회였다.

### 9.15.5 한계와 남은 것

- kind는 노드 1대·Docker 메모리 안에서 telemetrygen 합성 trace로 쟀다. Tempo 1Gi가 #384 단계 부하(실제 Java agent trace)에서 OOM 없이 버티는지는 B 계정에서 확인한다.
- Tempo 수집 상한(8MiB/s)을 넘으면 trace가 버려진다. 1000명 단계 trace 양은 재지 않았다.
- trace 대기열이 메모리에 있으므로 Collector가 재시작하면 대기 중인 trace는 사라진다.
- 시험 자원(telemetrygen Deployment·NetworkPolicy, 웹훅 Secret)은 지우고 observability release는 검증 전 revision 설정(Tempo·경보 끔)으로 되돌렸다.

## 9.16 빈 클러스터 첫 배포와 B 계정 부트스트랩 보완 (#760, 2026-11-18)

11/17 A 계정 재가동(9.11)에서 새 EKS에 cd-release를 처음 실행했더니 앱 server dry-run이 `release: not found`로 멈췄다(run 44038487015). 그 밖에도 손으로 메운 빈틈이 7개 더 있었다. 11/25 A 재가동과 B 계정(시연) 구축 때 반복하지 않도록 코드와 절차에 반영했다. 이 작업에서 AWS에는 아무것도 만들거나 바꾸지 않았다.

### 9.16.1 빈틈 분류

| # | 11/17 빈틈 | 처리 | 반영 |
|---|---|---|---|
| 1 | 빈 클러스터에서 cd-release 실패: 앱 dry-run이 기존 release를 요구, migration 전에 멈춤 | 코드 | 계획 `currentRelease: "none"`이면 plan-record에 `firstInstall: true` → `redeploy-app.ps1 -AllowInstall`. release가 없을 때만 미리보기는 `helm install --dry-run=server`, 적용은 `helm upgrade --install`. 기존 `deployed` release는 지금처럼 `helm upgrade`. `none`이 아닌데 release가 없으면 "first install needs -AllowInstall"로 멈춤. 결과 JSON·이력에 `install`/`upgrade`와 전후 revision(첫 설치는 `null`, 요약은 "첫 설치→r1"). rollback 계획에는 `none`을 쓸 수 없음 ([CD README](../../infrastructure/cd/README.md#빈-클러스터-첫-배포-2026-11-18-760)) |
| 2 | learning V14 `CREATE EXTENSION vector`가 migrate 계정으로 실패 | 절차 | cd-release 앞뒤로 `demo_stack.py rds-bootstrap --execute`. RDS master secret을 쓰므로 workflow에 넣지 않음 |
| 3 | scoring·report-api·report-worker ServiceAccount가 없어 Pod 생성 실패 | 코드 | 세 values의 `serviceAccount.create`를 true로(ai·learning과 같은 방식). Pod Identity 연결은 SA보다 먼저 있어도 됨. `app` 네임스페이스 Pod Identity SA는 같은 이름 release values가 만든다는 것을 시험으로 고정 |
| 4 | 웹(S3)이 11/4 빌드로 남음. cd-release는 웹을 배포하지 않음 | 절차(자동화는 B 범위) | 9.16.2. cd-release에 넣으려면 publish 역할에 S3·CloudFront 권한을 더해야 하고 버킷·배포 ID가 계정마다 다름 |
| 5 | core V39 약관·개인정보 1.1 재동의 전 학부모는 자녀 학생 로그인 `CHILD_NOT_LINKED`, fixture refresh 쿠키 7일 만료 | 절차 | [CD README D](../../infrastructure/cd/README.md#d-배포-후-경로-확인-fixture-작업자-pc에만) |
| 6 | 작업자 PC에 eksctl 없음 | 절차 | 도구 버전: AWS CLI v2, **eksctl v0.231.0**(공식 릴리스, 체크섬 확인), kubectl 1.35, Helm 4.3.1(ci-gitops와 같음), PowerShell 7, Python 3.12, Node.js·npm, gh |
| 7 | 주간 테마 0건이라 학생이 풀 문제 없음 | 절차 | CD README D. 시연 주차마다 관리자 화면에서 테마 게시(11/17 A에서 초안 READY까지 14분) |
| 8 | `demo_stack.py plan`이 eksctl 노드그룹을 DIFF로 표시 | 코드 | 디스크는 `describe-nodegroup`의 `diskSize`가 비면 그 launch template 버전의 루트 볼륨 크기(`ec2:DescribeLaunchTemplateVersions`)로 비교, 라벨은 eksctl이 붙이는 `alpha.eksctl.io/*`를 빼고 비교. 크기가 다르거나 template을 못 읽으면 그대로 DIFF |
| — | 승인자 수(이슈 본문): 정책·문서는 2명, 실제로는 1명 승인으로 deploy 시작 | 문서 | GitHub Environment의 Required reviewers는 **목록 중 1명** 승인으로 job이 시작되고, 필요 승인 수를 정하는 설정이 없다. `policy.json`의 `approvers`는 승인 가능자 목록(2명)이므로 문서를 "2명 중 1명 승인"으로 맞췄다(7.1과 같음) |

3번과 A 계정: 11/17에 손으로 만든 SA 3개는 11/19 EKS 삭제와 함께 사라졌다. 11/25 재가동은 새 클러스터라 Helm 소유권 충돌이 없다. 손으로 만든 SA가 남은 클러스터에 적용해야 하면, 승인 후 그 SA에 Helm 소유 표시(`meta.helm.sh/release-name`·`meta.helm.sh/release-namespace` 주석, `app.kubernetes.io/managed-by=Helm` 라벨)를 붙여 넘긴다.

### 9.16.2 계정별 순서

**A 계정 11/25 재가동**(11/17 방식, 9.11.5 기준). 11/19 종료(EKS·NAT·ALB 삭제, RDS는 최종 스냅샷 `sagomungchi-demo-db-final-20261119` 뒤 정지, SageMaker는 예약 확장만 일시정지) 상태에서 다시 올린다. 계정 번호는 그대로이고 스냅샷 복원이 아니다.

| # | 단계 | 11/17과 다른 점 |
|---|---|---|
| 1 | `demo_stack.py plan` | MISSING은 NAT·route·EKS 예상 |
| 2★ | RDS `start-db-instance` → `wait db-instance-available` | 정지 7일 뒤 자동 시작(11/26 22:48 KST 무렵) 전에 켠다. 데이터는 11/19 22:38 상태 |
| 3★ | `apply --confirm-account <계정>`(NAT) → private route table 2개 `replace-route` | RDS가 있으므로 `--without-rds`는 필요 없음 |
| 4★ | `render-eksctl --operator-cidr <작업자 IP>/32` → `eksctl create cluster` → `apply --after-eksctl` → `plan` | 노드그룹이 OK로 나와야 한다(9.16.1의 8번) |
| 5 | 플랫폼·관측 | 같음 |
| 6★ | `rds-bootstrap --execute` → cd-release(계획 `currentRelease: "none"`) → `rds-bootstrap --execute` | **#760이 main에 있어야 한다.** 없으면 11/17처럼 `release: not found`. SA는 chart가 만든다 |
| 7★ | ALB Ingress → CloudFront `/api/*` origin을 새 ALB로 | 같음 |
| 8 | SageMaker 예약 재개(`ScheduledScalingSuspended=false`) | 11/19에 일시정지 |
| 9 | 웹 | 11/19에 올린 빌드보다 새 main이면 다시 올린다(assets 먼저, `index.html` 마지막, 무효화) |
| 10 | fixture 재로그인·갱신 → 경로 확인 | refresh 쿠키 7일 만료. 첫 실행 경로 확인이 실패했으면 갱신 뒤 같은 계획을 다시 실행하거나 `verify_cd_deployment.py`만 실행 |
| 11★ | (A 종료 직전) B 공유용 스냅샷 | 11/25 확인(#927)이 모두 끝난 뒤, RDS 정지·삭제 전에 고객 관리 KMS 키 생성 → 새 수동 스냅샷 → 그 키로 복사 → B 공유. [B 런북 선행 A-K1~A-K5](../../infrastructure/aws/README.md#선행-a-계정-1125-a-종료-직전), 이유는 9.19 |

**B 계정**: 전체 순서는 [AWS README의 B 계정 전환 런북](../../infrastructure/aws/README.md#b-계정-전환-런북-809)이다(#809). 이 작업이 그 런북에서 맡는 것은 9단계 첫 배포(`currentRelease: "none"`)와 8·10단계 `rds-bootstrap` 앞뒤, 15단계 fixture·테마다.

**B DB용 A 쪽 스냅샷 단계**(2026-11-18 결정: B DB는 A 최종 RDS 스냅샷 복원):

| # | 단계 | 방법·상태 |
|---|---|---|
| A-1★ | 시험 데이터 정리 범위 | 부하 시험 계정(`load2*`)·스텁 `llm_usage` 행·경로 확인용 임시 계정 등 시연에 남기지 않을 데이터를 정한다. A에서 지운 뒤 스냅샷을 뜨거나 B 복원 뒤 지운다 |
| A-2★ | 공유용 스냅샷 | 11/19 최종 스냅샷은 AWS 관리 키(`aws/rds`)로 암호화돼 다른 계정과 공유할 수 없다. B 직전 A를 다시 내릴 때(11/26 전) 새 최종 스냅샷을 뜨고, A의 고객 관리 KMS 키로 `copy-db-snapshot --kms-key-id <키>` → **B 계정 번호가 정해진 뒤** 키 정책에 B 허용 → `modify-db-snapshot-attribute --attribute-name restore --values-to-add <B 계정>`. 시점은 11/25 A 종료 직전(위 11단계)으로 정했고 세부 단계는 런북 선행 A-K1~A-K4(9.19, 2026-11-23) |
| A-3 | 보존 | 공유 스냅샷·KMS 키(삭제 대기 기간 포함)·A Secrets Manager의 DB 계정 값 6개·`PAYMENT_BILLING_ENCRYPTION_KEY`는 B 복원이 끝날 때까지 지우지 않는다. B 쪽 복원·비밀번호·S3 경로는 런북 3·5·8단계 |

스냅샷을 복원해도 cd-release 한 번으로 경로 확인까지 끝나는 것은 보장되지 않는다. 학생 PIN·자녀 연결·약관 동의·테마는 스냅샷에 있지만, 부모 refresh 쿠키는 최초 로그인부터 7일이고 학생 기기 쿠키는 새 도메인에서 다시 받아야 한다. 첫 실행의 경로 확인이 실패하면 쿠키를 갱신한 뒤 같은 계획을 다시 실행해 성공 이력을 남긴다.

### 9.16.3 확인 (2026-11-18·11-20, AWS 실행 없음)

- 시험: `scripts/tests/test_cd_migration_runner.py`에 앱 경로 8개를 더했다.
  - release가 없고 스위치도 없으면 거부한다.
  - 첫 설치는 미리보기와 적용 모두 확인했다.
  - 기존 release는 스위치가 있어도 `upgrade`로 처리한다.
  - `failed` release는 덮어쓰지 않는다.
  - 첫 설치 실패는 결과에 기록한다.
  - migration에 스위치를 주면 거부한다.
- 그 밖에 `test_cd_release.py` 2개(rollback의 `none` 거부, `firstInstall` 기록)와 `test_aws_demo_stack.py` 2개(노드그룹 비교, SA 생성 규칙)를 더했다.
- 일회용 kind 클러스터(`app` 네임스페이스만 있는 빈 클러스터, 확인 뒤 삭제)에 cd-release deploy job의 "migration 미리보기"·"적용 미리보기" step 스크립트를 그대로 실행했다. aws만 계정·endpoint를 돌려주는 가짜로 두고 helm·kubectl은 실제로 썼다.
  - 기존 형식 계획: 첫 release에서 "first install needs -AllowInstall"로 멈췄다. 11/17과 같은 지점이고 메시지만 명확해졌다.
  - `currentRelease: "none"` 계획: migration Job·NetworkPolicy 3쌍과 앱 6개의 `helm install --dry-run=server`가 모두 통과했고, 클러스터에는 아무것도 생기지 않았다.
- 실제 Helm 4.3.1에는 `helm list -a`가 없어(가짜 helm 시험은 통과했음) release 조회를 Helm 3·4 공통 상태 필터(`--deployed --failed --pending --uninstalling`)로 고쳤다.
- "migration 적용·완료 확인"·"적용"·"배포 이력 기록" step은 가짜 helm·kubectl로 실행했다.
  - 첫 배포: 앱 6개가 `upgrade --install`, 이력 요약은 "첫 설치→r1 deployed"였다.
  - 기존 release 계획: `upgrade`, 요약은 "r4→r5"였다.

### 9.16.4 한계

- AWS에서 첫 배포 경로를 실행하지 않았다. 실제 확인은 11/25 A 재가동(9.16.2의 6단계)과 B 구축 때 한다.
- 첫 설치 중 한 release가 `failed`가 되면 다시 실행해도 자동으로 고치지 않는다. 원인을 고친 뒤 승인을 받아 `helm uninstall <release> -n app`으로 지우고 같은 계획을 다시 실행한다. 이미 설치된 release는 `upgrade`로 이어진다.
- 웹 배포 자동화는 B 범위로 남겼다.
## 9.17 리포트 Gemma SageMaker 경로 잠금과 적재 때 해시 검사 (#777, 2026-11-18)

SageMaker는 0대에서 켜질 때마다 S3에서 모델을 다시 받는데, 받은 파일의 sha256을 확인하지 않는다(#368·#493 원칙과 다름). #746에서는 배포 전 대조(`verify`)만 했다. 이 절은 남은 두 가지, 즉 승인 경로 잠금과 적재 때 검사를 구현하고 A 계정에서 미리 확인한 결과다. 운영 엔드포인트 `sagomungchi-demo-explanation`은 건드리지 않고 별도 시험 엔드포인트를 썼다. 실제 승인 경로 잠금과 gguf 정리, 운영 이미지 교체는 B 계정에서 한다(9.17.7). A에서 다시 확인하는 절차는 9.17.6이다.

### 9.17.1 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 검사 위치 | 기반 모델: 컨테이너 시작 스크립트. LoRA: vLLM 미들웨어(`POST /adapters`) | 기반은 `/opt/ml/model`로 받은 뒤 서버가 뜨기 전에 볼 수 있다. LoRA는 어댑터 IC가 따로 받아 `POST /adapters?src=/opt/ml/models/<어댑터 IC>/model`로 넘기므로 시작 스크립트로는 볼 수 없다 |
| 이미지 | [`sagemaker/model-check/`](../../infrastructure/aws/sagemaker/model-check/): #746 DLC(`vllm:server-sagemaker-cuda-v2.8.2`, digest `d084c1bf…`로 고정) 위에 `model_check.py`와 시작 스크립트만 더함. 원래 진입점(`sagemaker_entrypoint.sh`)을 그대로 이어 부른다 | AWS는 같은 태그로 보안 패치판을 다시 올린다(이미지 기록 `CACHE_REFRESH=2026-11-16`). 그래서 기반도 digest로 고정했다 |
| ECR | `sagomungchi/sagemaker-explanation`(IMMUTABLE, AES256, `demo-stack.json`). 수동 빌드·게시, `cd-release` 대상 아님. 모델은 `imageDigest`로 고정한다 | 이슈 범위 |
| 모델 데이터 | `base-awq/` → **버전 경로 전체** `explanation/<버전>/`(manifest.json + `base-awq/` + `adapter/`). vLLM에는 `SM_VLLM_MODEL=/opt/ml/model/base-awq`를 준다 | 컨테이너가 manifest.json을 같은 다운로드 안에서 받아야 대조할 수 있다. 대가로 어댑터(46MB)를 두 번 받는다 |
| 고정 값 | `MODEL_MANIFEST_SHA256` = manifest.json의 S3 FULL_OBJECT SHA-256. `apply`가 `verify` 통과 뒤 모델 환경 변수에 넣는다 | manifest를 바꿔치기해도 시작이 거부된다 |
| 검사 순서 | `MODEL_MANIFEST_SHA256` 형식 → manifest.json sha256 → `/opt/ml/model` 파일 전부(누락·추가·크기·sha256). 하나라도 다르면 vLLM을 띄우지 않고 종료 | 이슈 범위. 크기를 먼저 봐서 다른 파일이면 해시 전에 끝난다. 해시는 4스레드로 병렬 계산 |
| LoRA 우회 경로 | 미들웨어가 vLLM `/v1/load_lora_adapter`를 직접 경로와 `/invocations` + `route=` 사용자 속성 모두 403으로 막는다 | 런타임 LoRA(`VLLM_ALLOW_RUNTIME_LORA_UPDATING=true`)가 켜져 있어 호출 권한만 있으면 임의 경로 LoRA를 올릴 수 있었다 |
| `verify` 범위 | 버전 경로 아래 모든 객체 = manifest.json + manifest 목록. `base-gguf/`·`adapter-gguf/`가 남아 있으면 `apply`·`lock`이 멈춘다 | SageMaker가 버전 경로를 통째로 받고, 컨테이너도 남는 파일을 거부한다 |
| 경로 잠금 | 모델 버킷 정책에 `Deny`, `Principal: *`, `s3:PutObject`·`s3:DeleteObject`·`s3:DeleteObjectVersion`, 대상 `explanation/<버전>/*`. `sagemaker_explanation.py lock`이 `verify` 통과 뒤 넣고, 다른 문장은 그대로 둔다(같은 Sid는 교체). `--dry-run`, 시험용 `--prefix`·`--remove`가 있다 | 이슈 범위. `apply`(생성 전용)에 넣지 않은 것은 가중치를 올리기 전에 잠그면 업로드가 막히기 때문이다 |
| 실행 역할 | `PullModelCheckImage`(새 ECR 저장소 받기) 추가 | 새 이미지를 받으려면 필요 |
| 기동 제한 | `ContainerStartupHealthCheckTimeoutInSeconds`·`ModelDataDownloadTimeoutInSeconds`는 **1200초 유지** | 컨테이너 시작부터 InService까지 실측 약 5분(해시 45초 포함, 9.17.3)이라 여유가 4배 가깝다. 늘리면 실패한 IC를 지우기까지 기다리는 시간만 길어진다(9.13.9) |

### 9.17.2 A 계정 검증 결과 (2026-11-18 19:00~20:12 KST)

시험 엔드포인트 `sagomungchi-test777-explanation`(`ml.g6e.xlarge`, 설정·IC 이름도 `test777`)을 따로 만들었다. 가중치는 실제 승인본(`explanation/gemma4-26b-a4b-lora-20261118/`)의 `base-awq/`·`adapter/` 13개 파일을 S3 안에서 `CopyObject`(SHA-256)로 시험 경로에 복사해 썼다. A의 승인 경로에는 gguf가 아직 있어서 그대로는 새 방식의 `verify`를 통과하지 못하기 때문이다(B에서 정리한 뒤의 모습을 시험 경로로 재현). 시험 경로마다 manifest는 `manifest --upload`로 따로 올렸다.

| 시험 | 방법 | 결과 |
|---|---|---|
| 정상 모델 | 시험 경로 `test777-good/` + 검사 이미지(`sha256:3e5aacfc…`)로 `apply` | 컨테이너 안 검사 `13 files 16.09 GiB sha256 in 44.6s` 통과 → vLLM 기동 → 기반 IC InService. 어댑터 적재 때 `adapter … check OK: 2 files`. 기반·LoRA 호출 모두 200(LoRA 응답 `model`이 어댑터 IC 이름). 미들웨어 2개(`model_check`, DLC `sagemaker_serve`)가 함께 올라갔다 |
| 기반 파일 1개 변경 | `test777-bad/`의 `base-awq/generation_config.json` 1바이트(공백→탭, 크기 같음)를 바꾸고, 배포 전 대조를 일부러 건너뛰어 IC 생성 | 다운로드 뒤 검사에서 `FAIL SHA256 base-awq/generation_config.json cbe400ee… != b69207f9…`로 vLLM 전에 종료(`refusing to start`). SageMaker가 컨테이너를 다시 띄울 때마다 같은 이유로 18회 거부했고, IC는 기동 제한(이 시험만 600초)이 지난 뒤 Failed("did not pass the ping health check")가 됐다(생성 19:53:27 → Failed 20:09:00, 15.5분) |
| 배포 전 대조 | 같은 변경 경로에 `verify` | `DIFF base-awq/generation_config.json`, `MISMATCH`로 `apply`가 멈춤 |
| LoRA 파일 변경 | `adapter_config.json` 1바이트를 바꾼 경로로 어댑터 IC 생성 | IC는 InService로 표시되지만, 첫 호출 때 SageMaker의 `POST /adapters`를 미들웨어가 400으로 거부했다(`FAIL SHA256 adapter_config.json`). 호출은 `ModelError: adapter files do not match manifest.json`으로 실패하고, 이후 호출도 매번 다시 거부됐다. 같은 엔드포인트의 정상 LoRA 호출은 계속 성공 |
| 경로 잠금 | 시험 접두어 `explanation/test777-lock/`에 가상 객체 1개를 두고 `lock --prefix`로 잠금 | 새 키 쓰기, 덮어쓰기, `CopyObject`로 넣기, multipart 시작, 삭제(삭제 마커), 버전 삭제가 모두 `AccessDenied`. 읽기와 잠금 밖 경로 쓰기는 허용. `--remove`로 원복하자 버킷 정책이 원래대로(정책 없음) 돌아갔다 |
| 이미지 내용 | 저장소 파일과 게시 이미지 안 파일의 sha256 비교 | `model_check.py`·`entrypoint.sh` 모두 같음. 로컬 Docker에서 정상 가짜 모델은 검사 뒤 vLLM 진입(GPU 없어 거기서 종료), 잘못된 `MODEL_MANIFEST_SHA256`은 vLLM 전 종료(코드 1) |

- 단위 테스트(`scripts/tests/test_sagemaker_model_check.py`)는 가짜 파일로 누락·추가·크기·sha256·symlink·manifest 변조·형식 오류, 미들웨어의 통과·거부·우회 경로 차단, `lock` 정책 병합·원복·거부 조건, `verify`의 gguf 잔여 거부를 확인한다.

### 9.17.3 시간

| 구간 | #746(검사 없음) | #777(검사 이미지) |
|---|---|---|
| 해시 계산(16.09GiB, 13개 파일) | — | 44.6초 |
| 인스턴스가 있을 때 IC 생성 → InService | 약 9분(534~535초) | 9분 32초(19:11:09 → 19:20:41) |
| 0대 → 1대 콜드(Auto Scaling 반영 → 기반 IC InService) | 20.5분 | **13분 7초**(19:35:01 → 19:48:08). 인스턴스 1대 2.7분, 이미지·모델 받기 약 5.5분, 해시 44.8초, vLLM 기동 4.2분 |

- 이미지 크기는 DLC와 사실상 같다(압축 10.68GB, 더한 층은 수십 KB).
- 해시는 `/opt/ml/model`에 받은 뒤 vLLM 기동 전에 한 번 돈다. 어댑터 검사는 0.04GiB라 0초대다.
- **예약 확장 시각**: 바꿀 필요 없다. 해시는 콜드에 약 45초를 더한다. #746의 20.5분(인스턴스 확보 10분)에 더해도 약 21.3분이라, 일 23:30 확장이면 배치 시작(월 00:00) 전에 약 8분 남는다. 이번 13.1분은 인스턴스가 2.7분 만에 잡혀 짧았고, 인스턴스 확보 시간이 콜드 차이의 대부분이다

### 9.17.4 발견

- **어댑터는 첫 호출 때 적재된다**: 어댑터 IC가 InService가 되어도 `POST /adapters`는 그 IC로 첫 호출이 올 때 일어났다(정상 어댑터도 같음). 그래서 LoRA 파일이 바뀌어도 IC 상태로는 알 수 없고 호출마다 실패한다. 실패는 닫힌 쪽(설명 없이 발행)이라 안전하지만, 바뀐 것을 알아차리려면 창 시작 뒤 LoRA 호출 1건으로 확인하거나 IC 로그의 `[model-check] … FAILED`에 경보를 거는 편이 좋다
- 기반 파일이 바뀌면 컨테이너가 시작 직후 종료를 반복하고, IC는 기동 제한이 지나야 Failed가 된다(9.17.2). 그동안 IC를 지울 수 없다(9.13.9와 같음)
- vLLM이 `Found duplicate keys --middleware`를 출력하지만 두 미들웨어 모두 등록된다(인자 목록에 2개)
- `copies 1`은 Auto Scaling 대상 최소값을 먼저 1로 바꾸므로, Auto Scaling이 바로 사본 수를 바꾸기 시작하면 이어지는 `update-inference-component-runtime-config`가 `UPDATE_RC_IN_PROGRESS`로 실패한다(#746 스크립트의 경합). 확장 자체는 Auto Scaling이 진행한다. 이번에는 상태를 직접 따라가며 쟀다
- Windows Docker Desktop은 ECR 토큰을 자격 증명 저장소(wincred)에 넣지 못한다(`The stub received bad data`). 임시 `DOCKER_CONFIG`에 `auths`를 직접 쓰는 방식으로 우회했다
- 게시는 `docker buildx build --provenance=false --sbom=false --output type=image,name=…,oci-mediatypes=false,push=true`로 Docker v2 단일 manifest로 올렸다. 기본값(attestation 포함 OCI index)이 SageMaker에서 받아지는지는 확인하지 않았다

### 9.17.5 한계

- 버킷 정책 `Deny`는 루트 사용자를 포함한 모든 주체에 적용되지만, `s3:PutBucketPolicy` 권한이 있는 관리자는 정책을 지운 뒤 쓸 수 있다. 잠금은 실수와 다른 서비스 주체를 막는 장치이고, 관리자 변경은 CloudTrail로 추적한다. 모델 버킷에는 수명 주기 규칙이 없다(2026-11-18 확인). 규칙을 추가하면 만료 삭제는 버킷 정책과 상관없이 일어나므로 `explanation/`을 제외해야 한다
- 검사 이미지와 승인 목록은 같은 계정 안에서 고친 사람이 함께 바꿀 수 있다. `MODEL_MANIFEST_SHA256`은 SageMaker 모델에 고정되고 모델은 수정할 수 없으므로, 바꾸려면 새 모델을 만들어야 한다
- 해시 시간은 `ml.g6e.xlarge` 1회 측정이다

### 9.17.6 머지 뒤 영향과 11/25 A 확인 절차 (2026-11-20 정리)

결정(2026-11-20): 실제 적용 확인은 11/25 A 재가동 때 하고, B 적용 단계는 #809 B 런북에 넣는다.

**머지 뒤 영향**: `explanation-endpoint.json`이 검사 이미지(`imageDigest`)와 버전 경로 전체를 가리킨다. 그래서 이미지를 그 계정에 게시하기 전이나 버전 경로에 `base-gguf/`·`adapter-gguf/`가 남아 있으면 `verify`·`apply`·`lock`이 멈춘다. 지금 적힌 digest `sha256:3e5aacfc…`는 11/18 A 시험 이미지이고 시험 뒤 지웠으므로, 11/25에 다시 게시한 값으로 바꿔야 한다. 이미 떠 있는 엔드포인트와 IC는 바뀌지 않는다.

**#760 11/25 순서(9.16.2)와의 관계**: 어긋나지 않는다. 8단계 "SageMaker 예약 재개"는 11/19에 일시정지한 기존 IC(모델 `…-r4`, DLC 이미지, `base-awq/`)를 그대로 다시 켜는 것이라 이 변경과 상관없다. #777 확인은 8단계 뒤, 10단계(경로 확인) 전에 SageMaker만 따로 한다. EKS·RDS 단계와 서로 기다리지 않는다. 11/25(수)는 배치 창(일 23:30~월 02:00) 밖이다.

**11/25 A 확인 절차**

| # | 단계 | 확인 |
|---|---|---|
| 1 | 이미지 빌드·게시: `demo_stack.py plan`에서 ECR `sagomungchi/sagemaker-explanation`이 MISSING이면 `apply`(9.16.2의 3단계)가 만든다. 실행 역할이 남아 있으면 inline 정책(`PullModelCheckImage` 포함)은 `put-role-policy`로 넣는다. 9.17.7의 3번 명령으로 게시하고 digest를 `imageDigest`에 적는다(별도 커밋) | `describe-images`의 `imageManifestMediaType`이 `…docker.distribution.manifest.v2+json` |
| 2 | gguf 정리: 승인 경로의 `base-gguf/`(4개)·`adapter-gguf/`(1개)의 모든 버전 삭제 | `verify`가 `all objects match`(13개) |
| 3 | apply: `apply`는 없는 것만 만들고 **이미 있는 IC의 모델(`…-r4`)은 바꾸지 않는다**. 그래서 어댑터 IC → 기반 IC 순서로 지운 뒤 `apply --confirm-account <A>` → `schedule`을 다시 건다 | 새 모델 `…-r5`, IC 로그 `[model-check] model check OK: 13 files` |
| 4 | lock: `lock --dry-run` → `lock` | `status`에 `path lock …: locked`, 잠근 경로 쓰기 1건 `AccessDenied` |
| 5 | 콜드·LoRA 호출 1건: `copies 0 --wait` → `copies 1`(경합으로 실패하면 상태만 따라감, 9.17.4) → 기반·어댑터 IC 호출 각 1건 | 콜드 시간 기록, 어댑터 첫 호출 뒤 `adapter … check OK` |

- 결과와 걸린 시간은 이 절 아래에 덧붙인다.
- **B**: #809 B 런북(AWS README 13단계)에서 검사 이미지 사용 여부를 정한다(9.17.7). ECR은 8개(`demo-stack.json`).

**11/24 A 실행 결과** (11/25 예정을 하루 당김, 9.26)

| # | 시각 | 결과 |
|---|---|---|
| 1 | 18:27 | `model-check` 이미지 게시 `sagomungchi/sagemaker-explanation:777-a-20261124`, digest `sha256:02b233dd…`, 10.68GB, `…docker.distribution.manifest.v2+json`. 기반 계층이 작업자 PC에 있어 3초. `explanation-endpoint.json` `imageDigest` 교체 |
| 2 | 18:28 | 승인 경로 `base-gguf/` 4개·`adapter-gguf/` 1개 버전 삭제(삭제 마커 0) → `verify` `all objects match`(13개) |
| 3 | 18:31~18:46 | 어댑터 IC → 기반 IC 삭제(2분 40초) → `apply`: 모델 `…-r5`, 기반 IC Creating → InService 852초(사본 1, 이미지 10.7GB 받기 포함). IC 로그 `[model-check] model check OK: 13 files 16.09 GiB sha256 in 44.6s`. `schedule`로 일 23:30→1·월 02:00→0 다시 걸음 |
| 5 | 18:46 | 기반 IC 호출 2.7초(80토큰, `finish=length`), 어댑터 IC 호출 2.2초(38토큰, `stop`). 어댑터 첫 호출 뒤 `[model-check] adapter sagomungchi-demo-explanation-explain check OK: 2 files`. `copies 0`은 첫 요청이 Throttling으로 보였지만 실제로 반영됨(재시도는 `UPDATE_RC_IN_PROGRESS`, 9.17.4와 같은 경합). 인스턴스 0대 18:59 |
| 4 | 18:49 | `lock --dry-run` → `lock`. `status` `path lock …: locked`, 잠근 경로 `PutObject` 1건 `AccessDenied`(explicit deny), 객체 생기지 않음 |

- GPU(`ml.g6e.xlarge`) 사용 약 28분(18:31~18:59).
- B 판단(11/23 결정 기준): A에서 기동·해시 검사·기반·어댑터 호출이 모두 문제없어 **B에도 검사 이미지를 적용**한다(9.17.7 절차). B는 이미지 빌드·게시를 그 계정 ECR에 다시 하고 digest를 B 값으로 확인한다.
- 리포트 생성 흐름(ai → SageMaker)으로 설명이 붙는지는 A에서 따로 돌리지 않았다. 같은 IC를 직접 호출했고, 실제 흐름은 B #808 W1~W3 주간 리포트에서 확인한다.

### 9.17.7 B 계정 적용 절차

순서는 [aws README](../../infrastructure/aws/README.md#리포트-gemma-sagemaker-엔드포인트-746-2026-11-18)의 "새 계정 순서"와 같다. #777 때문에 더해진 부분만 적는다.

1. 가중치: 버전 경로에는 `base-awq/`·`adapter/`만 올리고(`base-gguf/`·`adapter-gguf/`는 올리지 않거나 지운다), `manifest --upload`로 manifest.json을 한 번 올린다. `verify`가 `all objects match`여야 한다
2. `demo_stack.py apply --confirm-account <B>`로 ECR `sagomungchi/sagemaker-explanation`(IMMUTABLE)과 실행 역할을 만든다. 역할이 이미 있으면 inline 정책(`PullModelCheckImage` 포함)을 `put-role-policy`로 넣는다. `iam/` JSON과 `demo-stack.json`의 계정 번호를 B로 바꾼 뒤 실행한다
3. 이미지: DLC 레지스트리(`763104351884`)와 B ECR에 로그인하고 저장소 루트에서
   `docker buildx build --provenance=false --sbom=false --output type=image,name=<B 계정>.dkr.ecr.ap-northeast-2.amazonaws.com/sagomungchi/sagemaker-explanation:<태그>,oci-mediatypes=false,push=true infrastructure/aws/sagemaker/model-check`
   (A에서 기반 10.7GB 받기 약 15분, 게시 약 5분). `aws ecr describe-images`로 digest를 확인해 `explanation-endpoint.json` `imageDigest`에 적는다(같은 파일이면 A와 digest가 같을 수 있지만 B 값으로 확인한다)
4. `lock --confirm-account <B> --dry-run`으로 정책을 확인하고 `lock --confirm-account <B>`로 잠근다. `status`에 `path lock …: locked`가 나와야 한다. 잠근 뒤 쓰기 1건이 `AccessDenied`인지 확인한다(시험 키는 잠근 경로 밖에)
5. `apply --confirm-account <B>` → `schedule`. IC 로그(`/aws/sagemaker/InferenceComponents/sagomungchi-demo-explanation-ic`)에서 `[model-check] model check OK: 13 files`와 첫 LoRA 호출 뒤 `adapter … check OK`를 확인한다

- 새 모델 버전을 올릴 때는 항상 새 버전 경로에 올리고 그 경로를 다시 쓰지 않는다. 옛 경로 잠금은 남겨 둔다

### 9.17.8 12/7 데모 전 적용 판단 근거 (결정은 팀)

| 관점 | 내용 |
|---|---|
| 콜드 시간 | 해시로 콜드가 약 45초 늘어난다. 예약 창(일 23:30)은 그대로 둬도 된다(9.17.3) |
| 추가 작업(B) | 이미지 빌드·게시(약 20분, 로컬 업로드), `lock` 1회, gguf를 올리지 않기. 나머지 `apply`·`schedule`은 어차피 B에서 새로 한다 |
| 새로 생기는 실패 | 버전 경로에 남는 파일이 있으면 시작 거부(`verify`가 먼저 막음). LoRA 파일이 바뀌면 설명 호출이 매번 실패(닫힌 쪽). 기반이 바뀌면 IC가 Failed가 될 때까지 최대 20분 넘게 걸림 |
| 적용하지 않을 때 | 배포 전 `verify`에만 기대고, 버전 경로는 쓰기 권한이 있는 주체가 덮어쓸 수 있다. 0대에서 켜질 때 받은 파일은 검사하지 않는다 |
| 되돌리기 | `imageDigest` 대신 DLC 이미지·`base-awq/` 경로로 새 모델을 만들고 IC를 다시 만들면 된다(약 9분 + 콜드). 버킷 정책은 `lock --remove` |

### 9.17.9 시험 자원과 정리

| 자원 | 이름 | 상태 |
|---|---|---|
| SageMaker 엔드포인트·설정·모델·IC | `sagomungchi-test777-explanation`(설정 `…-g6e-xlarge`), 모델 `…-good`·`…-bad`, IC `…-ic`·`…-explain`·`…-badadapter`·`…-badic`, Auto Scaling 대상 | 삭제(20:10) |
| CloudWatch 로그 그룹 | `/aws/sagemaker/InferenceComponents/sagomungchi-test777-explanation-{ic,badic}` | 삭제 |
| ECR 이미지 | `sagomungchi/sagemaker-explanation@sha256:3e5aacfc…`(태그 `777-trial-1`) | 삭제. 저장소는 `demo-stack.json` 정의라 빈 채로 둠(A 종료 때 함께 지움) |
| S3 | `explanation/test777-{good,bad,badadapter,lock,unlocked}/`의 모든 버전·삭제 마커 | 삭제(0개 확인), 남은 multipart 0건 |
| 버킷 정책 | 시험 잠금 | `--remove`로 원복, 정책 없음 확인 |
| 실행 역할 inline | `PullModelCheckImage` 문장 추가 | 저장소 정의(`iam/`)와 같아 그대로 둠 |

20:12 KST에 SageMaker 엔드포인트·IC·Auto Scaling 대상·로그 그룹이 운영 것(`sagomungchi-demo-explanation`, 사본 0, 마지막 변경 17:46)만 남았고 승인 경로(`explanation/gemma4-26b-a4b-lora-20261118/`, 31.7GB)는 바뀌지 않았음을 확인했다. 비용은 `ml.g6e.xlarge` 약 1시간(약 $3.2)과 S3 복사·요청이다.

## 9.18 prod Argo CD 전환 (에픽 #859, 2026-11-20)

2026-11-20 결정으로 운영(EKS) 배포를 B 계정 첫 배포(11/28)부터 Argo CD로 하고, 11/25 A 재가동에서 먼저 확인한다. 이미지는 cd-release가 만드는 digest PR의 승인·병합으로 바꾸고, 병합되면 Argo CD가 main을 자동 동기화한다. 하위 절은 이슈별로 9.18.1 #855(설치·root app·알림), 9.18.2 #856(플랫폼 Application), 9.18.3 #857(앱 ApplicationSet·images 파일·migration PreSync), 9.18.4 #858(cd-release digest PR)이다. 네 이슈는 에픽 본문의 "병렬 진행 계약"을 기준으로 동시에 작업했다.

### 9.18.1 Argo CD 설치 값과 진입점 (#855, 2026-11-20)

절차는 [prod Argo CD README](../../infrastructure/gitops/argocd/prod/README.md), 값은 `infrastructure/gitops/environments/prod/argocd.json`.

| 항목 | 결정 | 근거 |
|---|---|---|
| 버전 | argo-cd chart **10.11.7**(Argo CD **v3.5.7**), `global.image.tag`도 고정 | 로컬 kind와 같은 3.5대의 최신 patch(확인 필요 기본안). 3.6(chart 10.12 이상)은 로컬에서 쓴 적이 없다 |
| 설치 | 손으로 `helm install` 1회 → `project.yaml` → `root-app.yaml`. Argo CD 자체는 root app이 관리하지 않음 | 자기 자신을 동기화하다 망가지면 복구 경로가 없어진다(확인 필요 기본안). 버전 변경도 손으로 `helm upgrade` |
| 구성 | dex·HA·Ingress 끔, 각 1개, `eks.amazonaws.com/nodegroup=application` 필수 배치. 요청 CPU 275m·메모리 640Mi, 메모리 limit 합 약 2Gi | 데모 단일 클러스터, `application` 노드그룹 t3.medium 2대 예산. 자리가 없으면 Karpenter `application-burst`가 노드를 늘린다. 접속은 `kubectl port-forward`와 admin 계정만 |
| AppProject | `sagomungchi-prod`. 출처는 이 저장소와 ESO·LB Controller·Karpenter chart 저장소, 대상은 `argocd`·`app`·`platform`·`observability`·`external-secrets`·`kube-system`, cluster 범위 자원은 Namespace·StorageClass·CRD·ClusterRole(Binding)·webhook 설정·IngressClass(Params)·NodePool·EC2NodeClass만. AppProject 자체는 하위 Application이 만들 수 없음 | #856·#857이 쓰는 범위만 연다. 새 namespace·외부 chart가 필요하면 그 PR에서 이 파일을 함께 고친다 |
| root app | `sagomungchi-prod-root`, `targetRevision: main`, `argocd/prod`에서 `{platform/*.yaml,apps/*.yaml}`만 읽음. 자동 동기화(prune 끔, selfHeal 켬), 재시도 3회 | main 병합이 배포 승인이다. 하위 Application 파일을 지워도 배포된 리소스가 함께 지워지지 않도록 prune은 손으로 |
| sync wave 대기 | `resource.customizations.health.argoproj.io_Application`으로 하위 Application health를 root에 올림 | Argo CD 1.8부터 Application health가 꺼져 있어, 켜지 않으면 app-of-apps에서 다음 wave가 앞 wave의 Healthy를 기다리지 않는다 |
| 알림 | Notifications 켬, webhook 서비스 `discord`, 기본 구독으로 모든 Application의 동기화 성공·실패(같은 revision 1회)와 Health Degraded. webhook URL은 `argocd-notifications-secret`의 `discord-webhook-url`에 손으로. **webhook은 Argo CD 전용**(원본 Secrets Manager `sagomungchi/demo/argocd/discord-webhook`), Grafana 경보 webhook과 나눔(#1003, 2026-11-24 결정) | Grafana 경보와 같은 Discord 채널(확인 필요 기본안). 전송마다 webhook URL이 로그에 남는데 설정으로 끌 수 없어 값을 나눴다(아래 #1003). Argo CD에는 Discord 전용 서비스가 없어 webhook JSON(`content`)으로 보내고, 메시지는 `toJson`으로 따옴표를 처리 |
| CI | `ci-gitops.yml`의 kubeconform이 `argocd/` 전체(local·prod)를 이미 검사. `argocd.json`은 외부 chart values로 건너뛰기 목록에 추가 | 빠지면 app-service chart로 렌더링돼 실패한다(testing-ci 4절의 규칙) |

**확인 (2026-11-20, 저장소·로컬만, AWS 실행 없음)**

| 확인 | 결과 |
|---|---|
| `helm template`(Helm 4.3.1, `--kube-version 1.35.8`) | 52개 리소스. Deployment 5·StatefulSet 1·Job 1 모두 `application` 노드그룹 필수 배치, 위 자원 값 |
| kubeconform 0.8.0(ci-gitops와 같은 스키마 커밋, `-strict`) | `argocd/`·렌더 결과 60개 중 57개 통과, 실패 0. 건너뛴 3개는 Argo CD CRD 정의 자체 |
| 카탈로그 Argo CD 스키마 대조 | datreeio `27233a5`의 Application·ApplicationSet·AppProject 스키마와 v3.5.7 CRD의 필드 경로가 각각 1482·7893·73개로 모두 같음. testing-ci 4절의 "v3.5.5 일치 여부 미확인" 항목을 정리 |
| 별도 kind 클러스터(v1.35.8, 확인 뒤 삭제) | 같은 values(노드그룹 배치만 비움)로 설치 37초, Pod 6개 Running. 사용 메모리 controller 106Mi, 나머지 각 11~34Mi |
| root app, 하위 폴더 비어 있음 | 리소스 0개로 Synced·Healthy |
| sync wave 대기 | 시험용 하위 Application 2개(wave `1`은 readiness 60초 지연, wave `10`은 ConfigMap): root 동기화가 "waiting for healthy state of …/check-slow"로 63초 기다린 뒤 wave 10을 만들고 둘 다 Synced·Healthy |
| AppProject 제한 | 허용하지 않은 저장소와 `default` namespace 대상 Application은 `InvalidSpecError` |
| 알림 | webhook을 클러스터 안 echo 서버로 돌려 확인. root 수동 동기화 1회에 `{"content": "[Argo CD prod] sagomungchi-prod-root 동기화 성공, revision …"}` 1건(`Content-Type: application/json`), 하위 Application마다 1건 |

kind에서는 GitHub 대신 클러스터 안 git 서버(이 PR의 `argocd/prod` 파일 사본, 저장소 URL만 바꿈)를 썼다. 실제 Discord 수신, Health Degraded 알림, EKS 노드 배치와 자원 여유, `main`의 실제 GitHub 동기화는 11/25 A에서 처음 확인한다.

**A(11/25)·B(11/26~28)에서 할 일**: argocd CLI v3.5.7 준비 → `helm install`(README) → `argocd-notifications-secret` 생성 → `project.yaml`·`root-app.yaml` 적용 → root 수동 동기화 1회로 Discord 1건 → admin 비밀번호 변경·초기 Secret 삭제. B 런북 0·7단계에 넣었다.

**한계**: root app은 `argocd` namespace에 Application을 만들 수 있으므로, 하위 Application 파일이 다른 AppProject(`default` 등)를 가리키지 않는지는 PR 리뷰로 확인한다. 하위 Application이 생긴 뒤 root app·Argo CD를 지우면 배포된 리소스까지 지워질 수 있어 되돌리기는 손으로 확인하며 한다.

**webhook URL 로그 (#1003, 2026-11-24 A 계정 EKS)**

11/24 A 재가동에서 `argocd-notifications-controller` 로그에 Discord webhook URL 원문이 남는 것을 확인했다. 원인은 소스로 확인했다.

- notifications-engine `0cff13b8a717`(v3.5.7의 `go.mod`)의 webhook 서비스가 `go-retryablehttp` v0.7.8 `NewClient()`를 기본값 그대로 만든다.
- 기본 Logger는 Go 표준 `log`(stderr)이고, 요청마다 `[DEBUG] <메서드> <URL>`을 찍는다. URL에서 가리는 것은 비밀번호 부분뿐이다.
- `WebhookOptions`에는 Logger를 바꾸는 칸이 없다. upstream 기본 브랜치의 같은 파일(마지막 변경 `06152007e273`, 2026-01)도 같다.
- chart 10.11.7 values(`configs.params`의 `notificationscontroller.log.level`·`log.format`)는 logrus만 바꾸므로 이 줄에는 영향이 없다.
- 전송이 실패하면 오류 메시지 `request to {… URL} has failed`에도 URL이 들어간다.

| 시각(KST) | 설정 | 알림 | webhook URL 줄 수 |
|---|---|---|---|
| 11/24 14:12~20:35 (Pod 6시간 22분) | 설치값(`log.level=info`, `log.format=text`) | 동기화·Degraded 알림 44건 | 44 (`[DEBUG] POST` 44) |
| 11/24 20:36 | `argocd-cmd-params-cm`의 `notificationscontroller.log.level=error`로 바꾸고 controller 재시작. root app의 `notified.notifications.argoproj.io` 주석을 지워 동기화 성공 알림 1건을 다시 보냄(20:36:51) | 1건 | 1 (Argo CD info 로그는 사라졌는데 이 줄은 남음) |
| 11/24 20:37 | `info`로 되돌리고 재시작. Helm release는 바꾸지 않음(rev 1 그대로) | 0건 | 0 |

로그 원문은 출력하지 않고 `grep -c 'discord.com/api/webhooks'`로 건수만 셌다. 참고로 `log.format=text`인데도 Argo CD 자체 로그는 JSON으로 나왔고, 이 줄만 `2026/11/24 11:36:51 [DEBUG] POST …` 형식이다.

| 대안 | 판단 |
|---|---|
| 로그 수준·형식, webhook 서비스 옵션 | 끌 방법 없음(위 시험) |
| **Argo CD 전용 webhook 분리 (채택)** | 같은 `aws-alerts` 채널에 webhook을 하나 더 만든다. 로그에는 계속 남지만 Grafana 경보 webhook은 노출되지 않고, Argo CD 값만 따로 재발급할 수 있다. 저장소는 README의 Secret 출처만 바뀌고 `argocd.json`은 그대로다 |
| 클러스터 안 중계 프록시 | 로그의 URL은 사라지지만 B 구축(11/26~28) 전에 구성요소 1개를 더 만들고 시험해야 해서 채택하지 않음 |
| 그대로 두고 문서화 | 노출되면 Grafana 경보까지 함께 재발급해야 해서 채택하지 않음 |

Pod 로그는 클러스터 밖으로 모으지 않는다(Loki·Fluent Bit·CloudWatch 컨테이너 로그 없음). 노드의 컨테이너 로그와 `pods/log` 권한으로만 볼 수 있다. 로그를 볼 때는 README의 명령처럼 건수만 세거나 URL을 가린다. A·B 모두 기존 webhook을 폐기하고 Grafana용·Argo CD용 두 값을 새로 만든다(담당자 직접, 값 출력·기록 없음).

### 9.18.2 플랫폼 Application과 sync wave (#856)

손으로 하던 플랫폼 적용(prod README 2절, B 런북 7·7a·12단계)을 `infrastructure/gitops/argocd/prod/platform/`의 Application 10개로 옮겼다. 값은 기존 `environments/prod/*.json`을 그대로 참조하고(외부 chart는 `$values` 다중 source, manifest는 directory `include`), 내용은 바꾸지 않았다. B 값(`vpcId`·서브넷·SG·클러스터 이름)은 #809 6a PR이 같은 파일을 바꾸면 그대로 따라간다. 새 파일은 `environments/prod/namespaces.json`(namespace 4개) 하나다.

| wave | Application | 기다리는 것 |
|---|---|---|
| 0 | `prod-cluster-base` | namespace `app`·`platform`·`external-secrets`·`observability`, gp3 StorageClass |
| 1 | `prod-external-secrets` | ESO Deployment 3개 Ready(webhook 포함) |
| 2 | `prod-external-secret-resources` | SecretStore 2개·ExternalSecret 14개 Ready(Secrets Manager 값·ESO Pod Identity) |
| 3 | `prod-aws-load-balancer-controller` | LB Controller Ready. Service 변경 webhook이 `failurePolicy: Fail`이라 Service를 만드는 platform-data·관측보다 먼저 |
| 4 | `prod-platform-network` | platform 기본 거부·클라이언트 허용·Prometheus 수집 허용 |
| 5 | `prod-platform-data` | RabbitMQ·Redis StatefulSet, 초기화 Job Complete(`platform-data-credentials` 필요) |
| 6 | `prod-karpenter` | Karpenter 컨트롤러 Ready |
| 7 | `prod-karpenter-nodepool` | EC2NodeClass Ready(서브넷·SG·역할 확인), NodePool |
| 8 | `prod-observability` | Collector·Prometheus·Grafana·Tempo(관측 Secret 2개 필요) |
| 9 | `prod-app-network` | app 일회성 DB Pod·배포 확인 Pod egress, ALB → core:8080 |

앱 ApplicationSet은 wave 10(#857)이고, root app이 Application health를 보고 다음 wave로 넘어간다(#855 설정). 순서는 prod README 2절과 같다. 다른 점은 namespace·gp3를 맨 앞에 Git으로 두고, 관측 수집 정책(`observability-platform-network.json`)을 platform 정책과 같은 wave에 둔 것이다(대상 Pod가 없어도 해가 없음).

결정("확인 필요"는 기본안대로):
- CRD 동기화: ESO는 `ServerSideApply=true`. `secretstores`·`clustersecretstores` CRD가 각 약 740KB라 client-side apply의 last-applied 주석 한도(256KB)를 넘는다(임시 kind에서 SSA 없이 `metadata.annotations: Too long`으로 실패, SSA로 성공). Karpenter도 `ServerSideApply=true`. 로컬 KEDA의 `Replace=true`는 CRD를 지웠다 다시 만들 수 있어 쓰지 않았다. LB Controller CRD는 작아 기본 apply.
- CRD가 다른 Application에 있는 CR(ExternalSecret·SecretStore, EC2NodeClass·NodePool)은 `SkipDryRunOnMissingResource=true`. 같은 chart 안의 CR(LB Controller `IngressClassParams`)은 Argo CD가 자동으로 dry-run을 건너뛴다.
- webhook 인증서: LB Controller chart는 렌더링할 때마다 인증서를 새로 만들고(Argo CD 렌더링에는 `lookup`이 없음), ESO는 cert-controller가 실행 중에 caBundle을 채운다. 둘 다 `ignoreDifferences`(Secret `aws-load-balancer-tls` `/data`, webhook `caBundle`)와 `RespectIgnoreDifferences=true`로 첫 동기화 때 짝을 유지한다. 임시 kind에서 동기화 몇 분 뒤에도 두 Application이 Synced로 남는 것을 확인했다.
- prune·selfHeal: 플랫폼 10개는 prune 끔·selfHeal 켬, finalizer 없음(앱 ApplicationSet은 prune 켬, #857). RabbitMQ·Redis PVC는 StatefulSet `volumeClaimTemplates`라 원래 Argo CD 추적 대상이 아니고, 관측 PVC 3개는 chart의 `helm.sh/resource-policy: keep`에 더해 prune 끔으로 보호한다. namespace 4개에는 `Prune=false,Delete=false`를 붙였다. NodePool을 지우면 Karpenter 노드가 정리되므로 이것도 prune하지 않는다. 대신 Git에서 지운 자원은 클러스터에 남으므로 손으로 지운다. selfHeal 때문에 손 변경(관측 0으로 축소 등)은 root app과 해당 Application의 자동 동기화를 먼저 끄고 한다.
- 범위: platform-data·관측도 함께 옮겼다(기본안). 빠진 것: core Ingress(origin 헤더 실제 값이 Git 밖), 관측 Secret 2개, `app/rds-ca` ConfigMap(손으로). `karpenter-nodepool-explanation.json`·`sllm-server.json`은 #835에서 이미 지워져 대상이 없다.
- 실패 재시도: 플랫폼은 `retry` 5회(30초부터 2배, 최대 5분). CRD 등록·webhook 기동 순간의 일시 오류를 넘기기 위함이다. platform-data 초기화 Job은 이름에 값 해시가 있어 같은 커밋 재시도에서 다시 돌지 않는다.
- 문서 정정: `external-secret-resources.json`은 SecretStore 2개·ExternalSecret 14개(prod README·B 런북 7단계의 "12개"를 고침).

확인(2026-11-20, AWS 실행 없음):
- 외부 chart 3개를 prod 값으로 `helm template`(Helm 4.3.1): 객체 종류·webhook·CRD 크기 확인.
- 임시 kind 클러스터(`kindest/node:v1.35.8`, 기존 `sagomungchi-local`과 분리, 확인 뒤 삭제)에서 두 번 확인했다. 1차는 argo-cd chart 10.18.2(Argo CD v3.6.2)·project `default`, 2차는 #855와 같은 chart 10.11.7(v3.5.7)과 `environments/prod/argocd.json`(kind에 없는 노드 affinity만 뺌)·AppProject `sagomungchi-prod`(#855 `project.yaml`)다. 사본은 `targetRevision: develop`으로만 바꿨다. 10개 모두 manifest 생성 성공(`List` 펼침 16·2·3개, `include` 여러 파일, `$values` JSON, Karpenter OCI). Karpenter OCI chart는 두 버전 모두 저장소 선언(`enableOCI`) 없이 받아졌다. 자동 동기화를 켠 6개 중 cluster-base·platform-network·app-network·LB Controller·ESO는 Synced/Healthy(몇 분 뒤에도 Synced 유지), ExternalSecret은 AWS 자격 증명이 없어 Degraded다. 실제로는 이 지점에서 다음 wave가 멈춘다. ESO를 SSA 없이 동기화하면 CRD 주석 크기 초과로 실패하는 것도 1차에서 확인했다. 2차에서 `prod-cluster-base`가 destination namespace가 비어 AppProject에 거부되는 것을 찾아 `kube-system`으로 고쳤다. Karpenter·NodePool·platform-data·관측은 AWS·EBS가 없어 동기화하지 않았다.
- 새 `namespaces.json`과 Application 10개는 kubeconform 0.8.0으로 검사(ci-gitops와 같은 스키마 위치).

11/25 A에서 할 일: root app 전에 관측 namespace·Secret 2개 → root app 동기화 → wave 0~9 Synced/Healthy, `kubectl get externalsecret -A` 14개 Ready, `kubectl get nodepool,ec2nodeclass`(EC2NodeClass Ready), Grafana 로그인. 걸린 시간과 막힌 wave를 이 절에 적는다.

한계: 실제 EKS에서의 ESO·LB Controller·Karpenter 동작, EC2NodeClass Ready, observability PVC 바인딩은 11/25 A에서 처음 확인한다. A·B에서 막히면 비상용 수동 Helm(prod README 2절)으로 해당 단계만 적용하고, 그 Application의 자동 동기화를 끈 상태로 둔다.

### 9.18.3 앱 ApplicationSet과 migration PreSync (#857)

#### 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| ApplicationSet | [`argocd/prod/apps/applicationset.yaml`](../../infrastructure/gitops/argocd/prod/apps/applicationset.yaml): list generator 6개(core·learning·ai·scoring·report-api·report-worker, `sllm-server` 제외), Application `prod-<앱>`, project `sagomungchi-prod`, chart·values 모두 `targetRevision: main`(multi-source `$values`), namespace `app`, root app sync-wave `"10"` | 로컬 ApplicationSet과 같은 구조. main이 운영 값의 기준이다 |
| 값 파일 | `environments/prod/<앱>.json`(설정) + `images/<앱>.json`(이미지) 순서. 이미지 파일 키는 `image.repository`·`image.digest`, core·learning·report-api는 `migration.image.repository`·`migration.image.digest`·`migration.revision`. 설정 파일에서는 같은 키를 지웠다. 값은 develop(A 계정)의 것을 그대로 옮겼다 | develop이 `images/`를 건드리지 않으면 develop → main 릴리스 병합(3-way merge)에서 main의 digest(#858 PR이 갱신)가 남는다. 서비스마다 파일을 둬 digest PR diff가 서비스 단위로 보인다 |
| migration | `migrations/*.json` 덮어쓰기 파일을 없애고 env·자원·`rds-ca` 볼륨·`networkPolicy.migrationEgress`를 설정 파일에 합쳐 `migration.enabled: true`. chart의 PreSync 훅(NetworkPolicy wave -2 → Job wave -1)이 앱보다 먼저 돈다. report-api는 앱 이미지 안의 Alembic(`alembic upgrade head`) | Argo CD가 그리는 조합 하나로 Job·앱을 함께 관리한다 |
| revision·훅 정책 | Job 이름 `<앱>-migrate-<revision>`, `hook-delete-policy: HookFailed`(chart 그대로). 성공한 Job은 남아 같은 revision이면 다시 돌지 않고, 실패한 Job은 지워져 다음 동기화 때 다시 만들어진다. revision은 새 migration이 있을 때만 바꾼다 | named 훅은 한 번만 만들어진다. 실패 이력은 Argo CD 동기화 결과에 남는다 |
| 동기화 정책 | automated, `prune: true`, `selfHeal: true`, retry 없음. ApplicationSet `preserveResourcesOnDeletion: true` | 같은 커밋에서 실패한 자동 동기화는 다시 시도되지 않으므로 실패한 migration이 저절로 반복되지 않는다. selfHeal은 손 변경을 main 값으로 돌린다(비상용 Helm 경로는 먼저 자동 동기화를 끔) |
| 순서 | 앱 NetworkPolicy·ExternalSecret·`app` namespace는 플랫폼 Application(#856)이 wave 10보다 먼저. 앱 사이 순서는 두지 않음 | 앱마다 Application이라 scoring이 모델 경로 문제(#809)로 Degraded여도 다른 앱 동기화는 막히지 않는다 |
| `rds-bootstrap` | 훅으로 옮기지 않고 B 런북 8·10단계에서 손으로 | RDS master secret을 쓴다 |
| 비상용 경로 | `redeploy-app.ps1`은 두 파일을 함께 넘기고 앱 release에는 `--set migration.enabled=false`를 덧붙인다(Helm은 PreSync 훅을 일반 리소스로 만든다). `-Migration`·`-ImageDigest`·`-Revision`은 이미지 파일의 임시 사본을 바꾼다. 매개변수는 그대로라 cd-release deploy job도 그대로 동작한다 | 12/7 시연까지 비상용으로 남긴다 |
| CI | `ci-gitops` prod 렌더링이 앱마다 두 파일을 넘기고(전체 렌더링에 migration 훅 포함), ApplicationSet 목록과 `images/` 파일 이름이 같은지 본다. `cd-candidate`는 `images/**`와 migration을 가진 설정 파일 3개 변경에서도 돈다 | ApplicationSet과 같은 조합을 검사한다 |

#### 확인 (2026-11-20, AWS·클러스터 실행 없음)

- `helm template`: 앱 6개를 develop(설정 파일 하나)과 이 변경(두 파일)으로 그려 비교했다. 앱 리소스는 같고, 차이는 migration 3개 서비스에 PreSync NetworkPolicy·Job이 더해진 것뿐이다. 그 둘은 develop의 `<앱>.json` + `migrations/<앱>.json` 렌더링과 같다(이미지 digest·revision·env·볼륨). `redeploy-app.ps1` 앱 경로 조합(`migration.enabled=false`)은 develop 앱 렌더링과 같다.
- kubeconform 0.8.0(ci-gitops와 같은 버전·스키마 커밋, Kubernetes 1.35.8): 6개 렌더링과 `argocd/`(새 ApplicationSet 포함) 40개 리소스 모두 valid.
- 로컬 kind(`sagomungchi-local`, Kubernetes 1.35)에 migration NetworkPolicy·Job 3쌍을 `kubectl apply --dry-run=server`로만 넘겨 API 서버가 받는 것을 확인했다(클러스터 변경 없음). 이 클러스터에는 지금 Argo CD가 없어 ApplicationSet 생성은 보지 못했다.
- `scripts/tests/test_cd_migration_runner.py`(실제 helm·pwsh로 `redeploy-app.ps1` 렌더링·순서·멱등·실패 처리, 앱 release에 두 파일과 `migration.enabled=false`가 넘어가는 시험 추가) 16개, `test_cd_*` 전체, `test_aws_account_switch.py`·`test_aws_demo_stack.py` 통과.
- 실제 Argo CD 동기화(PreSync 순서·훅 보존·자동 동기화 1회)는 11/25 A 재가동에서 확인한다.

#### 한계와 11/25 A에서 볼 것

- ApplicationSet 자체의 health를 root app wave가 기다리는지는 #855의 Argo CD 설정에 달려 있다.
- A 첫 동기화에서 migration Job 3개(`core-service-migrate-main-c6809ddb65ee`, `learning-service-migrate-main-c6809ddb65ee`, `report-api-migrate-b67d8a462b6b`)가 Complete인지, 그 뒤 앱 6개 Synced/Healthy, 로그인 → 학습 제출.
- `images/`는 main에서 #858 digest PR이 바꾼다. B 계정 번호 교체(런북 선행 2)는 `images/`도 바꾸므로 develop과 main 양쪽 값을 맞춰야 한다.

### 9.18.4 cd-release digest PR 전환 (#858, 2026-11-20)

| 결정 | 내용 | 근거 |
|---|---|---|
| 배포 승인 | cd-release의 deploy job 대신 digest-pr job이 `environments/prod/images/**`만 고친 브랜치를 push하고, 사람이 실행 요약 링크로 main 대상 PR을 연다(11/24 변경, 아래). 그 PR 승인·병합 = 배포 승인 | Argo CD가 Git을 읽으므로 승인 지점을 Git 변경에 둔다. 승인·병합 기록이 그대로 배포 기록이 됨 |
| 대상 파일 | `policy.json` `delivery`: 서비스 5개 → release 파일 6개(report-service → report-api·report-worker), migration 값은 core·learning·report-api. 키는 #857 계약(`image.repository`·`image.digest`, `migration.image.*`·`migration.revision`) | 서비스 목록·파일 대응을 한 곳에 두고 `cd_release.py`가 검증 |
| 게이트 | validate에서 `--check-images`(파일·키 구조, 이미지 빌드 전), digest-pr에서 `--require-executable --write-images`. 하나라도 틀리면 파일을 하나도 쓰지 않음. 저장소 주소가 다르면 오류, 계정 전환 때만 `allowRepositoryChange`(서비스 5개 전부일 때) | 다른 계정·레지스트리 digest가 섞이지 않게 |
| PR 기준 | 실행 SHA가 아니라 그때의 main HEAD에서 images 파일을 고침. 본문에 원본 SHA와 기준 HEAD를 함께 | 앞서 병합된 digest PR을 덮어쓰지 않음 |
| PR 생성 | (11/24 변경) workflow는 `GITHUB_TOKEN`(`contents: write`만)으로 브랜치 push까지. 커밋 메시지를 1행 제목 + 빈 줄 + PR 본문으로 만들어(`git commit --cleanup=verbatim -F`) compare 링크(`compare/main...<브랜치>?expand=1`)에서 제목·본문이 채워진다. 사람이 연 PR이라 `ci-gitops`가 `pull_request`로 돈다 | 11/20 안(`gh pr create` + `ci-gitops` dispatch)은 조직 정책으로 실패. 새 토큰·도구 없이 되는 방식(CD README PR 생성 토큰 표) |
| 승인자 | main 보호 규칙 필수 리뷰 1명 + CODEOWNERS(김동섭·김태윤), PR을 연 사람과 다른 code owner가 승인, status check 필수 아님 | #760 승인자 수 결정(1명 기본안, 팀장 확인 전)과 같게. 경로 필터 CI를 필수로 걸면 릴리스 PR이 대기함 |
| 브랜치 규칙 | "main은 develop에서만" 예외: images만 바꾸는 PR은 main 직접 병합. develop은 images 파일을 고치지 않음 | main에 digest 커밋이 쌓여도 develop → main 병합에서 충돌 없음(3-way에서 develop 쪽 변경 없음) |
| 이력 | digest PR + Argo CD sync 이력. `cd_record.py` artifact는 비상용 Helm 경로에서만 | PR 본문에 원본 SHA·digest·계획 JSON·호환성 근거가 남음 |
| 되돌리기 | digest PR revert(같은 승인). Argo CD UI rollback은 쓰지 않음. rollback 계획은 비상용 Helm에서만 | UI rollback은 Git과 어긋나 다음 자동 동기화가 되돌림. DB는 되돌리지 않음(7.1 원칙 유지) |
| 비상용 | `delivery: helm-emergency`로 예전 deploy job(작업자 PC runner) 실행. 12/7 시연 뒤 runner·job 정리 | Argo CD 경로가 막혔을 때 첫 배포 수단을 남김(에픽 대체안) |

- 변경 사유(2026-11-24, #986): 11/24 첫 실행에서 digest-pr job의 `gh pr create` 단계가 실패했다. 조직(SKNETWORKS-FAMILY-AICAMP) 정책이 "Actions가 PR을 만들고 승인하는 것"을 막고 있고, 조직은 정책을 바꿀 수 없다고 답했다. 이미지 빌드·ECR 게시·images 파일 갱신·브랜치 push는 됐다.
- 결정(2026-11-24 팀장): workflow는 digest 브랜치 push와 실행 요약의 PR 만들기 링크까지 하고, **PR은 사람이 링크로 연다.** job 권한은 `contents: write`만 남기고 `gh pr create`·`gh workflow run ci-gitops.yml` 단계를 지웠다. 게이트(`--require-executable`·`--write-images`·images 밖 변경 차단)는 그대로다. 승인 → 병합 → Argo CD 자동 동기화 → PreSync migration → revert 복구 흐름도 그대로다. 기각한 대안: deploy key(SSH push용이라 PR API를 못 부르고, main 직접 push는 승인 단계가 없어지며 보호 규칙과 충돌), 개인 계정 포크(OIDC 신뢰·Argo CD repoURL·변수·문서를 모두 바꿔야 하고 배포 기록이 포크에만 남음), 개인 토큰 PAT(만료·보안 관리 부담, 조직 차단 가능성).
- 저장소 설정(main 보호 규칙, Code Owners 리뷰)은 관리자 손 작업으로 11/24 develop → main 릴리스 뒤 적용한다. 예전 "Actions PR 생성 허용" 단계는 조직 정책상 켤 수 없어 뺐다. 절차는 [CD README B2](../../infrastructure/cd/README.md#b2-digest-pr-저장소-설정-858-관리자-손-작업-1124-예정).
- 11/25 A 확인 순서: cd-release 실행 → 실행 요약 링크로 PR 열기(제목·본문 채워짐) → `pull_request` ci-gitops → 다른 code owner 승인·병합 → Argo CD Synced/Healthy → `verify_cd_deployment.py` 결과 PR 댓글 → revert 병합으로 이전 버전 복구 → 최신으로 다시 배포([CD README](../../infrastructure/cd/README.md#1125-a-계정-확인-절차-858)). 결과는 이 절에 덧붙인다.
- 확인(2026-11-20, GitHub·AWS 실행 없음): `scripts/tests` 시험(images 파일 계약 fixture), digest-pr job 셸 단계 모의 실행(임시 저장소·로컬 bare 원격·가짜 `gh`): 파일 6개만 바뀐 커밋, `cd/prod-images-main-<SHA 12자리>-<run id>` 브랜치 push까지. 11/24 변경 뒤에는 `test_cd_deployment.py`가 권한(`contents: write`만), `gh pr create`·`gh workflow run` 없음, `-F` 커밋, compare 링크를 검사한다.
- 한계: PR 작성자는 링크로 연 사람이라 본인 승인이 세지 않는다. 다른 code owner(동섭 ↔ 태윤)가 없으면 병합할 수 없다(막히면 비상용 Helm 경로). PR 열기가 사람 손이라 링크를 열지 않으면 브랜치만 남고 배포되지 않으며, 오래된 digest 브랜치·PR은 사람이 닫고 지운다. 11/20 안의 한계였던 "봇 작성자라 실행한 사람도 승인 가능"과 "`GITHUB_TOKEN` PR에는 ci-gitops 외 `pull_request` CI가 돌지 않음"은 사람이 PR을 열면서 없어졌다. #857 병합으로 생긴 실제 images 파일 6개는 `RealImagesFileTests`가 구조를 검사한다.

## 9.19 B 복원용 스냅샷의 고객 관리 KMS 키 공유 (#809, 2026-11-23)

2026-11-18 결정 "B DB는 A 최종 RDS 스냅샷 복원"(9.16.2 A-2)에는 A 쪽 단계가 한 줄로만 있었고, 런북 일정에는 언제 하는지가 없었다. 11/25 A 재가동(#927)이 B 부트스트랩(11/26~27) 바로 앞이라 A 종료 직전에 해야 한다는 점을 절차로 넣었다. 이 정리에서 AWS는 조회도 변경도 하지 않았다.

### 9.19.1 결정

| 항목 | 결정 | 이유 |
|---|---|---|
| 11/19 최종 스냅샷 | `sagomungchi-demo-db-final-20261119`은 B에 쓰지 않는다 | AWS 관리 키(`aws/rds`)로 암호화돼 키 정책을 바꿀 수 없어 다른 계정과 공유할 수 없다. 11/25 재가동에서 migration·시연 데이터(#897 재동의 등)로 DB가 바뀌어 그 뒤 상태가 B에 필요하다 |
| 시점 | 11/25 A 확인이 모두 끝난 뒤, A RDS 정지·삭제 직전(9.16.2 A 11단계) | 그 뒤 A DB는 바뀌지 않는다. RDS가 켜져 있어야 새 스냅샷을 뜰 수 있다 |
| 키 | A에 고객 관리 KMS 키(CMK)를 하나 두고 키 정책에 B 주체를 허용 | 다른 계정이 복사·복원하려면 원본 키를 B가 쓸 수 있어야 하고, 그 허용은 고객 관리 키에서만 된다 |
| A 순서 | 새 수동 스냅샷 → CMK로 `copy-db-snapshot --kms-key-id` → `modify-db-snapshot-attribute --attribute-name restore --values-to-add <B 계정>` | RDS는 인스턴스 키로 스냅샷을 만들므로 키를 바꾸려면 복사가 필요하다. 공유는 CMK 복사본만 |
| B 순서 | B 작업자 IAM에도 A CMK 허용 → 공유 스냅샷을 B 키로 복사 → 복사본으로 복원 | 다른 계정 키는 키 정책과 호출자 IAM 정책이 둘 다 있어야 쓸 수 있다. B 소유 복사본을 만들어 두면 그 뒤 복원은 A 키·A 계정에 기대지 않는다 |
| 보존 | CMK·공유 스냅샷·A-K2 원본·A DB 계정 값 6개·`PAYMENT_BILLING_ENCRYPTION_KEY`는 B 복원 확인 전까지 지우지 않음 | 키 삭제를 예약하면 대기 기간(7~30일) 동안에도 키를 쓸 수 없어 B가 복사·복원하지 못한다. 복원 DB는 A 계정 비밀번호와 A 결제 암호화 키로 만든 값을 그대로 갖는다(9.16.2 A-3) |
| B 번호가 늦을 때 | 11/25에는 키 생성·스냅샷·CMK 복사까지, B 허용과 공유는 번호를 받은 뒤 | 두 작업은 A RDS가 꺼져 있어도 된다 |

실행 절차와 명령 예시는 [AWS README B 런북 "선행 (A 계정, 11/25 A 종료 직전)"](../../infrastructure/aws/README.md#선행-a-계정-1125-a-종료-직전)(A-K1~A-K5)과 같은 런북 5단계 "RDS 복원"이다.

### 9.19.2 비용·시간 (실행 전 추정)

| 항목 | 값 | 근거·상태 |
|---|---|---|
| KMS 고객 관리 키 | 키당 월 $1(시간 비례), 요청 1만 건당 $0.03 | AWS 공개 가격. 실행 전 가격 페이지로 다시 확인 |
| 스냅샷 저장 | A-K2 원본·A-K3 CMK 복사본·B 복사본이 각각 전체 크기로 과금될 수 있음(할당 20GiB gp3) | 서울 리전 GB-월 단가와 실제 사용량은 확인 필요 |
| 스냅샷 생성·CMK 복사·B 복사 시간 | 확인 필요 | 11/19 최종 스냅샷 소요 시간 기록이 없다. 11/25·B 실측을 이 절에 덧붙인다 |

### 9.19.3 남은 확인

- B 계정 번호와 B 복원 주체(B 루트 위임 또는 복원 역할 하나)
- 11/25 실행 결과(스냅샷·복사 시각, 키 ARN은 적지 않고 별칭만), B 복원 결과와 A 쪽 보존 자원 정리 시점

## 9.20 추억 그림책 prod 설정과 A 확인 절차 (#974, 2026-11-24)

PR #966(추억 그림책 PDF 발급)이 develop에 들어갔지만 prod report-worker에 그림 받기 허용 출처가 없어, 실서버에서는 그림이 모두 빠진 PDF가 완성(READY)으로 나갈 수 있었다. 결정 E2(`docs/proposals/memory-book-decisions.md`)대로 A 계정에서 한 번 돌려 보기 전에 저장소 설정을 맞췄다. 이 정리에서 AWS는 조회도 변경도 하지 않았다.

### 9.20.1 설정과 근거

| 항목 | 값·상태 | 근거 |
|---|---|---|
| 그림 허용 출처 | `report-worker.json`에 `MEMORY_BOOK_ASSET_ORIGINS=https://sagomungchi-demo-347161580747-missions.s3.ap-northeast-2.amazonaws.com` | learning은 `ASSET_S3_BUCKET`(missions)·`S3_REGION`으로 AWS SDK v2 `S3Presigner`를 만들고 `endpointOverride`가 없다(`S3_PUBLIC_ENDPOINT_URL` 없음). 그래서 서명 URL은 virtual-hosted 방식 regional 주소 `https://<버킷>.s3.<리전>.amazonaws.com/theme-drafts/…`다. 버킷 이름에 점이 없어 경로 방식으로 바뀌지 않는다. `asset_fetcher.py`는 `scheme://host[:port]`를 소문자로 비교하므로 경로·쿼리 없이 출처만 넣는다. `scripts/tests/test_runtime_config.py`가 두 파일 값이 맞는지 본다 |
| 클러스터 안 주소 치환 | prod에는 넣지 않음(`MEMORY_BOOK_ASSET_INTERNAL_ORIGINS` 없음) | kind의 MinIO용이다. prod는 S3에 바로 연결한다 |
| 크기 상한 | 기본값 그대로: 그림 1장 5MiB(`MEMORY_BOOK_IMAGE_MAX_BYTES`), 1권 40MiB(`MEMORY_BOOK_TOTAL_MAX_BYTES`), 그림 1장 10초(`MEMORY_BOOK_ASSET_TIMEOUT_SECONDS`) | ai 테마 그림은 장면마다 PNG 1장이고 1권은 최대 7장(표지·월~금·엔딩)이다. 실제 크기는 9.20.2 6단계의 D6 측정으로 확인한다. 장당 2MB를 넘으면 상한이 아니라 축소(Pillow)를 더하는 것이 D6 기준이다 |
| egress | 바꾸지 않음 | report-worker NetworkPolicy에 이미 443 → S3 대역 9개(서울 S3 prefix list 대역, report-api·scoring과 같음)가 있다. private 라우팅 테이블 2개는 S3 Gateway endpoint(`sagomungchi-demo-vpce-s3`, 기본 정책)로 가므로 NAT를 거치지 않는다(5절, #212). regional 주소라 서울 대역 안이고, global 주소(`s3.amazonaws.com`)는 쓰지 않는다. 서명 URL은 learning 역할의 `s3:GetObject`(`theme-drafts/*`)로 서명돼 report-worker에는 S3 권한이 필요 없다. DNS(53)는 chart 기본 허용 |
| RabbitMQ | 바꾸지 않음 | 큐 `report.memorybook.generate`(재시도 3개·DLQ)·`core.memorybook.events`와 바인딩(`cmd.direct` `memorybook.generate`, `events.topic` `memorybook.completed`)은 공용 `charts/platform-data/files/rabbitmq/definitions.json`에 있고 prod도 같은 파일을 쓴다. 권한(`import-definitions.sh`): report 읽기에 `report.memorybook.generate`, topic 쓰기에 `memorybook.completed`, core 읽기에 `core.memorybook.events`. 초기화 Job 이름에 definitions 해시가 들어 있어 platform-data를 새 revision으로 동기화하면 다시 돈다 |
| 구독·KEDA | 바꾸지 않음 | report-worker는 Pod 1개(`replicaCount: 1`, HPA·KEDA 꺼짐)가 큐 3개(삭제·리포트·그림책)를 각자 채널, `CONSUMER_PREFETCH=1`로 구독한다. 큐는 passive로만 확인하므로 **platform-data가 앱보다 먼저 동기화돼야** 한다(Argo CD wave 5 → 앱). 큐가 없으면 report-worker가 기동에 실패한다. 리포트 1건과 그림책 1권이 동시에 Chromium을 띄울 수 있다(메모리 한도 1Gi, E4·[9.20.3](#9203-e4-메모리-측정과-limit-상향-1006-2026-11-24)) |
| core V57 | 바꾸지 않음 | `V57__memory_book_jobs.sql`은 core-migrate 이미지에 들어 있고 digest PR의 `migration.revision`(`main-<SHA>`)으로 PreSync Job이 앱보다 먼저 돈다(9.18.3). 상품 값도 이 migration이 넣는다: `price = 0` 상품 `features.memoryBook=false`, `price > 0` 상품 `true`, 모든 상품 `limits.dailyMemoryBooks=3`. 결정 B1(유료 상품 전체)·B2(자녀당 하루 3권)와 같다. 따로 넣는 seed·상품 SQL은 없다 |
| 기존 구독 | 그대로 동작 | V57 전에 만든 구독 스냅숏(시연 `prepare-demo-account-students.sql` 포함)에는 두 키가 없다. 이때 `features.memoryBook`은 구독 중이면 허용, `limits.dailyMemoryBooks`는 무료 상품 값(V57 뒤 3)을 쓴다(`ProductEntitlementService`). 결과는 B1·B2와 같다 |
| B 계정 | 계정 번호 교체에 포함 | 출처에 missions 버킷 이름(계정 번호)이 들어 있다. `scripts/aws_account_switch.py`가 prod `*.json`을 바꾸므로 같이 바뀐다. 리전이 바뀌면 `s3.<리전>`과 S3 egress 대역도 바꾼다([AWS README B 런북](../../infrastructure/aws/README.md#a-계정-값-교체)) |

그림이 빠지는 경우(2026-11-24 결정): `asset_fetcher.py`는 받지 못한 그림만 빈 칸으로 둔다. #974 당시에는 그림을 하나도 받지 못해도 READY로 끝났고, #975부터는 아래 "실행 중 실패"처럼 FAILED로 끝난다.
- 설정 누락: 허용 출처가 비면 report-worker가 뜰 때 경고 로그(`MEMORY_BOOK_ASSET_ORIGINS`가 비어 있어 그림 없이 만듦)를 남긴다(#974). 같은 워커가 리포트·자녀 삭제 큐도 처리하므로 기동은 막지 않는다. 값이 맞는지는 `test_runtime_config`가 PR에서 본다.
- 실행 중 실패(#975 반영): 그림 주소가 있는데 한 장도 받지 못하면 `memory_book/service.py`가 PDF를 만들지 않고 FAILED `ASSET_UNAVAILABLE`로 끝낸다. 사용 예약은 미사용으로 마감해 한도를 쓰지 않는다. 일부만 빠지면 그 칸만 비우고 READY다. 그래서 A·B 확인에서는 지금처럼 그림 수를 직접 센다(일부 누락은 READY로 나오므로).

### 9.20.2 11/25 A 확인 절차

전제: 이 설정(#974)이 들어간 main이 A에 배포돼 있다. 11/25까지 main에 없으면 이 브랜치의 `report-worker.json`으로 report-worker만 다시 배포하거나(`redeploy-app.ps1`, 비상용 Helm 경로) 그림 확인을 다음 배포 뒤로 미룬다. Argo CD가 관리하는 Deployment에 `kubectl set env`로 넣으면 다음 동기화에서 되돌아간다. 명령의 `<A>`는 A 프로필, `<ID>`는 시연 자녀·그림책 ID다. 측정값은 #974 댓글에 남긴다.

| # | 단계 | 명령·방법 | 확인 |
|---|---|---|---|
| 1 | 설정 | 아래 명령 1 | report-worker env에 출처 1개, RabbitMQ 그림책 큐 2개에 consumer 1 |
| 2 | V57·상품 값 | `demo-db-oneoff.k8s.yaml`로 core_db에 읽기 전용 쿼리(아래 SQL) | `flyway_schema_history` 57 `success=true`, 무료 `false`·유료 `true`, 모든 상품 `3` |
| 3 | 발급 | 유료 시연 학부모로 웹 "리포트·AI 챗봇" → 그림책 → 액자가 있는 회차 1개 발급. 동시에 명령 2(메모리)를 돌린다 | 화면이 "만드는 중" → "받기", 작업 READY |
| 4 | 받기 | 같은 화면 "받기"로 PDF 저장 | PDF가 열리고 9쪽 안팎 |
| 5 | 그림 들어갔는지 | 명령 3(PDF 그림 세기)과 report-worker 로그 | 그림 수 = 그 회차 그림 수(엔딩을 봤으면 7, 아니면 6), 로그에 `그림책 그림 건너뜀` 0줄 |
| 6 | D6 그림 크기 | 명령 4(원본 크기)와 명령 3의 가로·세로 | 장당 최대 크기. 2MB를 넘는 그림이 있으면 D6대로 축소를 더할지 정한다 |
| 7 | E4 메모리 | 명령 2 결과의 최댓값, 재시작 수 | 최대 메모리가 한도(1Gi, 11/24 A 측정 때는 768Mi)의 몇 %인지, `restartCount` 변화 없음·`OOMKilled` 없음 |

```powershell
# 명령 1: 설정·큐·구독
kubectl -n app get deploy report-worker -o jsonpath='{.spec.template.spec.containers[0].env[?(@.name=="MEMORY_BOOK_ASSET_ORIGINS")].value}'
kubectl -n platform exec rabbitmq-0 -- rabbitmqctl list_queues name consumers messages | Select-String memorybook

# 명령 2: 발급 동안 report-worker 메모리(2초 간격, 발급이 끝나면 Ctrl+C) 뒤 재시작 수
while ($true) { kubectl -n app top pod -l app.kubernetes.io/name=report-worker --containers --no-headers; Start-Sleep 2 }
kubectl -n app get pod -l app.kubernetes.io/name=report-worker -o jsonpath='{range .items[*]}{.metadata.name} {.status.containerStatuses[0].restartCount} {.status.containerStatuses[0].lastState.terminated.reason}{"\n"}{end}'
kubectl -n app logs deploy/report-worker --since=30m | Select-String '그림책 그림 건너뜀'

# 명령 4: 원본 테마 그림 크기(큰 순 5개, 2MB 초과 수)
aws s3api list-objects-v2 --bucket sagomungchi-demo-347161580747-missions --prefix theme-drafts/ --profile <A> --query 'reverse(sort_by(Contents[?ends_with(Key, `.png`)], &Size))[:5].[Key, Size]' --output table
aws s3api list-objects-v2 --bucket sagomungchi-demo-347161580747-missions --prefix theme-drafts/ --profile <A> --query 'length(Contents[?ends_with(Key, `.png`) && Size > `2097152`])'
```

명령 3은 작업자 PC의 Python 가상 환경에 `pypdf`를 설치해 받은 PDF 경로를 넘긴다. PDF 안의 그림(Form XObject 안쪽 포함)마다 쪽·가로·세로·압축 크기를 출력한다.

```python
import sys
from pypdf import PdfReader

def images(resources, seen):
    for ref in (resources or {}).get("/XObject", {}).values():
        obj = ref.get_object()
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        if obj.get("/Subtype") == "/Image":
            yield obj
        elif obj.get("/Subtype") == "/Form":
            yield from images(obj.get("/Resources"), seen)

reader, total = PdfReader(sys.argv[1]), 0
for number, page in enumerate(reader.pages, 1):
    for obj in images(page.get("/Resources"), set()):
        total += 1
        print(number, obj["/Width"], obj["/Height"], obj.get("/Filter"), len(obj._data))
print("pages", len(reader.pages), "images", total)
```

```sql
SELECT version, success FROM flyway_schema_history WHERE version = '57';
SELECT code, price, active, features -> 'memoryBook' AS memory_book, limits -> 'dailyMemoryBooks' AS daily FROM product ORDER BY price;
SELECT status, failure_code, size_bytes, created_at, completed_at FROM memory_book_job ORDER BY created_at DESC LIMIT 3;
```

- 마지막 SQL의 칸 이름은 V57 기준이다. 다르면 `\d memory_book_job`으로 맞춘다.
- B(시연)에서는 같은 절차를 B 런북 경로 확인 뒤 한 번 더 한다(#927 B 항목).

### 9.20.3 E4 메모리 측정과 limit 상향 (#1006, 2026-11-24)

11/24 A에서 9.20.2 7단계(명령 2, 2초 간격 `kubectl top`)로 그림 6장(엔딩 전 회차) 그림책 1권을 발급하는 동안 report-worker 최대 메모리는 **669Mi / limit 768Mi(87%)**였다. 재시작·`OOMKilled`는 없었다. 엔딩을 본 회차(그림 7장)나 주간 리포트와 겹치면 limit을 넘을 수 있어 limit만 올렸다.

| 항목 | 전 | 후 | 근거 |
|---|---|---|---|
| prod `report-worker.json` | requests 256Mi·limits 768Mi | requests 256Mi·**limits 1Gi** | 측정 최대 669Mi에서 약 355Mi 여유. 그림 7장 회차·리포트와 겹치는 경우가 이 안에 드는지는 B에서 잰다(아래 남은 확인) |
| local `report-worker.yaml`(kind도 이 파일) | 같음 | 같음(limits 1Gi) | prod와 같은 PDF 경로라 같은 값으로 맞췄다 |
| requests | 256Mi | 256Mi(그대로) | 스케줄링은 requests 기준이라 노드 배치·Karpenter 확장·비용이 바뀌지 않는다 |

동시 처리: report-worker는 Pod 1개, 큐마다 채널 `CONSUMER_PREFETCH=1`이라 그림책은 Pod 안에서 한 번에 1권씩이다. 겹칠 수 있는 것은 그림책 1권 + 주간 리포트 1건(full·free 2판 Chromium)이다. 이번 변경에서 동시 처리 수 제한(E4)은 더하지 않았다. 둘지 여부는 B 측정 뒤 정하고, replica나 prefetch를 늘리면 다시 잰다.

노드 여유(저장소 값 기준, AWS 조회 없음):
- ResourceQuota·LimitRange: `app` namespace를 포함해 저장소에 정의가 없다. limit 상향을 막는 제한이 없다.
- 관리형 노드 그룹 `application`: t3.medium(메모리 4GiB) 2대. limit 1Gi는 노드 한 대에 들어간다. limits 합은 requests와 달리 노드 용량을 넘을 수 있고(overcommit), 실제 사용이 늘 때만 노드 압박이 생긴다. 11/24 A의 같은 노드 실제 사용 약 62%, requests 합 67%(#1006)였고 requests가 그대로라 67%도 그대로다.
- Karpenter NodePool `application-burst`(t3.medium·t3.large, limits CPU 4·메모리 16Gi): NodePool `limits`는 만드는 노드 용량의 합이라 Pod limit과 관계없다. report-worker에 nodeSelector가 없어 어느 노드에 가도 1Gi보다 노드가 크다.

확인: `helm lint --strict`와 `helm template`(prod는 `images/report-worker.json`까지, kube 1.35.8)에서 prod·local 모두 limits memory 1Gi·requests 256Mi. `test_runtime_config`·`test_memory_book_contract` 14개, `test_cd_*` 101개 통과.

남은 확인(B): develop → main 릴리스로 B 첫 배포에 들어간 뒤, B에서 엔딩을 본 회차(그림 7장) 1권 발급 중 최대 메모리를 9.20.2 명령 2로 재고 limit 1Gi의 몇 %인지, 재시작·`OOMKilled`가 없는지 #1006에 적는다. 90%를 넘으면 limit을 더 올릴지, 그림책과 리포트가 동시에 렌더링하지 않게 할지 정한다.

## 9.21 S3 수명 주기: 추억 그림책 (#975, 2026-11-24)

2026-11-24 결정 C3([결정 기록](../proposals/memory-book-decisions.md)): 보관 기간(30일)이 지난 추억 그림책 PDF는 S3 수명 주기 규칙으로 지운다. 이 절은 규칙 정의만 다룬다. prod report-worker 설정과 A 계정 확인 절차는 #974다.

### 9.21.1 확인한 것

- `reports` 버킷(`infrastructure/aws/demo-stack.json` `buckets`)에는 수명 주기 규칙이 없었다. `demo_stack.py`는 버킷의 버전 관리·공개 차단·기본 암호화만 만들고 대조했다(AWS 계정은 조회하지 않고 코드와 정의 파일만 확인).
- 버킷은 **버전 관리가 켜져 있다**. 현재 버전만 만료하면 삭제 표시만 생기고 이전 버전이 남으므로 이전 버전 만료와 남은 삭제 표시 정리도 함께 둔다.
- S3 수명 주기 규칙은 대상을 **접두어 하나(와일드카드 없음)나 객체 태그**로만 고른다. 결정 문구의 `reports/*/memory-books/`처럼 학생 ID가 가운데 있는 키는 고를 수 없다.

### 9.21.2 결정과 변경

- 그림책 키를 `reports/{studentId}/memory-books/{bookId}/pdf`에서 `reports/memory-books/{studentId}/{bookId}/pdf`로 옮겼다(`backend/report-service/app/clients/storage.py`). report IAM(`report-s3-role`)은 `reports/*`라 권한을 바꾸지 않는다(E1 "IAM 변경 없음" 유지). 객체 태그 방식은 `s3:PutObjectTagging` 권한 추가와 B 계정 IAM 반영이 필요해 쓰지 않았다.
- 학생 삭제(P09)는 그대로 `delete_prefix("reports/{studentId}/")` 한 번이고, 저장소가 `reports/memory-books/{studentId}/`도 함께 지운다. 허용 모양은 학생 전체, 리포트 판, 그림책 한 권(`reports/memory-books/{s}/{b}/`)뿐이다.
- prod에는 아직 그림책 파일이 없어 옮길 파일은 없다. 로컬에서 옛 키로 만든 파일은 받기가 410(보관 기간 지남)이 되고, 학생 삭제의 `reports/{studentId}/` 아래라 그대로 지워진다.

### 9.21.3 규칙 정의 (`demo-stack.json` `bucketLifecycle`, apply 안 함)

| ID | 대상 | 동작 |
|---|---|---|
| `memory-book-expire` | 접두어 `reports/memory-books/` | 현재 버전 35일 뒤 만료(30일 보관 + 여유 5일, core 만료 판정보다 늦게), 이전 버전 1일 뒤 삭제 |
| `memory-book-delete-markers` | 접두어 `reports/memory-books/` | 남은 삭제 표시 정리(`ExpiredObjectDeleteMarker`) |

- 여유 5일: core는 `expires_at`(발급 + 30일)으로 받기를 막고, S3는 객체 생성일부터 일 단위로 세어 자정(UTC) 기준으로 지운다. 파일은 발급 직후 만들어지므로 35일이면 core 만료 뒤에만 지워진다.
- `demo_stack.py plan`은 정의와 실제 규칙을 비교해 다르면 DIFF로 보여 준다. `apply`는 **규칙이 하나도 없는 버킷에만** 이 정의를 넣는다. `put-bucket-lifecycle-configuration`은 버킷의 규칙 전체를 바꾸므로, 다른 규칙이 이미 있으면 덮어쓰지 않고 DIFF로 남겨 사람이 합친다.
- 이 PR에서는 AWS에 적용하지 않았다. 적용은 #974의 A 계정 확인 일정에서 `plan`으로 차이를 본 뒤 `apply --confirm-account`로 한다.
- 시험: `scripts/tests/test_aws_demo_stack.py`(정의가 그림책 접두어만 고름·35일·이전 버전·삭제 표시, 빈 버킷에만 넣고 다른 규칙은 덮지 않음), report `tests/test_memory_book_generation.py`(새 키 모양, 한 권·학생 전체 삭제, 위험한 접두어 거부).

## 9.22 시연 도메인 www.sagomungchi.co.kr 전환 (2026-11-24)

시연 주소를 CloudFront 기본 주소(`https://d3jf0rnm6vhd9v.cloudfront.net`)에서 `https://www.sagomungchi.co.kr`로 바꿨다. 계정과 무관한 주소라 A→B 계정 전환(#809) 때 앱·OAuth·CD 값을 다시 바꾸지 않아도 된다. 아래 AWS·가비아 작업은 동섭이 손으로 했고, 이 PR은 저장소 값과 문서만 바꾼다.

### 9.22.1 한 일

| 항목 | 값·상태 | 비고 |
|---|---|---|
| 도메인 구입 | 2026-11-24 가비아 `sagomungchi.co.kr`, 네임서버는 가비아 | |
| DNS | 가비아 `www` CNAME → `d3jf0rnm6vhd9v.cloudfront.net` | B 계정 때는 대상만 B CloudFront 기본 주소로 바꾼다 |
| 인증서 | us-east-1 ACM, `www.sagomungchi.co.kr`·`sagomungchi.co.kr`, DNS 검증(가비아 CNAME), ISSUED | CloudFront는 us-east-1 인증서만 쓴다 |
| A CloudFront | `EW2QD9OAPEVRK`에 대체 도메인 `www.sagomungchi.co.kr`, 위 인증서, 보안 정책 TLSv1.2_2021 | 루트는 별칭에 넣지 않았다 |
| 루트 주소 | 가비아 포워딩으로 `https://www.sagomungchi.co.kr`에 넘길 예정 | 루트(apex)에는 CNAME을 둘 수 없어 CloudFront에 직접 연결하지 않는다 |
| core `AUTH_WEB_ORIGIN` | prod `core-service.json`에서 `https://www.sagomungchi.co.kr` | 아래 9.22.2 |
| 스크립트 기본값 | `verify-viewer-ip.ps1`, `evaluation/load/core-load.js`, `evaluation/load/README.md` | 요청 Origin이 `AUTH_WEB_ORIGIN`과 같아야 하므로 함께 바꿨다 |

### 9.22.2 `AUTH_WEB_ORIGIN` 하나만 바꾼 근거

- core는 웹 주소를 `AuthProperties.webOrigin`(`app.auth.web-origin`, 환경변수 `AUTH_WEB_ORIGIN`) 하나로만 받는다. 이 값으로 Google OAuth callback(`/api/v1/auth/google/callback`)·재인증 callback(`/api/v1/auth/google/reauth/callback`)과 로그인 뒤 이동 주소(`/oauth/complete`, `/login?oauthError=…`)를 만들고, `PublicAuthFilter`가 쿠키 인증 경로(refresh·학생 로그인 등)의 `Origin` 헤더를 이 값과 정확히 비교한다.
- 값은 경로·끝 `/` 없는 origin이어야 한다(`AuthProperties` 초기 검사, `TokenServiceTest`). 그래서 여러 주소를 허용할 수 없다.
- 다른 서비스는 웹 주소를 받지 않는다. 결제 성공·실패 주소와 재인증 주소 검사는 웹이 `location.origin`으로 만들고, 웹 빌드 env에도 주소가 없다(웹과 API가 같은 origin). 리포트·알림에 웹 링크를 넣는 설정도 없다.
- **예전 주소로는 로그인이 안 된다.** `https://d3jf0rnm6vhd9v.cloudfront.net`으로 열면 화면은 뜨지만 Google 로그인은 callback이 새 주소로 돌아가고, refresh·학생 로그인은 Origin 불일치로 403이다. 2026-11-24에 이를 받아들이기로 했다. 쿠키는 host 단위라 예전 주소에서 받은 refresh·`student_device` 쿠키는 새 주소에서 쓰이지 않으므로 다시 로그인·기기 등록을 한다(CD 경로 확인 fixture 포함).

### 9.22.3 손으로 바꿀 것 (저장소 밖)

| 대상 | 값 |
|---|---|
| Google OAuth 클라이언트 → 승인된 JavaScript 원본 | `https://www.sagomungchi.co.kr` |
| Google OAuth 클라이언트 → 승인된 리디렉션 URI | `https://www.sagomungchi.co.kr/api/v1/auth/google/callback`, `https://www.sagomungchi.co.kr/api/v1/auth/google/reauth/callback` |
| GitHub Environment `prod` 변수 `CD_BASE_URL` | `https://www.sagomungchi.co.kr` |

예전 cloudfront.net origin·callback은 B 전환이 끝날 때까지 지우지 않아도 된다(core가 새 값만 쓰므로 영향 없음).

### 9.22.4 B 계정

도메인은 그대로 쓰고 앱 값(`AUTH_WEB_ORIGIN`, OAuth, `CD_BASE_URL`)은 바꾸지 않는다. B에서는 us-east-1 ACM 인증서 재발급(가비아 검증 CNAME 추가) → A CloudFront에서 대체 도메인 떼기 → B CloudFront에 붙이기 → 가비아 `www` CNAME 대상 변경 순서로 한다([AWS README 확인 필요 표](../../infrastructure/aws/README.md#확인-필요)). 같은 대체 도메인은 두 배포에 동시에 둘 수 없어 바꾸는 동안 잠깐 끊긴다.

### 9.22.5 남은 확인 (A 재가동 뒤)

이 PR은 develop 병합 → develop→main 릴리스(#623) → A 재가동으로 반영된다. 아래는 아직 확인하지 않았다.

- `https://www.sagomungchi.co.kr` 웹 첫 화면과 인증서, `sagomungchi.co.kr` 포워딩
- 학부모 Google 로그인·재인증, 학생 기기 로그인(refresh 403 없음)
- `verify_cd_deployment.py --base-url https://www.sagomungchi.co.kr` 경로 확인(fixture 쿠키를 새 주소에서 다시 받은 뒤)
- 예전 주소에서 로그인이 막히는 것(예상 동작)

## 9.23 표현 분류 재학습 이미지 ECR 게시와 digest 고정 (#985, 2026-11-24)

MLOps 단계 점검(11/24)에서 재학습 이미지 배포가 빠져 있었다. `ml/tox/Dockerfile`(#729)을 운영 ECR에 올리는 경로가 없었고, #730 CronJob이 쓸 digest도 없었다. 새 도구 없이 cd-release의 `main-<SHA>` 불변 태그·재사용 규칙과 digest PR(#858·#986)을 그대로 쓴다.

### 9.23.1 결정

| 항목 | 결정 | 근거 |
|---|---|---|
| 빌드 시점 | 선택값. 계획에 `"jobs": ["tox-retrain"]`이 있을 때만 빌드·게시(2026-11-24 동섭) | 이미지가 약 1.89GB(CPU torch)라 앱 릴리스마다 빌드하면 runner 시간·ECR 용량이 커진다. 재학습 코드는 앱보다 드물게 바뀐다 |
| 앱 없는 계획 | `"services": []` + `jobs` 허용 | 재학습 이미지만 바꿀 때 앱을 억지로 넣지 않는다. 호환성 여섯 항목 근거 규칙은 그대로 |
| 고정 위치 | `infrastructure/gitops/environments/prod/images/tox-retrain.json`(`image.repository`·`image.digest`), `policy.json` `delivery.jobImageFiles` | 앱과 같은 images 폴더라 digest PR·CODEOWNERS·revert 규칙을 그대로 쓴다. 앱 ApplicationSet 목록과는 따로 둔다(ci-gitops 목록 검사에서 제외) |
| 비상용 Helm 경로 | `jobs`가 있으면 거부 | Helm 경로는 앱 release만 적용한다. 작업 이미지는 digest PR로만 고정 |
| 계정 전환 | `allowRepositoryChange`는 서비스 5개 + `jobs` 전부일 때만 | 작업 이미지 파일만 A 레지스트리로 남는 혼재를 막는다 |
| PR 확인 | `ci-ml-tox` `image` job이 `docker build -f ml/tox/Dockerfile .`만(push·로그인 없음) | 빌드 깨짐을 릴리스 전에 본다. `ml/tox/**`·`scripts/prepare_model_upload.py`가 바뀐 PR에서만 돈다 |

### 9.23.2 바꾼 것

- `cd-release.yml`: validate가 `jobs`를 출력하고, publish가 `sagomungchi/tox-retrain`을 `-f ml/tox/Dockerfile .`로 게시한다(같은 `publish` 함수). digest-pr의 PR 열기 링크 단계는 바꾸지 않았다.
- `scripts/cd_release.py`: `JOBS`, `jobs` 검증(deploy만, 저장소 이름 `tox-retrain`, `images` 키 = services ∪ jobs), `jobImageFiles` 정책 검사, images 파일 갱신·PR 본문에 작업 이미지 포함.
- IAM `github-cd-publish-role.inline.ecr-push.json`과 `demo-stack.json` `ecrRepositories`에 `sagomungchi/tox-retrain`(ECR 8개 → 9개).
- `images/tox-retrain.json`의 처음 digest는 `sha256:0…0` 자리표시다. 첫 `jobs` 실행 digest PR이 실제 값으로 바꾼다.

### 9.23.3 사람이 할 일 (AWS, 아직 하지 않음)

| 계정 | 할 일 | 순서 |
|---|---|---|
| A | ECR `sagomungchi/tox-retrain` 생성(IMMUTABLE, AES256) → 게시 역할 인라인 `ecr-push` 다시 넣기 → `jobs` 계획으로 cd-release 한 번 → digest PR에 `tox-retrain.json` 갱신 확인 | [CD README 작업 이미지 게시](../../infrastructure/cd/README.md#작업-이미지-게시-tox-retrain-985) 표 1~3. A 재가동(11/25) 중 앱 digest PR 확인 뒤 |
| B | 6a PR(계정 번호 교체) 뒤 `demo_stack.py apply`가 저장소와 역할 정책을 함께 만든다(B 런북 1단계). 첫 digest PR은 서비스 5개 + `"jobs": ["tox-retrain"]` + `allowRepositoryChange=true`(16단계) | [AWS README B 런북](../../infrastructure/aws/README.md#b-계정-전환-런북-809) |

### 9.23.4 #730 CronJob 연결 (후속)

#730(`feature/tox-retrain-kind`)의 차트는 `.Values.image`를 문자열로 받고 kind용 `imagePullPolicy: Never`다. prod Application을 만들 때 values에 `images/tox-retrain.json`을 같이 넘기고, 차트가 `image.repository`·`image.digest`로 `<저장소>@<digest>`를 만들게 한다(앱 chart와 같은 방식, prod는 `IfNotPresent`). 자리표시 digest인 동안에는 prod CronJob을 켜지 않는다.

## 9.24 관측 chart 검증 스크립트 동기화 (#996, 2026-11-24)

`verify_chart.py`가 현재 chart·운영 values를 따라가지 못해 정상 설정도 실패로 판정했다. #984에서 일부 검사를 뺀 임시 사본으로 실행한 이력을 확인하고, 검사를 유지한 원본 스크립트를 수정했다.

- trace pipeline의 processor 이름을 `transform/trace_urls`로 맞췄다. `trace_statements`의 첫 그룹만 보던 검사를 모든 그룹의 `conditions`·`statements`로 넓혀 Google callback 조건·query 삭제와 토스 billing/payment 키 치환을 함께 확인한다. 아키텍처 문서의 이전 processor 이름도 고쳤다.
- prod 앱 렌더는 CI·ApplicationSet처럼 `prod/<서비스>.json` 다음 `prod/images/<서비스>.json`을 전달한다. 분리된 repository·digest를 읽고 기존 OTLP·Java agent 설정을 계속 검사한다.
- 작업 시작 시 develop `9e075979`로 실행하면 위 두 검사보다 먼저 기준 리소스 비교가 실패했다. #984 대시보드를 현재 chart에서만 껐기 때문이다. 기준 chart에서도 같은 옵션을 적용하며, 대시보드를 켠 local·prod의 provisioning 검사는 별도로 유지한다.
- 기본 baseline `de8e225`, #984 이전 `75ddc7fe`, 작업 시작 기준 `9e075979`, 이후 반영한 develop `35fa87d9` 각각 default·local·baseline-prod 렌더가 같은지 확인했다(12조합 통과).

API 변경 없음. 애플리케이션 동작·DB·chart·배포 values 변경 없이 검증 스크립트와 설명을 동기화했다. 이 PR이 영향을 주는 CI는 `ci-gitops`, `ci-contracts`의 저장소 전체 계약 검사, `ci-secrets`다. `verify_chart.py`의 Docker 경보 검사는 CI에 포함되어 있지 않으므로 별도로 실행하며, CI 자동 편입은 이 이슈의 범위 밖이다.

완료 확인 명령:

```powershell
python infrastructure/gitops/operational-alerts/verify_chart.py --helm <helm-실행파일> --baseline 9e075979
```

`verify_chart.py`의 검증은 Python `assert`를 사용하므로 이 명령에는 `-O`를 붙이지 않는다. 저장소 계약 검사는 해당 CI의 명령인 `python -O -m unittest discover -s scripts/tests -v`로 실행한다.

CI와 같은 Linux 환경에서 Helm 4.3.1 lint 17조합과 환경별 렌더 25파일, prod ApplicationSet·이미지 파일 목록 일치를 확인했다. kubeconform 0.8.0·Kubernetes 1.35.8·CI 고정 스키마로 45파일의 187개 리소스를 검사해 전부 유효했고 오류·건너뜀은 없었다. core·learning migration 이미지 빌드도 모두 통과했다(이미지 게시·DB 적용 없음).

위 원본 명령은 검사를 제외한 사본 없이 끝까지 종료 코드 0으로 통과했다. 격리 Docker에서 Grafana 규칙 16개, 경보 발생·반복 억제·회복, 큐별 DLQ, 비용·미산정 비용, 인증 오류율·지연, NoData·잘못된 쿼리·없는 datasource, 재적용 중복 방지, 수집 중단·job 제거를 확인했다. 알림은 내부 네트워크의 로컬 수신 대역으로 전달했고 검증용 컨테이너·네트워크는 종료 후 제거했다.

최신 develop `35fa87d9`를 반영한 Linux 전체 계약 검사도 429개 실행, 실패 0개, 건너뜀 1개로 통과했다. 건너뜀은 원문 HWP 폴더가 필요한 기존 검사 하나다. 코드·설정 변경 범위를 다시 대조하고 `git diff --check`도 통과했다. 원격 PR CI 결과와 별도로 수행한 로컬 검증 결과다.

## 9.25 로컬 kind 표현 분류 재학습 (#730)

chart의 기본값은 `suspend: true`다. 로컬 kind values에서만 `suspend: false`를 지정해 예약 실행을 켠다.

`app/tox-retrain`은 일요일 03:00(Asia/Seoul)에 실행된다. 같은 CronJob의 예약 실행은 겹치지 않으며 실패한 Pod는 재시도하지 않는다. 로컬 요청은 CPU 1개·메모리 2560Mi, 상한은 CPU 2개·메모리 3Gi이고 Job 기한은 40분이다. 이 값은 [#729의 CPU 실측](../../ml/tox/results/eval_tox.md)에 여유를 둔 로컬 설정이다.

Job이 MinIO에서 지난 실행 기준을 읽고 learning에 새 라벨 수를 묻는다. 200건 미만이면 정상 종료한다. 200건 이상이면 임시 볼륨에서 학습하고, 모델을 MinIO에 올린 뒤 core에 후보로 등록하고 `last.json`을 갱신한다. 활성화는 운영자 승인 대상이다. Job에는 Kubernetes API 토큰을 마운트하지 않는다. Pod의 송신과 수신 측 정책은 DNS, learning, core, MinIO 통신을 허용한다.

### 로컬 설치와 수동 실행

1. [kind 설치 절차](../../infrastructure/kind/README.md)에 따라 Calico, platform 데이터 서비스, 앱을 준비한다. `app-service-credentials`에 서로 다른 내부 토큰과 MinIO 접속 키가 있어야 한다. learning·core는 `INTERNAL_TOKEN_OPS`를 읽고 Job은 같은 값을 `INTERNAL_TOKEN`으로 읽는다. 기존 Secret에 OPS 키를 처음 넣었다면 learning·core Pod를 새로 띄워 환경변수를 반영한다.
2. local core·learning values와 [platform NetworkPolicy](../../infrastructure/gitops/policies/local/platform.yaml)를 함께 적용한다. 활성 `tox-` 모델과 비공개 MinIO 버킷의 공개 데이터 묶음은 [이미지 실행 전제](../../ml/tox/README.md)에 맞춰 준비한다.
3. 저장소 루트에서 이미지를 빌드하고 대상 kind에 넣는다. 아래 명령은 기본 개발 클러스터 이름을 사용한다. 수동 실행 전 이미 실행 중인 재학습 Job이 있는지 확인한다. `Forbid`는 사람이 직접 만든 Job 사이의 중복을 막지 않는다.

```powershell
docker build -f ml/tox/Dockerfile -t sagomungchi/tox-retrain:local .
kind load docker-image sagomungchi/tox-retrain:local --name sagomungchi-local
helm upgrade --install tox-retrain infrastructure/gitops/charts/tox-retrain -n app --kube-context kind-sagomungchi-local -f infrastructure/gitops/environments/local/tox-retrain.yaml
kubectl --context kind-sagomungchi-local -n app get jobs -l app.kubernetes.io/name=tox-retrain
$job = 'tox-retrain-manual-' + (Get-Date -Format yyyyMMddHHmmss)
kubectl --context kind-sagomungchi-local -n app create job $job --from=cronjob/tox-retrain
kubectl --context kind-sagomungchi-local -n app logs -f job/$job
kubectl --context kind-sagomungchi-local -n app get job $job
```

종료 코드 0은 학습 완료와 라벨 부족에 공통이다. 로그의 `skip reason=not_enough_labels`는 건너뜀을 뜻한다. 학습 성공은 `stage=register`·`stage=last_write` 완료와 모델 등록부의 새 `REGISTERED` 행으로 확인한다. 실행 중인 Pod에는 임시 자료가 있으며 완료된 Job의 로그는 Kubernetes의 이력 보관 범위에서 조회할 수 있다.

로컬 observability release에 [local values](../../infrastructure/gitops/environments/local/observability.yaml)를 적용하면 Prometheus가 같은 Pod의 kube-state-metrics에서 `app`의 Job·CronJob 상태를 읽는다. Grafana에서 최근 24시간 내 생성된 재학습 Job의 최종 실패와 활성 스케줄의 5분 초과 지연을 확인한다. 예약 중단 시에는 일정 지연 경보를 제외한다. 로컬에서는 Discord로 발송하지 않는다.

### 2026-11-23 격리 kind 실행 기록

전용 `kind-skn730` 클러스터에 Calico, PostgreSQL, MinIO, 실제 core·learning·scoring 이미지를 배포했다. core DB는 V56, learning DB는 V27까지 적용했다. 입력은 학습용 합성 라벨 200건, 고정한 BEEP·APEACH 일부, 무작위 초기화한 소형 BERT였다. 200건 중 한 건을 보류한 뒤 첫 검증이 끝나고 추가했다.

| 수동 Job | 결과 | 등록부·MinIO 대조 |
|---|---|---|
| `kind730-retrain-199` | 4초, 새 라벨 199건으로 건너뜀, 종료 코드 0 | 기존 활성 모델 1개, 후보 파일 0개, 진행 기록 없음 |
| `kind730-retrain-200` | 12초, 학습·평가·업로드·등록, 종료 코드 0 | 후보 `tox-kind-fixture:20261123-1200` 1개가 `REGISTERED`·`NOT_RECOMMENDED`, 후보 파일 5개와 `last.json` 생성, 기존 활성 모델 유지 |

재학습 Pod와 같은 라벨을 준 점검 Pod에서 DNS 조회와 core:8080·learning:8081·MinIO:9000 TCP 연결이 성공했다. PostgreSQL:5432·scoring:8001 직접 연결은 시간 초과였다. 검증용 소형 모델의 12초로 운영 모델의 학습 시간이나 EKS 적정 CPU를 산정할 수 없으며, 이번 실행의 최고 메모리는 측정하지 않았다.

| 경보 시험 | 관측 결과 |
|---|---|
| 존재하지 않는 로컬 MinIO 버킷으로 수동 실행 | `last_read`에서 `NoSuchBucket`, 종료 코드 11. Job의 최종 실패 지표가 1이 되고 Grafana 실패 경보 발화 |
| 배치할 수 없는 CPU 256개 요청, 시험 Job 기한 20초 | Pod가 `Pending / Insufficient cpu`에 머물다가 Job이 `DeadlineExceeded`로 실패. 컨테이너가 시작되지 않아도 Grafana 실패 경보 발화 |
| 격리 클러스터의 마지막 예약 시각을 15일 전으로 설정해 일정 누락 모의 | 지연 경보 발화. `suspend: true`에서 해제됐고 시험 후 주간 일정과 상태를 복원 |

kind API 서버는 호스트 네트워크를 사용한다. 지표 수집기의 API 접근은 Calico의 `default/kubernetes` Service 대상 송신 정책으로 확인했다. Prometheus에서 수집 대상이 `up=1`이었고 수집기 계정의 권한은 `app`의 Job·CronJob 조회로 제한했다.

로컬에서 `ci-gitops`의 Helm·kubeconform 단계를 실행해 리소스 193개가 모두 유효했고 건너뜀은 0개였다. prod 관측 values로 렌더링한 Kubernetes 객체 21개를 변경 전과 대조했다. 원격 CI 및 Discord 수신은 이 로컬 검증에 포함하지 않았다.

운영 노드 배치, AWS 권한과 Discord 수신은 11/26 결정으로 A에 먼저 넣었다(9.35). EKS 노드 여유와 실제 학습 데이터 사용 결정(#887)을 운영 활성화 전에 확인한다.

## 9.26 A 계정 11/24 재가동 기록 (#927, 2026-11-24)

9.16.2 순서로 A 계정(347161580747, ap-northeast-2)을 11/19 종료 상태에서 다시 올렸다. 첫 배포는 Argo CD(9.18), Helm 경로는 server dry-run만 했다(11/20 결정). 원래 11/25 예정이던 것을 하루 앞당겼다. 모든 시각은 KST, 수행 구분은 **A**(실서버)다. 작업 폴더는 저장소 밖 `aws-demo-state/restart-20261124`(로그·설정 백업)이다.

### 9.26.1 기준 커밋

| 시각 | 커밋 | 내용 |
|---|---|---|
| 13:57:30 | main `abcbb9d4` | develop→main 릴리스 #987 |
| 14:10:04 | main `c2ed78b0` | #986(digest PR을 사람이 링크로 여는 방식)만 담은 릴리스 #989. #987이 #988보다 22초 먼저 병합돼 따로 올렸다 |
| 14:43:54 | main `e5082cd6` | digest PR #991 병합(images 6개를 `main-c2ed78b0d04e`로). 김태윤이 merge commit으로 병합, GitHub 리뷰 승인 기록 0건 |
| 17:12:35 | main `cfc04538` | #858 revert 확인용 PR #1008(#991 digest를 11/06 값으로 되돌림) |
| 17:26:06 | main `54d12a9a` | 복구 PR #1010(images 6개를 다시 `main-c2ed78b0d04e`로, #991과 같음) |

런북(9.16.2·9.18)은 #987 전 main에 없어서 1~4단계는 develop `e9f55e37` 사본으로 실행했다. 두 커밋의 인프라 스크립트는 같다.

### 9.26.2 단계별 결과

| 시각 | 9.16.2 단계 | 결과 |
|---|---|---|
| 13:40 | 1 `plan` | DIFF 3·MISSING 2: NAT MISSING, private route 2개가 삭제된 NAT(blackhole), EKS MISSING, **reports 버킷 수명 주기 DIFF**(#975 규칙, 버킷에 규칙 없음) |
| 13:43~13:54 | 2★ RDS 시작 | `start-db-instance` → available 13:53:55(약 10분). 데이터는 11/19 22:38 상태(core V53·learning V22) |
| 13:43~13:46 | 3★ `apply`·route | NAT `nat-08dbd4b301a48a3bb`(새 EIP), reports 수명 주기 규칙 2개 생성(`apply`가 규칙 없는 버킷에만 넣음), private route 2개 `replace-route` |
| 13:48~14:05 | 4★ EKS | `render-eksctl`(작업자 IP가 바뀌어 공개 접근 CIDR만 11/17과 다름) → `eksctl create cluster` 16분 38초. 노드 4대(application·platform-observability 각 2, 2a·2b). `apply --after-eksctl` 새로 만든 것 없음, `plan` OK=67(노드그룹 OK, 9.16.1의 8번 확인) |
| 14:09 | #760 dry-run | Argo CD 전 `app` namespace만 두고 `redeploy-app.ps1 -AllowInstall`(적용 없음): migration 3개 NetworkPolicy·Job `created (server dry run)`, 앱 6개 `First install … pending-install`, 모두 exit 0. 클러스터 변경 없음 |
| 14:12~14:14 | 9.18.1 설치 | argo-cd 10.11.7 `helm install` 50초, Pod 6개 모두 `application` 노드. `argocd-notifications-secret`·관측 Secret 2개(Secrets Manager 값을 출력 없이 전달)·`app/rds-ca`·`project.yaml` |
| 14:14~14:24 | #858 cd-release | run 45331865412(서비스 5개, `delivery=pull-request`): validate 9초·publish 9분·digest-pr 9초. 브랜치는 main HEAD 위 커밋 1개, `images/*.json` 6개만, digest 9개가 ECR `main-c2ed78b0d04e` 태그와 같음 |
| 14:45~14:55 | root app | `root-app.yaml` 적용 뒤 10분 14초에 Application 17개(root·플랫폼 10·앱 6) Synced/Healthy |
| 14:56 | `rds-bootstrap` | 1회(24초). DB 3개 PUBLIC CONNECT 회수, 로그인 계정 2개씩 |
| 14:57~15:01 | 7★ ALB·CloudFront | 11/17 Ingress 적용 → ALB `sagomungchi-demo-core-15704624…` active 14:59:30, target healthy. `EW2QD9OAPEVRK`의 `core` origin `DomainName`만 교체(변경 전 설정 `cf-before.json`, 바뀐 필드 1개) → Deployed 15:01:12 |
| 15:00 | 8★ SageMaker | 예약 확장 재개(`ScheduledScalingSuspended=false`), IC InService·사본 0 |
| 15:01~15:02 | 9 웹 | main `e5082cd6` 빌드(`npm ci`·`npm run build`, production-mocks 통과) → assets → 기타 → `index.html`(no-cache) → `/*` 무효화. `index.html` 버전 `5tWfC2…` → `WWFiIGxo…`, 서빙 index·`index-DbXry-S3.js`가 로컬 빌드와 sha256 같음, 첫 화면 콘솔 오류 0 |
| 15:21 | 10 경로 확인 | `verify_cd_deployment.py --base-url https://www.sagomungchi.co.kr`: ok=true, 6단계 모두 ok(student-login·pick-mission·start-attempt·read-answer·parent-refresh·list-reports). 결과는 #991 댓글 |

- 런북과 다르게 한 것: 5단계(플랫폼 손 Helm)와 6단계(cd-release 첫 배포)는 Argo CD 경로로 바꿨다(9.18, 동섭 확인). `rds-bootstrap`은 앱 동기화 뒤 한 번만 했다. ESO가 만드는 DB Secret이 있어야 돌 수 있는데 root app은 wave 9 다음 바로 앱 migration으로 넘어간다. A DB는 11/17에 이미 계정·권한·`vector`가 있어 migration은 막히지 않았다.
- digest를 root app 전에 바꾼 이유: develop·main의 `images/*.json`이 11/06 빌드(`main-322e7976b26a`, migration은 11/05 `main-c6809ddb65ee`)를 가리켜, 그대로 붙이면 11/06 앱이 V53 DB 위에 올라간다. 그래서 digest PR을 먼저 병합하고 root app을 붙였다.
- fixture: 11/19 쿠키는 예전 도메인 것이라 새로 받았다. fixture 학부모(`smoke601a`, 자녀 부하1)로 새 주소에 로그인 → V54 법정대리인 동의 1.1 재동의 → 기기 등록·학생 로그인. 쿠키는 `Path=/api/v1/auth`·`/api/v1/auth/student`라 개발자 도구에서는 그 경로 주소를 열어야 보인다.

### 9.26.3 #927 A 칸 결과

| 항목 | 결과 |
|---|---|
| #760 | 위 dry-run 통과. 비상용 Helm 경로 확인 끝 |
| #855 | 설치·`project.yaml`·`root-app.yaml`·root Synced. Discord 채널에 동기화 알림 수신 확인(동섭, 14:45·14:52 알림). admin 비밀번호는 동섭이 port-forward 웹 화면에서 변경(`argocd-secret`의 `admin.passwordMtime` 17:52:23, 값은 작업자에게 공유하지 않음). 초기 비밀번호는 화면 출력 없이 클립보드로만 넘겼다. 변경 뒤 `argocd-initial-admin-secret` 삭제(17:52), Argo CD Pod 6개 Running·Application 17개 Synced/Healthy 유지 |
| #856 | 플랫폼 10개 Synced/Healthy, ExternalSecret 14개 Ready, EC2NodeClass `application` Ready, NodePool `application-burst`(노드 0) |
| #857 | migration Job 3개 Complete(core V54~V57 4개 → v57, learning V23~V27 5개 → v27, report Alembic 변경 없음) → 앱 6개 Synced/Healthy, 재시작 0 → 경로 확인 ok(학습은 이미 답변이 있는 진행 중 시도라 `read-answer`) |
| #858 | cd-release → digest 브랜치 → 사람이 링크로 PR #991 → 병합 → Argo CD 동기화 → 경로 확인 PR 댓글. revert 복구 1회는 아래 9.26.6. 승인 기록 없이 병합된 것은 위 9.26.1 |
| #910 | core 활성 목록에 `PROMPT` 행 0개 → ai는 내장 `report-explanation@4` 사용, ai readiness `versions: UP`. `/internal/versions`는 ops 토큰이 없어(9.13 남은 것과 같음) Pod 안 내장 버전 표로 대신 확인 |
| #897 | 시연 학부모 `teamparent1`로 `demo_account_data.py children --child 부하1:5`(15:24): 계정 동의 저장·법정대리인 재동의 → `/me` READY, `guardianConsentRequired=false`. A에는 #624 시연 계정이 아직 없다(B에서 만들 때 새 버전으로 동의) |
| #691 | 동섭이 관리자 화면에서 `tox-koelectra-small 1.0-1119`(범위 `answer-filter`) 등록·승인·활성화. scoring 로딩 확인, 활성 tox 1개. 1,500자 1칸 20회(scoring Pod 안): 혼자 p50 315·**p95 332**·최대 352ms, M2 실제 추론과 같이 p50 915·**p95 1,061**·최대 1,063ms(같은 시간 M2 6건 p50 3.0초), 모두 200. 메모리 522Mi → 최대 591Mi(limit 2Gi), CPU 최대 656m, 재시작 0. M2와 같이 돌 때 p95가 마감 1.3초에 약 240ms 남는다 |
| #974 | 아래 9.26.4 |
| #900 | Tempo 직접 검색, 범위 14:45~16:3x: 토스 청구 0건·취소 0건·콜백 `url.query` 0건. Google 로그인 콜백 span 2건(15:06·15:07)은 query가 지워져 있음 → 새 도메인 Google 로그인도 확인. 재인증: 18:04 동섭이 Google 계정 학부모로 "보호자 비밀번호 Google 본인 확인"만 하고 비밀번호는 정하지 않음. `GET /api/v1/auth/google/reauth/callback` span 1건(200)에 `url.path`·`http.route`만 있고 `url.query` 없음, `code=` 포함 span 0건. 같은 trace의 Google token·certs 호출은 `url.full`에 query 없음. 24시간 전체 범위 확인은 B |
| #882 | API 읽기만: 운영 홈 건수(문의·신고·실패 작업 0)와 도착 목록 건수 일치, PAYMENT_VIEW 없는 관리자는 환불 카드·목록 모두 막힘. 편성표 G3·G5 11/23~12/14 4주 모두 미편성·잠금 없음, READY 후보 15개. 화면(18:1x, `teamadmin1`, 읽기·화면 조작만): 운영 홈 "재생성 장면 비교 대기 3건" → 검수 목록 `stage=pair` 3건 일치. "반납 그림책을 찾아라"(초3) 시작 영상 버전 3개 비교, 오른쪽만 v3→v2로 바꿔도 왼쪽 현재 선택본 v1 유지, 새로고침 뒤 선택본 유지. 월요일 장면 ↔ 미션 내용 왕복 이동. 게시 관리 초3 11/23~12/14 4주 편성표·미편성 후보 표시. 쓰기(동섭 요청, 되돌릴 수 있는 것만, 18:2x): 시작 영상 "이 버전 사용"으로 선택본 v1→v3 저장, 새로고침 뒤 v3 유지 → v1로 되돌림(새로고침 뒤 v1). 초4 "동물원 바구니 찾기"(생성 기준 주 11/23) 미편성 → 12/14 편성 확정 → 12/07로 주차 변경(12/14 칸 비워짐) → 편성 해제로 미편성 복귀, 단계마다 새로고침 뒤 유지. 생성 기준 주와 편성 주가 따로 표시됨. 맞바꾸기는 초4 후보가 1개라 하지 않음. 채택·게시 확정은 하지 않음: 확정 이전 상태로 되돌리는 기능은 없고(채택한 테마·미션은 남고 학년·주는 바꿀 수 없음, 확정 때 풀린 같은 주 후보 편성도 돌아오지 않음) 게시 중단·수정 → 재검토 → 재게시로만 수습하므로 A에서 시험 흔적을 B로 넘기지 않고, B 시연 테마를 실제 게시할 때 한 번 지나간다. 목록 상태는 "영상 비교 대기"인데 상세 제목 옆 표시는 "검수 대기"(단계와 초안 상태 표시가 다름) |
| #777 | 9.17.6 "11/24 A 실행 결과": 검사 이미지 게시·gguf 정리·IC 재생성(`…-r5`, 해시 검사 13개 44.6초)·경로 잠금(쓰기 `AccessDenied`)·기반·어댑터 호출 성공(어댑터 검사 OK) → 0대. B에도 적용 |
| 9.22.5 | 웹 첫 화면·인증서 확인, 예전 주소 refresh 403(예상), Google 로그인 확인. **루트 `sagomungchi.co.kr`은 http·https 모두 응답 없음**(가비아 포워딩 미설정으로 보임) |

### 9.26.4 #974 추억 그림책

A에 액자(`theme_frame`)가 하나도 없고 이번 주(11/23) 테마도 게시돼 있지 않아 발급할 회차가 없었다. 동섭 승인으로 시험 데이터를 넣었다(16:06).

- learning: 부하1(`smoke601a`)에게 초5 11/16 회차 액자 1개(`974f0000-0000-4000-8000-000000000974`). 실제 완료가 아니라 행만 넣어 엔딩을 안 본 상태다.
- core: 같은 자녀에 PREMIUM 시험 구독 `974a0000-0000-4000-8000-000000000974`(결제 없음, 12/1까지, 스냅숏은 현재 PREMIUM 상품 값).
- 부하1의 답변 원문 공개를 켰다(그 전 회차 목록 403 `STUDENT_RECORDS_PRIVATE`).

| 확인 | 결과 |
|---|---|
| 발급 | 16:15:54 202 QUEUED → 16:16:16 READY(25초), 받기 200 |
| PDF | 7쪽, 그림 6개(841~850×864, FlateDecode, 1.01~1.23MB) = 엔딩 전 기대값 6. 로그 `그림책 그림 건너뜀` 0줄 |
| 설정 | `MEMORY_BOOK_ASSET_ORIGINS`가 missions 버킷 출처, `report.memorybook.generate`·`core.memorybook.events` consumer 1, 상품 FREE `memoryBook=false`·PREMIUM `true`·하루 3권, core V57 성공(migration 로그) |
| D6 원본 크기 | 이 회차 PNG 16개 1.06~1.66MB, missions `theme-drafts/` PNG 173개 중 최대 1.89MB, 2MB 초과 0 → 축소 추가 이슈 불필요 |
| E4 메모리 | report-worker 126Mi → 최대 **669Mi / 768Mi(87%)**, CPU 최대 472m, 재시작 0·OOMKilled 없음. 그림 7장(엔딩 본 회차)이나 동시 발급에서는 한도를 넘을 수 있어 limit 조정 판단이 필요하다(#1006) |

시험 데이터 3가지는 동섭 결정으로 17:57에 정리했다(B로 넘기지 않음). 넣을 때와 같은 사전 조건 검사를 둔 트랜잭션으로 실행했다.

- learning: 액자 `974f0000-…` 삭제(부하1 액자 0개)
- core: 시험 구독 `974a0000-…`을 `CANCELED`로(삽입 SQL 헤더의 되돌리기 방식, 이력은 남김). 부하1의 ACTIVE 구독 0개
- 부하1 원문 공개 `parentSharingEnabled` true → false. 학부모 회차 목록이 다시 403 `STUDENT_RECORDS_PRIVATE`
- 발급한 그림책 1권(`f41b1ce8`, report_db 행과 reports 버킷 PDF, 만료 12/24)은 남겨 두었다. 원문 비공개라 학부모 목록에서도 403으로 보이지 않는다. 동섭 결정으로 그대로 둔다. B DB는 A 스냅샷에서 만들므로 이 기록 1개가 B로 넘어가지만 PDF는 A reports 버킷에만 있다. B에서 부하1 원문 공개를 다시 켜면 목록에는 보이고 받기는 실패할 수 있다.

### 9.26.5 발견

- **Argo CD 알림 로그에 Discord webhook URL 원문**: notifications-controller 로그 수준이 `info`인데도 HTTP 클라이언트가 `[DEBUG] POST https://discord.com/api/webhooks/…`로 URL 전체를 남긴다. Pod 로그를 볼 수 있는 사람은 webhook 값을 알 수 있다. 확인 중 작업자 출력에도 한 번 찍혔다(다른 곳에 옮기지 않음). webhook 재발급과 B 적용 전 로그 설정 변경 여부는 결정 필요(#1003).
- **cd-release 계획 인코딩**: Windows Git Bash에서 계획 JSON을 `python`으로 만들어 `gh workflow run -f plan=`에 넘기면 한국어가 CP949로 깨져 PR 본문 사유·호환성 근거가 깨졌다(#991 본문은 손으로 고침, 커밋 메시지·`planSha256`은 깨진 입력 기준). `PYTHONIOENCODING=utf-8`로 만든다(#1004).
- **이번 주(11/23) 테마 미게시**: 게시된 테마는 초5 11/16 하나뿐이라 학습은 지난 테마를 재사용하고 있다.
- **Argo CD 알림 revision 빈칸**: 여러 source를 쓰는 앱 일부의 Discord 알림에 revision이 비어 나온다(#1003에 같이 적음).
- **Grafana 알림 링크가 `localhost:3000`**: Grafana `root_url`이 설정되지 않아 알림의 링크가 접속할 수 없는 주소다.
- core app 계정은 `flyway_schema_history`를 읽을 수 없다(9.20.2 2번 SQL 첫 줄은 migrate 계정이나 Job 로그로 확인).

### 9.26.6 #858 revert 복구 확인

#991 digest를 되돌리는 PR #1008을 병합해 Argo CD가 예전 버전으로 되돌리는지 봤다. 되돌린 대상은 #991 전 값(앱 11/06 `main-322e7976b26a`, migration 11/05 `main-c6809ddb65ee`)이다.

| 시각 | 확인 | 결과 |
|---|---|---|
| 17:12~17:18 | Argo CD 동기화 | 병합 약 4분 뒤 `cfc04538` 기준 동기화. core·learning·ai·scoring·report-worker가 예전 digest로 Synced/Healthy |
| 17:18~17:19 | 예전 migration Job | core·learning `…-migrate-main-c6809ddb65ee` Complete(Flyway는 모르는 최신 migration을 건너뜀) |
| 17:16~17:24 | report-api 예전 migration | `Can't locate revision identified by '20261110_08'`로 실패. 11/03 Alembic이 지금 DB revision을 모른다. PreSync 실패로 report-api는 최신 이미지에 남고 Argo CD가 5회 재시도 뒤 멈춤 |
| 17:21:48 | 경로 확인 | student-login ok, **pick-mission 실패**: `GET /api/v1/students/me/weekly-theme` 404(지금 웹이 부르는 경로가 예전 앱에 없음) |
| 17:26~17:31 | 복구 #1010 | 앱 6개가 다시 main images 파일 digest와 같고 Synced/Healthy. 롤링 업데이트 중 자리가 모자라 Karpenter가 `application-burst` t3.medium 1대를 띄움(노드 5대) |
| 17:32 | 경로 확인 | ok=true, 6단계 모두 ok |

- 결론: revert 절차(digest PR 되돌림 → 병합 → Argo CD 동기화)는 동작한다. 다만 migration이 여러 번 쌓인 시점까지 이미지만 되돌리면 DB(report Alembic)와 API(웹이 부르는 경로)가 맞지 않아 서비스가 깨진다. 확인 중 DB 데이터 변경은 없었다.
- Argo CD 화면의 report-api 마지막 동작은 revert 때 기록(Failed, 5회 재시도)이 남아 있다. 앱 상태는 Synced/Healthy이고 다음 동기화 때 바뀐다.

**되돌리기 판단 기준(앞으로)**

| 상황 | 대응 |
|---|---|
| 직전 digest 릴리스 뒤 migration 변경이 없고 API가 지금 웹과 맞음 | 직전 digest로 revert(#1008과 같은 방식) |
| 그 사이 migration 변경이 있음 | revert하지 않고 고친 커밋으로 새 digest PR(fix-forward) |
| 데이터가 잘못 바뀜 | RDS 시점 복원(9.12 PITR, #629). 데이터 손실이 있을 수 있어 마지막 수단 |

digest PR만 보고 이 판단을 할 수 있게 PR 본문에 migration 변경 여부를 넣는 일은 #1013에서 한다.

### 9.26.7 비용과 남은 것

- 켜 둔 과금 자원: RDS, NAT·EIP, EKS, t3.medium 4대(17:28부터 Karpenter 1대 더해 5대), ALB(시간당 약 $0.43, 추가 노드 포함 시 조금 더). ECR에 `main-c2ed78b0d04e` 이미지 7개가 늘었다.
- 남은 것: 9.16.2 11단계(B 공유용 KMS 스냅샷)와 A 종료.
- 2026-11-26 변경(동섭): 11/25 밤 A 종료는 하지 않았다. A를 계속 켜 두고 지원 한도(총 30만 원) 안에서 쓰며, 12/2 멘토링 뒤 B로 옮긴다(#809). 비용을 줄이려고 EventBridge Scheduler 그룹 `sagomungchi-night-stop`(역할 `sagomungchi-night-stop-scheduler`)으로 화·목·금·토·일 01:00에 노드 그룹 2개를 0대로, 01:05에 RDS를 멈추고 07:00 RDS·07:15 노드를 되살린다. 월요일(주간 리포트·SageMaker 창)과 수요일(03:00 테마 초안) 새벽은 제외했고 일정은 12/10에 끝난다. A를 지울 때 이 일정과 역할도 지운다.

## 9.27 LLM 호출 지연·오류 지표와 경보·대시보드 (#1028, 2026-11-25)

설계 기준은 [architecture 4.7 LLM 호출 지표](../design/architecture.md#llm-호출-지표-1028)다. 에픽 #1027의 core 부분이다.

### 9.27.1 결정 (동섭, 11/25)

- prod 경보는 B 첫 배포에 넣는다. 12/1 이후 장애·시험 메시지 금지(#886)는 그대로 지킨다
- 임계값은 이슈 기준안을 그대로 쓰고 실측 뒤 조정한다
- `llm.call.duration`에 `prompt_version` 속성을 넣는다

### 9.27.2 바꾼 것

- core `LlmCallMetrics`: `LlmUsageService.record()`에서 `insertIfAbsent()`가 1을 돌려준 때만 `llm.call.duration`(초, 버킷 0.25~300초)과 `llm.call.tokens`를 기록한다
- prod `observability.json`: `llm-call-errors`·`llm-call-latency-dialog`·`llm-call-latency-word-help`·`llm-call-rate-limited`. 기존 LLM 규칙(`llm-unpriced-calls`) 바로 뒤에 둔다
- 대시보드 `charts/observability/dashboards/llm-calls.json`("LLM 호출"): 호출 유형별 p95·p50, 오류율, 오류 코드별 건수, 호출 건수, 모델·방향별 토큰
- `operational-alerts/verify_chart.py`: local·prod 렌더에 `llm-calls.json`이 provision되는지 확인한다

오류율·429 규칙은 `increase()` 대신 `clamp_min(X - (X offset 창 or X * 0), 0)`으로 센다. 처음 나온 속성 조합(예: 처음 나온 오류 코드)의 첫 값을 `increase()`가 0으로 보기 때문이다. core가 재시작하면 `exported_instance`가 바뀌어 새 시계열이 생기는데, 이 식은 그 값도 창 안의 새 호출로 센다.

### 9.27.3 검증

- core `./gradlew clean test bootJar`(`eclipse-temurin:21-jdk` 컨테이너와 Testcontainers): 780건 중 실패 0, 건너뜀 3, bootJar 생성. `LlmUsageQueryTest`에 새 시험을 넣었다. 새 이벤트 1건은 히스토그램 1회와 토큰 입력·출력에 기록되고, 같은 이벤트를 다시 받으면 더 기록하지 않는다. 토큰이 없는 호출은 토큰에서 빠진다(InMemoryMetricReader)
- `verify_chart.py`(Helm 4.3.1, 실제 Grafana·Prometheus 컨테이너): exit 0. prod 규칙 20개(기존 16개 + 새 4개)가 실제 엔진에서 정상 평가됐다
- `ci-gitops`와 같은 `helm lint --strict`와 `helm template --kube-version 1.35.8`를 local·prod observability values로 돌려 통과했다. kubeconform은 로컬에 없어 돌리지 않았다
- 로컬 kind(`sagomungchi-local`)
  - 이 브랜치 core 이미지(`local-1028`)를 임시로 올리고, ai-service 안에서 `/internal/followups`를 12회 불렀다(LLM stub, 200)
  - Prometheus에서 `llm_call_duration_seconds_count{call_type="FOLLOWUP",prompt_version="followup@4",outcome="success",error_code="none"}`가 12였다. `llm_call_tokens_total`은 입력 4560·출력 3371이었다
  - 버킷 시계열은 20개였다(19개 경계와 `+Inf`). `llm-call-errors` 식은 FOLLOWUP에서 0이었고 10건 조건을 채웠다
  - Grafana API에서 대시보드 `llm-calls`가 provision된 것을 확인했다. p95(4.87초)·토큰·호출 건수 패널 쿼리가 값을 돌려줬다
  - 확인 뒤 core는 원래 `sagomungchi/core-service:local`로 되돌렸다. observability release는 `--reuse-values`로 `grafana.dashboards.enabled=true`를 켰다. 배포된 값에 `prometheus.retrainJobMetrics`가 없어 `enabled=false`를 함께 줬다(revision 17)
  - 재전달 중복은 kind에서 다시 보내 보지 않았고 core 시험으로만 확인했다

### 9.27.4 한계·남은 일

- 이벤트 소비 시점에 기록해 수 초 늦다. best-effort 발행에서 빠진 호출은 없다. 지연은 provider 호출 한 번이며 기능 전체 지연이 아니다
- 대시보드와 지연 경보는 `rate()`·`increase()` 기반이라 새 속성 조합의 첫 호출이 빠진다. kind에서도 호출 건수 패널이 12건이 아니라 약 4.6건(30분 `increase`)을 보였다. 추세를 보는 용도로 쓴다
- JUDGMENT·FOLLOWUP·WORD_HELP 밖의 호출 유형 지연 경보와 SLO 확정은 실측 뒤에 한다
- prod 값은 B 계정에서 Collector egress와 core Java agent가 켜져야 생긴다. B 첫 배포 뒤 Grafana 패널을 확인해야 한다

## 9.28 ai-service trace·HTTP 지표 (#1029, 2026-11-25)

에픽 #1027의 ai-service 계측이다. 지금까지 ai 구간은 Tempo에 span이 없었고(architecture 4.7 남은 경계), prod Langfuse도 꺼져 있어(#379) 판정·분석 실패 요청을 ai 안에서 추적할 수 없었다. 새 의존성 없이 기존 `opentelemetry-sdk`(langfuse 의존성)와 `opentelemetry-exporter-otlp-proto-http`를 쓴다.

### 9.28.1 구성

| 항목 | 내용 |
|---|---|
| provider | `app/tracing.py`. `OTEL_TRACES_EXPORTER=otlp`면 trace, `OTEL_METRICS_EXPORTER=otlp`면 지표 SDK를 설치하고, 아니면 no-op이라 받은 `traceparent`를 그대로 넘긴다. lifespan 시작에 설치하고 종료에 flush한다 |
| 전역 provider | 등록하지 않는다. Langfuse v4는 전역 TracerProvider가 있으면 거기에 자기 processor를 붙여, 섞으면 Langfuse generation이 Tempo로, 앱 span이 Langfuse로 간다. 앱 계측은 `tracing.tracer()`·`tracing.meter()`만 쓴다 |
| HTTP | 순수 ASGI 미들웨어(분석 SSE도 끝까지 잰다), 가장 바깥에 둬 401·403도 잰다. SERVER span의 부모는 요청 `traceparent`. 지표 `http.server.request.duration`(초, Prometheus `http_server_request_duration_seconds`, `exported_job="ai-service"`). 속성은 메서드·경로 템플릿·상태 코드, 5xx면 `error.type`. `/health`는 뺀다 |
| LLM | `LlmClient` 제공자 요청 1회마다 CLIENT span `llm <callType>`. 호출 종류·프롬프트 버전·시도 번호·요청/응답 모델·토큰 수·성공 여부·오류 코드만 넣는다. 사용량 이벤트 봉투 `traceparent`가 그 시도 span이다 |
| 이벤트 | `model.version.activated` 소비는 봉투 `traceparent`를 부모로 CONSUMER span. ai가 소비하는 이벤트는 이것뿐이다. 판정·분석·리포트 문장은 core·learning·report-worker가 HTTP로 부른다 |
| 하위 호출 | scoring·core·learning 호출 헤더의 `traceparent`는 현재 span 값이다(no-op이면 받은 값) |
| 원문 차단 | 경로 값·질의·헤더·본문·프롬프트·응답·학생 ID는 span·지표에 넣지 않는다. 예외 메시지는 원문이 섞일 수 있어 span event로 남기지 않는다(`record_exception=False`, 예외 종류 이름만 `error.type`) |
| values | local: `egressToCollector`, `OTEL_SERVICE_NAME`·endpoint·protocol·`OTEL_METRICS_EXPORTER=otlp`(지표만. local은 Tempo가 없어 trace는 끈다). prod: `egressToCollector`, `tracing.enabled`, `OTEL_METRICS_EXPORTER=otlp`. chart는 바꾸지 않았다(비agent 분기는 trace 값만 넣으므로 지표 값은 ai values에 둔다) |

- 경보 쿼리는 `exported_job="core-service"`·`learning-service`로 걸러 ai 지표가 기존 규칙에 섞이지 않는다.
- Collector NetworkPolicy는 app 네임스페이스 전체에서 4317·4318을 받으므로 observability 쪽 변경은 없다.
- #1030(AI 품질 카운터)은 같은 provider를 `tracing.meter()`·`tracing.instrument()`로 쓴다.

### 9.28.2 결정 (동섭, 2026-11-25)

| 확인 필요 | 결정 |
|---|---|
| prod 적용 시점 | B 첫 배포(11/26~28)에 포함한다. 12/1 이후 장애·시험 메시지 금지(#886) 전이다 |
| 경보 임계값 | 이번에는 지표만 낸다. ai 경보 규칙은 B 실측 뒤 정한다 |
| Collector·Tempo 자원 | 그대로 두고 B에서 관찰한다. 근거는 아래 |
| 지표 env 위치 | ai values에만 넣는다(공용 chart를 바꾸지 않아 #1031과 겹치지 않음) |

자원 근거(#784, 9.15):
- Collector limits 256Mi. trace 전용 `memory_limiter/traces` 144MiB, 대기열 16MiB, 재시도 30초라 Tempo가 죽어도 지표 수집은 격리된다(kind에서 거부 지표 0점).
- Tempo limits 1Gi, `GOMEMLIMIT` 800MiB, 수집 상한 8MiB/s, 보존 24h. kind에서 초당 400 trace × 10 span에 재시작 0회였다.
- ai가 더하는 span은 요청당 2~4개(서버 1, LLM 시도 1~2, 소비 1)다. core 요청 1건의 Java agent span(JDBC·HTTP·Rabbit) 수십 개보다 적고, ai 요청 수도 core 요청보다 적다.
- 지표는 히스토그램 하나(경로 템플릿 약 20개 × 메서드 × 상태 코드 × 버킷 19개)라 Prometheus(limits 512Mi, 보존 3d·2GB) 부담이 작다.
- 실제 부하에서 Tempo 1Gi가 버티는지는 9.15.5대로 B에서 확인한다.

### 9.28.3 검증

- 로컬 ai 시험: 전체 1,451개 통과(새 `tests/test_tracing.py` 14개, 기존 Langfuse 시험 포함. 경고 3건은 기존 aio_pika 연결 정리 경고). `ruff check`·`ruff format --check` 통과.
  - exporter 값이 없으면 provider를 설치하지 않고, 받은 `traceparent`를 그대로 넘긴다.
  - 값이 있으면 요청한 provider만 설치하고 전역 provider는 그대로다.
  - HTTP SERVER span의 부모가 요청 `traceparent`이고, 이름·속성·지표는 경로 템플릿이다(경로 값·질의 없음). 5xx는 ERROR이고 예외 메시지 event는 없다. 404는 메서드만 남고 `/health`는 재지 않는다.
  - 소비 span의 부모가 봉투 `traceparent`다. 형식 오류는 `INVALID_EVENT`로 남는다.
  - LLM 시도 span 2개(실패·성공)의 속성에 원문이 없다. 사용량 이벤트 `traceparent`와 하위 HTTP 헤더가 현재 span이다.
  - Langfuse를 켜도 Langfuse exporter에는 `langfuse-sdk` span만, 앱 exporter에는 앱 span만 간다. Langfuse 부모는 이전처럼 요청 `traceparent`다.
- `helm lint --strict`·`helm template`: local `ai-service.yaml`과 prod `ai-service.json` + `images/ai-service.json` 모두 통과.
  - prod 렌더: chart가 `OTEL_TRACES_EXPORTER=otlp`·endpoint·service name을 넣고, values의 `OTEL_METRICS_EXPORTER=otlp`, Collector 4317·4318 egress가 들어간다.
  - local 기본 렌더: 지표 값만 들어가고 `OTEL_TRACES_EXPORTER`는 없다.
- kubeconform은 로컬에 없어 원격 `ci-gitops`에서 확인한다(PR 생성 뒤).
- Docker 격리 확인(공용 kind는 다른 세션이 쓰고 있어 건드리지 않음): 격리 네트워크에 `grafana/tempo:2.10.10`과 이 브랜치 ai 이미지(`OTEL_TRACES_EXPORTER=otlp`, LLM 키 없음)를 띄웠다. 원문·학생 ID를 넣은 되묻기 요청과 잘못된 토큰 요청에 `traceparent`를 붙여 보낸 뒤 Tempo `/api/traces/<id>`로 조회했다.

| span | 부모 | 상태·속성 |
|---|---|---|
| `POST /internal/followups`(SERVER) | 요청 `traceparent`의 span | ERROR, `http.route=/internal/followups`, `503` |
| `llm FOLLOWUP`(CLIENT) | 위 SERVER span | ERROR, `error.type=LLM_NOT_CONFIGURED`, `followup@4`, 시도 1 |
| `GET`(SERVER, 401) | 요청 `traceparent`의 span | 경로 템플릿 없음(인증 거부는 라우팅 전), 질의 값 없음 |

  - trace 전체에 원문·학생 ID·질의 값이 없고, span event도 0개였다.
  - 처음 확인에서 재시도 없이 끝난 LLM span의 `error.type`이 오류 코드 대신 `LlmUnavailable`로 덮이는 것을 찾아 고쳤다. 시험(`test_final_llm_failure_keeps_error_code`)을 추가하고 다시 확인했다.
  - 확인 뒤 컨테이너·네트워크·이미지를 지웠다.

### 9.28.4 한계와 남은 것

- core 요청 → ai 판정 → 사용량 이벤트 전체가 Tempo 한 trace로 보이는지는 B 계정에서 확인한다(동섭 결정, 2026-11-25). 공용 kind는 다른 세션 작업 중이라 Docker 격리로 ai 구간만 확인했다. 확인 방법: observability `tempo.enabled=true`, core·learning·ai `tracing.enabled=true`로 올리고 판정 한 번 뒤 Grafana Tempo에서 `service.name=ai-service` SERVER span의 부모가 learning HTTP client span인지, `llm.usage.recorded` core 소비 span이 ai `llm JUDGMENT` span 아래인지 본다. kind에서 확인할 때는 local ai values에 지표용 `OTEL_SERVICE_NAME`·endpoint가 이미 있어 `tracing.enabled=true`면 같은 값이 두 번 렌더된다(값이 같아 동작은 같다).
- 제공자 SDK(openai·anthropic·boto3) 내부 HTTP는 자동 계측하지 않는다. LLM 시도 span의 시간이 그 구간이다.
- scoring·report-api는 여전히 자체 span·HTTP 지표가 없다.
- Langfuse를 켜면 generation 부모는 이전처럼 요청 `traceparent`(호출한 서비스 span)이고 ai span이 아니다. 두 저장소는 trace ID로 맞춘다.

## 9.29 리포트 설명 누락 지표와 경보 (#1031, 2026-11-25)

에픽 #1027의 리포트 설명 부분이다. 리포트 Gemma(SageMaker, #742)가 창 시작 뒤 InService가 아니거나 0대 호출에 실패해도 리포트는 `COMPLETED`라 기존 규칙에 잡히지 않았다.

### 9.29.1 결정 (2026-11-25 동섭)

| 항목 | 결정 |
|---|---|
| 지표 출처 | CloudWatch 데이터 소스 대신 report-worker 지표. 새 IAM·데이터 소스 없음. 엔드포인트 InService 여부·`NoCapacityInvocationFailures` 자체는 보지 않고 "설명이 실제로 빠졌다"는 결과만 본다 |
| 내보내기 | `app/tracing.py`가 `tracing.enabled`(`OTEL_TRACES_EXPORTER=otlp`)일 때 trace와 함께 MeterProvider를 설치. chart는 Java가 아닌 서비스에 `OTEL_METRICS_EXPORTER`를 주지 않아 chart 렌더는 바꾸지 않음. ai-service(#1029)는 values의 `OTEL_METRICS_EXPORTER`로 따로 켠다 |
| 임계값 | 기준안. 30명 배치 실측 뒤 조정 |
| prod 적용 | prod values에 넣었으나 B 첫 배포 포함 여부는 결정 대기(#886: 12/1 이후 장애·시험 메시지 금지) |

### 9.29.2 바꾼 것

- report-worker: OTel 카운터 `report.explanation.state`(Prometheus `report_explanation_state_total`). 속성은 `state`(`INCLUDED`·`NOT_INCLUDED`·`NO_TARGET`) 하나이고 학생·리포트·답변 ID와 원문은 넣지 않는다(NFR-SEC-05). `explanation_generator.py`가 상태를 정하는 두 곳(공유 꺼짐 `NO_TARGET`, 설명 단계 끝)에서 1을 더하고, 일일 리포트·설명 꺼짐은 세지 않는다. 재시작 뒤 첫 결정도 `increase()`에 잡히도록 세 상태를 0부터 낸다
- prod `observability.json`에 규칙 2개 추가(#1028 포함 총 22개). 둘 다 지속 5분, 창 밖은 `noDataState: OK`

| uid | 조건 |
|---|---|
| `report-explanation-not-included` | 최근 30분 `NO_TARGET`을 뺀 결정 5건 이상 중 `NOT_INCLUDED` > 50% |
| `report-explanation-none-included` | 최근 30분 `NOT_INCLUDED` 3건 이상이고 `INCLUDED` 0건 |

- 창(일 23:30 ~ 월 02:00 KST, `explanation-endpoint.json` `schedule`)은 UTC 일 14:30~17:00으로 바꿔 `day_of_week()`·`hour()`·`minute()` 조건으로 건다. 창 밖에서는 값이 비어 울리지 않는다. `increase()` 외삽으로 건수가 소수가 되지 않도록 건수는 `round()`로 본다
- 검증기 `verify_chart.py`·`verify.py`, `operational-alerts/README.md`, architecture 4.7 남은 경계 갱신

### 9.29.3 검증 (로컬)

| 검사 | 결과 |
|---|---|
| report 시험 | 전체 564개 통과. 상태별 카운터(INCLUDED 1·NOT_INCLUDED 1·NO_TARGET 2, 설명 꺼짐은 미집계), 속성이 `state` 하나뿐이고 학생 ID·원문이 없음, 세 상태 0 시작 확인. ruff 통과 |
| 실제 Collector | `otel/opentelemetry-collector-contrib:0.164.0`에 OTLP로 보내 `report_explanation_state_total{job="report-worker",state=...}`로 나오고 `NO_TARGET` 0도 나오는 것 확인(Prometheus 수집 뒤 `exported_job`) |
| Helm | observability prod·local, report-worker prod `helm lint --strict`·`helm template` 통과 |
| `verify_chart.py` (Docker 격리) | 22개 규칙 정상 평가. 창 조건을 Prometheus `time` 지정 조회로 일 14:29:59·14:30·15:30·16:59:59·17:00 UTC와 월·토 15:30 UTC에서 확인. 가속 사본(창 조건 제거, `[1m]`)에서 `NO_TARGET` 제외 비율 발생(넣으면 울리지 않는 값), `INCLUDED` 0건 발생, 두 규칙 회복. 기존 검사 모두 통과 |

AWS·SageMaker·A 계정 클러스터와 실제 Discord 수신은 이 검증에 포함하지 않았다.

### 9.29.4 남은 것

- 배치가 아예 돌지 않거나 report-worker 지표가 끊기면 두 규칙 모두 울리지 않는다(창 안에서도 NoData는 OK)
- 엔드포인트 InService 직접 감시(CloudWatch)는 하지 않는다
- 30명 배치 실측 뒤 임계값·30분 창·창 끝 시각 조정
- B 첫 배포 포함 여부 결정

## 9.30 첫 사용 안내 완료 기록 migration V58 (#1035, 2026-11-25)

에픽 #1034(첫 사용 안내)의 core 부분이다. 제안 [onboarding 7.1 B안](../proposals/onboarding.md)대로 완료 기록을 서버에 둬 기기·브라우저를 바꿔도 안내가 한 번만 보이게 한다.

| 항목 | 내용 |
|---|---|
| 변경 | `V58__onboarding_completion.sql`: `user_account.onboarding_completed_at`·`student.onboarding_completed_at` (`timestamptz NULL`) 추가. 인덱스·CHECK·DEFAULT 없음 |
| 학생을 `student`에 둔 근거 | 학생은 `user_account` 행이 없다(V7에서 `student.user_account_id` 삭제). 학생 본인 설정 시각을 `student`에 두는 `look_updated_at`(V23) 선례를 따른다. 형제가 한 보호자 계정을 써도 학생별로 따로 남는다 |
| 기존 행 | 모두 NULL = 미완료. 배포 뒤 기존 사용자도 안내를 한 번 본다. 시연 계정은 시연 전에 각 계정으로 들어가 안내를 끝내 둔다(에픽 #1034) |
| 기록 규칙 | `... WHERE ... AND onboarding_completed_at IS NULL` 조건부 UPDATE라 다시 기록해도 처음 시각을 유지한다(learning `ThemeFrameMapper.xml` `seen_at` 선례). 지우는 API·관리자 초기화는 없고, 학생 삭제·탈퇴 때도 지우지 않는다(개인정보가 아닌 시각 값이고 차단된 행은 다시 쓰이지 않음) |
| 배포 | 칼럼 추가만이라 잠금이 짧고 되돌릴 데이터가 없다. core-migrate 이미지의 PreSync Job이 앱보다 먼저 돈다(9.18.3). local values `migration.revision`을 `v58`로 올렸다 |

API: `GET·PUT /api/v1/me/onboarding`(학부모), `GET·PUT /api/v1/students/me/onboarding`(학생). 기록은 [auth-account 19](auth-account.md#19-첫-사용-안내-완료-기록-1035-2026-11-25).

## 9.31 추억 그림책 같이 읽음 칸·알림 유형 (#1025 V59, 2026-11-25)

core migration `V59__memory_book_read_together.sql`(#1035가 V58을 먼저 써서 V59). API·정한 것은 [core-gateway 36절](core-gateway.md#36-추억-그림책-같이-읽음-표시토요일-저녁-알림-1025-2026-11-25), 저장 구조는 [ERD 3.5.3](../design/erd.md).

| 바꾼 것 | 내용 | 근거 |
|---|---|---|
| 잠금 | `LOCK TABLE memory_book_job, notification, notification_setting IN ACCESS EXCLUSIVE MODE` | V41·V30처럼 고치는 표를 먼저 한 번에 잠가 순서를 고정한다. 세 표 모두 작고 문장이 짧아 잠금 시간이 짧다 |
| 칸 추가 | `memory_book_job.read_together_at timestamptz` (nullable, 기본값 없음) | nullable 칸 추가라 기존 행은 NULL로 남고 다시 쓰지 않는다(PostgreSQL은 기본값 없는 칸 추가에 표를 다시 쓰지 않음). 기본값을 두지 않는 ERD 규칙(3.6)을 따른다 |
| CHECK 추가 | `ck_memory_book_job_read_together (read_together_at IS NULL OR status = 'READY')` | 상태는 QUEUED → READY·FAILED로 한 번만 바뀌고 READY는 다시 바뀌지 않으며, API도 READY에서만 값을 넣는다. 정상 흐름을 막지 않고 잘못된 값만 막는다. 기존 행은 모두 NULL이라 통과한다(확인을 위해 표를 한 번 읽음) |
| 알림 CHECK | `ck_notification_type`·`ck_notification_setting_type`을 지우고 기존 9개 + `MEMORY_BOOK_READ_REMINDER`로 다시 만듦 | V41과 같은 방식. 허용 목록만 넓혀 기존 행은 모두 통과한다 |
| 인덱스 | 새로 만들지 않음 | 토요일 예약 작업이 주 1회 `status='READY' AND completed_at ≥ … AND read_together_at IS NULL AND expires_at > …`를 읽는다. 행 수가 자녀당 하루 최대 3권인 데모 규모라 표 전체 읽기로 충분하다. 커지면 부분 인덱스 `(completed_at) WHERE status='READY' AND read_together_at IS NULL`을 검토한다 |

- 되돌리기: 칸·CHECK를 지우고 알림 CHECK를 V41 목록으로 되돌리는 새 migration이 필요하다(그 전에 `MEMORY_BOOK_READ_REMINDER` 알림·설정 행을 지워야 함). 적용된 V59는 고치지 않는다
- local GitOps `environments/local/core-service.yaml`의 `migration.revision`을 `v58`(#1035) → `v59`로 올렸다(`test_core_migration_versions`가 마지막 migration과 같은지 봄). prod 쪽 migration 판 번호는 이 PR에서 바꾸지 않았다
- 새 ShedLock 이름 `core-memory-book-read-reminder`는 기존 `shedlock` 표에 행으로 생기며 migration이 필요 없다

## 9.32 AI 품질 신호 대시보드 (#1030, 2026-11-25)

에픽 #1027의 ai 품질 부분이다. #1029의 ai-service meter provider·Collector 전송 경로를 그대로 쓰고 새 의존성·운영 도구는 없다. 지표 정의는 [architecture 4.6](../design/architecture.md#46-관측), 정한 것과 주간 비교 SQL은 [ai 28](ai.md#28-ai-품질-신호-지표와-주간-판정-비교-1030-2026-11-25).

### 9.32.1 구성

| 항목 | 내용 |
|---|---|
| 지표 | ai-service OTel 카운터 `ai.judgment.results`·`ai.analysis.fallbacks`·`ai.guard.blocked` → Collector → Prometheus(`ai_judgment_results_total`·`ai_analysis_fallbacks_total`·`ai_guard_blocked_total`). 단위는 중괄호 주석(`{judgment}` 등)이라 이름에 단위 접미사가 붙지 않는다(#984 `{check}`와 같음) |
| 대시보드 | `charts/observability/dashboards/ai-quality.json`(uid `ai-quality`, "AI 품질 신호"). chart가 `dashboards/*.json`을 `grafana-dashboards` ConfigMap에 넣으므로(templates/configmaps.yaml) 파일 추가만으로 local·prod 모두 provision된다. values 변경 없음 |
| 창 | 비율·건수 모두 `increase(...[24h])`(이슈 "24시간 창"). local Prometheus 보존이 1d라 띄운 지 24시간이 안 되면 창이 다 차지 않는다(패널 설명에 적음). prod 보존은 3d |
| 분모 | 판정·인용 대조 차단은 `ai_judgment_results_total`. 분석 대체 응답·되묻기 누출은 #1029 HTTP 지표 `http_server_request_duration_seconds_count{exported_job="ai-service",http_route=…,http_response_status_code="200"}`(경로 `/internal/analysis/stream`·`/internal/followups`) |
| 0건 표시 | `(분자 or 0 * 분모) / 분모`(표현 분류 판정 대시보드와 같은 모양) |
| 경보 | 두지 않음(이슈 범위 밖) |

### 9.32.2 검증

| 확인 | 결과 |
|---|---|
| ai 단위 시험 `tests/test_quality_metrics.py`(InMemoryMetricReader) | 16 통과. 판정 정상·LLM 전 보류·`QUOTE_MISMATCH`(+`judgment_quote`)·503 0회, 분석 대체 두 이유 각 1회·안내 3경로·템플릿 대조 실패 0회, 되묻기 누출 0·1·2회·빈 질문 0회, 속성 키 고정·원문·ID 없음 |
| ai 전체 `uv run pytest`·`ruff check`·`ruff format --check` | 1467 통과, ruff 통과 |
| `verify_chart.py`에 `ai-quality.json` uid·식·datasource 확인 추가(local·prod 렌더) | `verify_chart.py`는 helm이 없어 못 돌림, ai-quality 확인 식만 따로 통과. 이 스크립트는 CI 워크플로에서 돌지 않는다(README의 수동 절차) |
| ci-gitops(helm lint·template·kubeconform) | PR CI에서 확인 |
| 로컬 확인 방식 | kind 없어 #1029(9.28.3)처럼 Docker 격리로 확인, QUOTE_MISMATCH는 llm-stub 한계로 0만 확인(단위 시험으로 대신). `compose.yaml`의 postgres·rabbitmq·learning·이 브랜치 ai 이미지에 llm-stub, local values와 같은 판의 Collector 0.164.0·Prometheus v3.15.1(보존 1d)·Grafana 13.3.0을 붙였다. helm이 없어 Collector(otlp → memory_limiter·batch → prometheus :8889)·수집(job `otel-collector`)·datasource(uid `prometheus`)·대시보드 provider는 chart 템플릿을 손으로 옮겼고 대시보드는 이 브랜치 `ai-quality.json` 그대로. core를 띄우지 않아 ai readiness는 `versions` DOWN(core 프롬프트 snapshot 없음)이었고 요청은 기본 활성 버전(`judge@2` 등)으로 처리됐다. 요청은 ai 내부 API를 직접 불렀다 |
| 보낸 요청 (두 번 반복) | 판정 정상 3·짧은 답 2, 되묻기 정상 2·금지어 누출 2(재생성도 누출), 분석 2, llm-stub을 멈춘 뒤 분석 2·판정 1(503) |
| Prometheus 이름·라벨 | `ai_judgment_results_total{result,held_reason,prompt_version}`·`ai_analysis_fallbacks_total{reason}`·`ai_guard_blocked_total{guard}`, HTTP 분모 `http_server_request_duration_seconds_count{exported_job="ai-service",http_route="/internal/analysis/stream"·"/internal/followups"·"/internal/judgments"}`. 문서·대시보드에 적은 이름과 같음. 이 밖의 라벨은 Collector·Prometheus 공통(`exported_job`·`exported_instance`(SDK `service.instance.id`)·`job`·`instance`·`otel_scope_name`)뿐 |
| 첫 회 값 (한 번째 반복 뒤) | 판정 `CORRECT/none/judge@2` 3, `HELD/TOO_SHORT/none` 2, 503은 0(HTTP 503 1건과 대조), 대체 응답 `AI_UNAVAILABLE` 2(llm-stub이 떠 있을 때 0), `followup_leak` 4(요청 2 × 2회) |
| 원문·ID | ai 시계열 89개 전체에서 답변·질문에 붙인 표시 문자열과 학생·사용자 ID가 나오지 않음 |
| 주간 SQL(ai 28.2) | learning_db에서 두 문 모두 오류 없이 실행, 결과 0행(ai 직접 호출이라 `judgment` 행 없음). 같은 SQL을 세션 임시 테이블의 합성 7행에 돌려 KST 주 경계(일 23:59 → 앞 주, 월 00:00 → 그 주), `RULE`·`FAILED` 제외, NULL → `none`, 주·버전 안 비율을 확인(실제 표에는 쓰지 않음) |
| Grafana 패널 6개(식 8개) | "AI 품질 신호"가 provision됨(`provisioned=true`). 두 번째 반복 뒤 Grafana datasource로 조회해 모두 값이 나옴: 보류율 `judge@2` 0, 결과 분포 `none` HELD 1·`judge@2` CORRECT 1, 보류 이유 TOO_SHORT 2.13, 대체 응답률 전체·`AI_UNAVAILABLE` 0.504, 차단율 `followup_leak` 1·`judgment_quote` 0, 차단 건수 `followup_leak` 4.26. 소수는 `increase()`의 창 끝 보정 |
| 확인한 한계 | 카운터는 첫 증가 때 시계열이 생기므로 Prometheus가 처음 본 값(첫 반복의 3·2·4 등)은 `increase()`에 들어가지 않는다. 프로세스마다 `exported_instance`가 달라 재시작 뒤 처음 나온 조합의 첫 건도 같다. 드문 조합(`QUOTE_MISMATCH` 등)은 적게 보일 수 있다 |

### 9.32.3 1주 실측 (배포 뒤)

prod 반영 뒤 1주 값을 여기에 남기고 경보가 필요한지만 적는다(임계값은 정하지 않음).

| 지표 | 1주 값 | 경보 필요 여부 |
|---|---|---|
| 판정 보류율(프롬프트 버전별) | 기록 예정 | 판단 예정 |
| 분석 대체 응답률 | 기록 예정 | 판단 예정 |
| 가드 차단율(`followup_leak`·`judgment_quote`) | 기록 예정 | 판단 예정 |

## 9.33 법정대리인 동의서 1.2 시드 (#1061 V60, 2026-11-26)

에픽 #1064의 core 부분이다. 학부모 원문 제공을 학생 선택(#206)에서 법정대리인 동의서(GUARDIAN) 1.2 필수 동의로 옮겼다. 문구·시행일은 [auth-account 20절](auth-account.md#20-원문-제공-법정대리인-필수-동의-1064)(#1058), API 변경은 [core-gateway 38절](core-gateway.md#38-학생-원문-공개-비공개-차단-제거와-법정대리인-동의서-12-1061-2026-11-26).

| 바꾼 것 | 내용 | 근거 |
|---|---|---|
| `V60__guardian_consent_record_sharing.sql` | `consent_document`에 GUARDIAN 1.2 행 1개 추가(`00000000-0000-4000-8000-000010610001`, `required = true`, `effective_from = 2026-11-27`). 본문은 V54 GUARDIAN 1.1 원문에서 두 번째 항목 목적 줄 끝 한 구절만 다름 | #732(V54)처럼 게시한 행은 고치지 않고 새 판 행을 더한다. 현재 판 조회(`effective_from DESC`)가 시행일부터 1.2를 고르므로 코드 변경 없이 기존 자녀는 `guardianConsentRequired = true`·학생 세션 차단(재동의 전까지) |
| `student.parent_sharing_enabled`(V21) | 지우지 않고 남김. 앱은 더 이상 읽고 쓰지 않는다 | `docs/README.md` DB migration·API 변경 규칙(#1076): 칼럼 삭제는 안 쓰게 바꾼 PR과 나눠 다음 릴리스에서 한다. 이 릴리스를 되돌리면 옛 앱이 이 칼럼을 읽기 때문. 삭제는 #1078 |

- 잠금·데이터: INSERT 1건이라 잠금이 짧고 기존 행은 바뀌지 않는다
- 되돌리기: 칼럼 삭제·이름 변경이 없어 직전 digest로 되돌릴 수 있다. 되돌리면 옛 앱이 칼럼 값(대부분 false)으로 다시 원문을 가리고, GUARDIAN 1.2 행은 옛 앱에서도 현재 판으로 쓰인다(재동의 화면은 같음)
- 시행일: 2026-11-27은 prod 배포일 기준안이며 배포일이 바뀌면 병합 전에 V60 날짜를 같이 바꾼다(auth-account 20절). 시행일 전에 배포되면 그날까지는 1.1 동의만으로 학부모가 원문을 본다
- 시연·더미 계정: 시행일 뒤 `demo_account_data.py children`·`prepare_accounts.py --families`를 다시 돌려 GUARDIAN 1.2 재동의를 보낸다(#1063, `infrastructure/aws/README.md`)
- local GitOps `environments/local/core-service.yaml`의 `migration.revision`을 `v59` → `v60`으로 올렸다. prod 쪽 migration 판 번호는 이 PR에서 바꾸지 않았다

## 9.34 main 보호 규칙 적용 (#1004, 2026-11-26)

9.26.1에서 digest PR #991이 승인 기록 0건으로 병합된 원인이던 main 보호 규칙을 켰다. 필요 승인 수 1명은 팀장 확정 값이다. 절차는 [CD README B2](../../infrastructure/cd/README.md#b2-digest-pr-저장소-설정-858-관리자-손-작업-1004). API 변경 없음.

| 항목 | 값 |
|---|---|
| 방식 | repository ruleset `main-protection-1004`(id 28138960), 대상 `refs/heads/main`, 활성. 2026-11-26 15:11 KST `gh api`로 생성 |
| pull request | 승인 1명, Require review from Code Owners, Dismiss stale approvals 켬. 필수 status check 없음(경로 필터 때문, B2) |
| 그 밖 | Block force pushes·Restrict deletions 켬. Bypass list 비움(`current_user_can_bypass: never`) |

- 확인: 확인 PR #1081(`.github/CODEOWNERS` 주석 한 줄, 병합하지 않음)에서 `reviewDecision=REVIEW_REQUIRED`·`mergeStateStatus=BLOCKED`, code owner `20220348-kim`에게 리뷰 요청. 관리자 계정의 `gh pr merge`도 "the base branch policy prohibits the merge"로 거부
- 영향: develop → main 릴리스 PR도 작성자가 아닌 1명의 승인이 있어야 병합된다(B2)
- #991 커밋 메시지(`c283a2b8`)의 깨진 사유·호환성 근거 원문은 이력 재작성 없이 [#1004 댓글](https://github.com/SKNETWORKS-FAMILY-AICAMP/SKN34-FINAL-3TEAM/issues/1004#issuecomment-7184212482)에 남겼다. #991 본문 손 수정 때 빠진 호환성 근거 5행(data·api·events·ongoingLearning·payments)도 커밋 메시지에서 복원해 같이 적었다
- 남은 것: 다른 code owner 승인 1명 뒤 병합 가능해지는지, 다음 cd-release digest PR 본문 한국어가 정상인지(#1004)

## 9.35 운영(A) 표현 분류 재학습 CronJob (#730, 2026-11-26)

9.25의 로컬 구성을 prod(A 계정 EKS)에 옮겼다. 재학습 이미지는 #985로 A ECR에 있고, digest는 main `images/tox-retrain.json`(1차 릴리스 digest PR #1077)이 갖는다. API 변경 없음.

### 9.35.1 결정 (동섭, 2026-11-26)

- A에서는 예약 실행을 끈다(`suspend: true`). 기본 일요일 03:00이 A 야간 정지(화·목·금·토·일 01:00~07:15 노드·RDS 정지)와 겹친다. 배포 뒤 수동 실행 1회로 확인한다
- 실패·예약 지연 경보 2개와 상태 수집기(kube-state-metrics 곁 컨테이너)를 prod 관측에 같이 넣는다. 예약을 꺼 둔 동안 예약 지연 경보는 울리지 않는다(9.25 규칙 그대로)

### 9.35.2 구성

| 항목 | 로컬(kind, 9.25) | 운영(A) |
|---|---|---|
| 값 | `environments/local/tox-retrain.yaml` | `environments/prod/tox-retrain.json` + `images/tox-retrain.json` |
| Argo CD | `local-tox-retrain` | `prod-tox-retrain`(`argocd/prod/apps/tox-retrain.yaml`, wave 10, 자동 동기화). chart가 app-service가 아니라 ApplicationSet 목록에 넣지 않았다 |
| 이미지 | `sagomungchi/tox-retrain:local`, `Never` | `<A ECR>/sagomungchi/tox-retrain@sha256:…`, `IfNotPresent` |
| 저장소 | MinIO 주소·루트 키(`storage: minio`) | S3 기본 주소, `S3_BUCKET_OWNER`=A 계정, Pod Identity(`storage: aws`, ServiceAccount `tox-retrain`, 역할 `sagomungchi-demo-tox-retrain-s3-role`) |
| 내부 토큰 | `app-service-credentials`의 `INTERNAL_TOKEN_OPS` | `internal-service-credentials`(ESO, `sagomungchi/demo/app/internal`)의 `INTERNAL_TOKEN_OPS`. core·learning도 같은 키를 env로 받는다 |
| egress | core 8080·learning 8081·MinIO 9000·DNS | core 8080·learning 8081·S3 443(scoring과 같은 S3 prefix list 대역 9개)·Pod Identity agent `169.254.170.23/32:80`·DNS |
| ingress | core·learning `ingressFromApps`에 `tox-retrain` | 같음(prod core·learning) |
| 노드 | kind 노드 | `nodeSelector: workload=application-burst`(Karpenter, t3.medium·t3.large, taint 없음). 요청 CPU 1·2560Mi는 상시 노드그룹 여유로 모자라 burst 노드에 둔다. Job이 끝나 노드가 비면 5분 뒤 정리된다 |
| 상태 수집기 API 접근 | Calico `projectcalico.org/v3` 정책(`default/kubernetes` Service) | 표준 NetworkPolicy `tox-retrain-state-api`: `172.20.0.1/32`(kubernetes Service ClusterIP)·사설 서브넷 `10.20.128.0/20`·`10.20.144.0/20`(control plane ENI `10.20.130.189`·`10.20.148.21`, 11/26 조회) 443. EKS 네트워크 정책 agent v1.4.0에는 Calico API가 없다 |
| 경보 | Discord 끔 | 같은 식 2개(`tox-retrain-failed`·`tox-retrain-missed`)를 prod 규칙에 더해 Discord로 보낸다 |

chart는 `storage`(minio·aws), `image`(문자열·`repository`+`digest`), `imagePullPolicy`, `serviceAccount`, `nodeSelector`·`tolerations`, `networkPolicy.s3Egress`로 나눴다. 로컬 values의 렌더 결과는 바뀌지 않는다(아래 검증).

### 9.35.3 검증 (로컬, 2026-11-26)

- `helm lint --strict`·`helm template`(Helm 4.3.1): tox-retrain local·prod, observability local·prod, core·learning prod 모두 통과
- 로컬 렌더 대조: tox-retrain·observability local values의 렌더 결과가 변경 전과 같다(줄 끝 제외 `diff` 0줄). observability prod values를 변경 전 값으로 렌더한 결과도 같다
- `verify_chart.py`: 기존 단계 전부와 새 단계 "prod retraining scrape, EKS API egress and the kind-verified rules routed to Discord" 통과. 가속 복사 시험(Docker)에서는 kube-state-metrics를 띄우지 않으므로 `tox-retrain-*` 규칙을 뺐다(kind에서 9.25로 확인한 식과 prod 식이 같은지는 새 단계가 본다)
- `scripts/tests` 중 `test_aws_demo_stack`(IAM 역할 수 13→14)·`test_runtime_config`·`test_cd_deployment`·`test_cd_digest_pr` 102개 통과. `demo_stack.py plan`은 9.35.4
- kubeconform은 로컬에 없어 원격 `ci-gitops`로 확인한다

### 9.35.4 A 사전 준비

2026-11-26 16시 무렵 A 계정(프로필 `sagomungchi-provided`, ap-northeast-2)에 적용했다. 절차는 [AWS README #730 절](../../infrastructure/aws/README.md#표현-분류-재학습-권한-730-2026-11-26).

| 작업 | 결과 |
|---|---|
| `demo_stack.py plan` | 적용 전 `iam-role sagomungchi-demo-tox-retrain-s3-role`·`pod-identity app/tox-retrain`만 MISSING(나머지 68개 OK) |
| `demo_stack.py apply --confirm-account 347161580747` | `created iam-role sagomungchi-demo-tox-retrain-s3-role`(trust·inline `sagomungchi-demo-tox-retrain-s3-access`) |
| `aws eks create-pod-identity-association` | `app/tox-retrain` → 위 역할, association `a-sfpnfra90dhpn6xn5` |
| `plan` 재실행 | `summary: OK=70` |
| Secrets Manager `sagomungchi/demo/app/internal` | `INTERNAL_TOKEN_OPS`를 무작위 값(43자, 다른 토큰과 다름)으로 더함. 기존 키 7개 값은 그대로인지 대조했다. 값은 출력·기록하지 않았고 임시 파일은 지웠다 |

배포 전이라 ServiceAccount `app/tox-retrain`은 아직 없다. Pod Identity 연결은 ServiceAccount가 생긴 뒤 만든 Pod부터 적용된다. 지금 떠 있는 ExternalSecret은 새 키를 아직 읽지 않으므로 영향이 없다.

### 9.35.5 배포 뒤 수동 실행 (main 반영 뒤)

전제: 이 변경이 2차 릴리스로 main에 들어가 `prod-tox-retrain`·`prod-observability`·`prod-external-secret-resources`·core·learning이 Synced/Healthy. core·learning Pod가 새 env(`INTERNAL_TOKEN_OPS`)로 다시 떠 있어야 한다.

```powershell
$env:KUBECONFIG = '<A kubeconfig>'
kubectl -n argocd get applications prod-tox-retrain prod-observability prod-core-service prod-learning-service
kubectl -n app get cronjob tox-retrain -o jsonpath='{.spec.suspend}'   # true
kubectl -n app get externalsecret internal-service-credentials          # Ready True(키가 없으면 SecretSyncedError)
kubectl -n app get secret internal-service-credentials -o go-template='{{range $k, $v := .data}}{{$k}}{{"\n"}}{{end}}'   # 키 이름만, INTERNAL_TOKEN_OPS 포함
kubectl -n app get jobs -l app.kubernetes.io/name=tox-retrain          # 실행 중인 Job이 없어야 함(손 Job은 Forbid가 막지 않음)
$job = 'tox-retrain-manual-' + (Get-Date -Format yyyyMMddHHmmss)
kubectl -n app create job $job --from=cronjob/tox-retrain
kubectl -n app get pod -l job-name=$job -o wide -w                     # Karpenter burst 노드에 배치되는지
kubectl -n app logs -f job/$job
kubectl -n app get job $job
```

확인 기준:

| 항목 | 통과 |
|---|---|
| 배치 | Pod가 `workload=application-burst` 노드에서 실행, 이미지 pull 성공 |
| 자격 증명 | Pod에 `eks-pod-identity-token` 볼륨, 로그에 S3 `AccessDenied`·자격 증명 오류 없음 |
| S3·내부 API | `last_read` 단계 통과(처음이면 `last.json` 없음), learning `label-count` 응답 |
| 라벨 200건 미만 | `skip reason=not_enough_labels`, 종료 코드 0, Job Complete. 이 경우 다운로드·업로드·등록은 확인되지 않는다 |
| 라벨 200건 이상 | `stage=register`·`stage=last_write` 완료, S3 `models/<활성 tox 이름>/<새 버전>/` 파일 5개와 `models/tox-retrain/last.json`, 등록부 새 행 `REGISTERED`(활성화 안 함), 기존 활성 모델 유지 |
| 경보 | Prometheus `up{job="tox-retrain-state"}=1`, Grafana 두 규칙이 Normal(예약 지연 규칙은 suspend라 0). 실패하면 실패 경보가 Discord로 온다 |
| 정리 | Job 완료 5분 뒤 burst 노드 정리(`kubectl get nodes -l workload=application-burst`) |

### 9.35.6 한계·남은 것

- 전체 경로(다운로드·학습·업로드·등록) 확인에는 두 가지가 먼저 있어야 한다. A models 버킷에 공개 데이터 묶음 `datasets/tox-retrain/public-v1/`이 아직 없고(11/26 조회 0개, learning.md 16절), 새 라벨이 200건 이상이어야 한다. 둘 중 하나라도 없으면 수동 실행은 `last_read`·라벨 수 조회까지만 확인한다
- 상태 수집기 API egress는 EKS 네트워크 정책 agent에서 ClusterIP와 ENI 대역 중 어느 쪽으로 판정되는지 실제로 재지 않아 둘 다 열었다. 배포 뒤 `up{job="tox-retrain-state"}`로 확인한다. 사설 서브넷 443이 함께 열리는 범위는 Prometheus Pod 하나다
- `ListBucket`은 접두사 조건 없이 models 버킷 전체 목록을 볼 수 있다(처음 실행의 `NoSuchKey` 판정 때문, AWS README #730 절)
- 실제 학습 시간·최고 메모리는 운영 모델로 재지 않았다. Job 기한 40분·상한 3Gi는 9.25 값 그대로다
- B 전환(#809): 역할·Pod Identity·`INTERNAL_TOKEN_OPS`는 런북 1·3·6단계에 들어 있다. API 송신 대역은 "B 자원을 만든 뒤 바꿀 값"에 더했다. B에서 예약을 켤지는 B 야간 정지 계획에 맞춰 따로 정한다

## 10. 근거 링크

- [ingress-nginx 지원 버전](https://github.com/kubernetes/ingress-nginx#supported-versions-table), [종료 공지](https://kubernetes.io/blog/2025/11/11/ingress-nginx-retirement/), [kind v0.33.0](https://github.com/kubernetes-sigs/kind/releases/tag/v0.33.0)
- [Calico 요구사항](https://docs.tigera.io/calico/latest/getting-started/kubernetes/requirements), [native v3 CRD](https://docs.tigera.io/calico/latest/operations/native-v3-crds)
- [MinIO 배포 방식](https://github.com/minio/minio#source-only-distribution), [Chainguard MinIO](https://images.chainguard.dev/directory/image/minio/overview), [curl SigV4](https://curl.se/docs/manpage.html#--aws-sigv4)
- [Compose 변수 해석](https://docs.docker.com/reference/compose-file/interpolation/), [RabbitMQ 메모리](https://www.rabbitmq.com/docs/memory), [quorum WAL](https://www.rabbitmq.com/docs/quorum-queues#resource-use), [Redis eviction](https://redis.io/docs/latest/develop/reference/eviction/)
- [Langfuse 자체 호스팅 자원](https://langfuse.com/self-hosting/configuration/scaling), [Langfuse OTel 계약](https://langfuse.com/integrations/native/opentelemetry/migration-to-v4), [VPC 요금](https://aws.amazon.com/vpc/pricing/)
